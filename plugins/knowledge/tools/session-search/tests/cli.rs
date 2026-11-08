use std::process::Command;

#[test]
fn public_cli_contract() {
    let python = std::env::var("PYTHON").unwrap_or_else(|_| "python3".into());
    for script in ["check.py", "adapters.py"] {
        let output = Command::new(&python)
            .arg(format!("{}/tests/{script}", env!("CARGO_MANIFEST_DIR")))
            .arg(env!("CARGO_BIN_EXE_session-search"))
            .output()
            .expect("Python 3 is required only for the isolated CLI regression fixtures");
        assert!(
            output.status.success(),
            "{script}: {}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }
}
