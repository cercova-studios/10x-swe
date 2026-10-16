use ego_tree::NodeId;
use once_cell::sync::Lazy;
use scraper::{ElementRef, Html, Node, Selector};

static BODY_SEL: Lazy<Selector> = Lazy::new(|| Selector::parse("body").expect("valid selector"));
static HTML_SEL: Lazy<Selector> = Lazy::new(|| Selector::parse("html").expect("valid selector"));
static TECHNICAL_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("pre, code, math, table, sup, sub").expect("valid selector"));

/// Heuristic pruning must not remove technical content or its containers.
pub fn contains_technical_content(el: &ElementRef<'_>) -> bool {
    el.ancestors()
        .filter_map(ElementRef::wrap)
        .chain(std::iter::once(*el))
        .any(|node| {
            matches!(
                node.value().name(),
                "pre" | "code" | "math" | "table" | "sup" | "sub"
            )
        })
        || el.select(&TECHNICAL_SEL).next().is_some()
}

/// Parse an HTML fragment into a mutable document (`html > body > …`).
pub fn parse_fragment(input: &str) -> Html {
    Html::parse_fragment(input)
}

/// Serialize the fragment contents back to an HTML string.
pub fn serialize_fragment(doc: &Html) -> String {
    if let Some(body) = doc.select(&BODY_SEL).next() {
        return body.inner_html();
    }
    // scraper/html5ever may place fragment children directly under `<html>`.
    if let Some(html) = doc.select(&HTML_SEL).next() {
        return html.inner_html();
    }
    doc.html()
}

/// Detach nodes by id. Missing/already-detached ids are ignored.
pub fn detach_nodes(doc: &mut Html, ids: impl IntoIterator<Item = NodeId>) {
    for id in ids {
        if let Some(mut node) = doc.tree.get_mut(id) {
            node.detach();
        }
    }
}

/// Depth of a node (root = 0). Used to detach parents before children.
pub fn node_depth(doc: &Html, id: NodeId) -> usize {
    let mut depth = 0usize;
    let mut current = id;
    while let Some(node) = doc.tree.get(current) {
        match node.parent() {
            Some(parent) => {
                depth += 1;
                current = parent.id();
            }
            None => break,
        }
    }
    depth
}

/// Sort ids shallow-first so parent detach makes child detach a no-op.
pub fn sort_shallow_first(doc: &Html, ids: &mut [NodeId]) {
    ids.sort_by_key(|id| node_depth(doc, *id));
}

/// Lowercased class/id/data-* blob for partial-pattern matching.
pub fn attr_match_blob(el: &scraper::ElementRef<'_>) -> String {
    let mut blob = String::new();
    if let Some(class) = el.value().attr("class") {
        blob.push_str(class);
        blob.push(' ');
    }
    if let Some(id) = el.value().attr("id") {
        blob.push_str(id);
        blob.push(' ');
    }
    for (name, value) in el.value().attrs() {
        if name.starts_with("data-") {
            blob.push_str(name);
            blob.push(' ');
            blob.push_str(value);
            blob.push(' ');
        }
    }
    blob.to_ascii_lowercase()
}

/// Next element sibling of `id`, skipping non-element nodes.
pub fn next_element_sibling(doc: &Html, id: NodeId) -> Option<NodeId> {
    let node = doc.tree.get(id)?;
    for sibling in node.next_siblings() {
        if matches!(sibling.value(), Node::Element(_)) {
            return Some(sibling.id());
        }
    }
    None
}
