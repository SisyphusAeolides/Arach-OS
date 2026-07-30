use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const DOCUMENT_LIMIT: u64 = 1024 * 1024;
const TRANSACTION_SCHEMA: u32 = 1;
static TEMPORARY_SERIAL: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallerState {
    pub schema: u32,
    pub transaction_id: String,
    #[serde(rename = "firmwareType", skip_serializing_if = "Option::is_none")]
    pub firmware_type: Option<String>,
    #[serde(rename = "partitionChoices", skip_serializing_if = "Option::is_none")]
    pub partition_choices: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub locale: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub region: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub zone: Option<String>,
    #[serde(rename = "keyboardLayout", skip_serializing_if = "Option::is_none")]
    pub keyboard_layout: Option<String>,
    #[serde(rename = "keyboardVariant", skip_serializing_if = "Option::is_none")]
    pub keyboard_variant: Option<String>,
    #[serde(
        rename = "keyboardVConsoleKeymap",
        skip_serializing_if = "Option::is_none"
    )]
    pub keyboard_vconsole_keymap: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub username: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fullname: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hostname: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallPlan {
    pub schema: u32,
    pub transaction_id: String,
    pub state_sha256: String,
    pub distribution: String,
    pub operations: Vec<InstallOperation>,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum InstallOperation {
    CorinthInstall,
    GraniteActivate,
    CosmicVerify,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum JournalStatus {
    Prepared,
    Applying,
    ApplyFailed,
    Applied,
    Verified,
    RolledBack,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InstallJournal {
    pub schema: u32,
    pub transaction_id: String,
    pub plan_sha256: String,
    pub status: JournalStatus,
    pub target: Option<String>,
    pub mutations: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct InstallerError {
    pub message: String,
    pub unavailable: bool,
}

impl InstallerError {
    fn invalid(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            unavailable: false,
        }
    }

    fn unavailable(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            unavailable: true,
        }
    }
}

impl fmt::Display for InstallerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for InstallerError {}

pub fn prepare(
    state_path: &Path,
    plan_path: &Path,
    journal_path: &Path,
) -> Result<(), InstallerError> {
    require_distinct_paths(&[state_path, plan_path, journal_path])?;
    let state: InstallerState = read_private_json(state_path)?;
    validate_transaction_id(&state.transaction_id)?;
    if state.schema != TRANSACTION_SCHEMA {
        return Err(InstallerError::invalid(
            "unsupported installer state schema",
        ));
    }
    let state_bytes = canonical_json(&state)?;
    let plan = InstallPlan {
        schema: TRANSACTION_SCHEMA,
        transaction_id: state.transaction_id.clone(),
        state_sha256: digest(&state_bytes),
        distribution: crate::DISTRIBUTION.into(),
        operations: vec![
            InstallOperation::CorinthInstall,
            InstallOperation::GraniteActivate,
            InstallOperation::CosmicVerify,
        ],
    };
    let plan_bytes = canonical_json(&plan)?;
    let journal = InstallJournal {
        schema: TRANSACTION_SCHEMA,
        transaction_id: state.transaction_id,
        plan_sha256: digest(&plan_bytes),
        status: JournalStatus::Prepared,
        target: None,
        mutations: Vec::new(),
    };
    create_private(plan_path, &plan_bytes)?;
    if let Err(error) = create_private(journal_path, &canonical_json(&journal)?) {
        let _ = fs::remove_file(plan_path);
        return Err(error);
    }
    Ok(())
}

pub fn apply(plan_path: &Path, journal_path: &Path, target: &Path) -> Result<(), InstallerError> {
    let target = validate_target(target)?;
    let (plan, mut journal) = load_bound_documents(plan_path, journal_path)?;
    if journal.status != JournalStatus::Prepared {
        return Err(InstallerError::invalid("transaction is not prepared"));
    }
    journal.status = JournalStatus::Applying;
    journal.target = Some(target.display().to_string());
    rewrite_private(journal_path, &canonical_json(&journal)?)?;

    journal.status = JournalStatus::ApplyFailed;
    rewrite_private(journal_path, &canonical_json(&journal)?)?;
    let _ = plan;
    Err(InstallerError::unavailable(
        "durable Corinth installation and Granite activation are not implemented; target left unchanged",
    ))
}

pub fn verify(plan_path: &Path, journal_path: &Path, target: &Path) -> Result<(), InstallerError> {
    let target = validate_target(target)?;
    let (_plan, journal) = load_bound_documents(plan_path, journal_path)?;
    if journal.status != JournalStatus::Applied
        || journal.target.as_deref() != Some(target.to_string_lossy().as_ref())
    {
        return Err(InstallerError::invalid(
            "only an applied transaction may enter verification",
        ));
    }
    Err(InstallerError::unavailable(
        "installed Corinth generation, Granite measurement, and COSMIC session verification are not implemented",
    ))
}

pub fn rollback(journal_path: &Path, target: &Path) -> Result<(), InstallerError> {
    let target = validate_target(target)?;
    let mut journal: InstallJournal = read_private_json(journal_path)?;
    validate_journal(&journal)?;
    if !matches!(
        journal.status,
        JournalStatus::Prepared
            | JournalStatus::Applying
            | JournalStatus::ApplyFailed
            | JournalStatus::Applied
    ) {
        return Err(InstallerError::invalid(
            "transaction state cannot be rolled back",
        ));
    }
    if !journal.mutations.is_empty() {
        return Err(InstallerError::unavailable(
            "rollback backend is unavailable for a transaction with recorded mutations",
        ));
    }
    journal.status = JournalStatus::RolledBack;
    journal.target = Some(target.display().to_string());
    rewrite_private(journal_path, &canonical_json(&journal)?)
}

pub fn parse_flag_arguments(
    arguments: &[String],
) -> Result<BTreeMap<String, PathBuf>, InstallerError> {
    if arguments.len() % 2 != 0 {
        return Err(InstallerError::invalid("flags require path values"));
    }
    let mut parsed = BTreeMap::new();
    for pair in arguments.chunks_exact(2) {
        let flag = pair[0]
            .strip_prefix("--")
            .ok_or_else(|| InstallerError::invalid(format!("invalid flag {}", pair[0])))?;
        if !matches!(flag, "state" | "plan" | "journal" | "target") {
            return Err(InstallerError::invalid(format!("unknown flag --{flag}")));
        }
        if parsed
            .insert(flag.into(), PathBuf::from(&pair[1]))
            .is_some()
        {
            return Err(InstallerError::invalid(format!("duplicate flag --{flag}")));
        }
    }
    Ok(parsed)
}

fn load_bound_documents(
    plan_path: &Path,
    journal_path: &Path,
) -> Result<(InstallPlan, InstallJournal), InstallerError> {
    let plan: InstallPlan = read_private_json(plan_path)?;
    let journal: InstallJournal = read_private_json(journal_path)?;
    validate_transaction_id(&plan.transaction_id)?;
    validate_journal(&journal)?;
    if plan.schema != TRANSACTION_SCHEMA
        || plan.distribution != crate::DISTRIBUTION
        || plan.transaction_id != journal.transaction_id
        || journal.plan_sha256 != digest(&canonical_json(&plan)?)
        || plan.operations
            != [
                InstallOperation::CorinthInstall,
                InstallOperation::GraniteActivate,
                InstallOperation::CosmicVerify,
            ]
    {
        return Err(InstallerError::invalid(
            "plan and journal do not satisfy the Arach transaction contract",
        ));
    }
    Ok((plan, journal))
}

fn validate_journal(journal: &InstallJournal) -> Result<(), InstallerError> {
    if journal.schema != TRANSACTION_SCHEMA {
        return Err(InstallerError::invalid("unsupported journal schema"));
    }
    validate_transaction_id(&journal.transaction_id)
}

fn validate_transaction_id(value: &str) -> Result<(), InstallerError> {
    if value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
    {
        Ok(())
    } else {
        Err(InstallerError::invalid(
            "transaction id must be 32 lowercase hexadecimal characters",
        ))
    }
}

fn validate_target(path: &Path) -> Result<PathBuf, InstallerError> {
    if !path.is_absolute() || path == Path::new("/") {
        return Err(InstallerError::invalid(
            "installation target must be an absolute non-root directory",
        ));
    }
    let canonical = fs::canonicalize(path)
        .map_err(|error| InstallerError::invalid(format!("invalid target: {error}")))?;
    if canonical == Path::new("/") || !canonical.is_dir() {
        return Err(InstallerError::invalid(
            "installation target resolves to an unsafe path",
        ));
    }
    Ok(canonical)
}

fn require_distinct_paths(paths: &[&Path]) -> Result<(), InstallerError> {
    for (index, left) in paths.iter().enumerate() {
        for right in &paths[index + 1..] {
            if left == right {
                return Err(InstallerError::invalid(
                    "state, plan, and journal paths must be distinct",
                ));
            }
        }
    }
    Ok(())
}

fn read_private_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, InstallerError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > DOCUMENT_LIMIT {
        return Err(InstallerError::invalid(format!(
            "{} is not a bounded regular document",
            path.display()
        )));
    }
    if metadata.permissions().mode() & 0o077 != 0 {
        return Err(InstallerError::invalid(format!(
            "{} is accessible outside its owner",
            path.display()
        )));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    File::open(path)
        .and_then(|mut file| file.read_to_end(&mut bytes))
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    serde_json::from_slice(&bytes)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))
}

fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, InstallerError> {
    let mut bytes = serde_json::to_vec(value)
        .map_err(|error| InstallerError::invalid(format!("JSON encoding failed: {error}")))?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn create_private(path: &Path, bytes: &[u8]) -> Result<(), InstallerError> {
    let parent = path
        .parent()
        .ok_or_else(|| InstallerError::invalid("document path has no parent"))?;
    fs::create_dir_all(parent)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", parent.display())))?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", parent.display())))?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    file.write_all(bytes)
        .and_then(|()| file.sync_all())
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    sync_parent(parent)
}

fn rewrite_private(path: &Path, bytes: &[u8]) -> Result<(), InstallerError> {
    let parent = path
        .parent()
        .ok_or_else(|| InstallerError::invalid("document path has no parent"))?;
    let serial = TEMPORARY_SERIAL.fetch_add(1, Ordering::Relaxed);
    let temporary = parent.join(format!(
        ".arach-install-{}-{serial}.tmp",
        std::process::id()
    ));
    create_private(&temporary, bytes)?;
    fs::rename(&temporary, path).map_err(|error| {
        let _ = fs::remove_file(&temporary);
        InstallerError::invalid(format!("{}: {error}", path.display()))
    })?;
    sync_parent(parent)
}

fn sync_parent(parent: &Path) -> Result<(), InstallerError> {
    File::open(parent)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", parent.display())))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_SERIAL: AtomicU64 = AtomicU64::new(1);

    struct TestRoot(PathBuf);

    impl TestRoot {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "arach-install-test-{}-{}",
                std::process::id(),
                TEST_SERIAL.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    fn write_state(root: &Path, extra: &str) -> PathBuf {
        let state = root.join("state.json");
        let text = format!(
            "{{\"schema\":1,\"transaction_id\":\"0123456789abcdef0123456789abcdef\",\"hostname\":\"arach\"{extra}}}\n"
        );
        create_private(&state, text.as_bytes()).unwrap();
        state
    }

    #[test]
    fn prepare_binds_plan_and_private_journal() {
        let root = TestRoot::new();
        let state = write_state(&root.0, "");
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal).unwrap();
        let (_, loaded) = load_bound_documents(&plan, &journal).unwrap();
        assert_eq!(loaded.status, JournalStatus::Prepared);
        assert_eq!(
            fs::metadata(journal).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn secrets_are_rejected_as_unknown_state_fields() {
        let root = TestRoot::new();
        let state = write_state(&root.0, ",\"password\":\"never\"");
        let error = prepare(
            &state,
            &root.0.join("plan.json"),
            &root.0.join("journal.json"),
        )
        .unwrap_err();
        assert!(error.message.contains("unknown field"));
    }

    #[test]
    fn production_apply_fails_closed_and_can_roll_back() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir(&target).unwrap();
        let state = write_state(&root.0, "");
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal).unwrap();
        let error = apply(&plan, &journal, &target).unwrap_err();
        assert!(error.unavailable);
        assert_eq!(fs::read_dir(&target).unwrap().count(), 0);
        rollback(&journal, &target).unwrap();
        let value: InstallJournal = read_private_json(&journal).unwrap();
        assert_eq!(value.status, JournalStatus::RolledBack);
    }

    #[test]
    fn root_target_is_rejected() {
        let error = validate_target(Path::new("/")).unwrap_err();
        assert!(error.message.contains("non-root"));
    }
}
