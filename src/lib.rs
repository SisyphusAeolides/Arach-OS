pub mod installer;

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::path::Path;

pub const LOCK_FORMAT: u32 = 1;
pub const PROFILE_FORMAT: u32 = 1;
pub const DISTRIBUTION: &str = "Arach OS";
pub const INSTALLER_FORMAT: u32 = 1;
pub const LIVE_IMAGE_FORMAT: u32 = 1;
pub const CALAMARES_VERSION: &str = "3.4.2";
pub const CALAMARES_REPOSITORY: &str = "https://codeberg.org/Calamares/calamares.git";
pub const CALAMARES_REVISION: &str = "36d30c492e5c7b5d6d32fed5c5d9790522e1eea3";
pub const BRANDING_SHA256: &str =
    "87cc9d21c92c1cfd648e316e3e22e2961b644d375eec21c4ded1c0afc1de5a6e";

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

const EXPECTED_COSMIC_COMPONENTS: &[&str] = &[
    "cosmic-applets",
    "cosmic-applibrary",
    "cosmic-bg",
    "cosmic-comp",
    "cosmic-edit",
    "cosmic-files",
    "cosmic-greeter",
    "cosmic-icons",
    "cosmic-idle",
    "cosmic-initial-setup",
    "cosmic-launcher",
    "cosmic-monitor",
    "cosmic-notifications",
    "cosmic-osd",
    "cosmic-panel",
    "cosmic-player",
    "cosmic-randr",
    "cosmic-screenshot",
    "cosmic-session",
    "cosmic-settings",
    "cosmic-settings-daemon",
    "cosmic-sound-theme",
    "cosmic-store",
    "cosmic-term",
    "cosmic-wallpapers",
    "cosmic-workspaces-epoch",
    "pop-launcher",
    "xdg-desktop-portal-cosmic",
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
pub struct LiveImageContract {
    pub format: u32,
    pub distribution: String,
    pub root_layout: String,
    pub boot_bundle_source: String,
    pub repository_generation: String,
    pub manifest: String,
    pub system_manifest: String,
    pub init: String,
    pub required_path: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LiveSystemContract {
    pub format: u32,
    pub distribution: String,
    pub artifact_layout: String,
    pub provider: Vec<LiveProvider>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LiveProvider {
    pub name: String,
    pub artifact_prefix: String,
    pub layout: String,
    pub required: bool,
    #[serde(default)]
    pub files: Vec<LiveFile>,
    #[serde(default)]
    pub aliases: Vec<LiveAlias>,
    #[serde(default)]
    pub required_tree_path: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LiveFile {
    pub source: String,
    pub destination: String,
    pub mode: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LiveAlias {
    pub source: String,
    pub destination: String,
    pub mode: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Desktop {
    pub package_bundle: String,
    pub components: Vec<String>,
    pub display_manager: String,
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
    pub preflight: String,
    pub preflight_report: String,
    pub catalog_profiles: String,
    pub catalog_keyring: String,
    pub catalog_lock: String,
    pub binary_index: String,
    pub binary_signature: String,
    pub driver_abi: String,
    pub plan: String,
    pub require_target_profiles: bool,
    pub capabilities: Vec<String>,
    pub allow_adapted_c_drivers: bool,
    pub allow_unmatched_binary_kernel_modules: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallerContract {
    pub format: u32,
    pub calamares: CalamaresContract,
    pub transaction: TransactionContract,
    pub security: InstallerSecurity,
    pub asset: Vec<InstallerAsset>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CalamaresContract {
    pub version: String,
    pub repository: String,
    pub revision: String,
    pub settings: String,
    pub branding: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TransactionContract {
    pub module: String,
    pub executable: String,
    pub runtime_directory: String,
    pub generation_source: String,
    pub boot_bundle_source: String,
    pub target_recovery_directory: String,
    pub prepare_before: String,
    pub commit_after: String,
    pub rollback_on_failure: bool,
    pub journal_before_mutation: bool,
    pub shell_commands: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallerSecurity {
    pub excluded_global_storage_keys: Vec<String>,
    pub state_mode: u32,
    pub directory_mode: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallerAsset {
    pub source: String,
    pub destination: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompositionReport {
    pub components: usize,
    pub root_filesystems: usize,
    pub installer_assets: usize,
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

pub fn parse_live_image_contract(text: &str) -> Result<LiveImageContract, CompositionError> {
    toml::from_str(text)
        .map_err(|error| CompositionError::new("live/image.toml", error.to_string()))
}

pub fn parse_live_system_contract(text: &str) -> Result<LiveSystemContract, CompositionError> {
    toml::from_str(text)
        .map_err(|error| CompositionError::new("live/system.toml", error.to_string()))
}

pub fn parse_installer_contract(text: &str) -> Result<InstallerContract, CompositionError> {
    toml::from_str(text)
        .map_err(|error| CompositionError::new("installer/contract.toml", error.to_string()))
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
    if desktop.package_bundle != "cosmic-desktop"
        || desktop.display_manager != "greetd"
        || desktop.compositor != "cosmic-comp"
        || desktop.session != "cosmic-session"
        || desktop.greeter != "cosmic-greeter"
        || desktop.portal != "xdg-desktop-portal-cosmic"
    {
        return Err(CompositionError::new(
            "desktop",
            "the complete COSMIC session contract is required",
        ));
    }
    let expected_cosmic = EXPECTED_COSMIC_COMPONENTS
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let actual_cosmic = desktop
        .components
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if actual_cosmic != expected_cosmic || desktop.components.len() != actual_cosmic.len() {
        return Err(CompositionError::new(
            "desktop.components",
            "the desktop bundle must enumerate every pinned COSMIC component",
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
        || profile.hardware.preflight != "/system/arach-hwd"
        || profile.hardware.preflight_report != "/run/arach-installer/hardware.toml"
        || profile.hardware.catalog_profiles != "/etc/arach/hwd/profiles"
        || profile.hardware.catalog_keyring != "/etc/arach/hwd/keys.toml"
        || profile.hardware.catalog_lock != "/etc/arach/hwd/catalog.lock"
        || profile.hardware.binary_index != "/etc/arach/hwd/packages.toml"
        || profile.hardware.binary_signature != "/etc/arach/hwd/packages.toml.sig"
        || profile.hardware.driver_abi != "/etc/arach/hwd/driver-abi"
        || profile.hardware.plan != "/run/arach-installer/hardware.plan.toml"
        || !profile.hardware.require_target_profiles
        || !profile.hardware.allow_adapted_c_drivers
        || profile.hardware.allow_unmatched_binary_kernel_modules
    {
        return Err(CompositionError::new(
            "hardware",
            "hardware provisioning must use Arach-HWD, Corinth, and the measured C-driver boundary",
        ));
    }
    require_exact_set(
        "hardware.capabilities",
        &profile.hardware.capabilities,
        &[
            "network",
            "wireless",
            "audio",
            "graphics",
            "storage",
            "input",
            "bluetooth",
            "firmware",
        ],
    )?;
    Ok(())
}

pub fn validate_live_image_contract(
    image: &LiveImageContract,
    root: &Path,
) -> Result<(), CompositionError> {
    if image.format != LIVE_IMAGE_FORMAT || image.distribution != DISTRIBUTION {
        return Err(CompositionError::new(
            "live/image.toml",
            "format or distribution identity differs from the image contract",
        ));
    }
    if image.root_layout != "posix"
        || image.boot_bundle_source != "/run/arach-live/boot-bundle"
        || image.repository_generation != "/run/arach-live/repository/system.gen"
        || image.manifest != "/run/arach-live/image.json"
        || image.system_manifest != "/run/arach-live/system.json"
        || image.init != "/system/push"
    {
        return Err(CompositionError::new(
            "live/image.toml",
            "live root paths do not match the measured Arach runtime boundary",
        ));
    }
    let expected = [
        "/system/push",
        "/system/corinth",
        "/system/arach-hwd",
        "/etc/arach/hwd/keys.toml",
        "/etc/arach/hwd/driver-abi",
        "/etc/arach/hwd/catalog.lock",
        "/etc/arach/hwd/packages.toml",
        "/etc/arach/hwd/packages.toml.sig",
        "/etc/arach/hwd/driver-sources/modules.alias",
        "/etc/arach/hwd/driver-sources/modules.dep",
        "/etc/arach/hwd/driver-sources/modules.builtin",
        "/etc/arach/hwd/driver-sources/modules.firmware",
        "/system/dbus-broker-launch",
        "/system/seatd",
        "/system/pipewire",
        "/system/pipewire-pulse",
        "/system/wireplumber",
        "/system/greetd",
        "/system/cosmic-comp",
        "/system/cosmic-greeter",
        "/usr/bin/cosmic-greeter-start",
        "/system/cosmic-session",
        "/system/cosmic-term",
        "/system/xdg-desktop-portal-cosmic",
        "/etc/greetd/cosmic-greeter.toml",
        "/etc/greetd/config.toml",
        "/usr/libexec/arach-install",
        "/usr/bin/calamares",
        "/usr/bin/firefox",
        "/usr/share/calamares/branding/arach/arach-logo.png",
    ];
    let actual = image
        .required_path
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let expected_set = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected_set || image.required_path.len() != actual.len() {
        return Err(CompositionError::new(
            "live/image.toml.required_path",
            "the live root must contain the complete measured Push/COSMIC/Calamares path set",
        ));
    }
    for path in &image.required_path {
        let path = Path::new(path);
        if !path.is_absolute()
            || path
                .components()
                .any(|component| matches!(component, std::path::Component::ParentDir))
        {
            return Err(CompositionError::new(
                "live/image.toml.required_path",
                "required paths must be absolute and cannot escape the live root",
            ));
        }
    }
    if !root.join("scripts/assemble-live-root.sh").is_file() {
        return Err(CompositionError::new(
            "scripts/assemble-live-root.sh",
            "the live root assembler is absent",
        ));
    }
    if !root.join("scripts/materialize-live-system.sh").is_file() {
        return Err(CompositionError::new(
            "scripts/materialize-live-system.sh",
            "the signed package-to-live-system materializer is absent",
        ));
    }
    if !root.join("scripts/build-live-iso.sh").is_file() {
        return Err(CompositionError::new(
            "scripts/build-live-iso.sh",
            "the bootable ISO assembler is absent",
        ));
    }
    Ok(())
}

pub fn validate_live_system_contract(
    system: &LiveSystemContract,
    root: &Path,
) -> Result<(), CompositionError> {
    if system.format != LIVE_IMAGE_FORMAT
        || system.distribution != DISTRIBUTION
        || system.artifact_layout != "corinth-v1"
    {
        return Err(CompositionError::new(
            "live/system.toml",
            "format, distribution, or artifact layout differs from the live image contract",
        ));
    }
    let expected = [
        "push",
        "corinth",
        "arach-hwd",
        "arach-hardware-catalog",
        "dbus-broker",
        "seatd",
        "pipewire",
        "wireplumber",
        "greetd",
        "cosmic-desktop",
        "firefox",
        "calamares",
        "arach-install",
        "arach-branding",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    let mut names = BTreeSet::new();
    for provider in &system.provider {
        if provider.name.to_ascii_lowercase().contains("crest") {
            return Err(CompositionError::new(
                format!("live/system.toml.provider.{}", provider.name),
                "Crest is reserved for the measured C0 boot payload and cannot be a live desktop provider",
            ));
        }
        if !names.insert(provider.name.as_str())
            || !provider.required
            || provider.artifact_prefix.trim().is_empty()
            || !provider.artifact_prefix.ends_with('-')
            || !matches!(provider.layout.as_str(), "files" | "tree")
        {
            return Err(CompositionError::new(
                "live/system.toml.provider",
                "provider identity or layout is invalid",
            ));
        }
        if provider.layout == "tree" && !provider.files.is_empty()
            || provider.layout == "files"
                && (!provider.aliases.is_empty() || !provider.required_tree_path.is_empty())
        {
            return Err(CompositionError::new(
                format!("live/system.toml.provider.{}", provider.name),
                "tree and file mappings cannot be mixed",
            ));
        }
        if provider.layout == "files" && provider.files.is_empty() {
            return Err(CompositionError::new(
                format!("live/system.toml.provider.{}", provider.name),
                "file providers require at least one mapping",
            ));
        }
        for file in &provider.files {
            if !safe_relative(&file.source)
                || !safe_absolute(&file.destination)
                || file.mode & !0o7777 != 0
            {
                return Err(CompositionError::new(
                    format!("live/system.toml.provider.{}", provider.name),
                    "file mappings must be bounded and use safe paths/modes",
                ));
            }
        }
        for alias in &provider.aliases {
            if !safe_absolute(&alias.source)
                || !safe_absolute(&alias.destination)
                || alias.mode & !0o7777 != 0
            {
                return Err(CompositionError::new(
                    format!("live/system.toml.provider.{}", provider.name),
                    "aliases must use bounded absolute paths and safe modes",
                ));
            }
        }
        for path in &provider.required_tree_path {
            if !safe_absolute(path) {
                return Err(CompositionError::new(
                    format!("live/system.toml.provider.{}", provider.name),
                    "required tree paths must be absolute and bounded",
                ));
            }
        }
    }
    if names != expected {
        return Err(CompositionError::new(
            "live/system.toml.provider",
            "the provider set differs from the measured live system contract",
        ));
    }
    if !root.join("scripts/materialize-live-system.sh").is_file() {
        return Err(CompositionError::new(
            "scripts/materialize-live-system.sh",
            "the package-to-live-system materializer is absent",
        ));
    }
    Ok(())
}

pub fn validate_installer_contract(
    contract: &InstallerContract,
    root: &Path,
) -> Result<(), CompositionError> {
    if contract.format != INSTALLER_FORMAT
        || contract.calamares.version != CALAMARES_VERSION
        || contract.calamares.repository != CALAMARES_REPOSITORY
        || contract.calamares.revision != CALAMARES_REVISION
        || contract.calamares.settings != "installer/calamares/settings.conf"
        || contract.calamares.branding != "installer/calamares/branding/arach/branding.desc"
    {
        return Err(CompositionError::new(
            "installer.calamares",
            "Calamares authority is not the exact reviewed 3.4.2 source object",
        ));
    }
    if contract.transaction.module != "arachtransaction"
        || contract.transaction.executable != "/usr/libexec/arach-install"
        || contract.transaction.runtime_directory != "/run/arach-installer"
        || contract.transaction.generation_source != "/run/arach-live/repository/system.gen"
        || contract.transaction.boot_bundle_source != "/run/arach-live/boot-bundle"
        || contract.transaction.target_recovery_directory != "/var/lib/arach-installer/transactions"
        || contract.transaction.prepare_before != "partition"
        || contract.transaction.commit_after != "unpackfs"
        || !contract.transaction.rollback_on_failure
        || !contract.transaction.journal_before_mutation
        || contract.transaction.shell_commands
    {
        return Err(CompositionError::new(
            "installer.transaction",
            "the journaled no-shell transaction boundary is required",
        ));
    }
    require_exact_set(
        "installer.security.excluded_global_storage_keys",
        &contract.security.excluded_global_storage_keys,
        &["luksPassphrase", "password", "rootPassword"],
    )?;
    if contract.security.state_mode != 0o600 || contract.security.directory_mode != 0o700 {
        return Err(CompositionError::new(
            "installer.security",
            "installer state must be private to the installation process",
        ));
    }
    let settings_path = root.join(&contract.calamares.settings);
    let settings = fs::read_to_string(&settings_path).map_err(|error| {
        CompositionError::new(settings_path.display().to_string(), error.to_string())
    })?;
    let exec = settings
        .split_once("  - exec:\n")
        .and_then(|(_, rest)| rest.split_once("  - show:\n").map(|(block, _)| block))
        .ok_or_else(|| {
            CompositionError::new(
                "installer/calamares/settings.conf",
                "a bounded Calamares exec block is required",
            )
        })?;
    let prepare = token_position(exec, "- arachtransaction@prepare")?;
    let hardware = token_position(exec, "- arachhardware@preflight")?;
    let partition = token_position(exec, "- partition")?;
    let unpack = token_position(exec, "- unpackfs")?;
    let commit = token_position(exec, "- arachtransaction@commit")?;
    if !(hardware < prepare && prepare < partition && unpack < commit)
        || settings.matches("arachtransaction@prepare").count() != 1
        || settings.matches("arachtransaction@commit").count() != 1
        || settings.matches("arachhardware@preflight").count() != 1
    {
        return Err(CompositionError::new(
            "installer/calamares/settings.conf",
            "prepare must precede partition and commit must follow unpackfs",
        ));
    }
    for required in [
        &contract.calamares.branding,
        "installer/calamares/modules/arachtransaction/module.desc",
        "installer/calamares/modules/arachtransaction/main.py",
        "installer/calamares/modules/arachtransaction/protocol.py",
        "installer/calamares/modules/arachhardware/module.desc",
        "installer/calamares/modules/arachhardware/main.py",
        "installer/calamares/modules/arach-prepare.conf",
        "installer/calamares/modules/arach-commit.conf",
        "installer/calamares/modules/partition.conf",
        "installer/calamares/modules/users.conf",
        "installer/calamares/modules/unpackfs.conf",
    ] {
        if !root.join(required).is_file() {
            return Err(CompositionError::new(
                required,
                "required installer integration file is absent",
            ));
        }
    }
    require_file_tokens(
        root,
        "installer/calamares/modules/arach-prepare.conf",
        &[
            "phase: prepare",
            "executable: /usr/libexec/arach-install",
            "generationSource: /run/arach-live/repository/system.gen",
            "bootBundleSource: /run/arach-live/boot-bundle",
        ],
    )?;
    require_file_tokens(
        root,
        "installer/calamares/modules/arachhardware.conf",
        &[
            "executable: /system/arach-hwd",
            "sysfs: /sys",
            "modulesAlias:",
            "- /etc/arach/hwd/driver-sources/modules.alias",
            "modulesFirmware:",
            "- /etc/arach/hwd/driver-sources/modules.firmware",
            "modulesDep:",
            "- /etc/arach/hwd/driver-sources/modules.dep",
            "modulesBuiltin:",
            "- /etc/arach/hwd/driver-sources/modules.builtin",
            "firmwareRoots: []",
            "report: /run/arach-installer/hardware.toml",
            "profiles: /etc/arach/hwd/profiles",
            "keyring: /etc/arach/hwd/keys.toml",
            "catalogLock: /etc/arach/hwd/catalog.lock",
            "driverAbi: /etc/arach/hwd/driver-abi",
            "plan: /run/arach-installer/hardware.plan.toml",
            "requireTargetProfiles: true",
        ],
    )?;
    require_file_tokens(
        root,
        "installer/calamares/modules/arach-commit.conf",
        &[
            "phase: commit",
            "executable: /usr/libexec/arach-install",
            "generationSource: /run/arach-live/repository/system.gen",
            "bootBundleSource: /run/arach-live/boot-bundle",
        ],
    )?;
    require_file_tokens(
        root,
        "installer/calamares/modules/users.conf",
        &[
            "setRootPassword: true",
            "doAutologin: false",
            "minLength: 12",
            "allowWeakPasswords: false",
        ],
    )?;
    require_file_tokens(
        root,
        "installer/calamares/modules/partition.conf",
        &[
            "luksGeneration: luks2",
            "defaultPartitionTableType: gpt",
            "requiredPartitionTableType: gpt",
        ],
    )?;
    let python = [
        "installer/calamares/modules/arachtransaction/main.py",
        "installer/calamares/modules/arachtransaction/protocol.py",
        "installer/calamares/modules/arachhardware/main.py",
    ]
    .iter()
    .map(|path| fs::read_to_string(root.join(path)))
    .collect::<Result<Vec<_>, _>>()
    .map_err(|error| CompositionError::new("installer.python", error.to_string()))?
    .join("\n");
    if python.contains("shell=True") || python.contains("os.system") {
        return Err(CompositionError::new(
            "installer.python",
            "installer transaction code may not invoke a shell",
        ));
    }
    if contract.asset.len() != 1 {
        return Err(CompositionError::new(
            "installer.asset",
            "exactly one canonical Arach branding asset is required",
        ));
    }
    let asset = &contract.asset[0];
    if asset.source != "branding/arach-logo.png"
        || asset.destination != "usr/share/calamares/branding/arach/arach-logo.png"
        || asset.sha256 != BRANDING_SHA256
    {
        return Err(CompositionError::new(
            "installer.asset",
            "branding asset mapping differs from the measured contract",
        ));
    }
    let bytes = fs::read(root.join(&asset.source))
        .map_err(|error| CompositionError::new(asset.source.clone(), error.to_string()))?;
    let digest = format!("{:x}", Sha256::digest(bytes));
    if digest != asset.sha256 {
        return Err(CompositionError::new(
            "installer.asset.sha256",
            "canonical branding digest differs from the contract",
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
    let image_path = root.join("live/image.toml");
    let image_text = fs::read_to_string(&image_path).map_err(|error| {
        CompositionError::new(image_path.display().to_string(), error.to_string())
    })?;
    let system_path = root.join("live/system.toml");
    let system_text = fs::read_to_string(&system_path).map_err(|error| {
        CompositionError::new(system_path.display().to_string(), error.to_string())
    })?;
    let installer_path = root.join("installer/contract.toml");
    let installer_text = fs::read_to_string(&installer_path).map_err(|error| {
        CompositionError::new(installer_path.display().to_string(), error.to_string())
    })?;
    let lock = parse_lock(&lock_text)?;
    let profile = parse_live_profile(&profile_text)?;
    let image = parse_live_image_contract(&image_text)?;
    let system = parse_live_system_contract(&system_text)?;
    let installer = parse_installer_contract(&installer_text)?;
    validate_lock(&lock)?;
    validate_live_profile(&profile, root)?;
    validate_live_image_contract(&image, root)?;
    validate_live_system_contract(&system, root)?;
    validate_installer_contract(&installer, root)?;
    Ok(CompositionReport {
        components: lock.component.len(),
        root_filesystems: profile.filesystems.root.len(),
        installer_assets: installer.asset.len(),
    })
}

fn token_position(text: &str, token: &str) -> Result<usize, CompositionError> {
    text.find(token).ok_or_else(|| {
        CompositionError::new(
            "installer/calamares/settings.conf",
            format!("required sequence token is absent: {token}"),
        )
    })
}

fn require_file_tokens(root: &Path, path: &str, tokens: &[&str]) -> Result<(), CompositionError> {
    let text = fs::read_to_string(root.join(path))
        .map_err(|error| CompositionError::new(path, error.to_string()))?;
    if tokens.iter().all(|token| text.contains(token)) {
        Ok(())
    } else {
        Err(CompositionError::new(
            path,
            "required installer behavior is absent",
        ))
    }
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

fn safe_relative(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty()
        && !path.is_absolute()
        && !path.components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir
                    | std::path::Component::RootDir
                    | std::path::Component::Prefix(_)
            )
        })
}

fn safe_absolute(value: &str) -> bool {
    let path = Path::new(value);
    path.is_absolute()
        && value != "/"
        && !path.components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir | std::path::Component::Prefix(_)
            )
        })
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

    #[test]
    fn incomplete_live_root_contract_is_rejected() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("live/image.toml")).unwrap();
        let mut image = parse_live_image_contract(&text).unwrap();
        image.required_path.pop();
        assert!(validate_live_image_contract(&image, root).is_err());
    }

    #[test]
    fn incomplete_live_system_contract_is_rejected() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("live/system.toml")).unwrap();
        let mut system = parse_live_system_contract(&text).unwrap();
        system.provider.pop();
        assert!(validate_live_system_contract(&system, root).is_err());
    }

    #[test]
    fn crest_is_reserved_for_boot_and_rejected_as_a_desktop_provider() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("live/system.toml")).unwrap();
        let mut system = parse_live_system_contract(&text).unwrap();
        let mut forbidden = system
            .provider
            .iter()
            .find(|provider| provider.name == "cosmic-desktop")
            .cloned()
            .unwrap();
        forbidden.name = "crest-desktop".into();
        system.provider.push(forbidden);
        assert!(validate_live_system_contract(&system, root).is_err());
    }

    #[test]
    fn reordered_installer_transaction_is_rejected() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("installer/contract.toml")).unwrap();
        let contract = parse_installer_contract(&text).unwrap();
        let fixture = tempfile_root(
            root,
            "  - exec:\n      - partition\n      - arachtransaction@prepare\n      - arachtransaction@commit\n      - unpackfs\n  - show:\n      - finished\n",
        );
        assert!(validate_installer_contract(&contract, &fixture).is_err());
        fs::remove_dir_all(fixture).unwrap();
    }

    #[test]
    fn installer_secret_exclusion_is_exact() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(root.join("installer/contract.toml")).unwrap();
        let mut contract = parse_installer_contract(&text).unwrap();
        contract.security.excluded_global_storage_keys.pop();
        assert!(validate_installer_contract(&contract, root).is_err());
    }

    fn tempfile_root(source: &Path, settings: &str) -> std::path::PathBuf {
        let root = std::env::temp_dir().join(format!(
            "arach-compose-test-{}-{}",
            std::process::id(),
            std::thread::current().name().unwrap_or("unnamed")
        ));
        let _ = fs::remove_dir_all(&root);
        for file in [
            "installer/calamares/branding/arach/branding.desc",
            "installer/calamares/modules/arachtransaction/module.desc",
            "installer/calamares/modules/arachtransaction/main.py",
            "installer/calamares/modules/arachtransaction/protocol.py",
            "installer/calamares/modules/arachhardware/module.desc",
            "installer/calamares/modules/arachhardware/main.py",
            "installer/calamares/modules/arachhardware.conf",
            "installer/calamares/modules/arach-prepare.conf",
            "installer/calamares/modules/arach-commit.conf",
            "installer/calamares/modules/partition.conf",
            "installer/calamares/modules/users.conf",
            "installer/calamares/modules/unpackfs.conf",
            "branding/arach-logo.png",
        ] {
            let destination = root.join(file);
            fs::create_dir_all(destination.parent().unwrap()).unwrap();
            fs::copy(source.join(file), destination).unwrap();
        }
        let settings_path = root.join("installer/calamares/settings.conf");
        fs::create_dir_all(settings_path.parent().unwrap()).unwrap();
        fs::write(settings_path, settings).unwrap();
        root
    }
}
