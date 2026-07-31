use arach_compose::installer;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

fn main() {
    if let Err(error) = run(std::env::args().skip(1).collect()) {
        eprintln!("arach-install: {error}");
        std::process::exit(if error.unavailable { 69 } else { 1 });
    }
}

fn run(arguments: Vec<String>) -> Result<(), installer::InstallerError> {
    let (command, rest) = arguments
        .split_first()
        .ok_or_else(|| invalid("expected prepare, apply, verify, rollback, or recover"))?;
    let flags = installer::parse_flag_arguments(rest)?;
    match command.as_str() {
        "prepare" => {
            require_flags(
                &flags,
                &[
                    "boot-bundle",
                    "generation",
                    "hardware-plan",
                    "journal",
                    "plan",
                    "state",
                ],
            )?;
            installer::prepare_with_hardware_plan(
                required(&flags, "state")?,
                required(&flags, "plan")?,
                required(&flags, "journal")?,
                required(&flags, "generation")?,
                required(&flags, "boot-bundle")?,
                required(&flags, "hardware-plan")?,
            )
        }
        "apply" => {
            let hardware = [
                "hardware-profiles",
                "hardware-keyring",
                "hardware-catalog-lock",
                "hardware-binary-index",
                "hardware-binary-signature",
                "hardware-work",
                "hardware-artifacts",
            ];
            let has_hardware_flag = hardware.iter().any(|name| flags.contains_key(*name));
            if has_hardware_flag {
                require_flags(
                    &flags,
                    &[
                        "boot-bundle",
                        "journal",
                        "plan",
                        "target",
                        "hardware-profiles",
                        "hardware-keyring",
                        "hardware-catalog-lock",
                        "hardware-binary-index",
                        "hardware-binary-signature",
                        "hardware-work",
                        "hardware-artifacts",
                    ],
                )?;
                installer::apply_with_hardware(
                    required(&flags, "plan")?,
                    required(&flags, "journal")?,
                    required(&flags, "target")?,
                    required(&flags, "boot-bundle")?,
                    installer::HardwareApplyInputs {
                        profiles: required(&flags, "hardware-profiles")?.to_path_buf(),
                        keyring: required(&flags, "hardware-keyring")?.to_path_buf(),
                        catalog_lock: required(&flags, "hardware-catalog-lock")?.to_path_buf(),
                        binary_index: required(&flags, "hardware-binary-index")?.to_path_buf(),
                        binary_signature: required(&flags, "hardware-binary-signature")?
                            .to_path_buf(),
                        work: required(&flags, "hardware-work")?.to_path_buf(),
                        artifacts: required(&flags, "hardware-artifacts")?.to_path_buf(),
                    },
                )
            } else {
                require_flags(&flags, &["boot-bundle", "journal", "plan", "target"])?;
                installer::apply(
                    required(&flags, "plan")?,
                    required(&flags, "journal")?,
                    required(&flags, "target")?,
                    required(&flags, "boot-bundle")?,
                )
            }
        }
        "verify" => {
            require_flags(&flags, &["journal", "plan", "target"])?;
            installer::verify(
                required(&flags, "plan")?,
                required(&flags, "journal")?,
                required(&flags, "target")?,
            )
        }
        "rollback" => {
            require_flags(&flags, &["journal", "plan", "target"])?;
            installer::rollback(
                required(&flags, "plan")?,
                required(&flags, "journal")?,
                required(&flags, "target")?,
            )
        }
        "recover" => {
            require_flags(&flags, &["target"])?;
            installer::recover(required(&flags, "target")?).map(|_| ())
        }
        _ => Err(invalid(format!("unknown command {command}"))),
    }
}

fn require_flags(
    flags: &BTreeMap<String, PathBuf>,
    expected: &[&str],
) -> Result<(), installer::InstallerError> {
    if flags.len() == expected.len() && expected.iter().all(|name| flags.contains_key(*name)) {
        Ok(())
    } else {
        Err(invalid(
            "command flags differ from the transaction contract",
        ))
    }
}

fn required<'a>(
    flags: &'a BTreeMap<String, PathBuf>,
    name: &str,
) -> Result<&'a Path, installer::InstallerError> {
    flags
        .get(name)
        .map(PathBuf::as_path)
        .ok_or_else(|| invalid(format!("missing --{name}")))
}

fn invalid(message: impl Into<String>) -> installer::InstallerError {
    installer::InstallerError {
        message: message.into(),
        unavailable: false,
    }
}
