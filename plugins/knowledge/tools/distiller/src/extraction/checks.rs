pub fn structure_noise_score(markdown: &str) -> i32 {
    let mut score = 0;
    let mut non_empty_run = 0;
    for line in markdown.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            non_empty_run = 0;
            continue;
        }

        non_empty_run += 1;
        if non_empty_run >= 10 {
            score += 1;
        }

        let lower = trimmed.to_ascii_lowercase();
        if matches!(
            lower.as_str(),
            "sign up" | "sign in" | "get app" | "write" | "search" | "follow" | "listen" | "share"
        ) {
            score += 3;
        }
        if trimmed == "!" || trimmed == "·" {
            score += 2;
        }
        if trimmed.chars().all(|c| c.is_ascii_digit()) {
            score += 2;
        }
        if trimmed.starts_with('[') && trimmed.ends_with(')') && trimmed.len() < 120 {
            score += 1;
        }
        if !trimmed.starts_with('#') {
            let words = trimmed.split_whitespace().count();
            if words <= 2 {
                score += 1;
            }
        }
    }
    score
}

pub fn passes_safety_checks(original: &str, candidate: &str) -> bool {
    let ow = word_count(original) as f32;
    let cw = word_count(candidate) as f32;
    if ow > 0.0 && (cw < ow * 0.75 || cw > ow * 1.35) {
        return false;
    }

    let ol = link_count(original) as f32;
    let cl = link_count(candidate) as f32;
    if ol >= 6.0 && cl < ol * 0.55 {
        return false;
    }

    let original_heading = first_heading(original);
    let candidate_heading = first_heading(candidate);
    if let (Some(a), Some(b)) = (original_heading, candidate_heading) {
        if heading_token_overlap(&a, &b) < 0.5 {
            return false;
        }
    }

    true
}

fn word_count(text: &str) -> usize {
    text.split_whitespace().count()
}

fn link_count(text: &str) -> usize {
    text.matches("](").count()
}

fn first_heading(text: &str) -> Option<String> {
    text.lines()
        .find_map(|line| line.strip_prefix('#').map(str::trim))
        .map(|s| s.trim_matches('#').trim().to_string())
        .filter(|s| !s.is_empty())
}

fn heading_token_overlap(a: &str, b: &str) -> f32 {
    let a_tokens: Vec<String> = a
        .split_whitespace()
        .map(|t| {
            t.to_ascii_lowercase()
                .chars()
                .filter(|c| c.is_alphanumeric())
                .collect::<String>()
        })
        .filter(|t| t.len() > 2)
        .collect();
    let b_tokens: Vec<String> = b
        .split_whitespace()
        .map(|t| {
            t.to_ascii_lowercase()
                .chars()
                .filter(|c| c.is_alphanumeric())
                .collect::<String>()
        })
        .filter(|t| t.len() > 2)
        .collect();
    if a_tokens.is_empty() || b_tokens.is_empty() {
        return 1.0;
    }
    let shared = a_tokens.iter().filter(|t| b_tokens.contains(*t)).count() as f32;
    shared / (a_tokens.len().max(b_tokens.len()) as f32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noise_score_penalizes_nav_chrome() {
        let noisy = "Sign up\nSearch\nFollow\n1\n!\n\n# Title\nBody text";
        let clean = "# Title\n\nBody text";
        assert!(structure_noise_score(noisy) > structure_noise_score(clean));
    }

    #[test]
    fn safety_checks_block_large_rewrite() {
        let original = "# Title\n\none two three four five six seven eight nine ten";
        let candidate = "# Title\n\none two";
        assert!(!passes_safety_checks(original, candidate));
    }
}
