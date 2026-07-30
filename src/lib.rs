use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::path::Path;

pub const LOCK_FORMAT: u32 = 1;
pub const PROFILE_FORMAT: u32 = 1;
pub const DISTRIBUTION: &str = "Arach OS";

const EXPECTED_COMPONENTS: &[(&str, &str, &str)] = &[
    ("arach-kernel", "Arach-Kernel", "kernel"),
    ("slope", "Slope", "userspace-abi"),
    ("push", "Push", "pid1"),
    ("granite", "Granite", "bootloader"),
    ("corinth", "Corinth", "package-manager"),
    ("arach-packages", "Arach-Packages", "package-recipes"),
    ("arach-hwd", "Arach-HWD", "hardware-provisioning"),
    ("libinput-rs", "libinput-rs", "input-stack"),
    ("elan-guardian", "elan-guardian", "input-recovery"),
    ("tuned-rs", "tuned-rs", "system-tuning"),
    ("ccze-rs", "ccze-rs", "log-presentation"),
];

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ComponentLock {
    pub format: u32,
    pub distribution: String,
    pub component: Vec<Component>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Component {
    pub name: String,
    pub repository: String,
    pub revision: String,
    pub role: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LiveProfile {
    pub format: u32,
    pub distribution: String,
    pub desktop: Desktop,
    pub installer: Installer,
    pub filesystems: Filesystems,
    pub hardware: Hardware,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Desktop {
    pub compositor: String,
    pub session: String,
    pub greeter: String,
    pub portal: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Installer {
    pub framework: String,
    pub transaction_engine: String,
    pub branding: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Filesystems {
    pub efi: Vec<String>,
    pub root: Vec<String>,
    pub home: Vec<String>,
    pub experimental: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Hardware {
    pub detector: String,
    pub package_manager: String,
    pub allow_adapted_c_drivers: bool,
    pub allow_unmatched_binary_kernel_modules: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompositionReport {
    pub components: usize,
    pub root_filesystems: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompositionError {
    pub path: String,
    pub message: String,
}

impl CompositionError {
    fn new(path: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            path: path.into(),
            message: message.into(),
        }
    }
}

impl fmt::Display for CompositionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.path, self.message)
    }
}

impl std::error::Error for CompositionError {}

pub fn parse_lock(text: &str) -> Result<ComponentLock, CompositionError> {
    toml::from_str(text)
        .map_err(|error| CompositionError::new("components.lock", error.to_string()))
}

pub fn parse_live_profile(text: &str) -> Result<LiveProfile, CompositionError> {
    toml::from_str(text).map_err(|error| CompositionError::new("live.profile", error.to_string()))
}

pub fn validate_lock(lock: &ComponentLock) -> Result<(), CompositionError> {
    if lock.format != LOCK_FORMAT || lock.distribution != DISTRIBUTION {
        return Err(CompositionError::new(
            "components.lock",
            "format or distribution identity differs from the image contract",
        ));
    }
    let mut components = BTreeMap::<&str, &Component>::new();
    let mut repositories = BTreeSet::new();
    for component in &lock.component {
        if components
            .insert(component.name.as_str(), component)
            .is_some()
        {
            return Err(CompositionError::new(
                "component.name",
                format!("duplicate component {}", component.name),
            ));
        }
        if !repositories.insert(&component.repository) {
            return Err(CompositionError::new(
                "component.repository",
                format!("duplicate repository {}", component.repository),
            ));
        }
        if !valid_revision(&component.revision) {
            return Err(CompositionError::new(
                format!("component.{}.revision", component.name),
                "revision must be a lowercase full Git object ID",
            ));
        }
    }
    let expected_names = EXPECTED_COMPONENTS
        .iter()
        .map(|(name, _, _)| *name)
        .collect::<BTreeSet<_>>();
    let actual_names = components.keys().copied().collect::<BTreeSet<_>>();
    if actual_names != expected_names {
        return Err(CompositionError::new(
            "component",
            "component set differs from the Arach OS composition contract",
        ));
    }
    for (name, repository_name, role) in EXPECTED_COMPONENTS {
        let component = components[name];
        let repository = format!("https://github.com/SisyphusAeolides/{repository_name}.git");
        if component.repository != repository || component.role != *role {
            return Err(CompositionError::new(
                format!("component.{name}"),
                "repository authority or role differs from the composition contract",
            ));
        }
    }
    Ok(())
}

pub fn validate_live_profile(profile: &LiveProfile, root: &Path) -> Result<(), CompositionError> {
    if profile.format != PROFILE_FORMAT || profile.distribution != DISTRIBUTION {
        return Err(CompositionError::new(
            "live.profile",
            "format or distribution identity differs from the image contract",
        ));
    }
    let desktop = &profile.desktop;
    if desktop.compositor != "cosmic-comp"
        || desktop.session != "cosmic-session"
        || desktop.greeter != "cosmic-greeter"
        || desktop.portal != "xdg-desktop-portal-cosmic"
    {
        return Err(CompositionError::new(
            "desktop",
            "the complete COSMIC session contract is required",
        ));
    }
    if profile.installer.framework != "calamares"
        || profile.installer.transaction_engine != "arach-install"
        || profile.installer.branding != "branding/arach-logo.png"
        || !root.join(&profile.installer.branding).is_file()
    {
        return Err(CompositionError::new(
            "installer",
            "Calamares, arach-install, and canonical branding are required",
        ));
    }
    validate_filesystems(&profile.filesystems)?;
    if profile.hardware.detector != "arach-hwd"
        || profile.hardware.package_manager != "corinth"
        || !profile.hardware.allow_adapted_c_drivers
        || profile.hardware.allow_unmatched_binary_kernel_modules
    {
        return Err(CompositionError::new(
            "hardware",
            "hardware provisioning must use Arach-HWD, Corinth, and the measured C-driver boundary",
        ));
    }
    Ok(())
}

pub fn validate_root(root: &Path) -> Result<CompositionReport, CompositionError> {
    let lock_path = root.join("components.lock.toml");
    let profile_path = root.join("live/profile.toml");
    let lock_text = fs::read_to_string(&lock_path).map_err(|error| {
        CompositionError::new(lock_path.display().to_string(), error.to_string())
    })?;
    let profile_text = fs::read_to_string(&profile_path).map_err(|error| {
        CompositionError::new(profile_path.display().to_string(), error.to_string())
    })?;
    let lock = parse_lock(&lock_text)?;
    let profile = parse_live_profile(&profile_text)?;
    validate_lock(&lock)?;
    validate_live_profile(&profile, root)?;
    Ok(CompositionReport {
        components: lock.component.len(),
        root_filesystems: profile.filesystems.root.len(),
    })
}

fn validate_filesystems(filesystems: &Filesystems) -> Result<(), CompositionError> {
    require_exact_set("filesystems.efi", &filesystems.efi, &["fat32"])?;
    require_exact_set(
        "filesystems.root",
        &filesystems.root,
        &["btrfs", "ext4", "f2fs", "xfs"],
    )?;
    require_exact_set(
        "filesystems.home",
        &filesystems.home,
        &["btrfs", "ext4", "f2fs", "xfs"],
    )?;
    require_exact_set(
        "filesystems.experimental",
        &filesystems.experimental,
        &["bcachefs", "zfs"],
    )
}

fn require_exact_set(
    path: &str,
    actual: &[String],
    expected: &[&str],
) -> Result<(), CompositionError> {
    let actual_len = actual.len();
    let actual = actual.iter().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual == expected && actual_len == actual.len() {
        Ok(())
    } else {
        Err(CompositionError::new(
            path,
            "filesystem set differs from the live installer contract",
        ))
    }
}

fn valid_revision(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repository_composition_is_valid() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let report = validate_root(root).unwrap();
        assert_eq!(report.components, EXPECTED_COMPONENTS.len());
    }

    #[test]
    fn symbolic_component_revision_is_rejected() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("components.lock.toml")).unwrap();
        let mut lock = parse_lock(&text).unwrap();
        lock.component[0].revision = "main".into();
        assert!(validate_lock(&lock).is_err());
    }

    #[test]
    fn incomplete_cosmic_contract_is_rejected() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("live/profile.toml")).unwrap();
        let mut profile = parse_live_profile(&text).unwrap();
        profile.desktop.greeter.clear();
        assert!(validate_live_profile(&profile, root).is_err());
    }
}
