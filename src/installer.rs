use arach_hwd::catalog::verify_catalog;
use arach_hwd::plan::PlanSet;
use arach_hwd::signature::Keyring;
use corinth::binary::{BinaryInstallStore, BinaryProvisioner, verify_binary_index};
use corinth::generation::{GenerationDigest, GenerationImage, MAX_GENERATION_BYTES, NO_GENERATION};
use corinth::hardware::{HardwareProvisioner, verify_plan_set};
use corinth::store::FilesystemGenerationStore;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const DOCUMENT_LIMIT: u64 = 1024 * 1024;
const TRANSACTION_SCHEMA: u32 = 1;
pub const BOOT_BUNDLE_SCHEMA: u32 = 1;
const MAX_BOOT_ARTIFACT_BYTES: u64 = 32 * 1024 * 1024;
const MAX_RECOVERY_TRANSACTIONS: usize = 128;
const HARDWARE_RECIPES_URL: &str = "https://github.com/SisyphusAeolides/Arach-Packages.git";
const HARDWARE_RECIPES_REVISION: &str = "7918fd243ce9b2cc4ea1de90efc38bcbff7a57b9";
static TEMPORARY_SERIAL: AtomicU64 = AtomicU64::new(1);

const BOOT_MANIFEST_NAME: &str = "manifest.json";
const GRANITE_ARTIFACT_NAME: &str = "granite.efi";
const ARACH_ARTIFACT_NAME: &str = "arach";
const PUSH_ARTIFACT_NAME: &str = "push";
const CREST_ARTIFACT_NAME: &str = "crest";
const TARGET_GRANITE_PATH: &str = "boot/EFI/BOOT/BOOTX64.EFI";
const TARGET_ARACH_PATH: &str = "boot/BOOT/ARACH";
const TARGET_PUSH_PATH: &str = "boot/BOOT/PUSH";
const TARGET_CREST_PATH: &str = "boot/BOOT/CREST";
const TARGET_MANIFEST_PATH: &str = "boot/BOOT/ARACH-MANIFEST.json";

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct BootBundleManifest {
    pub schema: u32,
    pub granite_sha256: String,
    pub arach_sha256: String,
    pub push_sha256: String,
    pub crest_sha256: String,
}

struct BootBundle {
    manifest_bytes: Vec<u8>,
    granite: Vec<u8>,
    arach: Vec<u8>,
    push: Vec<u8>,
    crest: Vec<u8>,
}

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
    pub boot_bundle_sha256: String,
    pub distribution: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hardware_plan_sha256: Option<String>,
    pub operations: Vec<InstallOperation>,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum InstallOperation {
    CorinthInstall,
    HardwareProvision,
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
    #[serde(default)]
    pub hardware_packages: Vec<String>,
    pub mutations: Vec<String>,
}

/// Live-installer inputs for the signed HWD plan.  The profile directory and
/// catalog lock are read-only image inputs; build work and artifacts remain in
/// the private transaction runtime directory.  Network access is enabled only
/// for the pinned recipe revision and every recipe is still digest-bound by
/// the signed hardware profile.
#[derive(Clone, Debug)]
pub struct HardwareApplyInputs {
    pub profiles: PathBuf,
    pub keyring: PathBuf,
    pub catalog_lock: PathBuf,
    pub binary_index: PathBuf,
    pub binary_signature: PathBuf,
    pub work: PathBuf,
    pub artifacts: PathBuf,
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
    boot_bundle_path: &Path,
) -> Result<(), InstallerError> {
    prepare_internal(
        state_path,
        plan_path,
        journal_path,
        generation_path,
        boot_bundle_path,
        None,
    )
}

pub fn prepare_with_hardware_plan(
    state_path: &Path,
    plan_path: &Path,
    journal_path: &Path,
    generation_path: &Path,
    boot_bundle_path: &Path,
    hardware_plan_path: &Path,
) -> Result<(), InstallerError> {
    prepare_internal(
        state_path,
        plan_path,
        journal_path,
        generation_path,
        boot_bundle_path,
        Some(hardware_plan_path),
    )
}

fn prepare_internal(
    state_path: &Path,
    plan_path: &Path,
    journal_path: &Path,
    generation_path: &Path,
    boot_bundle_path: &Path,
    hardware_plan_path: Option<&Path>,
) -> Result<(), InstallerError> {
    require_distinct_paths(&[
        state_path,
        plan_path,
        journal_path,
        generation_path,
        boot_bundle_path,
    ])?;
    if hardware_plan_path.is_some_and(|path| {
        [
            state_path,
            plan_path,
            journal_path,
            generation_path,
            boot_bundle_path,
        ]
        .into_iter()
        .any(|other| other == path)
    }) {
        return Err(InstallerError::invalid(
            "hardware plan path must be distinct from transaction inputs",
        ));
    }
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
    let boot_bundle = read_boot_bundle(boot_bundle_path)?;
    let hardware_plan = hardware_plan_path.map(read_hardware_plan).transpose()?;
    let staged_generation = staged_generation_path(plan_path)?;
    let staged_hardware_plan = staged_hardware_plan_path(plan_path)?;
    let state_bytes = canonical_json(&state)?;
    let plan = InstallPlan {
        schema: TRANSACTION_SCHEMA,
        transaction_id: state.transaction_id.clone(),
        state_sha256: digest(&state_bytes),
        generation_sha256: generation_sha256.clone(),
        distribution: crate::DISTRIBUTION.into(),
        boot_bundle_sha256: digest(&boot_bundle.manifest_bytes),
        hardware_plan_sha256: hardware_plan.as_deref().map(digest),
        operations: operations_for(hardware_plan.is_some()),
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
        hardware_packages: Vec::new(),
        mutations: Vec::new(),
    };
    create_private(&staged_generation, &generation_bytes)?;
    if let Some(bytes) = hardware_plan.as_deref() {
        if let Err(error) = create_private(&staged_hardware_plan, bytes) {
            let _ = fs::remove_file(&staged_generation);
            return Err(error);
        }
    }
    if let Err(error) = create_private(plan_path, &plan_bytes) {
        let _ = fs::remove_file(&staged_generation);
        let _ = fs::remove_file(&staged_hardware_plan);
        return Err(error);
    }
    if let Err(error) = create_private(journal_path, &canonical_json(&journal)?) {
        let _ = fs::remove_file(plan_path);
        let _ = fs::remove_file(&staged_generation);
        let _ = fs::remove_file(&staged_hardware_plan);
        return Err(error);
    }
    Ok(())
}

pub fn apply(
    plan_path: &Path,
    journal_path: &Path,
    target: &Path,
    boot_bundle_path: &Path,
) -> Result<(), InstallerError> {
    apply_internal(plan_path, journal_path, target, boot_bundle_path, None)
}

pub fn apply_with_hardware(
    plan_path: &Path,
    journal_path: &Path,
    target: &Path,
    boot_bundle_path: &Path,
    hardware: HardwareApplyInputs,
) -> Result<(), InstallerError> {
    apply_internal(
        plan_path,
        journal_path,
        target,
        boot_bundle_path,
        Some(hardware),
    )
}

fn apply_internal(
    plan_path: &Path,
    journal_path: &Path,
    target: &Path,
    boot_bundle_path: &Path,
    hardware: Option<HardwareApplyInputs>,
) -> Result<(), InstallerError> {
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
    validate_hardware_plan_file(
        &staged_hardware_plan_path(plan_path)?,
        plan.hardware_plan_sha256.as_deref(),
    )?;
    GenerationImage::decode(&generation_bytes).map_err(|error| {
        InstallerError::invalid(format!("invalid staged Corinth generation: {error:?}"))
    })?;
    let boot_bundle = read_boot_bundle(boot_bundle_path)?;
    if digest(&boot_bundle.manifest_bytes) != plan.boot_bundle_sha256 {
        return Err(InstallerError::invalid(
            "boot bundle manifest differs from the immutable install plan",
        ));
    }
    let store_root = target_store_root(&target)?;
    let previous = FilesystemGenerationStore::inspect_active(&store_root).map_err(|error| {
        InstallerError::invalid(format!("cannot read Corinth authority: {error}"))
    })?;
    journal.status = JournalStatus::Applying;
    journal.target = Some(target.display().to_string());
    journal.previous_corinth_generation = previous.map(encode_generation_digest);
    journal.intended_corinth_generation = plan.generation_sha256.clone();
    let hardware_plan_bytes = if plan.hardware_plan_sha256.is_some() {
        Some(read_regular(
            &staged_hardware_plan_path(plan_path)?,
            DOCUMENT_LIMIT,
            true,
        )?)
    } else {
        None
    };
    let checkpoint_journal = checkpoint_transaction(
        &target,
        &plan,
        &journal,
        &generation_bytes,
        hardware_plan_bytes.as_deref(),
    )?;
    rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;

    if plan.hardware_plan_sha256.is_some() {
        let hardware = hardware.ok_or_else(|| {
            InstallerError::invalid(
                "a signed hardware plan requires catalog and recipe inputs during apply",
            )
        })?;
        provision_hardware(
            plan_path,
            &target,
            &plan,
            &mut journal,
            &hardware,
            &checkpoint_journal,
            journal_path,
        )?;
    } else if hardware.is_some() {
        return Err(InstallerError::invalid(
            "hardware catalog inputs were supplied without a hardware plan",
        ));
    }

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

    if let Err(error) = activate_boot_bundle(&target, &plan, &boot_bundle) {
        journal.status = JournalStatus::ApplyFailed;
        rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;
        return Err(error);
    }
    journal.status = JournalStatus::Applied;
    journal.mutations.push("boot-bundle".into());
    rewrite_journal_copies(journal_path, Some(&checkpoint_journal), &journal)?;
    Ok(())
}

fn provision_hardware(
    plan_path: &Path,
    target: &Path,
    plan: &InstallPlan,
    journal: &mut InstallJournal,
    inputs: &HardwareApplyInputs,
    checkpoint_journal: &Path,
    runtime_journal: &Path,
) -> Result<(), InstallerError> {
    let hardware_plan_path = staged_hardware_plan_path(plan_path)?;
    let bytes = read_regular(&hardware_plan_path, DOCUMENT_LIMIT, true)?;
    if plan.hardware_plan_sha256.as_deref() != Some(digest(&bytes).as_str()) {
        return Err(InstallerError::invalid(
            "staged hardware plan differs from the immutable install plan",
        ));
    }
    let plans = parse_hardware_plans(&bytes)?;
    verify_catalog(&inputs.catalog_lock, &inputs.profiles, &inputs.keyring)
        .map_err(|error| InstallerError::invalid(format!("hardware catalog: {error}")))?;
    let keyring = Keyring::load(&inputs.keyring)
        .map_err(|error| InstallerError::invalid(format!("hardware keyring: {error}")))?;
    let documents = load_hardware_profile_documents(&inputs.profiles, &keyring)?;
    let verified = if plans.plan.is_empty() {
        Vec::new()
    } else {
        verify_plan_set(plans, &documents)
            .map_err(|error| InstallerError::invalid(format!("hardware plan: {error}")))?
    };

    let index_bytes = read_regular(&inputs.binary_index, DOCUMENT_LIMIT, false)?;
    let index_signature = String::from_utf8(read_regular(
        &inputs.binary_signature,
        DOCUMENT_LIMIT,
        false,
    )?)
    .map_err(|_| InstallerError::invalid("hardware binary-index signature is not UTF-8"))?;
    let binary_index = verify_binary_index(&index_bytes, &index_signature, &keyring)
        .map_err(|error| InstallerError::invalid(format!("hardware binary index: {error}")))?;

    let hardware_state =
        target_transaction_directory(target, &journal.transaction_id).join("hardware-state");
    let expected_packages = verified
        .iter()
        .flat_map(|plan| plan.plan.package.iter().map(|intent| intent.name.clone()))
        .collect::<BTreeSet<_>>();
    if !expected_packages.is_empty() {
        journal.hardware_packages = expected_packages.into_iter().collect();
        journal.mutations.push("hardware-provisioning".into());
        rewrite_journal_copies(runtime_journal, Some(checkpoint_journal), journal)?;
    }
    let packages = if verified.is_empty() {
        Vec::new()
    } else if binary_index_covers(&binary_index, &verified) {
        let mut provisioner = BinaryProvisioner::new(inputs.artifacts.clone())
            .map_err(|error| InstallerError::invalid(format!("hardware binaries: {error}")))?;
        provisioner.allow_network = true;
        provisioner
            .install_hardware_plan_set_to_root(
                hardware_state.clone(),
                target.to_path_buf(),
                &binary_index,
                &verified,
            )
            .map_err(|error| InstallerError::invalid(format!("hardware binary install: {error}")))?
            .into_iter()
            .map(|receipt| receipt.package)
            .collect()
    } else {
        let mut provisioner =
            HardwareProvisioner::new(inputs.work.clone(), inputs.artifacts.clone())
                .map_err(|error| InstallerError::invalid(format!("hardware builder: {error}")))?;
        // The signed profile and catalog are the authority boundary.  The
        // only network operation below is fetching the exact pinned recipe
        // revision and its locked sources; recipe policy still decides
        // whether a build may use network access.
        provisioner.allow_network = true;
        let recipes = provisioner
            .acquire_recipe_repository(HARDWARE_RECIPES_URL, HARDWARE_RECIPES_REVISION, false)
            .map_err(|error| InstallerError::invalid(format!("hardware recipes: {error}")))?;
        let receipts = provisioner
            .build_verified_set(&verified, &recipes)
            .map_err(|error| InstallerError::invalid(format!("hardware build: {error}")))?;
        provisioner
            .install_plan_set_to_root(
                hardware_state.clone(),
                target.to_path_buf(),
                &verified,
                &receipts,
            )
            .map_err(|error| InstallerError::invalid(format!("hardware install: {error}")))?;
        receipts
            .into_iter()
            .map(|receipt| receipt.package)
            .collect()
    };
    journal.hardware_packages = packages;
    journal.hardware_packages.sort();
    journal.hardware_packages.dedup();
    rewrite_journal_copies(runtime_journal, Some(checkpoint_journal), journal)?;

    Ok(())
}

fn parse_hardware_plans(bytes: &[u8]) -> Result<PlanSet, InstallerError> {
    if let Ok(set) = toml::from_slice::<PlanSet>(bytes) {
        if set.schema != arach_hwd::plan::PLAN_SCHEMA {
            return Err(InstallerError::invalid(
                "hardware plan set has an unsupported schema",
            ));
        }
        return Ok(set);
    }
    let plan = toml::from_slice::<arach_hwd::plan::ProvisionPlan>(bytes)
        .map_err(|error| InstallerError::invalid(format!("invalid hardware plan: {error}")))?;
    Ok(PlanSet {
        schema: arach_hwd::plan::PLAN_SCHEMA,
        plan: vec![plan],
    })
}

fn binary_index_covers(
    index: &corinth::binary::VerifiedBinaryIndex,
    plans: &[corinth::hardware::VerifiedHardwarePlan],
) -> bool {
    plans.iter().all(|plan| {
        plan.plan.package.iter().all(|intent| {
            index.index.packages.iter().any(|package| {
                package.name == intent.name
                    && package.version == intent.version
                    && package.scope == intent.scope
                    && package.repository == intent.repository
                    && package.metadata_sha256 == intent.metadata_sha256
                    && package.artifact_sha256 == intent.artifact_sha256
                    && package.source_lock_sha256 == intent.source_lock_sha256
            })
        })
    })
}

fn load_hardware_profile_documents(
    directory: &Path,
    keyring: &Keyring,
) -> Result<Vec<(Vec<u8>, String, Keyring)>, InstallerError> {
    fn walk(directory: &Path, paths: &mut Vec<PathBuf>) -> Result<(), InstallerError> {
        let mut entries = fs::read_dir(directory)
            .map_err(|error| InstallerError::invalid(format!("{}: {error}", directory.display())))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| InstallerError::invalid(error.to_string()))?;
        entries.sort_by_key(|entry| entry.path());
        for entry in entries {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
            if metadata.file_type().is_symlink() {
                return Err(InstallerError::invalid(format!(
                    "symlink in hardware profile catalog: {}",
                    path.display()
                )));
            }
            if metadata.is_dir() {
                walk(&path, paths)?;
            } else if metadata.is_file()
                && path
                    .extension()
                    .is_some_and(|extension| extension == "toml")
            {
                paths.push(path);
            }
        }
        Ok(())
    }

    let mut paths = Vec::new();
    walk(directory, &mut paths)?;
    if paths.is_empty() {
        return Err(InstallerError::invalid(
            "hardware profile catalog contains no profiles",
        ));
    }
    paths
        .into_iter()
        .map(|path| {
            let bytes = read_regular(&path, DOCUMENT_LIMIT, false)?;
            let signature_path = PathBuf::from(format!("{}.sig", path.display()));
            let signature =
                String::from_utf8(read_regular(&signature_path, DOCUMENT_LIMIT, false)?).map_err(
                    |_| InstallerError::invalid("hardware profile signature is not UTF-8"),
                )?;
            keyring
                .verify(&bytes, &signature)
                .map_err(|error| InstallerError::invalid(format!("hardware profile: {error}")))?;
            Ok((bytes, signature, keyring.clone()))
        })
        .collect()
}

pub fn verify(plan_path: &Path, journal_path: &Path, target: &Path) -> Result<(), InstallerError> {
    let target = validate_target(target)?;
    let (plan, runtime_journal) = load_bound_documents(plan_path, journal_path)?;
    let (mut journal, checkpoint_journal) = authoritative_journal(&target, &plan, runtime_journal)?;
    if journal.status != JournalStatus::Applied
        || journal.target.as_deref() != Some(target.to_string_lossy().as_ref())
    {
        return Err(InstallerError::invalid(
            "only an applied transaction may enter verification",
        ));
    }
    verify_installed_boot_bundle(&target, &plan)?;
    journal.status = JournalStatus::Verified;
    rewrite_journal_copies(journal_path, checkpoint_journal.as_deref(), &journal)?;
    Ok(())
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
            | JournalStatus::Verified
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
    let had_boot_bundle = journal
        .mutations
        .iter()
        .any(|mutation| mutation == "boot-bundle");
    let had_hardware = journal
        .mutations
        .iter()
        .any(|mutation| mutation == "hardware-provisioning");
    rollback_hardware(&target, &journal, had_hardware)?;
    if had_hardware
        && !journal
            .mutations
            .iter()
            .any(|mutation| mutation == "hardware-provisioning:rolled-back")
    {
        journal
            .mutations
            .push("hardware-provisioning:rolled-back".into());
    }
    rollback_boot_bundle(&target, &plan)?;
    if had_boot_bundle
        && !journal
            .mutations
            .iter()
            .any(|mutation| mutation == "boot-bundle:rolled-back")
    {
        journal.mutations.push("boot-bundle:rolled-back".into());
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

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct BootMutationRecord {
    schema: u32,
    manifest_sha256: String,
    complete: bool,
    entries: Vec<BootMutationEntry>,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct BootMutationEntry {
    destination: String,
    backup: Option<String>,
    installed: bool,
}

fn read_boot_bundle(root: &Path) -> Result<BootBundle, InstallerError> {
    let root = validate_boot_bundle_root(root)?;
    let manifest_path = root.join(BOOT_MANIFEST_NAME);
    let manifest_bytes = read_regular(&manifest_path, DOCUMENT_LIMIT, false)?;
    let manifest: BootBundleManifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|error| InstallerError::invalid(format!("boot manifest: {error}")))?;
    if manifest.schema != BOOT_BUNDLE_SCHEMA
        || !valid_digest(&manifest.granite_sha256)
        || !valid_digest(&manifest.arach_sha256)
        || !valid_digest(&manifest.push_sha256)
        || !valid_digest(&manifest.crest_sha256)
    {
        return Err(InstallerError::invalid(
            "boot manifest has an unsupported schema or digest",
        ));
    }
    let granite = read_boot_artifact(
        &root,
        GRANITE_ARTIFACT_NAME,
        &manifest.granite_sha256,
        "Granite",
        b"MZ",
    )?;
    let arach = read_boot_artifact(
        &root,
        ARACH_ARTIFACT_NAME,
        &manifest.arach_sha256,
        "Arach",
        b"\x7fELF",
    )?;
    let push = read_boot_artifact(
        &root,
        PUSH_ARTIFACT_NAME,
        &manifest.push_sha256,
        "Push",
        b"\x7fELF",
    )?;
    let crest = read_boot_artifact(
        &root,
        CREST_ARTIFACT_NAME,
        &manifest.crest_sha256,
        "Crest",
        b"\x7fELF",
    )?;
    Ok(BootBundle {
        manifest_bytes,
        granite,
        arach,
        push,
        crest,
    })
}

fn validate_boot_bundle_root(root: &Path) -> Result<PathBuf, InstallerError> {
    if !root.is_absolute() {
        return Err(InstallerError::invalid(
            "boot bundle source must be an absolute directory",
        ));
    }
    let metadata = fs::symlink_metadata(root)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", root.display())))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(InstallerError::invalid(
            "boot bundle source must be a real directory",
        ));
    }
    Ok(root.to_path_buf())
}

fn read_boot_artifact(
    root: &Path,
    name: &str,
    expected: &str,
    label: &str,
    magic: &[u8],
) -> Result<Vec<u8>, InstallerError> {
    let bytes = read_regular(&root.join(name), MAX_BOOT_ARTIFACT_BYTES, false)?;
    if bytes.is_empty() || !bytes.starts_with(magic) {
        return Err(InstallerError::invalid(format!(
            "{label} boot artifact has an invalid executable header",
        )));
    }
    let actual = digest(&bytes);
    if actual != expected {
        return Err(InstallerError::invalid(format!(
            "{label} boot artifact digest differs from its manifest",
        )));
    }
    Ok(bytes)
}

fn activate_boot_bundle(
    target: &Path,
    plan: &InstallPlan,
    bundle: &BootBundle,
) -> Result<(), InstallerError> {
    let checkpoint = target_transaction_directory(target, &plan.transaction_id);
    validate_private_directory(&checkpoint)?;
    let mutation_path = checkpoint.join("boot-mutation.json");
    if fs::symlink_metadata(&mutation_path).is_ok() {
        return Err(InstallerError::invalid(
            "boot activation checkpoint already exists",
        ));
    }
    let backup_root = checkpoint.join("boot-backup");
    ensure_private_directory(&backup_root)?;
    let files: [(&str, &[u8]); 5] = [
        (TARGET_GRANITE_PATH, &bundle.granite),
        (TARGET_ARACH_PATH, &bundle.arach),
        (TARGET_PUSH_PATH, &bundle.push),
        (TARGET_CREST_PATH, &bundle.crest),
        (TARGET_MANIFEST_PATH, &bundle.manifest_bytes),
    ];
    let mut entries = Vec::with_capacity(files.len());
    for (index, (destination, _)) in files.iter().enumerate() {
        let destination_path = target_boot_path(target, destination)?;
        ensure_target_parent(&destination_path)?;
        let backup = match fs::symlink_metadata(&destination_path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => {
                return Err(InstallerError::invalid(format!(
                    "{}: {error}",
                    destination_path.display()
                )));
            }
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
                return Err(InstallerError::invalid(format!(
                    "{} is not a replaceable regular file",
                    destination_path.display()
                )));
            }
            Ok(_) => {
                let name = format!("file-{index}");
                let backup_path = backup_root.join(&name);
                let bytes = read_regular(&destination_path, MAX_BOOT_ARTIFACT_BYTES, false)?;
                create_private(&backup_path, &bytes)?;
                Some(format!("boot-backup/{name}"))
            }
        };
        entries.push(BootMutationEntry {
            destination: (*destination).into(),
            backup,
            installed: false,
        });
    }
    let mut record = BootMutationRecord {
        schema: BOOT_BUNDLE_SCHEMA,
        manifest_sha256: plan.boot_bundle_sha256.clone(),
        complete: false,
        entries,
    };
    create_private(&mutation_path, &canonical_json(&record)?)?;
    for (index, (_, bytes)) in files.iter().enumerate() {
        let destination_path = target_boot_path(target, &record.entries[index].destination)?;
        atomic_target_file(&destination_path, bytes)?;
        record.entries[index].installed = true;
        rewrite_private(&mutation_path, &canonical_json(&record)?)?;
    }
    record.complete = true;
    rewrite_private(&mutation_path, &canonical_json(&record)?)?;
    Ok(())
}

fn verify_installed_boot_bundle(target: &Path, plan: &InstallPlan) -> Result<(), InstallerError> {
    let manifest_path = target_boot_path(target, TARGET_MANIFEST_PATH)?;
    let manifest_bytes = read_regular(&manifest_path, DOCUMENT_LIMIT, false)?;
    if digest(&manifest_bytes) != plan.boot_bundle_sha256 {
        return Err(InstallerError::invalid(
            "installed boot manifest differs from the install plan",
        ));
    }
    let manifest: BootBundleManifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|error| InstallerError::invalid(format!("installed boot manifest: {error}")))?;
    if manifest.schema != BOOT_BUNDLE_SCHEMA {
        return Err(InstallerError::invalid(
            "installed boot manifest has an unsupported schema",
        ));
    }
    verify_installed_artifact(
        target,
        TARGET_GRANITE_PATH,
        &manifest.granite_sha256,
        "Granite",
        b"MZ",
    )?;
    verify_installed_artifact(
        target,
        TARGET_ARACH_PATH,
        &manifest.arach_sha256,
        "Arach",
        b"\x7fELF",
    )?;
    verify_installed_artifact(
        target,
        TARGET_PUSH_PATH,
        &manifest.push_sha256,
        "Push",
        b"\x7fELF",
    )?;
    verify_installed_artifact(
        target,
        TARGET_CREST_PATH,
        &manifest.crest_sha256,
        "Crest",
        b"\x7fELF",
    )?;
    Ok(())
}

fn verify_installed_artifact(
    target: &Path,
    relative: &str,
    expected: &str,
    label: &str,
    magic: &[u8],
) -> Result<(), InstallerError> {
    let bytes = read_regular(
        &target_boot_path(target, relative)?,
        MAX_BOOT_ARTIFACT_BYTES,
        false,
    )?;
    if !bytes.starts_with(magic) || digest(&bytes) != expected {
        return Err(InstallerError::invalid(format!(
            "installed {label} artifact failed digest or header verification",
        )));
    }
    Ok(())
}

fn rollback_boot_bundle(target: &Path, plan: &InstallPlan) -> Result<(), InstallerError> {
    let checkpoint = target_transaction_directory(target, &plan.transaction_id);
    let mutation_path = checkpoint.join("boot-mutation.json");
    let metadata = match fs::symlink_metadata(&mutation_path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(InstallerError::invalid(format!(
                "{}: {error}",
                mutation_path.display()
            )));
        }
        Ok(metadata) => metadata,
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(InstallerError::invalid(
            "boot activation checkpoint is not a regular file",
        ));
    }
    let record: BootMutationRecord = read_private_json(&mutation_path)?;
    if record.schema != BOOT_BUNDLE_SCHEMA
        || record.manifest_sha256 != plan.boot_bundle_sha256
        || record.entries.iter().any(|entry| {
            !is_boot_destination(&entry.destination)
                || entry
                    .backup
                    .as_deref()
                    .is_some_and(|path| !path.starts_with("boot-backup/"))
        })
    {
        return Err(InstallerError::invalid(
            "boot activation checkpoint does not match the install plan",
        ));
    }
    for entry in record.entries.iter().rev().filter(|entry| entry.installed) {
        let destination = target_boot_path(target, &entry.destination)?;
        if let Some(backup) = entry.backup.as_deref() {
            let backup_path = checkpoint.join(backup);
            let bytes = read_regular(&backup_path, MAX_BOOT_ARTIFACT_BYTES, true)?;
            atomic_target_file(&destination, &bytes)?;
        } else {
            remove_target_file(&destination)?;
        }
    }
    fs::remove_file(&mutation_path).map_err(|error| {
        InstallerError::invalid(format!("{}: {error}", mutation_path.display()))
    })?;
    sync_parent(&checkpoint)?;
    Ok(())
}

fn is_boot_destination(path: &str) -> bool {
    matches!(
        path,
        TARGET_GRANITE_PATH
            | TARGET_ARACH_PATH
            | TARGET_PUSH_PATH
            | TARGET_CREST_PATH
            | TARGET_MANIFEST_PATH
    )
}

fn target_boot_path(target: &Path, relative: &str) -> Result<PathBuf, InstallerError> {
    if !is_boot_destination(relative) {
        return Err(InstallerError::invalid(
            "boot destination is not allow-listed",
        ));
    }
    let path = target.join(relative);
    let mut current = target.to_path_buf();
    let relative_path = Path::new(relative);
    for component in relative_path.components() {
        let std::path::Component::Normal(name) = component else {
            return Err(InstallerError::invalid("boot destination is not relative"));
        };
        current.push(name);
        if current == path {
            break;
        }
        if let Ok(metadata) = fs::symlink_metadata(&current) {
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(InstallerError::invalid(format!(
                    "{} is not a real boot directory",
                    current.display()
                )));
            }
        }
    }
    Ok(path)
}

fn ensure_target_parent(path: &Path) -> Result<(), InstallerError> {
    let parent = path
        .parent()
        .ok_or_else(|| InstallerError::invalid("boot destination has no parent"))?;
    let mut missing = Vec::new();
    let mut current = parent.to_path_buf();
    while !current.exists() {
        missing.push(current.clone());
        current = current
            .parent()
            .ok_or_else(|| InstallerError::invalid("boot parent has no root"))?
            .to_path_buf();
    }
    let metadata = fs::symlink_metadata(&current)
        .map_err(|error| InstallerError::invalid(format!("{}: {error}", current.display())))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(InstallerError::invalid(
            "boot parent is not a real directory",
        ));
    }
    for directory in missing.into_iter().rev() {
        fs::create_dir(&directory).map_err(|error| {
            InstallerError::invalid(format!("{}: {error}", directory.display()))
        })?;
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o755)).map_err(|error| {
            InstallerError::invalid(format!("{}: {error}", directory.display()))
        })?;
        sync_parent(&directory)?;
    }
    Ok(())
}

fn atomic_target_file(path: &Path, bytes: &[u8]) -> Result<(), InstallerError> {
    let parent = path
        .parent()
        .ok_or_else(|| InstallerError::invalid("target file has no parent"))?;
    ensure_target_parent(path)?;
    let serial = TEMPORARY_SERIAL.fetch_add(1, Ordering::Relaxed);
    let temporary = parent.join(format!(".arach-boot-{}-{serial}.tmp", std::process::id()));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .custom_flags(libc::O_NOFOLLOW)
            .mode(0o644)
            .open(&temporary)
            .map_err(|error| {
                InstallerError::invalid(format!("{}: {error}", temporary.display()))
            })?;
        file.write_all(bytes)
            .and_then(|()| file.sync_all())
            .map_err(|error| {
                InstallerError::invalid(format!("{}: {error}", temporary.display()))
            })?;
        fs::rename(&temporary, path)
            .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
        sync_parent(parent)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn remove_target_file(path: &Path) -> Result<(), InstallerError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(InstallerError::invalid(format!(
            "{}: {error}",
            path.display()
        ))),
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
            Err(InstallerError::invalid(format!(
                "{} is not a removable regular file",
                path.display()
            )))
        }
        Ok(_) => {
            fs::remove_file(path)
                .map_err(|error| InstallerError::invalid(format!("{}: {error}", path.display())))?;
            if let Some(parent) = path.parent() {
                sync_parent(parent)?;
            }
            Ok(())
        }
    }
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
        if !matches!(
            flag,
            "state"
                | "plan"
                | "journal"
                | "target"
                | "generation"
                | "boot-bundle"
                | "hardware-plan"
                | "hardware-profiles"
                | "hardware-keyring"
                | "hardware-catalog-lock"
                | "hardware-binary-index"
                | "hardware-binary-signature"
                | "hardware-work"
                | "hardware-artifacts"
        ) {
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
        || !valid_digest(&plan.boot_bundle_sha256)
        || plan
            .hardware_plan_sha256
            .as_deref()
            .is_some_and(|digest| !valid_digest(digest))
        || journal.intended_corinth_generation != plan.generation_sha256
        || (plan.operations != operations_for(false) && plan.operations != operations_for(true))
        || (plan.hardware_plan_sha256.is_some()
            && !plan
                .operations
                .contains(&InstallOperation::HardwareProvision))
        || (plan.hardware_plan_sha256.is_none()
            && plan
                .operations
                .contains(&InstallOperation::HardwareProvision))
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
    let boot_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "boot-bundle")
        .count();
    let rollback_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "corinth-generation:rolled-back")
        .count();
    let boot_rollback_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "boot-bundle:rolled-back")
        .count();
    let hardware_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "hardware-provisioning")
        .count();
    let hardware_rollback_mutations = journal
        .mutations
        .iter()
        .filter(|mutation| mutation.as_str() == "hardware-provisioning:rolled-back")
        .count();
    let coherent_transition = match journal.status {
        JournalStatus::Prepared => {
            journal.target.is_none()
                && journal.previous_corinth_generation.is_none()
                && !journal.corinth_published
                && journal.hardware_packages.is_empty()
                && journal.mutations.is_empty()
        }
        JournalStatus::Applying => {
            journal.target.is_some()
                && !journal.corinth_published
                && hardware_mutations <= 1
                && hardware_rollback_mutations == 0
                && journal
                    .hardware_packages
                    .iter()
                    .all(|package| valid_package_name(package))
        }
        JournalStatus::CorinthPublished
        | JournalStatus::ApplyFailed
        | JournalStatus::Applied
        | JournalStatus::Verified => {
            journal.target.is_some()
                && journal.corinth_published
                && published_mutations == 1
                && rollback_mutations == 0
                && boot_mutations <= 1
                && boot_rollback_mutations == 0
                && hardware_mutations <= 1
                && hardware_rollback_mutations == 0
                && journal
                    .hardware_packages
                    .iter()
                    .all(|package| valid_package_name(package))
        }
        JournalStatus::RolledBack => {
            journal.target.is_some()
                && !journal.corinth_published
                && rollback_mutations == 1
                && boot_rollback_mutations == boot_mutations
                && published_mutations <= 1
                && hardware_rollback_mutations == hardware_mutations
                && journal
                    .hardware_packages
                    .iter()
                    .all(|package| valid_package_name(package))
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
                "corinth-generation"
                    | "corinth-generation:rolled-back"
                    | "boot-bundle"
                    | "boot-bundle:rolled-back"
                    | "hardware-provisioning"
                    | "hardware-provisioning:rolled-back"
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

fn staged_hardware_plan_path(plan_path: &Path) -> Result<PathBuf, InstallerError> {
    plan_path
        .parent()
        .map(|parent| parent.join("hardware-plan.toml"))
        .ok_or_else(|| InstallerError::invalid("plan path has no parent"))
}

fn operations_for(has_hardware_plan: bool) -> Vec<InstallOperation> {
    let mut operations = vec![InstallOperation::CorinthInstall];
    if has_hardware_plan {
        operations.push(InstallOperation::HardwareProvision);
    }
    operations.extend([
        InstallOperation::GraniteActivate,
        InstallOperation::CosmicVerify,
    ]);
    operations
}

fn read_hardware_plan(path: &Path) -> Result<Vec<u8>, InstallerError> {
    let bytes = read_regular(path, DOCUMENT_LIMIT, false)?;
    let value: toml::Value = toml::from_slice(&bytes)
        .map_err(|error| InstallerError::invalid(format!("invalid hardware plan: {error}")))?;
    let schema = value
        .get("schema")
        .and_then(toml::Value::as_integer)
        .and_then(|value| u32::try_from(value).ok());
    let plan = value.get("plan").and_then(toml::Value::as_array);
    if schema != Some(1) || plan.is_none() {
        return Err(InstallerError::invalid(
            "hardware plan does not satisfy schema 1",
        ));
    }
    Ok(bytes)
}

fn validate_hardware_plan_file(path: &Path, expected: Option<&str>) -> Result<(), InstallerError> {
    let Some(expected) = expected else {
        return Ok(());
    };
    if !valid_digest(expected) {
        return Err(InstallerError::invalid(
            "hardware plan digest is not a SHA-256 value",
        ));
    }
    let bytes = read_hardware_plan(path)?;
    if digest(&bytes) != expected {
        return Err(InstallerError::invalid(
            "hardware plan differs from the immutable install plan",
        ));
    }
    Ok(())
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
    hardware_plan_bytes: Option<&[u8]>,
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
        if let Some(bytes) = hardware_plan_bytes {
            create_private(&temporary.join("hardware-plan.toml"), bytes)?;
        }
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
            validate_hardware_plan_file(
                &directory.join("hardware-plan.toml"),
                durable_plan.hardware_plan_sha256.as_deref(),
            )?;
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
    for name in [
        "plan.json",
        "generation.gen",
        "hardware-plan.toml",
        "journal.json",
    ] {
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

fn rollback_hardware(
    target: &Path,
    journal: &InstallJournal,
    provisioned: bool,
) -> Result<(), InstallerError> {
    if !provisioned || journal.hardware_packages.is_empty() {
        return Ok(());
    }
    let state =
        target_transaction_directory(target, &journal.transaction_id).join("hardware-state");
    let receipt_root = state.join("binary-installed");
    if !receipt_root.is_dir() {
        return Ok(());
    }
    let store = BinaryInstallStore::open(state, target.to_path_buf())
        .map_err(|error| InstallerError::invalid(format!("hardware rollback store: {error}")))?;
    for package in &journal.hardware_packages {
        let receipt = receipt_root.join(format!("{package}.toml"));
        if !receipt.is_file() {
            continue;
        }
        store
            .remove(package)
            .map_err(|error| InstallerError::invalid(format!("hardware rollback: {error}")))?;
    }
    Ok(())
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn valid_package_name(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-' || byte == b'_'
        })
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

    fn write_hardware_plan(root: &Path) -> PathBuf {
        let path = root.join("hardware.plan.toml");
        fs::write(&path, "schema = 1\n\nplan = []\n").unwrap();
        path
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

    fn write_boot_bundle(root: &Path) -> PathBuf {
        let bundle = root.join("boot-bundle");
        fs::create_dir(&bundle).unwrap();
        fs::set_permissions(&bundle, fs::Permissions::from_mode(0o700)).unwrap();
        let granite = b"MZ-granite-test";
        let arach = b"\x7fELF-arach-test";
        let push = b"\x7fELF-push-test";
        let crest = b"\x7fELF-crest-test";
        create_private(&bundle.join(GRANITE_ARTIFACT_NAME), granite).unwrap();
        create_private(&bundle.join(ARACH_ARTIFACT_NAME), arach).unwrap();
        create_private(&bundle.join(PUSH_ARTIFACT_NAME), push).unwrap();
        create_private(&bundle.join(CREST_ARTIFACT_NAME), crest).unwrap();
        let manifest = BootBundleManifest {
            schema: BOOT_BUNDLE_SCHEMA,
            granite_sha256: digest(granite),
            arach_sha256: digest(arach),
            push_sha256: digest(push),
            crest_sha256: digest(crest),
        };
        create_private(
            &bundle.join(BOOT_MANIFEST_NAME),
            &canonical_json(&manifest).unwrap(),
        )
        .unwrap();
        bundle
    }

    #[test]
    fn prepare_binds_plan_and_private_journal() {
        let root = TestRoot::new();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let boot_bundle = write_boot_bundle(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation, &boot_bundle).unwrap();
        let (_, loaded) = load_bound_documents(&plan, &journal).unwrap();
        assert_eq!(loaded.status, JournalStatus::Prepared);
        assert!(staged_generation_path(&plan).unwrap().is_file());
        assert_eq!(
            fs::metadata(journal).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn prepare_binds_the_signed_hardware_plan() {
        let root = TestRoot::new();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let boot_bundle = write_boot_bundle(&root.0);
        let hardware = write_hardware_plan(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare_with_hardware_plan(
            &state,
            &plan,
            &journal,
            &generation,
            &boot_bundle,
            &hardware,
        )
        .unwrap();
        let (loaded, _) = load_bound_documents(&plan, &journal).unwrap();
        assert!(loaded.hardware_plan_sha256.is_some());
        assert!(
            validate_hardware_plan_file(
                &staged_hardware_plan_path(&plan).unwrap(),
                loaded.hardware_plan_sha256.as_deref()
            )
            .is_ok()
        );
        assert!(
            loaded
                .operations
                .contains(&InstallOperation::HardwareProvision)
        );
    }

    #[test]
    fn secrets_are_rejected_as_unknown_state_fields() {
        let root = TestRoot::new();
        let state = write_state(&root.0, ",\"password\":\"never\"");
        let generation = write_generation(&root.0);
        let boot_bundle = write_boot_bundle(&root.0);
        let error = prepare(
            &state,
            &root.0.join("plan.json"),
            &root.0.join("journal.json"),
            &generation,
            &boot_bundle,
        )
        .unwrap_err();
        assert!(error.message.contains("unknown field"));
    }

    #[test]
    fn production_apply_activates_and_can_roll_back() {
        let root = TestRoot::new();
        let target = root.0.join("target");
        fs::create_dir_all(target.join("var/lib")).unwrap();
        let state = write_state(&root.0, "");
        let generation = write_generation(&root.0);
        let boot_bundle = write_boot_bundle(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation, &boot_bundle).unwrap();
        apply(&plan, &journal, &target, &boot_bundle).unwrap();
        verify(&plan, &journal, &target).unwrap();
        let store = FilesystemGenerationStore::open(&target.join("var/lib/corinth")).unwrap();
        assert!(store.active().unwrap().is_some());
        assert!(target.join(TARGET_GRANITE_PATH).is_file());
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
        let boot_bundle = write_boot_bundle(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &generation, &boot_bundle).unwrap();

        let transaction = target_transaction_directory(&target, "0123456789abcdef0123456789abcdef");
        ensure_private_directory(transaction.parent().unwrap().parent().unwrap()).unwrap();
        ensure_private_directory(transaction.parent().unwrap()).unwrap();
        ensure_private_directory(&transaction).unwrap();

        let error = apply(&plan, &journal, &target, &boot_bundle).unwrap_err();
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
        let boot_bundle = write_boot_bundle(&root.0);
        let plan = root.0.join("plan.json");
        let journal = root.0.join("journal.json");
        prepare(&state, &plan, &journal, &child, &boot_bundle).unwrap();
        apply(&plan, &journal, &target, &boot_bundle).unwrap();
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
        let boot_bundle = write_boot_bundle(&root.0);
        let plan_path = root.0.join("plan.json");
        let journal_path = root.0.join("journal.json");
        prepare(&state, &plan_path, &journal_path, &generation, &boot_bundle).unwrap();

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
            checkpoint_transaction(&target, &plan, &journal, &generation_bytes, None).unwrap();
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
