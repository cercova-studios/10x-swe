use std::{fs, process::Command};

#[test]
fn kfx_rejects_stdout_before_acquisition() {
    let output = Command::new(env!("CARGO_BIN_EXE_distiller"))
        .args(["https://example.invalid", "--mode", "kfx", "--stdout"])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("writes a file"));
}

#[test]
fn kfx_preserves_existing_file_before_acquisition_or_cover_generation() {
    let work = tempfile::tempdir().unwrap();
    let target = work.path().join("keep.kfx");
    fs::write(&target, b"keep existing book").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_distiller"))
        .args(["https://example.invalid", "--mode", "kfx", "-o"])
        .arg(&target)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("already exists"));
    assert_eq!(fs::read(target).unwrap(), b"keep existing book");
}
