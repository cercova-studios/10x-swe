use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ParseMode {
    #[default]
    Markdown,
    Json,
    Epub,
}

#[derive(Debug, Serialize, Clone, Default)]
pub struct MetaTag {
    pub name: Option<String>,
    pub property: Option<String>,
    pub content: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
pub struct DistillerResponse {
    pub content: String,
    pub title: String,
    pub description: String,
    pub domain: String,
    pub favicon: String,
    pub image: String,
    pub language: String,
    pub parse_time_ms: u64,
    pub published: String,
    pub author: String,
    pub site: String,
    pub schema_org_data: Option<serde_json::Value>,
    pub word_count: usize,
    pub content_markdown: Option<String>,
    pub meta_tags: Vec<MetaTag>,
}

#[derive(Debug, Clone)]
pub struct DistillerOptions {
    pub debug: bool,
    pub remove_exact_selectors: bool,
    pub remove_partial_selectors: bool,
    pub remove_hidden_elements: bool,
    pub remove_low_scoring: bool,
    pub remove_small_images: bool,
    pub remove_content_patterns: bool,
    pub language: Option<String>,
    pub proxy_url: Option<String>,
    pub mode: ParseMode,
    pub llm: bool,
}

impl Default for DistillerOptions {
    fn default() -> Self {
        Self {
            debug: false,
            remove_exact_selectors: true,
            remove_partial_selectors: true,
            remove_hidden_elements: true,
            remove_low_scoring: true,
            remove_small_images: true,
            remove_content_patterns: true,
            language: None,
            proxy_url: None,
            mode: ParseMode::Markdown,
            llm: false,
        }
    }
}
