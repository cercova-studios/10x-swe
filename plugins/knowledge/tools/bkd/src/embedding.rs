use anyhow::{Result, ensure};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
};
pub const MODEL_SHA: &str = "c5d2302edc429f679642433b9f96dd217799727a06e675abef3b40a79f5e1589";
pub const SPEC: &str = "bge-small-en-v1.5:cls:384:l2:window400-mean:rust-v1";
pub const DIM: usize = 384;
pub fn path() -> PathBuf {
    std::env::var_os("BKD_MODEL_PATH").map(PathBuf::from).unwrap_or_else(||PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".cache/huggingface/hub/models--unsloth--bge-small-en-v1.5-GGUF/snapshots/395309658a295cc893b3aa279136ce84f472fc62/bge-small-en-v1.5-f16.gguf"))
}
pub fn windows(text: &str) -> Vec<String> {
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let text = if text.is_empty() { "bookmark" } else { &text };
    let mut chunks = Vec::new();
    let mut chunk = String::new();
    for c in text.chars() {
        if chunk.len() + c.len_utf8() > 400 {
            chunks.push(chunk);
            chunk = String::new();
        }
        chunk.push(c);
    }
    if !chunk.is_empty() {
        chunks.push(chunk);
    }
    chunks
}
pub fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(a, b)| a * b).sum()
}
pub fn normalize(v: &mut [f32]) -> Result<()> {
    let norm = dot(v, v).sqrt();
    ensure!(
        v.len() == DIM && v.iter().all(|x| x.is_finite()) && norm > 0.001,
        "Invalid embedding vector"
    );
    for x in v {
        *x /= norm;
    }
    Ok(())
}
pub struct Embedder {
    model: PathBuf,
}
impl Embedder {
    pub fn new() -> Result<Self> {
        let model = path();
        let mut file = File::open(&model)
            .map_err(|_| anyhow::anyhow!("Local BGE model missing; see bkd model"))?;
        let mut sha = Sha256::new();
        let mut bytes = [0u8; 65536];
        loop {
            let n = file.read(&mut bytes)?;
            if n == 0 {
                break;
            }
            sha.update(&bytes[..n]);
        }
        ensure!(
            format!("{:x}", sha.finalize()) == MODEL_SHA,
            "Pinned BGE model hash mismatch"
        );
        Ok(Self { model })
    }
    pub fn embed(&self, texts: &[String], query: bool) -> Result<Vec<Vec<f32>>> {
        let mut result = vec![vec![0.; DIM]; texts.len()];
        let mut counts = vec![0usize; texts.len()];
        let temp = tempfile::tempdir()?;
        let mut batch = Vec::new();
        for (index, text) in texts.iter().enumerate() {
            for chunk in windows(text) {
                batch.push((
                    index,
                    if query {
                        format!("Represent this sentence for searching relevant passages: {chunk}")
                    } else {
                        chunk
                    },
                ));
                if batch.len() == 8 {
                    self.batch(&temp, &batch, &mut result, &mut counts)?;
                    batch.clear();
                }
            }
        }
        if !batch.is_empty() {
            self.batch(&temp, &batch, &mut result, &mut counts)?;
        }
        for vector in &mut result {
            normalize(vector)?;
        }
        Ok(result)
    }
    fn batch(
        &self,
        temp: &tempfile::TempDir,
        items: &[(usize, String)],
        vectors: &mut [Vec<f32>],
        counts: &mut [usize],
    ) -> Result<()> {
        let input = temp.path().join("input");
        let output = temp.path().join("output");
        File::create(&input)?.write_all(
            items
                .iter()
                .map(|(_, s)| s.as_str())
                .collect::<Vec<_>>()
                .join("\n")
                .as_bytes(),
        )?;
        let mut child = Command::new(
            std::env::var_os("BKD_EMBED_BINARY").unwrap_or_else(|| "llama-embedding".into()),
        )
        .arg("-m")
        .arg(&self.model)
        .arg("-f")
        .arg(&input)
        .args([
            "--pooling",
            "cls",
            "--embd-normalize",
            "2",
            "--embd-output-format",
            "json",
            "--device",
            "none",
            "--offline",
            "--no-escape",
            "-ngl",
            "0",
            "-c",
            "2048",
            "-b",
            "2048",
            "-ub",
            "2048",
            "-t",
            "4",
        ])
        .stdout(File::create(&output)?)
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| anyhow::anyhow!("llama-embedding not available"))?;
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(120);
        let status = loop {
            if let Some(status) = child.try_wait()? {
                break status;
            }
            if std::time::Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                anyhow::bail!("Local embedding timed out; previous index preserved");
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        };
        ensure!(
            status.success(),
            "Local embedding failed; previous index preserved"
        );
        let data: serde_json::Value = serde_json::from_reader(File::open(output)?)?;
        let rows = data["data"]
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("Invalid embedding response"))?;
        ensure!(rows.len() == items.len(), "Embedding count mismatch");
        for (i, ((index, _), row)) in items.iter().zip(rows).enumerate() {
            ensure!(
                row["index"].as_u64() == Some(i as u64),
                "Embedding order mismatch"
            );
            let values = row["embedding"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("Invalid embedding"))?;
            ensure!(values.len() == DIM, "Embedding dimension mismatch");
            for (dest, value) in vectors[*index].iter_mut().zip(values) {
                let n = value
                    .as_f64()
                    .ok_or_else(|| anyhow::anyhow!("Invalid embedding number"))?
                    as f32;
                ensure!(n.is_finite(), "Nonfinite embedding");
                *dest += n;
            }
            counts[*index] += 1;
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn utf8_windows_preserve_all_text() {
        let input = "研究".repeat(800);
        let w = windows(&input);
        assert!(w.iter().all(|s| s.len() <= 400));
        assert_eq!(w.concat(), input);
    }
}
