use anyhow::{Context, Result, bail, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::fs::PermissionsExt;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
};

pub const MAX_FILES: usize = 256;
pub const MAX_BYTES: u64 = 8 * 1024 * 1024;
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn read_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>> {
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    ensure!(file.metadata()?.is_file(), "not a regular file");
    let mut bytes = Vec::new();
    file.take(maximum + 1).read_to_end(&mut bytes)?;
    ensure!(bytes.len() as u64 <= maximum, "file exceeds size limit");
    Ok(bytes)
}

pub fn safe_relative(path: &str) -> Result<PathBuf> {
    ensure!(
        !path.is_empty()
            && path.len() <= 1024
            && !path.contains('\\')
            && !path.chars().any(char::is_control),
        "invalid resource path"
    );
    let p = PathBuf::from(path);
    ensure!(
        p.components().all(|c| matches!(c, Component::Normal(_))),
        "unsafe resource path"
    );
    ensure!(
        !path
            .split('/')
            .any(|s| s.is_empty() || s == "." || s == ".."),
        "unsafe resource path"
    );
    Ok(p)
}

fn inventory(
    folder: &Path,
    base: &Path,
    files: &mut BTreeMap<String, String>,
    total: &mut u64,
    directories: &mut usize,
    depth: usize,
) -> Result<()> {
    *directories += 1;
    ensure!(
        *directories <= 2048 && depth <= 16,
        "bundle directory/depth limits exceeded"
    );
    let mut entries = fs::read_dir(folder)?
        .take(4097)
        .collect::<std::io::Result<Vec<_>>>()?;
    ensure!(entries.len() <= 4096, "directory entry limit exceeded");
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        ensure!(
            !metadata.file_type().is_symlink(),
            "symlink in quarantined bundle"
        );
        if metadata.is_dir() {
            inventory(&path, base, files, total, directories, depth + 1)?;
        } else {
            ensure!(metadata.is_file(), "special file in bundle");
            let relative = path
                .strip_prefix(base)?
                .to_str()
                .context("non-UTF8 filename")?
                .to_owned();
            safe_relative(&relative)?;
            ensure!(
                !crate::registry::secret_path(&relative),
                "credential-shaped file rejected"
            );
            let bytes = read_bounded(&path, 1024 * 1024)?;
            *total += bytes.len() as u64;
            ensure!(
                *total <= MAX_BYTES && files.len() < MAX_FILES,
                "bundle exceeds limits"
            );
            let text = std::str::from_utf8(&bytes).context("binary bundle files unsupported")?;
            ensure!(!text.contains('\0'), "binary bundle files unsupported");
            files.insert(
                relative,
                format!(
                    "{:o}:{}",
                    metadata.permissions().mode() & 0o777,
                    hash(&bytes)
                ),
            );
        }
    }
    Ok(())
}

pub fn fingerprint(folder: &Path) -> Result<(String, BTreeMap<String, String>)> {
    ensure!(
        !fs::symlink_metadata(folder)?.file_type().is_symlink(),
        "bundle root cannot be a symlink"
    );
    let mut files = BTreeMap::new();
    inventory(folder, folder, &mut files, &mut 0, &mut 0, 0)?;
    ensure!(files.contains_key("SKILL.md"), "missing SKILL.md");
    let bytes = read_bounded(&folder.join("SKILL.md"), 1024 * 1024)?;
    let text = std::str::from_utf8(&bytes)?;
    let mut lines = text.lines();
    ensure!(
        lines.next().is_some_and(|s| s.trim() == "---"),
        "missing frontmatter"
    );
    let mut yaml = String::new();
    let mut closed = false;
    for line in lines {
        if line.trim() == "---" {
            closed = true;
            break;
        }
        yaml.push_str(line);
        yaml.push('\n');
    }
    ensure!(closed, "unterminated frontmatter");
    let meta: Value = serde_yaml_ng::from_str(&yaml)?;
    ensure!(
        meta["name"].as_str().is_some_and(|s| !s.trim().is_empty())
            && meta["description"]
                .as_str()
                .is_some_and(|s| !s.trim().is_empty()),
        "invalid skill metadata"
    );
    Ok((hash(&serde_json::to_vec(&files)?), files))
}

pub fn atomic_json(path: &Path, data: &Value) -> Result<()> {
    let parent = path.parent().context("missing parent")?;
    fs::create_dir_all(parent)?;
    let mut file = tempfile::NamedTempFile::new_in(parent)?;
    use std::io::Write;
    file.write_all(&serde_json::to_vec_pretty(data)?)?;
    file.as_file().sync_all()?;
    file.persist(path).map_err(|e| e.error)?;
    Ok(())
}

pub fn load(folder: &Path, receipt: &Value, resource: &str) -> Result<Value> {
    let (digest, files) = fingerprint(folder)?;
    ensure!(
        receipt["schema"] == 1
            && receipt["classification"] == "accepted"
            && receipt["exit_code"] == 0,
        "bundle has no accepted receipt"
    );
    ensure!(
        receipt["fingerprint"].as_str() == Some(&digest),
        "bundle changed since scan"
    );
    ensure!(
        receipt["scanner"].as_str() == Some(crate::scanner::IMAGE),
        "unexpected scanner identity"
    );
    let covered: BTreeSet<String> = receipt["covered_files"]
        .as_array()
        .context("missing coverage")?
        .iter()
        .map(|v| v.as_str().map(str::to_owned).context("invalid coverage"))
        .collect::<Result<_>>()?;
    ensure!(
        files.keys().all(|p| covered.contains(p)),
        "receipt coverage incomplete"
    );
    let expected = folder
        .parent()
        .context("missing bundle parent")?
        .join("scan.json");
    let raw: Value = serde_json::from_slice(&read_bounded(&expected, 8 * 1024 * 1024)?)?;
    ensure!(
        receipt["raw_sha256"].as_str() == Some(&hash(&serde_json::to_vec(&raw)?)),
        "scan evidence changed"
    );
    let classified = crate::scanner::classify(&raw, 0, &digest, &files)?;
    ensure!(
        classified["classification"] == "accepted",
        "scan evidence does not accept bundle"
    );
    let relative = safe_relative(resource)?;
    ensure!(
        files.contains_key(resource),
        "resource outside scanned bundle"
    );
    let target = folder.join(relative);
    let metadata = fs::symlink_metadata(&target)?;
    ensure!(
        metadata.is_file() && !metadata.file_type().is_symlink(),
        "resource is not a regular file"
    );
    let bytes = read_bounded(&target, 1024 * 1024)?;
    ensure!(
        files.get(resource)
            == Some(&format!(
                "{:o}:{}",
                metadata.permissions().mode() & 0o777,
                hash(&bytes)
            )),
        "resource bytes or mode differ from scanned content"
    );
    let text = String::from_utf8(bytes)?;
    let (after, _) = fingerprint(folder)?;
    ensure!(after == digest, "concurrent bundle change");
    Ok(
        json!({"classification":"accepted", "fingerprint":digest, "resource":resource, "content":text}),
    )
}

pub fn snapshot(
    source: &Path,
    destination: &Path,
    expected: &BTreeMap<String, String>,
) -> Result<()> {
    fs::create_dir(destination)?;
    for (relative, recorded) in expected {
        let input = source.join(safe_relative(relative)?);
        let metadata = fs::symlink_metadata(&input)?;
        ensure!(
            metadata.is_file() && !metadata.file_type().is_symlink(),
            "snapshot source changed"
        );
        let bytes = read_bounded(&input, 1024 * 1024)?;
        ensure!(
            *recorded
                == format!(
                    "{:o}:{}",
                    metadata.permissions().mode() & 0o777,
                    hash(&bytes)
                ),
            "snapshot bytes changed"
        );
        let output = destination.join(relative);
        fs::create_dir_all(output.parent().context("missing resource parent")?)?;
        fs::write(&output, bytes)?;
        fs::set_permissions(&output, metadata.permissions())?;
    }
    ensure!(
        fingerprint(destination)?.1 == *expected,
        "incomplete snapshot"
    );
    Ok(())
}

fn walk_skills(
    path: &Path,
    ancestors: &mut BTreeSet<PathBuf>,
    observed: &mut BTreeSet<(PathBuf, PathBuf)>,
) -> Result<()> {
    let real = path
        .canonicalize()
        .context("missing root or broken alias")?;
    ensure!(ancestors.insert(real.clone()), "directory alias cycle");
    if path.join("SKILL.md").is_file() {
        observed.insert((path.join("SKILL.md"), path.join("SKILL.md").canonicalize()?));
        let workflows = path.join("workflows");
        if workflows.is_dir() {
            for entry in fs::read_dir(workflows)? {
                let p = entry?.path();
                if p.extension().is_some_and(|e| e == "md") {
                    let raw = String::from_utf8(read_bounded(&p, 1024 * 1024)?)?;
                    if let Some(front) = raw
                        .strip_prefix("---\n")
                        .and_then(|s| s.split_once("\n---").map(|v| v.0))
                    {
                        let meta: Value = serde_yaml_ng::from_str(front)?;
                        if meta["schema"] == "workflow/v1" {
                            ensure!(
                                !p.is_symlink() && p.canonicalize()?.starts_with(&real),
                                "workflow escapes bundle"
                            );
                            observed.insert((p.clone(), p.canonicalize()?));
                        }
                    }
                }
            }
        }
    } else {
        for e in fs::read_dir(path)? {
            let e = e?;
            let name = e.file_name();
            let name = name.to_string_lossy();
            if name.starts_with('.') || name == "__pycache__" {
                continue;
            }
            if e.path().is_dir() {
                walk_skills(&e.path(), ancestors, observed)?;
            } else if e.file_type()?.is_symlink() && !e.path().exists() {
                bail!("broken alias");
            }
        }
    }
    ancestors.remove(&real);
    Ok(())
}

pub fn check_graph(path: &Path) -> Result<Value> {
    let bytes = read_bounded(path, 16 * 1024 * 1024)?;
    let graph: Value = serde_json::from_slice(&bytes)?;
    ensure!(
        graph["schema"] == 1 && graph["errors"].as_array().is_some_and(|v| v.is_empty()),
        "invalid graph"
    );
    let nodes = graph["nodes"].as_array().context("missing nodes")?;
    let mut expected = BTreeSet::new();
    for n in nodes {
        let p = PathBuf::from(n["path"].as_str().context("missing path")?);
        let discovery = PathBuf::from(
            n["discovery_path"]
                .as_str()
                .context("missing discovery path")?,
        );
        ensure!(
            p.is_absolute() && discovery.is_absolute(),
            "graph paths must be absolute"
        );
        ensure!(
            hash(&read_bounded(&p, 1024 * 1024)?)
                == n["sha256"].as_str().context("missing hash")?,
            "skill changed; run skill-search refresh"
        );
        ensure!(
            n["declared_used_by"] == n["used_by"],
            "stale backlinks; run skill-search refresh"
        );
        expected.insert((discovery.clone(), p.clone()));
        ensure!(discovery.canonicalize()? == p, "changed discovery path");
        if n["kind"] == "workflow" {
            let owner = nodes
                .iter()
                .find(|v| v["id"] == n["owner"])
                .context("missing workflow owner")?;
            let root = Path::new(owner["path"].as_str().context("missing owner path")?)
                .parent()
                .context("missing bundle")?;
            for (relative, expected) in n["resources"]
                .as_object()
                .context("missing workflow resources")?
            {
                let resource = root.join(safe_relative(relative)?);
                ensure!(
                    !resource.is_symlink() && resource.canonicalize()?.starts_with(root),
                    "workflow resource escapes bundle"
                );
                ensure!(
                    hash(&read_bounded(&resource, 1024 * 1024)?)
                        == expected.as_str().context("missing resource hash")?,
                    "workflow resource changed; run skill-search refresh"
                );
            }
        }
    }
    for a in graph["aliases"].as_array().context("missing aliases")? {
        let target = nodes
            .iter()
            .find(|n| n["id"] == a["target"])
            .context("unknown alias target")?;
        expected.insert((
            PathBuf::from(a["path"].as_str().context("missing alias path")?),
            PathBuf::from(target["path"].as_str().context("missing target path")?),
        ));
    }
    let mut observed = BTreeSet::new();
    for root in graph["roots"].as_array().context("missing roots")? {
        walk_skills(
            Path::new(root["path"].as_str().context("missing root path")?),
            &mut BTreeSet::new(),
            &mut observed,
        )?;
    }
    ensure!(
        expected == observed,
        "skill inventory or aliases changed; run skill-search refresh"
    );
    Ok(graph)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn paths_fail_closed() {
        for p in ["../x", "/x", "a/../x", "a//b", "a\\b", "./x", ""] {
            assert!(safe_relative(p).is_err(), "{p}");
        }
        assert!(safe_relative("references/guide.md").is_ok());
    }
    #[test]
    fn fingerprint_tracks_all_bytes_and_modes() -> Result<()> {
        let d = tempfile::tempdir()?;
        fs::write(
            d.path().join("SKILL.md"),
            "---\nname: sample\ndescription: test\n---\nhello",
        )?;
        let first = fingerprint(d.path())?.0;
        fs::write(d.path().join("extra.txt"), "one")?;
        let second = fingerprint(d.path())?.0;
        assert_ne!(first, second);
        fs::set_permissions(
            d.path().join("extra.txt"),
            fs::Permissions::from_mode(0o700),
        )?;
        assert_ne!(second, fingerprint(d.path())?.0);
        std::os::unix::fs::symlink("SKILL.md", d.path().join("link"))?;
        assert!(fingerprint(d.path()).is_err());
        Ok(())
    }
    #[test]
    fn rejected_cannot_load() -> Result<()> {
        let d = tempfile::tempdir()?;
        fs::write(
            d.path().join("SKILL.md"),
            "---\nname: sample\ndescription: test\n---\nhello",
        )?;
        assert!(load(d.path(), &json!({"classification":"rejected"}), "SKILL.md").is_err());
        Ok(())
    }
}
