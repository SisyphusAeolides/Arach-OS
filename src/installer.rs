use corinth::generation::{GenerationDigest, GenerationImage, MAX_GENERATION_BYTES, NO_GENERATION};
use corinth::store::FilesystemGenerationStore;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const DOCUMENT_LIMIT: u64 = 1024 * 1024;
const TRANSACTION_SCHEMA: u32 = 1;
const MAX_RECOVERY_TRANSACTIONS: usize = 128;
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
    pub generation_sha256: String,
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
    CorinthPublished,
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
    pub previous_corinth_generation: Option<String>,
    pub intended_corinth_generation: String,
    pub corinth_published: bool,
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
    generation_path: &Path,
) -> Result<(), InstallerError> {
    require_distinct_paths(&[state_path, plan_path, journal_path, generation_path])?;
    let state: InstallerState = read_private_json(state_path)?;
    validate_transaction_id(&state.transaction_id)?;
    if state.schema != TRANSACTION_SCHEMA {
        return Err(InstallerError::invalid(
            "unsupported installer state schema",
        ));
    }
    let generation_bytes = read_regular(generation_path, MAX_GENERATION_BYTES as u64, false)?;
    GenerationImage::decode(&generation_bytes).map_err(|error| {
        InstallerError::invalid(format!("invalid Corinth generation: {error:?}"))
    })?;
    let generation_sha256 = digest(&generation_bytes);
    let staged_generation = staged_generation_path(plan_path)?;
    let state_bytes = canonical_json(&state)?;
    let plan = InstallPlan {
        schema: TRANSACTION_SCHEMA,
        transaction_id: state.transaction_id.clone(),
        state_sha256: digest(&state_bytes),
        generation_sha256: generation_sha256.clone(),
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
        previous_corinth_generation: None,
        intended_corinth_generation: generation_sha256,
        corinth_published: false,
        mutations: Vec::new(),
    };
    create_private(&staged_generation, &generation_bytes)?;
    if let Err(error) = create_private(plan_path, &plan_bytes) {
        let _ = fs::remove_file(&staged_generation);
        return Err(error);
    }
    if let Err(error) = create_private(journal_path, &canonical_json(&journal)?) {
        let _ = fs::remove_file(plan_path);
        let _ = fs::remove_file(&staged_generation);
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
    let generation_path = staged_generation_path(plan_path)?;
    let generation_bytes = read_regular(&generation_path, MAX_GENERATION_BYTES as u64, true)?;
    if digest(&generation_bytes) != plan.generation_sha256 {
        return Err(InstallerError::invalid(
            "staged Corinth generation differs from the immutable plan",
        ));
    }
    GenerationImage::decode(&generation_bytes).map_err(|error| {
        InstallerError::invalid(format!("invalid staged Corinth generation: {error:?}"))
    })?;
    let store_root = target_store_root(&target)?;
    let previous = FilesystemGenerationStore::inspect_active(&store_root).map_err(|error| {
        InstallerError::invalid(format!("cannot read Corinth authority: {error}"))
    })?;
    journal.status = JournalStatus::Applying;
    journal.target = Some(target.display().to_string());
    journal.previous_corinth_generation = previous.map(encode_generation_digest);
    journal.intended_corinth_generation = plan.generation_sha256.clone();
    let checkpoint_journal = checkpoint_transaction(&target, &plan, &journal, &generation_bytes)?;
    rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;

    let store = FilesystemGenerationStore::open(&store_root)
        .map_err(|error| InstallerError::invalid(format!("Corinth store: {error}")))?;
    let published = store
        .publish(&generation_bytes)
        .map_err(|error| InstallerError::invalid(format!("Corinth publication failed: {error}")))?;
    if encode_generation_digest(published) != plan.generation_sha256 {
        return Err(InstallerError::invalid(
            "Corinth published an unexpected generation digest",
        ));
    }
    journal.status = JournalStatus::CorinthPublished;
    journal.corinth_published = true;
    journal.mutations.push("corinth-generation".into());
    rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;

    journal.status = JournalStatus::ApplyFailed;
    rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;
    Err(InstallerError::unavailable(
        "Granite activation is not implemented; the published Corinth generation requires rollback",
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

pub fn rollback(
    plan_path: &Path,
    journal_path: &Path,
    target: &Path,
) -> Result<(), InstallerError> {
    let target = validate_target(target)?;
    let (plan, runtime_journal) = load_bound_documents(plan_path, journal_path)?;
    let (mut journal, checkpoint_journal) = authoritative_journal(&target, &plan, runtime_journal)?;
    if !matches!(
        journal.status,
        JournalStatus::Prepared
            | JournalStatus::Applying
            | JournalStatus::CorinthPublished
            | JournalStatus::ApplyFailed
            | JournalStatus::Applied
    ) {
        return Err(InstallerError::invalid(
            "transaction state cannot be rolled back",
        ));
    }
    if journal
        .target
        .as_deref()
        .is_some_and(|value| value != target.to_string_lossy().as_ref())
    {
        return Err(InstallerError::invalid(
            "rollback target differs from the journaled target",
        ));
    }
    rollback_corinth(&target, &plan, &journal)?;
    journal.status = JournalStatus::RolledBack;
    journal.target = Some(target.display().to_string());
    journal.corinth_published = false;
    if !journal
        .mutations
        .iter()
        .any(|mutation| mutation == "corinth-generation:rolled-back")
    {
        journal
            .mutations
            .push("corinth-generation:rolled-back".into());
    }
    rewrite_journal_copies(journal_path, checkpoint_journal.as_deref(), &journal)
}

/// Recover every target-persistent transaction that did not reach a terminal state.
pub fn recover(target: &Path) -> Result<u32, InstallerError> {
    let target = validate_target(target)?;
    let transactions = target_transactions_root(&target);
    match fs::symlink_metadata(&transactions) {
        Ok(_) => validate_private_directory(&transactions)?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(0),
        Err(error) => {
            return Err(InstallerError::invalid(format!(
                "{}: {error}",
                transactions.display()
            )));
        }
    }

    let mut recovered = 0u32;
    let mut seen = 0usize;
    let entries = fs::read_dir(&transactions)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", transactions.display())))?;
    for entry in entries {
        let entry = entry.map_err(|error| InstallerError::invalid(error.to_string()))?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| InstallerError::invalid("non-UTF-8 recovery transaction name"))?;
        if name.starts_with('.') {
            continue;
        }
        validate_transaction_id(&name)?;
        seen += 1;
        if seen > MAX_RECOVERY_TRANSACTIONS {
            return Err(InstallerError::invalid(
                "recovery transaction limit exceeded",
            ));
        }
        let directory = entry.path();
        validate_private_directory(&directory)?;
        let plan_path = directory.join("plan.json");
        let journal_path = directory.join("journal.json");
        let (_, journal) = load_bound_documents(&plan_path, &journal_path)?;
        if matches!(
            journal.status,
            JournalStatus::Prepared
                | JournalStatus::Applying
                | JournalStatus::CorinthPublished
                | JournalStatus::ApplyFailed
                | JournalStatus::Applied
        ) {
            rollback(&plan_path, &journal_path, &target)?;
            recovered = recovered.saturating_add(1);
        }
    }
    Ok(recovered)
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
        if !matches!(flag, "state" | "plan" | "journal" | "target" | "generation") {
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
        || !valid_digest(&plan.generation_sha256)
        || journal.intended_corinth_generation != plan.generation_sha256
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
    validate_transaction_id(&journal.transaction_id)?;
    let published_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "corinth-generation")
        .count();
    let rollback_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "corinth-generation:rolled-back")
        .count();
    let coherent_transition = match journal.status {
        JournalStatus::Prepared => {
            journal.target.is_none()
                && journal.previous_corinth_generation.is_none()
                && !journal.corinth_published
                && journal.mutations.is_empty()
        }
        JournalStatus::Applying => {
            journal.target.is_some() && !journal.corinth_published && journal.mutations.is_empty()
        }
        JournalStatus::CorinthPublished
        | JournalStatus::ApplyFailed
        | JournalStatus::Applied
        | JournalStatus::Verified => {
            journal.target.is_some()
                && journal.corinth_published
                && published_mutations == 1
                && rollback_mutations == 0
        }
        JournalStatus::RolledBack => {
            journal.target.is_some()
                && !journal.corinth_published
                && rollback_mutations == 1
                && published_mutations <= 1
        }
    };
    if !valid_digest(&journal.intended_corinth_generation)
        || journal
            .previous_corinth_generation
            .as_deref()
            .is_some_and(|value| !valid_digest(value))
        || journal.mutations.iter().any(|mutation| {
            !matches!(
                mutation.as_str(),
                "corinth-generation" | "corinth-generation:rolled-back"
            )
        })
        || !coherent_transition
    {
        return Err(InstallerError::invalid("invalid Corinth journal state"));
    }
    Ok(())
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

fn staged_generation_path(plan_path: &Path) -> Result<PathBuf, InstallerError> {
    plan_path
        .parent()
        .map(|parent| parent.join("generation.gen"))
        .ok_or_else(|| InstallerError::invalid("plan path has no parent"))
}

fn target_transactions_root(target: &Path) -> PathBuf {
    target.join("var/lib/arach-installer/transactions")
}

fn target_transaction_directory(target: &Path, transaction_id: &str) -> PathBuf {
    target_transactions_root(target).join(transaction_id)
}

fn checkpoint_transaction(
    target: &Path,
    plan: &InstallPlan,
    journal: &InstallJournal,
    generation_bytes: &[u8],
) -> Result<PathBuf, InstallerError> {
    let var_lib = target_store_root(target)?
        .parent()
        .ok_or_else(|| InstallerError::invalid("target /var/lib has no parent"))?
        .to_path_buf();
    let installer_root = var_lib.join("arach-installer");
    ensure_private_directory(&installer_root)?;
    let transactions = installer_root.join("transactions");
    ensure_private_directory(&transactions)?;

    let final_directory = transactions.join(&plan.transaction_id);
    if final_directory.exists() {
        return Err(InstallerError::invalid(
            "target transaction checkpoint already exists",
        ));
    }
    let serial = TEMPORARY_SERIAL.fetch_add(1, Ordering::Relaxed);
    let temporary = transactions.join(format!(
        ".{}-{}-{serial}.tmp",
        plan.transaction_id,
        std::process::id()
    ));
    let mut builder = fs::DirBuilder::new();
    builder
        .mode(0o700)
        .create(&temporary)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", temporary.display())))?;

    let result = (|| {
        create_private(&temporary.join("plan.json"), &canonical_json(plan)?)?;
        create_private(&temporary.join("generation.gen"), generation_bytes)?;
        create_private(&temporary.join("journal.json"), &canonical_json(journal)?)?;
        sync_parent(&temporary)?;
        fs::rename(&temporary, &final_directory).map_err(|error| {
            InstallerError::invalid(format!("{}: {error}", final_directory.display()))
        })?;
        sync_parent(&transactions)
    })();
    if result.is_err() {
        remove_incomplete_checkpoint(&temporary);
    }
    result?;
    Ok(final_directory.join("journal.json"))
}

fn authoritative_journal(
    target: &Path,
    plan: &InstallPlan,
    runtime_journal: InstallJournal,
) -> Result<(InstallJournal, Option<PathBuf>), InstallerError> {
    let directory = target_transaction_directory(target, &plan.transaction_id);
    match fs::symlink_metadata(&directory) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok((runtime_journal, None)),
        Err(error) => Err(InstallerError::invalid(format!(
            "{}: {error}",
            directory.display()
        ))),
        Ok(_) => {
            validate_private_directory(&directory)?;
            let checkpoint_plan = directory.join("plan.json");
            let checkpoint_journal = directory.join("journal.json");
            let (durable_plan, durable_journal) =
                load_bound_documents(&checkpoint_plan, &checkpoint_journal)?;
            if &durable_plan != plan {
                return Err(InstallerError::invalid(
                    "target checkpoint plan differs from the runtime plan",
                ));
            }
            Ok((durable_journal, Some(checkpoint_journal)))
        }
    }
}

fn rewrite_journal_copies(
    runtime_path: &Path,
    checkpoint_path: Option<&Path>,
    journal: &InstallJournal,
) -> Result<(), InstallerError> {
    let bytes = canonical_json(journal)?;
    if let Some(path) = checkpoint_path {
        rewrite_private(path, &bytes)?;
    }
    if checkpoint_path != Some(runtime_path) {
        rewrite_private(runtime_path, &bytes)?;
    }
    Ok(())
}

fn ensure_private_directory(path: &Path) -> Result<(), InstallerError> {
    match fs::symlink_metadata(path) {
        Ok(_) => validate_private_directory(path),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let parent = path
                .parent()
                .ok_or_else(|| InstallerError::invalid("private directory has no parent"))?;
            let metadata = fs::symlink_metadata(parent).map_err(|error| {
                InstallerError::invalid(format!("{}: {error}", parent.display()))
            })?;
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                return Err(InstallerError::invalid(
                    "private directory parent is unsafe",
                ));
            }
            let mut builder = fs::DirBuilder::new();
            builder
                .mode(0o700)
                .create(path)
                .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))
        }
        Err(error) => Err(InstallerError::invalid(format!(
            "{}: {error}",
            path.display()
        ))),
    }
}

fn validate_private_directory(path: &Path) -> Result<(), InstallerError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.permissions().mode() & 0o077 != 0
    {
        return Err(InstallerError::invalid(format!(
            "{} is not a private real directory",
            path.display()
        )));
    }
    Ok(())
}

fn remove_incomplete_checkpoint(path: &Path) {
    let Ok(metadata) = fs::symlink_metadata(path) else {
        return;
    };
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return;
    }
    for name in ["plan.json", "generation.gen", "journal.json"] {
        let file = path.join(name);
        if fs::symlink_metadata(&file)
            .is_ok_and(|metadata| metadata.is_file() && !metadata.file_type().is_symlink())
        {
            let _ = fs::remove_file(file);
        }
    }
    let _ = fs::remove_dir(path);
}

fn target_store_root(target: &Path) -> Result<PathBuf, InstallerError> {
    let mut current = target.to_path_buf();
    for component in ["var", "lib"] {
        current.push(component);
        let metadata = fs::symlink_metadata(&current)
            .map_err(|error| InstallerError::invalid(format!("{}: {error}", current.display())))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(InstallerError::invalid(
                "target /var/lib path must contain real directories",
            ));
        }
    }
    Ok(current.join("corinth"))
}

fn rollback_corinth(
    target: &Path,
    plan: &InstallPlan,
    journal: &InstallJournal,
) -> Result<(), InstallerError> {
    if journal.status == JournalStatus::Prepared && journal.target.is_none() {
        return Ok(());
    }
    let intended = decode_generation_digest(&plan.generation_sha256)?;
    let previous = journal
        .previous_corinth_generation
        .as_deref()
        .map(decode_generation_digest)
        .transpose()?;
    let store_root = target_store_root(target)?;
    match fs::symlink_metadata(&store_root) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && previous.is_none() => {
            return Ok(());
        }
        Err(error) => {
            return Err(InstallerError::invalid(format!(
                "{}: {error}",
                store_root.display()
            )));
        }
    }
    let store = FilesystemGenerationStore::open(&store_root)
        .map_err(|error| InstallerError::invalid(format!("Corinth rollback store: {error}")))?;
    let active = store.active().map_err(|error| {
        InstallerError::invalid(format!("cannot read Corinth rollback authority: {error}"))
    })?;
    if active == previous {
        return Ok(());
    }
    if active != Some(intended) {
        return Err(InstallerError::invalid(
            "active Corinth generation differs from both rollback authorities",
        ));
    }
    let restored = store
        .rollback(intended)
        .map_err(|error| InstallerError::invalid(format!("Corinth rollback failed: {error}")))?;
    if restored != previous {
        return Err(InstallerError::invalid(
            "Corinth rollback restored an unexpected generation",
        ));
    }
    Ok(())
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn decode_generation_digest(value: &str) -> Result<GenerationDigest, InstallerError> {
    if !valid_digest(value) {
        return Err(InstallerError::invalid("invalid generation digest"));
    }
    let mut digest = [0; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_value(pair[0]).ok_or_else(|| InstallerError::invalid("invalid digest"))?;
        let low = hex_value(pair[1]).ok_or_else(|| InstallerError::invalid("invalid digest"))?;
        digest[index] = (high << 4) | low;
    }
    if digest == NO_GENERATION {
        return Err(InstallerError::invalid(
            "zero generation digest is reserved",
        ));
    }
    Ok(digest)
}

fn encode_generation_digest(value: GenerationDigest) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(64);
    for byte in value {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn hex_value(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        _ => None,
    }
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
    let bytes = read_regular(path, DOCUMENT_LIMIT, true)?;
    serde_json::from_slice(&bytes)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))
}

fn read_regular(path: &Path, limit: u64, private: bool) -> Result<Vec<u8>, InstallerError> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    let metadata = file
        .metadata()
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    if !metadata.is_file() || metadata.len() > limit {
        return Err(InstallerError::invalid(format!(
            "{} is not a bounded regular document",
            path.display()
        )));
    }
    if private && metadata.permissions().mode() & 0o077 != 0 {
        return Err(InstallerError::invalid(format!(
            "{} is accessible outside its owner",
            path.display()
        )));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.read_to_end(&mut bytes)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
    Ok(bytes)
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
        .custom_flags(libc::O_NOFOLLOW)
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
    use corinth::pkg::{PackageLedger, ResolvedPackage};
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

    fn write_generation(root: &Path) -> PathBuf {
        write_generation_with_parent(root, NO_GENERATION, &[10], "source.gen")
    }

    fn write_generation_with_parent(
        root: &Path,
        parent: GenerationDigest,
        packages: &[u64],
        name: &str,
    ) -> PathBuf {
        let mut ledger = PackageLedger::new();
        for (index, name_hash) in packages.iter().enumerate() {
            let mut transaction = ledger.begin(ledger.authority()).unwrap();
            transaction
                .install(ResolvedPackage {
                    name_hash: *name_hash,
                    version_idx: index as u16 + 1,
                })
                .unwrap();
            ledger.commit(transaction).unwrap();
        }
        let image = GenerationImage::from_ledger(&ledger, parent);
        let mut bytes = [0; MAX_GENERATION_BYTES];
        let length = image.encode(&mut bytes).unwrap();
        let path = root.join(name);
        create_private(&path, &bytes[..length]).unwrap();
        path
    }

    #[test]
    fn prepare_binds_plan_and_private_journal() {
        let root = TestRoot::new();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation).unwrap();
        let (_, loaded) = load_bound_documents(&plan, &journal).unwrap();
        assert_eq!(loaded.status, JournalStatus::Prepared);
        assert!(staged_generation_path(&plan).unwrap().is_file());
        assert_eq!(
            fs::metadata(journal).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn secrets_are_rejected_as_unknown_state_fields() {
        let root = TestRoot::new();
        let state = write_state(&root.0, ",\"password\":\"never\"");
        let generation = write_generation(&root.0);
        let error = prepare(
            &state,
            &root.0.join("plan.json"),
            &root.0.join("journal.json"),
            &generation,
        )
        .unwrap_err();
        assert!(error.message.contains("unknown field"));
    }

    #[test]
    fn production_apply_fails_closed_and_can_roll_back() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir_all(target.join("var/lib")).unwrap();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation).unwrap();
        let error = apply(&plan, &journal, &target).unwrap_err();
        assert!(error.unavailable);
        let store = FilesystemGenerationStore::open(&target.join("var/lib/corinth")).unwrap();
        assert!(store.active().unwrap().is_some());
        rollback(&plan, &journal, &target).unwrap();
        assert_eq!(store.active().unwrap(), None);
        let value: InstallJournal = read_private_json(&journal).unwrap();
        assert_eq!(value.status, JournalStatus::RolledBack);
        assert!(
            value
                .mutations
                .iter()
                .any(|mutation| mutation == "corinth-generation:rolled-back")
        );
    }

    #[test]
    fn checkpoint_failure_precedes_corinth_store_creation() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir_all(target.join("var/lib")).unwrap();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation).unwrap();

        let transaction = target_transaction_directory(&target, "0123456789abcdef0123456789abcdef");
        ensure_private_directory(transaction.parent().unwrap().parent().unwrap()).unwrap();
        ensure_private_directory(transaction.parent().unwrap()).unwrap();
        ensure_private_directory(&transaction).unwrap();

        let error = apply(&plan, &journal, &target).unwrap_err();
        assert!(error.message.contains("checkpoint already exists"));
        assert!(!target.join("var/lib/corinth").exists());
        let loaded: InstallJournal = read_private_json(&journal).unwrap();
        assert_eq!(loaded.status, JournalStatus::Prepared);
    }

    #[test]
    fn rollback_restores_the_exact_previous_generation_authority() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir_all(target.join("var/lib")).unwrap();
        let store = FilesystemGenerationStore::open(&target.join("var/lib/corinth")).unwrap();
        let parent_path = write_generation_with_parent(&root.0, NO_GENERATION, &[10], "parent.gen");
        let parent_bytes = fs::read(parent_path).unwrap();
        let parent = store.publish(&parent_bytes).unwrap();

        let child = write_generation_with_parent(&root.0, parent, &[10, 20], "child.gen");
        let state = write_state(&root.0, "");
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &child).unwrap();
        assert!(apply(&plan, &journal, &target).unwrap_err().unavailable);
        assert_ne!(store.active().unwrap(), Some(parent));

        rollback(&plan, &journal, &target).unwrap();
        assert_eq!(store.active().unwrap(), Some(parent));
    }

    #[test]
    fn rollback_recovers_publication_before_post_publish_journal() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir_all(target.join("var/lib")).unwrap();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let plan_path = root.0.join("plan.json");
        let journal_path = root.0.join("journal.json");
        prepare(&state, &plan_path, &journal_path, &generation).unwrap();

        let (plan, mut journal) = load_bound_documents(&plan_path, &journal_path).unwrap();
        let store_root = target_store_root(&target).unwrap();
        assert_eq!(
            FilesystemGenerationStore::inspect_active(&store_root).unwrap(),
            None
        );
        assert!(!store_root.exists());

        journal.status = JournalStatus::Applying;
        journal.target = Some(target.display().to_string());
        journal.previous_corinth_generation = None;

        let generation_bytes = read_regular(
            &staged_generation_path(&plan_path).unwrap(),
            MAX_GENERATION_BYTES as u64,
            true,
        )
        .unwrap();
        let checkpoint_journal =
            checkpoint_transaction(&target, &plan, &journal, &generation_bytes).unwrap();
        fs::remove_file(&plan_path).unwrap();
        fs::remove_file(&journal_path).unwrap();
        fs::remove_file(staged_generation_path(&plan_path).unwrap()).unwrap();

        let store = FilesystemGenerationStore::open(&store_root).unwrap();
        let published = store.publish(&generation_bytes).unwrap();
        assert_eq!(encode_generation_digest(published), plan.generation_sha256);

        assert_eq!(recover(&target).unwrap(), 1);
        assert_eq!(store.active().unwrap(), None);
        let recovered: InstallJournal = read_private_json(&checkpoint_journal).unwrap();
        assert_eq!(recovered.status, JournalStatus::RolledBack);
        assert_eq!(recover(&target).unwrap(), 0);
    }

    #[test]
    fn root_target_is_rejected() {
        let error = validate_target(Path::new("/")).unwrap_err();
        assert!(error.message.contains("non-root"));
    }
}
