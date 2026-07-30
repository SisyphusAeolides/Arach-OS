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
            require_flags(&flags, &["generation", "journal", "plan", "state"])?;
            installer::prepare(
                required(&flags, "state")?,
                required(&flags, "plan")?,
                required(&flags, "journal")?,
                required(&flags, "generation")?,
            )
        }
        "apply" => {
            require_flags(&flags, &["journal", "plan", "target"])?;
            installer::apply(
                required(&flags, "plan")?,
                required(&flags, "journal")?,
                required(&flags, "target")?,
            )
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
