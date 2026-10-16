use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use url::Url;

pub const KINDS: [&str; 7] = [
    "blog",
    "article",
    "video",
    "paper",
    "documentation",
    "book",
    "other",
];
pub const PROVIDERS: [&str; 4] = ["instapaper", "raindrop", "neon", "manual"];

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Origin {
    pub provider: String,
    pub account: String,
    pub external_id: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Record {
    #[serde(default = "schema")]
    pub schema: u8,
    pub provider: String,
    pub account: String,
    pub external_id: String,
    pub url: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub excerpt: String,
    #[serde(default)]
    pub note: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub folder: String,
    #[serde(default)]
    pub saved_at: Option<String>,
    #[serde(default)]
    pub updated_at: Option<String>,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub kind_source: String,
    #[serde(default)]
    pub imported_origin: Option<Origin>,
}

fn schema() -> u8 {
    1
}
pub fn hash(bytes: impl AsRef<[u8]>) -> String {
    format!("{:x}", Sha256::digest(bytes.as_ref()))
}
pub fn valid_text(s: &str, max: usize) -> bool {
    s.len() <= max && !s.chars().any(|c| c.is_control() && c != '\n' && c != '\t')
}
pub fn clean(s: &str) -> String {
    s.chars()
        .filter(|c| !c.is_control() || *c == '\n')
        .collect()
}
pub fn validate_url(s: &str) -> Result<String> {
    let raw = s.trim();
    ensure!(
        raw.len() <= 8192 && !raw.chars().any(|c| c.is_whitespace() || c.is_control()),
        "Invalid HTTP(S) URL"
    );
    let u = Url::parse(raw).map_err(|_| anyhow::anyhow!("Invalid HTTP(S) URL"))?;
    ensure!(
        matches!(u.scheme(), "http" | "https")
            && u.host_str().is_some()
            && u.username().is_empty()
            && u.password().is_none(),
        "Invalid HTTP(S) URL"
    );
    Ok(raw.into())
}
pub fn classify(s: &str) -> (&'static str, &'static str) {
    let Ok(u) = Url::parse(s) else {
        return ("other", "unknown");
    };
    let host = u.host_str().unwrap_or("").to_lowercase();
    let path = u.path();
    let kind = if ((host == "youtube.com" || host == "www.youtube.com")
        && ((path == "/watch" && u.query_pairs().any(|(k, v)| k == "v" && !v.is_empty()))
            || ["/shorts/", "/live/", "/embed/"]
                .iter()
                .any(|p| path.starts_with(p))))
        || (host == "youtu.be" && path.len() > 1)
        || (host == "vimeo.com" && path.trim_matches('/').parse::<u64>().is_ok())
    {
        "video"
    } else if (host == "arxiv.org"
        && ["/abs/", "/pdf/", "/html/"]
            .iter()
            .any(|p| path.starts_with(p)))
        || ([
            "biorxiv.org",
            "medrxiv.org",
            "www.biorxiv.org",
            "www.medrxiv.org",
        ]
        .contains(&host.as_str())
            && path.starts_with("/content/"))
        || (host == "openreview.net"
            && ["/forum", "/pdf"].contains(&path)
            && u.query_pairs().any(|(k, _)| k == "id"))
    {
        "paper"
    } else if (host.starts_with("docs.") && host != "docs.google.com")
        || host.ends_with(".readthedocs.io")
    {
        "documentation"
    } else if host.starts_with("blog.")
        || host.starts_with("blogs.")
        || host.ends_with(".blog")
        || host.ends_with(".blogspot.com")
        || host.ends_with(".substack.com")
        || (host == "medium.com" && path.len() > 1)
        || (host == "openai.com" && path.starts_with("/index/") && path.len() > 7)
        || path
            .split('/')
            .any(|p| ["blog", "blogs", "weblog"].contains(&p))
        || (["huyenchip.com", "colah.github.io", "karpathy.github.io"].contains(&host.as_str())
            && (path == "/"
                || path
                    .split('/')
                    .nth(1)
                    .is_some_and(|p| p.len() == 4 && p.parse::<u16>().is_ok())))
    {
        "blog"
    } else if (host.ends_with("goodreads.com") && path.starts_with("/book/show/"))
        || (host == "openlibrary.org" && ["/books/", "/works/"].iter().any(|p| path.starts_with(p)))
    {
        "book"
    } else {
        "other"
    };
    (kind, if kind == "other" { "unknown" } else { "url" })
}
impl Record {
    pub fn new(provider: &str, account: &str, external_id: &str, url: &str) -> Result<Self> {
        let mut r: Self = serde_json::from_value(
            serde_json::json!({"provider":provider,"account":account,"external_id":external_id,"url":url}),
        )?;
        r.validate()?;
        Ok(r)
    }
    pub fn validate(&mut self) -> Result<()> {
        ensure!(
            self.schema == 1 && PROVIDERS.contains(&self.provider.as_str()),
            "Invalid record schema/provider"
        );
        ensure!(
            !self.account.is_empty()
                && valid_text(&self.account, 256)
                && !self.external_id.is_empty()
                && valid_text(&self.external_id, 8192),
            "Invalid origin"
        );
        self.url = validate_url(&self.url)?;
        for (s, max) in [
            (&self.title, 4096),
            (&self.excerpt, 10000),
            (&self.note, 10000),
            (&self.folder, 512),
        ] {
            ensure!(valid_text(s, max), "Invalid or oversized bookmark text");
        }
        ensure!(
            self.tags.len() <= 100 && self.tags.iter().all(|t| valid_text(t, 256)),
            "Invalid tags"
        );
        self.tags.sort();
        self.tags.dedup();
        for t in [&self.saved_at, &self.updated_at].into_iter().flatten() {
            ensure!(valid_text(t, 100), "Invalid timestamp");
        }
        if self.kind.is_empty() {
            let (k, p) = classify(&self.url);
            self.kind = k.into();
            self.kind_source = p.into();
        } else if self.kind_source.is_empty() {
            self.kind_source = "manual".into();
        }
        ensure!(
            KINDS.contains(&self.kind.as_str())
                && ["manual", "provider", "url", "unknown"].contains(&self.kind_source.as_str()),
            "Invalid kind/provenance"
        );
        if ["unknown", "url"].contains(&self.kind_source.as_str())
            || (self.kind_source == "provider" && self.kind == "article")
        {
            let (kind, source) = classify(&self.url);
            if kind != "other" {
                self.kind = kind.into();
                self.kind_source = source.into();
            }
        }
        if let Some(o) = &self.imported_origin {
            ensure!(
                PROVIDERS.contains(&o.provider.as_str())
                    && !o.account.is_empty()
                    && valid_text(&o.account, 256)
                    && !o.external_id.is_empty()
                    && valid_text(&o.external_id, 8192),
                "Invalid imported origin"
            );
        }
        Ok(())
    }
    pub fn id(&self) -> String {
        hash(&self.url)
    }
    pub fn origin(&self) -> String {
        serde_json::to_string(&[&self.provider, &self.account, &self.external_id]).unwrap()
    }
    pub fn body(&self) -> String {
        format!(
            "{} {} {} {} {} {}",
            self.title,
            self.url,
            self.excerpt,
            self.note,
            self.tags.join(" "),
            self.folder
        )
        .chars()
        .take(12000)
        .collect()
    }
    pub fn remote(&self) -> Self {
        let mut r = self.clone();
        if let Some(o) = r.imported_origin.take() {
            r.provider = o.provider;
            r.account = o.account;
            r.external_id = o.external_id;
        }
        r
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_identity_and_validation() {
        assert_ne!(hash("https://a.com/x?a=1"), hash("https://a.com/x?a=2"));
        for u in ["javascript:x", "https://u:p@a.com", "https://a.com/\u{7f}"] {
            assert!(validate_url(u).is_err());
        }
        assert_eq!(
            validate_url(" https://a.com#x ").unwrap(),
            "https://a.com#x"
        );
    }
    #[test]
    fn conservative_types() {
        assert_eq!(classify("https://youtube.com/").0, "other");
        assert_eq!(classify("https://arxiv.org/abs/2401.12345").0, "paper");
        assert_eq!(
            classify("https://openai.com/index/gpt-4-research/").0,
            "blog"
        );
        assert_eq!(classify("https://evil.org/?url=arxiv.org").0, "other");
        for url in [
            "https://huyenchip.com",
            "https://huyenchip.com/2023/04/11/llm-engineering.html",
            "https://example.com/blog/post",
            "https://blog.example.com",
            "https://example.substack.com/p/post",
        ] {
            assert_eq!(classify(url), ("blog", "url"));
        }
        for url in [
            "https://example.com/?path=/blog/post",
            "https://example.com/blogger",
            "https://huyenchip.com/ml-interviews-book",
        ] {
            assert_eq!(classify(url).0, "other");
        }
    }
    #[test]
    fn cached_classification_refresh_preserves_manual_choices_and_body() {
        let mut record =
            Record::new("instapaper", "fixture", "1", "https://huyenchip.com").unwrap();
        let body = record.body();
        record.kind = "other".into();
        record.kind_source = "unknown".into();
        record.validate().unwrap();
        assert_eq!(
            (record.kind.as_str(), record.kind_source.as_str()),
            ("blog", "url")
        );
        assert_eq!(record.body(), body);
        record.kind = "book".into();
        record.kind_source = "manual".into();
        record.validate().unwrap();
        assert_eq!(record.kind, "book");
        record.kind = "invalid-fixture-kind".into();
        record.kind_source = "unknown".into();
        assert!(record.validate().is_err());
    }
}
