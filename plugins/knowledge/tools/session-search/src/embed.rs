use anyhow::Result;
use blake2::{
    Blake2bVar,
    digest::{Update, VariableOutput},
};
use regex::Regex;
use std::sync::LazyLock;
pub const DIM: usize = 384;
pub fn name() -> Result<&'static str> {
    match std::env::var("SESSION_SEARCH_EMBEDDER")
        .unwrap_or_else(|_| "hash".into())
        .trim()
        .to_lowercase()
        .as_str()
    {
        "fastembed" | "bge" | "neural" => {
            #[cfg(feature = "neural")]
            {
                Ok("fastembed:bge-small-en-v1.5")
            }
            #[cfg(not(feature = "neural"))]
            {
                anyhow::bail!(
                    "fastembed unavailable: build session-search with --features neural and configure an existing local model; vectors were not changed"
                )
            }
        }
        _ => Ok("hash-ngram"),
    }
}
pub fn embed(text: &str) -> Result<Vec<u8>> {
    let model = name()?;
    #[cfg(feature = "neural")]
    if model != "hash-ngram" {
        return neural(text);
    }
    let _ = model;
    static WORDS: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[a-z0-9_]+").unwrap());
    static WHITESPACE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());
    let lower = text.to_lowercase();
    let compact = WHITESPACE.replace_all(&lower, " ");
    let chars = compact.chars().collect::<Vec<_>>();
    let grams = chars.windows(3).map(|v| v.iter().collect::<String>());
    let mut vec = [0f64; DIM];
    for token in WORDS
        .find_iter(&lower)
        .map(|m| m.as_str().to_owned())
        .chain(grams)
    {
        let mut hash = Blake2bVar::new(8).unwrap();
        hash.update(token.as_bytes());
        let mut digest = [0u8; 8];
        hash.finalize_variable(&mut digest).unwrap();
        vec[u16::from_le_bytes([digest[0], digest[1]]) as usize % DIM] +=
            if digest[2] & 1 != 0 { 1.0 } else { -1.0 };
    }
    let norm = vec.iter().map(|x| x * x).sum::<f64>().sqrt();
    let norm = if norm == 0.0 { 1.0 } else { norm };
    Ok(vec
        .into_iter()
        .flat_map(|n| ((n / norm) as f32).to_le_bytes())
        .collect())
}

#[cfg(feature = "neural")]
fn neural(text: &str) -> Result<Vec<u8>> {
    use anyhow::{Context, ensure};
    use fastembed::{
        InitOptionsUserDefined, Pooling, TextEmbedding, TokenizerFiles, UserDefinedEmbeddingModel,
    };
    use std::{cell::RefCell, io::Read, path::PathBuf};
    thread_local! {static MODEL: RefCell<Option<TextEmbedding>>=const {RefCell::new(None)};}
    MODEL.with(|cell| {
        let mut cached=cell.borrow_mut();
        if cached.is_none() {
            let root=PathBuf::from(std::env::var_os("SESSION_SEARCH_MODEL_DIR").context("Set SESSION_SEARCH_MODEL_DIR to an existing BGE-small-en-v1.5 ONNX/tokenizer directory; no models are downloaded")?);
            let read=|name:&str,max:u64|->Result<Vec<u8>> {let mut raw=Vec::new();std::fs::File::open(root.join(name)).with_context(||format!("Missing local model resource {name}"))?.take(max+1).read_to_end(&mut raw)?;ensure!(raw.len()as u64<=max,"Local model resource exceeds byte budget");Ok(raw)};
            let tokenizer=TokenizerFiles{tokenizer_file:read("tokenizer.json",8*1024*1024)?,config_file:read("config.json",8*1024*1024)?,special_tokens_map_file:read("special_tokens_map.json",8*1024*1024)?,tokenizer_config_file:read("tokenizer_config.json",8*1024*1024)?};
            let model=UserDefinedEmbeddingModel::new(read("model.onnx",512*1024*1024)?,tokenizer).with_pooling(Pooling::Cls);
            *cached=Some(TextEmbedding::try_new_from_user_defined(model,InitOptionsUserDefined::new().with_max_length(512).with_intra_threads(1)).context("Initialize local FastEmbed/ONNX runtime; configure ORT_DYLIB_PATH for the installed runtime")?);
        }
        let vector=cached.as_mut().unwrap().embed([text],None)?.pop().context("Local model returned no embedding")?;
        ensure!(vector.len()==DIM&&vector.iter().all(|n|n.is_finite()),"Expected a finite 384-dimensional BGE embedding");
        Ok(vector.into_iter().flat_map(f32::to_le_bytes).collect())
    })
}
pub fn cosine(a: &[u8], b: &[u8]) -> f64 {
    if a.len() != b.len() || !a.len().is_multiple_of(4) {
        return 0.0;
    }
    a.as_chunks::<4>()
        .0
        .iter()
        .zip(b.as_chunks::<4>().0.iter())
        .map(|(a, b)| f32::from_le_bytes(*a) as f64 * f32::from_le_bytes(*b) as f64)
        .sum()
}
