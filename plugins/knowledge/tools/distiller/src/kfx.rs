//! CLI-only adapter: EPUB extraction stays independent of the local KFX encoder.
use anyhow::{ensure, Context, Result};
use std::{path::PathBuf, process::Stdio, time::Duration};

pub struct Output {
    work: tempfile::TempDir,
    target: PathBuf,
}

impl Output {
    pub fn prepare(input: Option<&str>, output: Option<&str>) -> Result<Self> {
        let target = output.map(PathBuf::from).unwrap_or_else(|| {
            input
                .map(PathBuf::from)
                .filter(|path| path.is_file())
                .map(|path| path.with_extension("kfx"))
                .unwrap_or_else(|| PathBuf::from("webpage.kfx"))
        });
        ensure!(
            std::fs::symlink_metadata(&target)
                .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
            "KFX output already exists or cannot be inspected: {}",
            target.display()
        );
        ensure!(
            target
                .parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or_else(|| std::path::Path::new("."))
                .is_dir(),
            "KFX output directory does not exist"
        );
        let status = std::process::Command::new("epub-to-kfx")
            .arg("--check")
            .stdout(Stdio::null())
            .status()
            .context("KFX requires epub-to-kfx on PATH and its local Amazon converter")?;
        ensure!(
            status.success(),
            "KFX converter prerequisites are unavailable"
        );
        Ok(Self {
            work: tempfile::tempdir()?,
            target,
        })
    }

    pub fn epub(&self) -> PathBuf {
        self.work.path().join("article.epub")
    }

    pub async fn finish(self) -> Result<()> {
        let mut child = tokio::process::Command::new("epub-to-kfx")
            .arg(self.epub())
            .arg("-o")
            .arg(&self.target)
            .stdout(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .context("Start local KFX conversion")?;
        let status = tokio::time::timeout(Duration::from_secs(370), child.wait())
            .await
            .context("KFX conversion exceeded its total timeout")??;
        ensure!(
            status.success(),
            "KFX conversion failed; existing output was not overwritten"
        );
        eprintln!("Wrote output to {}", self.target.display());
        Ok(())
    }
}
