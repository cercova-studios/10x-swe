use std::time::Duration;

use anyhow::{anyhow, Result};
use encoding_rs::{Encoding, UTF_8};
use quick_xml::events::Event;
use quick_xml::Reader;
use tokio::time::sleep;
use url::Url;

#[cfg(feature = "browser")]
use chromiumoxide::browser::{Browser, BrowserConfig};
#[cfg(feature = "browser")]
use futures_util::StreamExt;

const MAX_SIZE: usize = 5 * 1024 * 1024;
const FETCH_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_FETCH_ATTEMPTS: usize = 3;

pub const DEFAULT_UA: &str = "Mozilla/5.0 (compatible; distiller/1.0; +https://example.com)";
pub const BOT_UA: &str = "Mozilla/5.0 (compatible; distiller/1.0; +https://example.com) bot";

const BOT_UA_DOMAINS: &[&str] = &["github.com"];

pub fn get_initial_ua(target_url: &str) -> &'static str {
    if let Ok(url) = url::Url::parse(target_url) {
        let host = url.host_str().unwrap_or_default();
        if BOT_UA_DOMAINS
            .iter()
            .any(|d| host == *d || host.ends_with(&format!(".{d}")))
        {
            return BOT_UA;
        }
    }
    DEFAULT_UA
}

pub async fn fetch_page(
    target_url: &str,
    user_agent: &str,
    language: Option<&str>,
    proxy_url: Option<&str>,
    debug_enabled: bool,
) -> Result<String> {
    crate::observability::debug(
        debug_enabled,
        "fetch.start",
        format!("url={target_url} proxy={}", proxy_log_value(proxy_url)),
    );
    let mut builder = reqwest::Client::builder()
        .timeout(FETCH_TIMEOUT)
        .redirect(reqwest::redirect::Policy::limited(10));
    if let Some(proxy) = proxy_url {
        builder = builder.proxy(reqwest::Proxy::all(proxy)?);
    }
    let client = builder.build()?;

    let mut last_error: Option<anyhow::Error> = None;
    for attempt in 0..MAX_FETCH_ATTEMPTS {
        crate::observability::debug(
            debug_enabled,
            "fetch.attempt",
            format!("attempt={} ua={}", attempt + 1, user_agent),
        );
        let mut req = client
            .get(target_url)
            .header("User-Agent", user_agent)
            .header(
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            )
            .header("Accept-Encoding", "gzip, deflate, br")
            .header("Connection", "keep-alive")
            .header("Upgrade-Insecure-Requests", "1")
            .header("DNT", "1");

        if is_medium_url(target_url) {
            req = req.header("Referer", "https://medium.com/");
        }

        if let Some(lang) = language {
            req = req.header("Accept-Language", lang);
        }

        let response = match req.send().await {
            Ok(resp) => resp,
            Err(err) => {
                crate::observability::debug(
                    debug_enabled,
                    "fetch.error",
                    format!("attempt={} err={err}", attempt + 1),
                );
                last_error = Some(anyhow!("Request error: {err}"));
                if attempt + 1 < MAX_FETCH_ATTEMPTS {
                    sleep(backoff_delay(attempt)).await;
                    continue;
                }
                break;
            }
        };

        if response.status().is_success() {
            crate::observability::debug(
                debug_enabled,
                "fetch.http_success",
                format!("status={}", response.status()),
            );
            let content_type = response
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_string();

            if !(content_type.contains("text/html")
                || content_type.contains("application/xhtml+xml"))
            {
                return Err(anyhow!("Not an HTML page (content-type: {content_type})"));
            }

            ensure_declared_size_within_limit(response.content_length())?;

            let bytes = read_body_capped(response).await?;

            let encoding = detect_charset(&content_type, &bytes);
            let (decoded, _, _) = encoding.decode(&bytes);
            crate::observability::debug(
                debug_enabled,
                "fetch.decoded",
                format!("bytes={} content_type={}", bytes.len(), content_type),
            );
            return Ok(decoded.into_owned());
        }

        if response.status().as_u16() == 403 {
            crate::observability::debug(
                debug_enabled,
                "fetch.403",
                "received 403, trying fallbacks",
            );
            if is_medium_url(target_url) {
                if let Ok(html) =
                    fetch_medium_via_feed(&client, target_url, user_agent, language).await
                {
                    crate::observability::debug(
                        debug_enabled,
                        "fetch.medium_rss",
                        "fallback succeeded",
                    );
                    return Ok(html);
                }
            }

            if let Ok(html) = fetch_page_via_browser(target_url).await {
                crate::observability::debug(debug_enabled, "fetch.browser", "fallback succeeded");
                return Ok(html);
            }
        }

        if is_retryable_status(response.status().as_u16()) && attempt + 1 < MAX_FETCH_ATTEMPTS {
            crate::observability::debug(
                debug_enabled,
                "fetch.retryable_status",
                format!("status={} attempt={}", response.status(), attempt + 1),
            );
            last_error = Some(anyhow!("Fetch failed: {}", response.status()));
            sleep(backoff_delay(attempt)).await;
            continue;
        }

        return Err(anyhow!("Failed to fetch: {}", response.status()));
    }

    crate::observability::debug(debug_enabled, "fetch.fail", "all attempts exhausted");
    Err(last_error.unwrap_or_else(|| anyhow!("Failed to fetch")))
}

#[cfg(feature = "browser")]
fn is_challenge_page(title: &str, html: &str) -> bool {
    let t = title.to_lowercase();
    let h = html.to_lowercase();
    t.contains("just a moment")
        || h.contains("cf-browser-verification")
        || h.contains("challenge-platform")
        || h.contains("captcha")
}

#[cfg(feature = "browser")]
async fn fetch_page_via_browser(target_url: &str) -> Result<String> {
    let config = BrowserConfig::builder()
        .no_sandbox()
        .build()
        .map_err(|e| anyhow!("Failed to build browser config: {e}"))?;
    let (mut browser, mut handler) = Browser::launch(config).await?;

    let handler_task = tokio::spawn(async move {
        while let Some(evt) = handler.next().await {
            if evt.is_err() {
                break;
            }
        }
    });

    let page = browser.new_page(target_url).await?;
    let title = page
        .evaluate("document.title")
        .await?
        .into_value::<String>()
        .ok()
        .unwrap_or_default();
    let html = page.content().await?;
    browser.close().await?;
    let _ = handler_task.await;

    if is_challenge_page(&title, &html) {
        return Err(anyhow!("Browser fallback hit challenge page"));
    }
    Ok(html)
}

#[cfg(not(feature = "browser"))]
async fn fetch_page_via_browser(_target_url: &str) -> Result<String> {
    Err(anyhow!(
        "browser fallback unavailable: build with --features browser"
    ))
}

fn detect_charset(content_type: &str, bytes: &[u8]) -> &'static Encoding {
    if let Some(charset) = extract_charset_from_content_type(content_type) {
        if let Some(enc) = Encoding::for_label(charset.as_bytes()) {
            return enc;
        }
    }

    let head = &bytes[..bytes.len().min(2048)];
    let head_str = String::from_utf8_lossy(head).to_lowercase();

    if let Some(pos) = head_str.find("charset=") {
        let fragment = &head_str[pos + 8..];
        let charset = fragment
            .split(['"', '\'', ';', '>', ' '])
            .next()
            .unwrap_or("")
            .trim_matches(',');
        if let Some(enc) = Encoding::for_label(charset.as_bytes()) {
            return enc;
        }
    }

    UTF_8
}

fn extract_charset_from_content_type(content_type: &str) -> Option<String> {
    let lower = content_type.to_lowercase();
    let charset_pos = lower.find("charset=")?;
    let value = &lower[charset_pos + 8..];
    let parsed = value
        .split(['"', '\'', ';', ',', ' '])
        .next()
        .unwrap_or("")
        .trim();

    if parsed.is_empty() {
        None
    } else {
        Some(parsed.to_string())
    }
}

fn backoff_delay(attempt: usize) -> Duration {
    // 300ms, 900ms, 1800ms
    match attempt {
        0 => Duration::from_millis(300),
        1 => Duration::from_millis(900),
        _ => Duration::from_millis(1800),
    }
}

fn is_retryable_status(status: u16) -> bool {
    matches!(status, 408 | 425 | 429 | 500 | 502 | 503 | 504)
}

fn is_medium_url(target_url: &str) -> bool {
    Url::parse(target_url)
        .ok()
        .and_then(|u| {
            u.host_str()
                .map(|h| h == "medium.com" || h.ends_with(".medium.com"))
        })
        .unwrap_or(false)
}

async fn fetch_medium_via_feed(
    client: &reqwest::Client,
    target_url: &str,
    user_agent: &str,
    language: Option<&str>,
) -> Result<String> {
    let feed_candidates = medium_feed_candidates(target_url)?;
    let target_post_id = medium_post_id(target_url);
    let target_norm = normalize_medium_url(target_url);

    for feed_url in feed_candidates {
        let mut req = client
            .get(&feed_url)
            .header("User-Agent", user_agent)
            .header(
                "Accept",
                "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
            );
        if let Some(lang) = language {
            req = req.header("Accept-Language", lang);
        }

        let response = match req.send().await {
            Ok(resp) if resp.status().is_success() => resp,
            _ => continue,
        };

        ensure_declared_size_within_limit(response.content_length())?;
        let content_type = response
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("application/rss+xml")
            .to_string();
        let bytes = read_body_capped(response).await?;
        let encoding = detect_charset(&content_type, &bytes);
        let (decoded, _, _) = encoding.decode(&bytes);
        let xml = decoded.into_owned();
        let items = parse_medium_feed_items(&xml)?;
        for item in items {
            let item_norm = normalize_medium_url(&item.link);
            let link_post_id = medium_post_id(&item.link);
            let id_match = target_post_id
                .as_deref()
                .zip(link_post_id.as_deref())
                .map(|(a, b)| a == b)
                .unwrap_or(false);
            if id_match || target_norm == item_norm {
                return Ok(wrap_medium_item_as_html(&item));
            }
        }
    }

    Err(anyhow!("Medium RSS fallback did not find target article"))
}

fn proxy_log_value(proxy_url: Option<&str>) -> String {
    let Some(proxy_url) = proxy_url else {
        return "none".to_string();
    };
    let Ok(url) = Url::parse(proxy_url) else {
        return "<invalid>".to_string();
    };
    let scheme = url.scheme();
    let Some(host) = url.host_str() else {
        return "<invalid>".to_string();
    };
    match url.port() {
        Some(port) => format!("{scheme}://{host}:{port}"),
        None => format!("{scheme}://{host}"),
    }
}

fn ensure_declared_size_within_limit(content_length: Option<u64>) -> Result<()> {
    if content_length.is_some_and(|len| len > MAX_SIZE as u64) {
        return Err(anyhow!("Page too large"));
    }
    Ok(())
}

fn ensure_actual_size_within_limit(actual_len: usize) -> Result<()> {
    if actual_len > MAX_SIZE {
        return Err(anyhow!("Page too large"));
    }
    Ok(())
}

async fn read_body_capped(mut response: reqwest::Response) -> Result<Vec<u8>> {
    let mut buf = Vec::new();
    if let Some(len) = response.content_length() {
        let capped = usize::try_from(len).unwrap_or(MAX_SIZE).min(MAX_SIZE);
        buf.reserve(capped);
    }

    while let Some(chunk) = response.chunk().await? {
        let next_len = buf.len().saturating_add(chunk.len());
        ensure_actual_size_within_limit(next_len)?;
        buf.extend_from_slice(&chunk);
    }

    ensure_actual_size_within_limit(buf.len())?;
    Ok(buf)
}

fn medium_feed_candidates(target_url: &str) -> Result<Vec<String>> {
    let url = Url::parse(target_url)?;
    let host = url.host_str().ok_or_else(|| anyhow!("Missing host"))?;
    let mut out = Vec::new();

    if host == "medium.com" || host.ends_with(".medium.com") {
        let segments: Vec<_> = url
            .path_segments()
            .map(|s| s.filter(|p| !p.is_empty()).collect())
            .unwrap_or_default();
        if let Some(first) = segments.first() {
            out.push(format!("https://{host}/feed/{first}"));
        }
        out.push(format!("https://{host}/feed"));
    }

    if out.is_empty() {
        return Err(anyhow!("Not a Medium host"));
    }
    out.dedup();
    Ok(out)
}

fn medium_post_id(url: &str) -> Option<String> {
    let parsed = Url::parse(url).ok()?;
    let segs: Vec<_> = parsed.path_segments()?.filter(|s| !s.is_empty()).collect();
    if segs.len() >= 2 && segs[segs.len() - 2] == "p" {
        return Some(segs[segs.len() - 1].to_string());
    }
    let last = segs.last()?.to_string();
    if let Some((_, suffix)) = last.rsplit_once('-') {
        if suffix.len() >= 8 && suffix.chars().all(|c| c.is_ascii_hexdigit()) {
            return Some(suffix.to_string());
        }
    }
    None
}

fn normalize_medium_url(url: &str) -> String {
    if let Ok(mut parsed) = Url::parse(url) {
        parsed.set_query(None);
        parsed.set_fragment(None);
        let mut s = parsed.to_string();
        while s.ends_with('/') {
            s.pop();
        }
        s
    } else {
        url.to_string()
    }
}

#[derive(Debug, Default)]
struct MediumFeedItem {
    title: String,
    link: String,
    content_html: String,
    description_html: String,
}

fn parse_medium_feed_items(xml: &str) -> Result<Vec<MediumFeedItem>> {
    let mut reader = Reader::from_str(xml);
    let mut buf = Vec::new();
    let mut items = Vec::new();

    let mut in_item = false;
    let mut current = MediumFeedItem::default();
    let mut current_field: Option<Vec<u8>> = None;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) => {
                let name = e.name().as_ref().to_vec();
                if name.as_slice() == b"item" {
                    in_item = true;
                    current = MediumFeedItem::default();
                    current_field = None;
                } else if in_item {
                    current_field = Some(name);
                }
            }
            Ok(Event::End(e)) => {
                let name = e.name().as_ref().to_vec();
                if name.as_slice() == b"item" && in_item {
                    if !current.link.is_empty() {
                        items.push(std::mem::take(&mut current));
                    }
                    in_item = false;
                    current_field = None;
                } else if in_item {
                    current_field = None;
                }
            }
            Ok(Event::Text(e)) => {
                if in_item {
                    let text = e.decode()?.into_owned();
                    apply_feed_field(&mut current, current_field.as_deref(), &text);
                }
            }
            Ok(Event::CData(e)) => {
                if in_item {
                    let text = String::from_utf8_lossy(e.as_ref()).into_owned();
                    apply_feed_field(&mut current, current_field.as_deref(), &text);
                }
            }
            Ok(Event::Eof) => break,
            Err(err) => return Err(anyhow!("Failed to parse Medium feed XML: {err}")),
            _ => {}
        }
        buf.clear();
    }

    Ok(items)
}

fn apply_feed_field(item: &mut MediumFeedItem, field: Option<&[u8]>, text: &str) {
    match field {
        Some(b"title") => item.title.push_str(text),
        Some(b"link") => item.link.push_str(text.trim()),
        Some(b"content:encoded") => item.content_html.push_str(text),
        Some(b"description") => item.description_html.push_str(text),
        _ => {}
    }
}

fn wrap_medium_item_as_html(item: &MediumFeedItem) -> String {
    let title = escape_html(item.title.trim());
    let body_html = if !item.content_html.trim().is_empty() {
        item.content_html.trim()
    } else {
        item.description_html.trim()
    };

    format!(
        "<html><head><title>{title}</title></head><body><article><h1>{title}</h1>{body_html}</article></body></html>"
    )
}

fn escape_html(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for c in input.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_medium_feed_with_content_encoded() {
        let xml = r#"
        <rss>
          <channel>
            <item>
              <title>My Post</title>
              <link>https://medium.com/@user/my-post-bdaf1bd6e64b?source=rss</link>
              <content:encoded><![CDATA[<p>Hello world</p>]]></content:encoded>
            </item>
          </channel>
        </rss>
        "#;

        let items = parse_medium_feed_items(xml).expect("feed parsing should succeed");
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].title, "My Post");
        assert!(items[0].link.contains("bdaf1bd6e64b"));
        assert!(items[0].content_html.contains("Hello world"));
    }

    #[test]
    fn derives_medium_post_id_from_slug_or_p_path() {
        let slug_url = "https://medium.com/@user/title-bdaf1bd6e64b";
        let p_url = "https://medium.com/p/bdaf1bd6e64b";
        assert_eq!(medium_post_id(slug_url).as_deref(), Some("bdaf1bd6e64b"));
        assert_eq!(medium_post_id(p_url).as_deref(), Some("bdaf1bd6e64b"));
    }

    #[test]
    fn extracts_charset_from_content_type() {
        let charset = extract_charset_from_content_type("text/xml; charset=utf-8");
        assert_eq!(charset.as_deref(), Some("utf-8"));
    }

    #[test]
    fn redacts_proxy_credentials_in_debug_log_value() {
        let redacted = proxy_log_value(Some("http://user:secret@example.com:8080/path?q=1"));
        assert_eq!(redacted, "http://example.com:8080");
        assert!(!redacted.contains("secret"));
        assert_eq!(proxy_log_value(Some("not a url")), "<invalid>");
    }

    #[test]
    fn enforces_size_limit_for_declared_and_actual_lengths() {
        assert!(ensure_declared_size_within_limit(Some(MAX_SIZE as u64)).is_ok());
        assert!(ensure_declared_size_within_limit(Some((MAX_SIZE as u64) + 1)).is_err());
        assert!(ensure_actual_size_within_limit(MAX_SIZE).is_ok());
        assert!(ensure_actual_size_within_limit(MAX_SIZE + 1).is_err());
    }

    #[test]
    fn escapes_medium_titles_in_synthetic_html() {
        let item = MediumFeedItem {
            title: r#"Hi <script>alert(1)</script>"#.to_string(),
            link: "https://medium.com/p/abc".to_string(),
            content_html: "<p>Body</p>".to_string(),
            description_html: String::new(),
        };
        let html = wrap_medium_item_as_html(&item);
        assert!(html.contains("&lt;script&gt;"));
        assert!(!html.contains("<script>alert(1)</script>"));
        assert!(html.contains("<p>Body</p>"));
    }
}
