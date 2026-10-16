use scraper::{Html, Selector};
use url::Url;

use super::registry::ExtractorResult;

pub fn extract(html: &Html, url: &str) -> Option<ExtractorResult> {
    if !is_chat_share_url(url) {
        return None;
    }

    let selectors = [
        "[data-message-author-role='assistant']",
        "[data-testid='conversation-turn']",
        "article.prose",
        "main",
    ];

    let mut messages = Vec::new();
    for selector in selectors {
        let sel = match Selector::parse(selector) {
            Ok(s) => s,
            Err(_) => continue,
        };
        for node in html.select(&sel) {
            let text = node.text().collect::<String>();
            if text.split_whitespace().count() < 12 {
                continue;
            }
            messages.push(node.html());
        }
        if !messages.is_empty() {
            break;
        }
    }
    if messages.is_empty() {
        return None;
    }

    Some(ExtractorResult {
        content_html: messages.join("\n"),
        site: Some("LLM Chat".to_string()),
        ..ExtractorResult::default()
    })
}

fn is_chat_share_url(url: &str) -> bool {
    Url::parse(url)
        .ok()
        .and_then(|u| {
            u.host_str().map(|h| {
                host_matches(h, "chatgpt.com")
                    || host_matches(h, "openai.com")
                    || host_matches(h, "claude.ai")
                    || host_matches(h, "grok.com")
                    || host_matches(h, "gemini.google.com")
            })
        })
        .unwrap_or(false)
}

fn host_matches(host: &str, domain: &str) -> bool {
    host == domain || host.ends_with(&format!(".{domain}"))
}

#[cfg(test)]
mod tests {
    use super::is_chat_share_url;

    #[test]
    fn rejects_hosts_that_only_contain_supported_domains() {
        assert!(!is_chat_share_url(
            "https://chatgpt.com.evil.example/share/123"
        ));
        assert!(!is_chat_share_url(
            "https://claude.ai.evil.example/share/123"
        ));
    }
}
