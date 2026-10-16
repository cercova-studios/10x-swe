//! Explicit public-page fetch; conversion stays inert and ephemeral in the browser.
use anyhow::{Result, ensure};
use serde_json::{Value, json};
use std::{
    io::Read,
    net::{IpAddr, SocketAddr, ToSocketAddrs},
    time::{Duration, Instant},
};

const LIMIT: u64 = 2 * 1024 * 1024;
fn public(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            let n = u32::from(ip);
            ![
                (0x00000000, 8),
                (0x0a000000, 8),
                (0x64400000, 10),
                (0x7f000000, 8),
                (0xa9fe0000, 16),
                (0xac100000, 12),
                (0xc0000000, 24),
                (0xc0000200, 24),
                (0xc0586300, 24),
                (0xc0a80000, 16),
                (0xc6120000, 15),
                (0xc6336400, 24),
                (0xcb007100, 24),
                (0xe0000000, 3),
            ]
            .iter()
            .any(|&(prefix, bits)| n >> (32 - bits) == prefix >> (32 - bits))
        }
        IpAddr::V6(ip) => {
            let s = ip.segments();
            // Conservative global unicast only; exclude special-purpose/tunnel/documentation ranges.
            s[0] & 0xe000 == 0x2000
                && !(s[0] == 0x2001 && (s[1] < 0x200 || s[1] == 0xdb8))
                && s[0] != 0x2002
                && !(s[0] == 0x3fff && s[1] < 0x1000)
        }
    }
}
fn target(text: &str) -> Result<url::Url> {
    let url = url::Url::parse(&crate::model::validate_url(text)?)?;
    ensure!(
        url.port().is_none(),
        "Reader accepts standard HTTP/HTTPS ports only"
    );
    ensure!(
        !url.host_str()
            .is_some_and(|s| s.eq_ignore_ascii_case("localhost") || s.ends_with(".localhost")),
        "Reader cannot access local addresses"
    );
    Ok(url)
}
fn addresses(host: &str, port: u16, resolved: Vec<SocketAddr>) -> Result<Vec<SocketAddr>> {
    ensure!(
        !resolved.is_empty() && resolved.iter().all(|a| public(a.ip()) && a.port() == port),
        "Reader destination must resolve only to public addresses"
    );
    ensure!(!host.is_empty(), "Missing reader host");
    Ok(resolved)
}
pub fn fetch(text: &str) -> Result<Value> {
    let mut url = target(text)?;
    let started = Instant::now();
    for hop in 0..=5 {
        let host = url
            .host_str()
            .ok_or_else(|| anyhow::anyhow!("Missing reader host"))?;
        let port = url.port_or_known_default().unwrap();
        let resolved: Vec<_> = (host.trim_matches(['[', ']']), port)
            .to_socket_addrs()?
            .collect();
        let ips = addresses(host, port, resolved)?;
        let remaining = Duration::from_secs(20)
            .checked_sub(started.elapsed())
            .ok_or_else(|| anyhow::anyhow!("Reader fetch timed out"))?;
        // Pin checked DNS results and disable proxies; every redirect is checked afresh.
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(remaining)
            .resolve_to_addrs(host.trim_matches(['[', ']']), &ips)
            .build()?;
        let mut response = client
            .get(url.clone())
            .header("Accept", "text/html, application/xhtml+xml")
            .header("Accept-Encoding", "identity")
            .header("User-Agent", "BookmarkDrop/0.1 Reader")
            .send()?;
        if response.status().is_redirection() {
            ensure!(hop < 5, "Reader redirect limit exceeded");
            let location = response
                .headers()
                .get("location")
                .ok_or_else(|| anyhow::anyhow!("Missing redirect location"))?
                .to_str()?;
            url = target(url.join(location)?.as_str())?;
            continue;
        }
        ensure!(
            response.status().is_success(),
            "Page unavailable (HTTP {})",
            response.status().as_u16()
        );
        let kind = response
            .headers()
            .get("content-type")
            .and_then(|h| h.to_str().ok())
            .unwrap_or("")
            .split(';')
            .next()
            .unwrap_or("")
            .trim();
        ensure!(
            matches!(kind, "text/html" | "application/xhtml+xml"),
            "Reader supports HTML pages; open PDFs or other files in their original viewer"
        );
        ensure!(
            response.content_length().is_none_or(|n| n <= LIMIT),
            "Reader page exceeds 2 MiB"
        );
        let mut bytes = Vec::new();
        Read::by_ref(&mut response)
            .take(LIMIT + 1)
            .read_to_end(&mut bytes)?;
        ensure!(bytes.len() as u64 <= LIMIT, "Reader page exceeds 2 MiB");
        let html =
            String::from_utf8(bytes).map_err(|_| anyhow::anyhow!("Reader requires UTF-8 HTML"))?;
        return Ok(json!({"url":url.as_str(), "html":html}));
    }
    unreachable!()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_destination_rejects_private_reserved_and_mixed_dns() {
        for ip in [
            "127.0.0.1",
            "10.0.0.1",
            "100.64.0.1",
            "169.254.169.254",
            "172.16.0.1",
            "192.168.1.1",
            "192.0.2.1",
            "198.18.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "::1",
            "::ffff:8.8.8.8",
            "fc00::1",
            "fe80::1",
            "2001:db8::1",
            "2002:808:808::1",
            "3fff::1",
        ] {
            assert!(!public(ip.parse().unwrap()), "{ip}");
        }
        assert!(public("8.8.8.8".parse().unwrap()));
        assert!(public("2606:4700:4700::1111".parse().unwrap()));
        assert!(addresses("example.org", 443, vec!["8.8.8.8:443".parse().unwrap()]).is_ok());
        assert!(
            addresses(
                "example.org",
                443,
                vec![
                    "8.8.8.8:443".parse().unwrap(),
                    "127.0.0.1:443".parse().unwrap()
                ]
            )
            .is_err()
        );
        assert!(addresses("example.org", 443, vec![]).is_err());
    }
    #[test]
    fn url_boundary_applies_to_initial_and_redirect_targets() {
        for u in [
            "file:///etc/passwd",
            "https://user:pass@example.org",
            "http://localhost",
            "http://a.localhost",
            "https://example.org:8443",
            "https://example.org\nwhoami",
        ] {
            assert!(target(u).is_err(), "{u}");
        }
        assert!(target("https://example.org/article?a=1#b").is_ok());
    }
}
