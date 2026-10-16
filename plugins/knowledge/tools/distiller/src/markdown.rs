use once_cell::sync::Lazy;
use regex::Regex;

static MULTI_NEWLINE_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\n{3,}").expect("valid regex"));
static LINK_TO_DATE_RUNON_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)(\]\([^)]+\))(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec[a-z]*\s+\d{1,2},\s+\d{4})",
    )
    .expect("valid regex")
});
static DATE_TO_SENTENCE_RUNON_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4})([A-Z])",
    )
    .expect("valid regex")
});
static LINK_LINE_TO_SENTENCE_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?m)(\]\([^)]+\))\s*\n\s*([A-Z])").expect("valid regex"));
static ASIDE_TO_SENTENCE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?im)^(\s*\*\*(?:update|note|tl;dr):\*\*.*)\n([A-Z])").expect("valid regex")
});
static MIDLINE_HEADING_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?m)([^\n])\s(#{2,6}\s)").expect("valid regex"));
static HEADING_RUNON_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?m)^(#{1,6}\s[^\n]{6,180}?[)\.!?])\s+((?:I|We|Here|Join|This|That|The|Then|After|Before|But|So|If|In|Functional|Non-Functional)\b[^\n]*)$",
    )
    .expect("valid regex")
});
static INLINE_BOLD_SECTION_BREAK_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)([.!?])\s+\*\*((?:non-functional requirements|functional requirements|key components|my answer)\b[^*]*:)\*\*",
    )
    .expect("valid regex")
});
static STANDALONE_ACTION_LINK_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"^\[(Sign up|Sign in|Get app|Write|Search|Follow|Listen|Share)\]\([^)]+\)\s*$"#)
        .expect("valid regex")
});
static COUNTER_SUFFIX_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)^\d+(?:\.\d+)?[kmb]$").expect("valid regex"));
static TRAILING_PLACEHOLDER_BANG_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?m)\s!\s*$").expect("valid regex"));
static MEDIUM_TAG_LINK_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"^\[[^\]]+\]\(https?://(?:www\.)?medium\.com/tag/[^)]+\)\s*$"#)
        .expect("valid regex")
});

pub fn guess_title(markdown: &str) -> Option<String> {
    markdown
        .lines()
        .find(|l| l.starts_with("# "))
        .map(|l| l.trim_start_matches("# ").trim().to_string())
}

pub fn ensure_title_heading(markdown: &str, title: &str) -> String {
    let clean_title = title.trim();
    if clean_title.is_empty() {
        return markdown.to_string();
    }

    let has_top_heading = markdown.lines().any(|l| l.starts_with("# "));
    if has_top_heading {
        return markdown.to_string();
    }

    let normalized_md = markdown.to_lowercase();
    let normalized_title = clean_title.to_lowercase();
    let appears_early = normalized_md
        .chars()
        .take(400)
        .collect::<String>()
        .contains(&normalized_title);

    if appears_early {
        markdown.to_string()
    } else {
        format!("# {clean_title}\n\n{}", markdown.trim_start())
    }
}

pub fn postprocess_markdown(input: &str) -> String {
    map_prose(input, postprocess_prose)
}

// Code and semantic HTML are source content, never prose-cleanup candidates.
fn map_prose(input: &str, transform: fn(&str) -> String) -> String {
    let mut out = String::new();
    let mut prose = String::new();
    let mut fence: Option<(char, usize)> = None;
    let mut html_tag: Option<&str> = None;
    for line in input.split_inclusive('\n') {
        let trimmed = line.trim_start();
        let marker = trimmed.chars().next().unwrap_or(' ');
        let run = trimmed.chars().take_while(|c| *c == marker).count();
        let was_fenced = fence.is_some();
        if let Some((open, length)) = fence {
            if marker == open && run >= length && trimmed[run..].trim().is_empty() {
                fence = None;
            }
        } else if matches!(marker, '`' | '~') && run >= 3 {
            fence = Some((marker, run));
        }
        let lower = line.to_ascii_lowercase();
        if html_tag.is_none() && !was_fenced && fence.is_none() {
            html_tag = ["math", "table", "pre", "sup", "sub"]
                .into_iter()
                .find(|tag| lower.contains(&format!("<{tag}")));
        }
        let protected =
            was_fenced || fence.is_some() || html_tag.is_some() || line.contains(['`', '$']);
        if protected {
            if !prose.is_empty() {
                out.push_str(&transform(&prose));
                out.push_str("\n\n");
                prose.clear();
            }
            out.push_str(line);
        } else {
            prose.push_str(line);
        }
        if let Some(tag) = html_tag {
            if lower.contains(&format!("</{tag}>")) {
                html_tag = None;
            }
        }
    }
    out.push_str(&transform(&prose));
    out.trim().to_string()
}

fn postprocess_prose(input: &str) -> String {
    let mut out = input.to_string();
    out = normalize_metadata_runons(&out);
    out = strip_prose_chrome(&out);
    out = fix_bold_spans_crossing_headings(&out);
    out = MULTI_NEWLINE_RE.replace_all(&out, "\n\n").to_string();
    out.trim().to_string()
}

pub fn strip_known_chrome(input: &str) -> String {
    map_prose(input, strip_prose_chrome)
}

fn strip_prose_chrome(input: &str) -> String {
    let lower = input.to_ascii_lowercase();
    let cutoff_markers = [
        "more blog posts to read",
        "you might also like",
        "related posts",
        "related articles",
        "\n## explore",
        "\n### explore",
        "\n## responses (",
        "\n## more from ",
        "\n## written by ",
        "\n[## written by ",
        "\nread more from",
    ];

    let mut cutoff = input.len();
    for marker in cutoff_markers {
        if let Some(idx) = lower.find(marker) {
            cutoff = cutoff.min(idx);
        }
    }

    let mut out = input[..cutoff].to_string();
    let drop_line_markers = [
        "contact sales",
        "start for free",
        "share this article",
        "all articles",
        "press enter or click to view image in full size",
        "top highlight",
    ];
    out = out
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            let ll = trimmed.to_lowercase();
            if drop_line_markers.iter().any(|m| ll.contains(m)) {
                return false;
            }
            if ll.contains("stories in your inbox")
                || ll.contains("join medium for free")
                || ll.contains("remember me for faster sign in")
            {
                return false;
            }
            if matches!(
                trimmed,
                "Subscribe" | "Write a response" | "Cancel" | "Respond"
            ) {
                return false;
            }
            if STANDALONE_ACTION_LINK_RE.is_match(trimmed) {
                return false;
            }
            if MEDIUM_TAG_LINK_RE.is_match(trimmed) {
                return false;
            }
            if trimmed == "!" || trimmed == "·" {
                return false;
            }
            if trimmed == "**" {
                return false;
            }
            if COUNTER_SUFFIX_RE.is_match(trimmed) {
                return false;
            }
            true
        })
        .collect::<Vec<_>>()
        .join("\n");
    out = TRAILING_PLACEHOLDER_BANG_RE
        .replace_all(&out, "")
        .to_string();
    out
}

fn normalize_metadata_runons(input: &str) -> String {
    let out = LINK_TO_DATE_RUNON_RE
        .replace_all(input, "$1\n\n$2")
        .to_string();
    let out = DATE_TO_SENTENCE_RUNON_RE
        .replace_all(&out, "$1\n\n$2")
        .to_string();
    let out = LINK_LINE_TO_SENTENCE_RE
        .replace_all(&out, "$1\n\n$2")
        .to_string();
    let out = ASIDE_TO_SENTENCE_RE
        .replace_all(&out, "$1\n\n$2")
        .to_string();
    let out = MIDLINE_HEADING_RE.replace_all(&out, "$1\n\n$2").to_string();
    let out = INLINE_BOLD_SECTION_BREAK_RE
        .replace_all(&out, "$1\n\n**$2**")
        .to_string();
    HEADING_RUNON_RE.replace_all(&out, "$1\n\n$2").to_string()
}

fn fix_bold_spans_crossing_headings(input: &str) -> String {
    let mut in_bold = false;
    let mut out: Vec<String> = Vec::new();

    for line in input.lines() {
        let mut current = line.to_string();
        let trimmed = current.trim_start();
        if in_bold && trimmed.starts_with("##") {
            if let Some(prev_idx) = out.iter().rposition(|l| !l.trim().is_empty()) {
                out[prev_idx].push_str("**");
            } else {
                current = format!("** {current}");
            }
            if current.trim_end().ends_with("**") {
                if let Some(idx) = current.rfind("**") {
                    current.replace_range(idx..idx + 2, "");
                }
                current = current.trim_end().to_string();
            }
            if out.last().map(|l| !l.trim().is_empty()).unwrap_or(false) {
                out.push(String::new());
            }
        }

        let marker_count = count_marker(&current, "**");
        if marker_count % 2 == 1 {
            in_bold = !in_bold;
        }
        if current.trim_end().ends_with("**") && marker_count % 2 == 1 {
            if let Some(idx) = current.rfind("**") {
                current.replace_range(idx..idx + 2, "");
                current = current.trim_end().to_string();
            }
            in_bold = false;
        }
        if current.trim() == "**" {
            continue;
        }
        out.push(current);
    }

    out.join("\n")
}

fn count_marker(haystack: &str, needle: &str) -> usize {
    haystack.match_indices(needle).count()
}

#[cfg(test)]
mod tests {
    use super::{fix_bold_spans_crossing_headings, normalize_metadata_runons, strip_known_chrome};

    #[test]
    fn strips_standalone_action_links_but_retains_numeric_content() {
        let input = "\
[Listen](https://example.com)\n\
1\n\
!\n\
Real paragraph.\n";
        let out = strip_known_chrome(input);
        assert!(!out.contains("[Listen]("));
        assert!(out.lines().any(|l| l.trim() == "1"));
        assert!(!out.lines().any(|l| l.trim() == "!"));
        assert!(out.contains("Real paragraph."));
    }

    #[test]
    fn inserts_break_after_update_line() {
        let input = " **Update:** see HN discussions: [https://news.ycombinator.com/item?id=1](https://news.ycombinator.com/item?id=1)\nI use Claude Code daily.";
        let out = normalize_metadata_runons(input);
        assert!(out.contains("item?id=1)\n\nI use Claude Code daily."));
    }

    #[test]
    fn splits_midline_heading_markers() {
        let input = "Intro sentence. ## Step 1: Requirements";
        let out = normalize_metadata_runons(input);
        assert_eq!(out, "Intro sentence.\n\n## Step 1: Requirements");
    }

    #[test]
    fn strips_counter_suffix_lines() {
        let input = "1.5K\n\nBody paragraph";
        let out = strip_known_chrome(input);
        assert!(!out.contains("1.5K"));
        assert!(out.contains("Body paragraph"));
    }

    #[test]
    fn strips_trailing_placeholder_bang() {
        let input = "I stopped myself. !\n\n## Step 1";
        let out = strip_known_chrome(input);
        assert!(out.contains("I stopped myself."));
        assert!(!out.contains(". !"));
    }

    #[test]
    fn strips_orphaned_bold_marker_lines() {
        let input = "**\n## Step 1";
        let out = strip_known_chrome(input);
        assert!(!out.lines().any(|l| l.trim() == "**"));
        assert!(out.contains("## Step 1"));
    }

    #[test]
    fn closes_bold_before_heading_boundary() {
        let input = "**Lead text that should stay bold\n## Step 1: Requirements still bold:**";
        let out = fix_bold_spans_crossing_headings(input);
        assert!(out.contains("Lead text that should stay bold"));
        assert!(out
            .contains("Lead text that should stay bold**\n\n## Step 1: Requirements still bold:"));
        assert!(!out.trim_end().ends_with("**"));
    }

    #[test]
    fn splits_heading_line_with_runon_sentence() {
        let input = "## Step 1: Requirements (The 5 Minutes I Actually Got Right) I asked clarification questions before touching the whiteboard.";
        let out = normalize_metadata_runons(input);
        assert_eq!(
            out,
            "## Step 1: Requirements (The 5 Minutes I Actually Got Right)\n\nI asked clarification questions before touching the whiteboard."
        );
    }

    #[test]
    fn strips_medium_signup_block_lines() {
        let input = "\
## Get Emily’s stories in your inbox
Join Medium for free to get updates from this writer.
Subscribe
Subscribe
- [x] Remember me for faster sign in
Real paragraph.";
        let out = strip_known_chrome(input);
        assert!(!out.contains("stories in your inbox"));
        assert!(!out.contains("Join Medium for free"));
        assert!(!out.contains("Subscribe"));
        assert!(!out.contains("Remember me for faster sign in"));
        assert!(out.contains("Real paragraph."));
    }

    #[test]
    fn trims_odd_trailing_bold_marker_on_line() {
        let input = "The interviewer didn’t let me stay at the high level. They pushed.**";
        let out = fix_bold_spans_crossing_headings(input);
        assert_eq!(
            out,
            "The interviewer didn’t let me stay at the high level. They pushed."
        );
    }

    #[test]
    fn splits_inline_bold_section_labels() {
        let input =
            "- The output feeds directly into pricing. **Non-Functional Requirements I Proposed:**";
        let out = normalize_metadata_runons(input);
        assert_eq!(
            out,
            "- The output feeds directly into pricing.\n\n**Non-Functional Requirements I Proposed:**"
        );
    }

    #[test]
    fn cuts_off_medium_written_by_section() {
        let input = "\
Body paragraph.
[## Written by Alice](https://medium.com/@alice)
Followers block.";
        let out = strip_known_chrome(input);
        assert!(out.contains("Body paragraph."));
        assert!(!out.contains("Written by Alice"));
        assert!(!out.contains("Followers block."));
    }

    #[test]
    fn strips_medium_tag_links() {
        let input = "\
[System Design Interview](https://medium.com/tag/system-design-interview)
Body paragraph.";
        let out = strip_known_chrome(input);
        assert!(!out.contains("system-design-interview"));
        assert!(out.contains("Body paragraph."));
    }
}
