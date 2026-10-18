use crate::model::{Record, hash};
use anyhow::{Result, ensure};
use rusqlite::Connection;
use serde::{Serialize, de::DeserializeOwned};
use std::{
    fs,
    io::{BufRead, Write},
    path::{Path, PathBuf},
};

pub fn home() -> PathBuf {
    std::env::var_os("BKD_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default())
                .join(".local/share/bookmarkdrop")
        })
}
/// Public site shown wherever bkd asks you to confirm publication.
/// Publication itself goes to BKD_DATABASE_URL; this only names where that feed appears.
pub const DEFAULT_PUBLIC_SITE: &str = "rsnair.tech";
pub fn public_site() -> String {
    site_or_default(std::env::var("BKD_PUBLIC_SITE").ok())
}
fn site_or_default(value: Option<String>) -> String {
    value
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| DEFAULT_PUBLIC_SITE.to_string())
}
#[cfg(test)]
mod public_site_tests {
    #[test]
    fn public_site_defaults_and_overrides() {
        assert_eq!(super::site_or_default(None), "rsnair.tech");
        assert_eq!(super::site_or_default(Some("  ".into())), "rsnair.tech");
        assert_eq!(super::site_or_default(Some(" example.org ".into())), "example.org");
    }
}
pub fn prepare(path: &Path) -> Result<()> {
    ensure!(!path.is_symlink(), "State directory cannot be a symlink");
    fs::create_dir_all(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}
pub fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    ensure!(!parent.is_symlink(), "Output directory cannot be a symlink");
    if !parent.exists() {
        prepare(parent)?;
    }
    let mut file = tempfile::NamedTempFile::new_in(parent)?;
    serde_json::to_writer(&mut file, value)?;
    file.write_all(b"\n")?;
    file.as_file().sync_all()?;
    file.persist(path).map_err(|e| e.error)?;
    fs::File::open(parent)?.sync_all()?;
    Ok(())
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn review_output_preserves_existing_directory_permissions() {
        let tmp = tempfile::tempdir().unwrap();
        fs::set_permissions(tmp.path(), fs::Permissions::from_mode(0o755)).unwrap();
        let file = tmp.path().join("review.json");
        write_json(&file, &serde_json::json!({"review":true})).unwrap();
        assert_eq!(
            tmp.path().metadata().unwrap().permissions().mode() & 0o777,
            0o755
        );
        assert_eq!(file.metadata().unwrap().permissions().mode() & 0o777, 0o600);
    }
}
pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    Ok(serde_json::from_reader(fs::File::open(path)?)?)
}
pub fn db(home: &Path) -> Result<Connection> {
    prepare(home)?;
    let path = home.join("index.sqlite");
    ensure!(!path.is_symlink(), "Index must not be a symlink");
    let db = Connection::open(path)?;
    db.busy_timeout(std::time::Duration::from_secs(5))?;
    db.execute_batch("PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
      INSERT OR IGNORE INTO meta VALUES('revision',0);
      CREATE TABLE IF NOT EXISTS records(origin TEXT PRIMARY KEY, provider TEXT NOT NULL, payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS vectors(hash TEXT NOT NULL,spec TEXT NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(hash,spec));
      CREATE TABLE IF NOT EXISTS sources(provider TEXT PRIMARY KEY,account TEXT NOT NULL,refreshed_at INTEGER NOT NULL,count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS relations(a TEXT NOT NULL,b TEXT NOT NULL,kind TEXT NOT NULL,suppressed INTEGER NOT NULL,PRIMARY KEY(a,b,kind));")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(home.join("index.sqlite"), fs::Permissions::from_mode(0o600))?;
    }
    Ok(db)
}
pub fn records(db: &Connection) -> Result<Vec<Record>> {
    let mut q = db.prepare("SELECT payload FROM records ORDER BY origin")?;
    let rows = q.query_map([], |r| r.get::<_, String>(0))?;
    rows.map(|raw| {
        let mut r: Record = serde_json::from_str(&raw?)?;
        r.validate()?;
        Ok(r)
    })
    .collect()
}
pub fn jsonl(reader: impl BufRead) -> Result<Vec<Record>> {
    let mut out = Vec::new();
    for (i, line) in reader.lines().enumerate() {
        let raw = line?;
        ensure!(raw.len() <= 65536, "JSONL line {} exceeds 64 KiB", i + 1);
        if raw.trim().is_empty() {
            continue;
        }
        let mut r: Record = serde_json::from_str(&raw)
            .map_err(|_| anyhow::anyhow!("Invalid JSONL record on line {}", i + 1))?;
        r.validate()?;
        out.push(r);
    }
    Ok(out)
}
fn credential_key(home: &Path, provider: &str, account: &str) -> Result<String> {
    Ok(format!(
        "{provider}:{}",
        hash(serde_json::to_vec(&(home.canonicalize()?, account))?)
    ))
}
pub fn account(home: &Path, provider: &str) -> Result<String> {
    let path = home.join("accounts.json");
    let map: serde_json::Value = if path.exists() {
        read_json(&path)?
    } else {
        serde_json::json!({})
    };
    Ok(map[provider].as_str().unwrap_or("default").into())
}
pub fn credential(home: &Path, provider: &str) -> Result<String> {
    let env = match provider {
        "instapaper" => "BKD_INSTAPAPER_TOKEN",
        "raindrop" => "BKD_RAINDROP_TOKEN",
        "neon" => "BKD_DATABASE_URL",
        _ => anyhow::bail!("Unsupported credential"),
    };
    if let Ok(v) = std::env::var(env) {
        ensure!(!v.trim().is_empty(), "Empty credential");
        return Ok(v);
    }
    ensure!(
        cfg!(target_os = "macos"),
        "No persistent keychain backend is configured on this platform; inject {env} explicitly"
    );
    keyring::Entry::new(
        "bookmarkdrop",
        &credential_key(home, provider, &account(home, provider)?)?,
    )?
    .get_password()
    .map_err(|_| anyhow::anyhow!("Missing {provider} credential; use bkd auth or {env}"))
}
pub fn auth(home: &Path, provider: &str, account: &str, secret: &str) -> Result<()> {
    ensure!(
        cfg!(target_os = "macos"),
        "Persistent keychain authentication is configured only on macOS; inject BKD_INSTAPAPER_TOKEN, BKD_RAINDROP_TOKEN or BKD_DATABASE_URL explicitly on this platform"
    );
    prepare(home)?;
    ensure!(
        crate::model::PROVIDERS.contains(&provider) && provider != "manual",
        "Unsupported provider"
    );
    ensure!(
        !account.is_empty() && crate::model::valid_text(account, 256) && !secret.trim().is_empty(),
        "Invalid account/credential"
    );
    keyring::Entry::new("bookmarkdrop", &credential_key(home, provider, account)?)?
        .set_password(secret)
        .map_err(|_| anyhow::anyhow!("OS credential store write failed"))?;
    let path = home.join("accounts.json");
    let mut map: serde_json::Value = if path.exists() {
        read_json(&path)?
    } else {
        serde_json::json!({})
    };
    map[provider] = account.into();
    write_json(&path, &map)
}
pub fn secret_stdin() -> Result<String> {
    use std::io::{self, IsTerminal, Read};
    if !io::stdin().is_terminal() {
        let mut secret = String::new();
        io::stdin().take(65537).read_to_string(&mut secret)?;
        ensure!(secret.len() <= 65536, "Credential input exceeds 64 KiB");
        return Ok(secret.trim().into());
    }
    struct Restore;
    impl Drop for Restore {
        fn drop(&mut self) {
            let _ = crossterm::terminal::disable_raw_mode();
            eprintln!();
        }
    }
    eprint!("Credential (hidden): ");
    io::stderr().flush()?;
    crossterm::terminal::enable_raw_mode()?;
    let _restore = Restore;
    let mut secret = String::new();
    loop {
        if let crossterm::event::Event::Key(key) = crossterm::event::read()? {
            use crossterm::event::{KeyCode, KeyModifiers};
            if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
                anyhow::bail!("Credential entry cancelled");
            }
            match key.code {
                KeyCode::Enter => break,
                KeyCode::Esc => anyhow::bail!("Credential entry cancelled"),
                KeyCode::Backspace => {
                    secret.pop();
                }
                KeyCode::Char(c) => {
                    ensure!(secret.len() < 65536, "Credential input exceeds 64 KiB");
                    secret.push(c);
                }
                _ => {}
            }
        }
    }
    Ok(secret.trim().into())
}
