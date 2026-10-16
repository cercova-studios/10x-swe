use pulldown_cmark::{Event, Parser, Tag, TagEnd};
pub fn html(markdown: &str) -> String {
    let events = Parser::new(markdown).map(|event| match event {
        Event::Html(_) | Event::InlineHtml(_) => Event::Text("".into()),
        Event::Start(Tag::Image { .. } | Tag::Link { .. }) => Event::Text("".into()),
        Event::End(TagEnd::Image | TagEnd::Link) => Event::Text("".into()),
        event => event,
    });
    let mut out = String::new();
    pulldown_cmark::html::push_html(&mut out, events);
    out
}
pub fn terminal(markdown: &str) -> String {
    let mut out = String::new();
    for e in Parser::new(markdown) {
        match e {
            Event::Text(t) | Event::Code(t) => out.push_str(&crate::model::clean(&t)),
            Event::Start(Tag::Heading { .. } | Tag::Strong) => out.push_str("\x1b[1m"),
            Event::End(TagEnd::Heading(_) | TagEnd::Strong) => out.push_str("\x1b[0m\n"),
            Event::Start(Tag::Emphasis) => out.push_str("\x1b[3m"),
            Event::End(TagEnd::Emphasis) => out.push_str("\x1b[0m"),
            Event::Start(Tag::Item) => out.push_str("• "),
            Event::End(TagEnd::Paragraph | TagEnd::Item) | Event::SoftBreak | Event::HardBreak => {
                out.push('\n')
            }
            _ => {}
        }
    }
    out
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hostile_markdown_stays_inert() {
        let h = html(
            "<script>bad()</script>\n\n![remote](https://a.com/img)\n[x](javascript:alert(1))\n**safe**",
        );
        assert!(!h.contains("<script"));
        assert!(!h.contains("<img"));
        assert!(!h.contains("href="));
        assert!(h.contains("<strong>safe</strong>"));
    }
}
