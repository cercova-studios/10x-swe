use std::time::{SystemTime, UNIX_EPOCH};

pub fn debug(enabled: bool, stage: &str, message: impl AsRef<str>) {
    if !enabled {
        return;
    }
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    eprintln!(
        "{{\"ts_ms\":{},\"level\":\"debug\",\"stage\":\"{}\",\"msg\":\"{}\"}}",
        ts,
        escape(stage),
        escape(message.as_ref())
    );
}

pub fn removal_step(
    enabled: bool,
    step: &str,
    reason: &str,
    before_words: usize,
    after_words: usize,
    before_chars: usize,
    after_chars: usize,
) {
    if !enabled {
        return;
    }
    debug(
        true,
        "pipeline.removal",
        format!(
            "step={step} reason={reason} before_words={before_words} after_words={after_words} before_chars={before_chars} after_chars={after_chars}"
        ),
    );
}

fn escape(input: &str) -> String {
    input
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
}
