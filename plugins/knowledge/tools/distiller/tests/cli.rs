use std::io::Write;
use std::process::{Command, Stdio};

fn run(args: &[&str], input: &[u8]) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_distiller"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let _ = child.stdin.take().unwrap().write_all(input);
    child.wait_with_output().unwrap()
}

#[test]
fn stdin_extracts_without_network_and_preserves_source_identity() {
    use sha2::{Digest, Sha256};
    let html = br#"<article><h1>Stream fixture</h1><p>Original text remains available for exact citations.</p><a href="/evidence">Evidence</a><pre><code>let n = 970;
    n &gt;&gt; 52</code></pre></article>"#;
    let output = run(
        &[
            "--stdin",
            "--base-url",
            "https://example.invalid/raw?q=1#x",
            "--mode",
            "json",
        ],
        html,
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let record: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(record["schema"], "article-extraction/v1");
    assert_eq!(record["source"]["url"], "https://example.invalid/raw?q=1#x");
    assert_eq!(
        record["source"]["sha256"],
        format!("{:x}", Sha256::digest(html))
    );
    let md = record["document"]["markdown"].as_str().unwrap();
    assert!(md.contains("let n = 970;\n    n >> 52"));
    assert!(md.contains("https://example.invalid/evidence"));
    let markdown = run(
        &["--stdin", "--base-url", "https://example.invalid/raw"],
        html,
    );
    assert!(markdown.status.success());
    assert!(String::from_utf8(markdown.stdout)
        .unwrap()
        .contains("Original text"));
}

#[test]
fn invalid_streams_and_conflicting_modes_fail_without_output() {
    for (args, input) in [
        (vec!["--stdin"], b"<p>text</p>".as_slice()),
        (
            vec!["--stdin", "--base-url", "file:///tmp/source"],
            b"text".as_slice(),
        ),
        (
            vec!["--stdin", "--base-url", "https://user:pass@example.org"],
            b"text".as_slice(),
        ),
        (
            vec!["--stdin", "--base-url", "https://example.org", "--llm"],
            b"text".as_slice(),
        ),
        (
            vec![
                "https://example.org",
                "--stdin",
                "--base-url",
                "https://example.org",
            ],
            b"text".as_slice(),
        ),
        (
            vec!["--stdin", "--base-url", "https://example.org"],
            &[0xff],
        ),
        (
            vec!["--stdin", "--base-url", "https://example.org"],
            b"".as_slice(),
        ),
    ] {
        let output = run(&args, input);
        assert!(!output.status.success(), "{args:?}");
        assert!(output.stdout.is_empty(), "{args:?}");
    }
    let output = run(
        &["--stdin", "--base-url", "https://example.org"],
        &vec![b'x'; 5 * 1024 * 1024 + 1],
    );
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
}

#[test]
fn occupied_outputs_are_rejected_before_reading_input() {
    let dir = tempfile::tempdir().unwrap();
    for mode in ["markdown", "json"] {
        let target = dir.path().join(mode);
        std::fs::write(&target, b"retain original").unwrap();
        let output = run(
            &[
                "missing-source.html",
                "--mode",
                mode,
                "-o",
                target.to_str().unwrap(),
            ],
            b"",
        );
        assert_eq!(output.status.code(), Some(1));
        assert!(output.stdout.is_empty());
        assert!(String::from_utf8_lossy(&output.stderr).contains("Output already exists"));
        assert_eq!(std::fs::read(&target).unwrap(), b"retain original");
    }
    #[cfg(unix)]
    {
        let link = dir.path().join("broken-link");
        let missing = dir.path().join("missing-target");
        std::os::unix::fs::symlink(&missing, &link).unwrap();
        let output = run(&["missing-source.html", "-o", link.to_str().unwrap()], b"");
        assert_eq!(output.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&output.stderr).contains("Output already exists"));
        assert!(link.is_symlink());
        assert!(!missing.exists());
    }
}

#[test]
fn text_output_is_complete_and_retry_preserves_it() {
    let dir = tempfile::tempdir().unwrap();
    let html =
        b"<article><h1>Evidence</h1><p>Retain this original evidence for citations.</p></article>";
    for mode in ["markdown", "json"] {
        let target = dir.path().join(mode);
        let args = [
            "--stdin",
            "--base-url",
            "https://example.invalid/article",
            "--mode",
            mode,
            "-o",
            target.to_str().unwrap(),
        ];
        let first = run(&args, html);
        assert!(
            first.status.success(),
            "{}",
            String::from_utf8_lossy(&first.stderr)
        );
        assert!(first.stdout.is_empty());
        let original = std::fs::read(&target).unwrap();
        if mode == "json" {
            let record: serde_json::Value = serde_json::from_slice(&original).unwrap();
            assert_eq!(record["schema"], "article-extraction/v1");
        }
        let retry = run(&args, html);
        assert_eq!(retry.status.code(), Some(1));
        assert_eq!(std::fs::read(&target).unwrap(), original);
    }
    assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 2);
}
