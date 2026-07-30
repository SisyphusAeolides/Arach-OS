use arach_compose::validate_root;
use std::env;
use std::path::PathBuf;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut arguments = env::args_os().skip(1);
    if arguments.next().as_deref() != Some(std::ffi::OsStr::new("verify")) {
        return usage();
    }
    let mut root = PathBuf::from(".");
    while let Some(flag) = arguments.next() {
        if flag != "--root" {
            return usage();
        }
        let Some(value) = arguments.next() else {
            return usage();
        };
        root = PathBuf::from(value);
    }
    match validate_root(&root) {
        Ok(report) => {
            println!(
                "validated {} components, {} root filesystems, and {} installer assets",
                report.components, report.root_filesystems, report.installer_assets
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn usage() -> ExitCode {
    eprintln!("usage: arach-compose verify [--root PATH]");
    ExitCode::from(2)
}
