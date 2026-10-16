use distiller::{parse_html, types::DistillerOptions};

#[test]
fn preserves_highlighted_code_and_literal_whitespace_through_extraction() {
    let html = r#"<article><h1>Technical article</h1>
      <p>This introduction contains enough words to select the article and preserve its examples.</p>
      <pre><code class="language-rust">fn clz(x: u32) -&gt; u32 {
    let a = 2.0f64.powi(-<span>970</span>);
    <span>32</span> - ((a.to_bits() | x as u64) &gt;&gt; <span>52</span>) as u32
}


1
// related posts
// &amp;lt;script&amp;gt;
// href="javascript:example" onclick="example" srcdoc="example"
// ```
</code></pre><p>Release <span>2026</span> contains <span>3</span> examples.</p><p>2026</p></article>"#;
    let result = parse_html(
        html,
        Some("https://example.com/article"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap();
    assert!(md.contains("````rust\nfn clz(x: u32) -> u32 {\n    let a = 2.0f64.powi(-970);\n    32 - ((a.to_bits() | x as u64) >> 52) as u32\n}\n\n\n1\n// related posts\n// &lt;script&gt;\n// href=\"javascript:example\" onclick=\"example\" srcdoc=\"example\"\n// ```\n````"), "{md}");
    assert!(
        md.contains("// href=\"javascript:example\" onclick=\"example\" srcdoc=\"example\""),
        "{md}"
    );
    assert!(md.contains("Release 2026 contains 3 examples."), "{md}");
    assert!(md.lines().any(|line| line == "2026"), "{md}");
}

#[test]
fn preserves_inline_boundaries_math_and_safe_semantic_html() {
    let html = r#"<article><h1>Math article</h1>
    <p>Enough article words explain these equations and links without discarding the introduction.</p>
    <p>Hello<span>world</span>, <strong>bold</strong>! x<sup>2</sup> + y<sub>1</sub>; <code>a`b</code>. <code>a  b</code> <code>   </code></p>
    <p><math><msup><mi>x</mi><mn>2</mn></msup></math> and
    <math><semantics><mi>x</mi><annotation encoding="application/x-tex">x^2</annotation></semantics></math>.</p>
    <p><a href="/safe">safe</a><a href="java&#x73;cript:alert(1)">unsafe</a></p>
    <math><semantics><mi>x</mi><annotation encoding="application/x-tex">x+\text{related posts}</annotation></semantics></math>
    <math><semantics><mi>x</mi><annotation encoding="application/x-tex">x+
\text{related posts}
+y</annotation></semantics></math>
    <math onclick="alert(1)"><mi>x</mi></math>
    </article>"#;
    let result = parse_html(
        html,
        Some("https://example.com/article"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap();
    assert!(
        md.contains("Helloworld, **bold**! x<sup>2</sup> + y<sub>1</sub>; ``a`b``."),
        "{md}"
    );
    assert!(
        md.contains("<math><msup><mi>x</mi><mn>2</mn></msup></math>"),
        "{md}"
    );
    assert!(md.contains("$x^2$"), "{md}");
    assert!(md.contains(r"$x+\text{related posts}$"), "{md}");
    assert!(
        md.contains("x+\n\\text{related posts}\n+y</annotation>"),
        "{md}"
    );
    assert!(md.contains("`a  b` `   `"), "{md}");
    assert!(md.contains("[safe](https://example.com/safe)"), "{md}");
    assert!(
        !md.contains("javascript:") && !md.contains("onclick="),
        "{md}"
    );
}

#[test]
fn retains_table_columns_links_and_complex_cell_structure() {
    let html = r#"<article><h1>Tables</h1>
    <p>This article explains several table layouts with empty cells, links and spanning headers.</p>
    <table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td><td></td><td><a href="/cell">3</a></td></tr></table>
    <table><tr><th colspan="2">Spanning header</th></tr><tr><td rowspan="2">left</td><td>right</td></tr><tr><td>bottom</td></tr></table>
    <table><tr><th>Mixed</th><td>data</td></tr></table>
    </article>"#;
    let result = parse_html(
        html,
        Some("https://example.com/article"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap();
    assert!(
        md.contains("| 1 |  | [3](https://example.com/cell) |"),
        "{md}"
    );
    assert!(
        md.contains("<th colspan=\"2\">Spanning header</th>"),
        "{md}"
    );
    assert!(md.contains("<td rowspan=\"2\">left</td>"), "{md}");
    assert!(
        md.contains("<table><tbody><tr><th>Mixed</th><td>data</td></tr></tbody></table>"),
        "{md}"
    );
}

#[test]
fn article_journey_retains_every_source_code_block_and_math_expression() {
    use scraper::{Html, Selector};
    let html = include_str!("fixtures/vectorized-clz-and-ctz.html");
    let source = Html::parse_document(html);
    let result = parse_html(
        html,
        Some("https://purplesyringa.moe/blog/vectorized-clz-and-ctz/"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap();
    let pre = Selector::parse("pre").unwrap();
    let blocks: Vec<_> = source.select(&pre).collect();
    assert_eq!(blocks.len(), 7);
    for block in blocks {
        let text = block.text().collect::<String>();
        assert!(md.contains(&text), "missing source code block: {text}");
    }
    let math = Selector::parse("math").unwrap();
    let expressions: Vec<_> = source.select(&math).collect();
    assert_eq!(expressions.len(), 48);
    for expression in expressions {
        assert!(
            md.contains(&expression.html()),
            "missing source math: {}",
            expression.html()
        );
    }
    assert!(md.contains("powi(-970)") && md.contains(">> 52"));
}

#[test]
fn extracts_basic_article_markdown() {
    let html = r#"
    <html>
      <head><title>Test Page</title></head>
      <body>
        <nav>Menu</nav>
        <article>
          <h1>Test Page</h1>
          <p>Hello world from distiller.</p>
          <p>This should be preserved as content.</p>
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    "#;

    let result = parse_html(
        html,
        Some("https://example.com/post"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap_or_default();

    assert!(result.word_count > 5);
    assert!(md.contains("Hello world"));
    assert!(!md.to_lowercase().contains("menu"));
}

#[test]
fn fixture_smoke_produces_non_empty_output() {
    let html = include_str!("../tests/fixtures/general--cp4space-jordan-algebra.html");
    let result = parse_html(
        html,
        Some("https://cp4space.hatsya.com/example"),
        DistillerOptions::default(),
    );

    assert!(result.word_count > 100);
    assert!(!result.content.is_empty());
    assert!(result.content_markdown.as_deref().unwrap_or_default().len() > 100);
}

#[test]
fn trims_mintlify_style_chrome_and_related_blocks() {
    let html = r#"
    <html>
      <head><title>How we built a virtual filesystem for our Assistant</title></head>
      <body>
        <header>
          <a href="/contact/sales">Contact sales</a>
          <a href="/signup">Start for free</a>
        </header>
        <article>
          <h1>How we built a virtual filesystem for our Assistant</h1>
          <p>March 24, 2026</p>
          <p>Dens Sumesh</p>
          <p>RAG is great, until it isn't.</p>
          <h2>The Container Bottleneck</h2>
          <p>Most harnesses solve this by spinning up a sandbox.</p>
          <h2>Conclusion</h2>
          <p>By replacing sandboxes with a virtual filesystem, we got faster boot.</p>
          <h3>More blog posts to read</h3>
          <p>Docs on autopilot</p>
          <p>Share this article</p>
        </article>
        <footer>
          <h3>explore</h3>
        </footer>
      </body>
    </html>
    "#;

    let result = parse_html(
        html,
        Some("https://www.mintlify.com/blog/how-we-built-a-virtual-filesystem-for-our-assistant"),
        DistillerOptions::default(),
    );

    let md = result.content_markdown.unwrap_or_default().to_lowercase();
    assert!(md.contains("how we built a virtual filesystem for our assistant"));
    assert!(md.contains("the container bottleneck"));
    assert!(md.contains("conclusion"));

    assert!(!md.contains("contact sales"));
    assert!(!md.contains("start for free"));
    assert!(!md.contains("more blog posts to read"));
    assert!(!md.contains("docs on autopilot"));
    assert!(!md.contains("share this article"));
    assert!(!md.contains("explore"));
}

#[test]
fn injects_title_heading_when_article_body_lacks_h1() {
    let html = r#"
    <html>
      <head>
        <title>Claude Code Source Leak Analysis</title>
        <meta property="og:title" content="Claude Code Source Leak Analysis" />
      </head>
      <body>
        <article>
          <p><strong>Update:</strong> see HN discussions.</p>
          <p>This post starts with an update paragraph and no visible h1 in the extracted body.</p>
          <h2>Key Findings</h2>
          <p>A lot of details followed from source analysis.</p>
        </article>
      </body>
    </html>
    "#;

    let result = parse_html(
        html,
        Some("https://example.com/posts/claude-code-source-leak"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap_or_default();

    assert!(md.starts_with("# Claude Code Source Leak Analysis"));
    assert!(md.to_lowercase().contains("update:"));
    assert!(md.contains("## Key Findings"));
}

#[test]
fn keeps_paragraph_breaks_between_adjacent_paragraph_tags() {
    let html = r#"
    <html>
      <head><title>Paragraph Break Test</title></head>
      <body>
        <article>
          <h1>Paragraph Break Test</h1>
          <p><strong>Update:</strong> see HN discussions about this post: <a href="https://news.ycombinator.com/item?id=1">https://news.ycombinator.com/item?id=1</a></p>
          <p>I use Claude Code daily, so I wanted to inspect this package.</p>
        </article>
      </body>
    </html>
    "#;

    let result = parse_html(
        html,
        Some("https://example.com/post"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap_or_default();

    assert!(md.contains("item?id=1)\n\nI use Claude Code daily"));
}

#[test]
fn preserves_breaks_between_byline_date_and_body_in_block_wrappers() {
    let html = r#"
    <html>
      <head><title>How Microsoft Vaporized a Trillion Dollars</title></head>
      <body>
        <article>
          <h2>How Microsoft Vaporized a Trillion Dollars</h2>
          <h3>Inside the complacency and decisions that eroded trust in Azure.</h3>
          <div class="byline">
            <div><a href="https://substack.com/@isolveproblems">Axel Rietschin</a></div>
            <div>Mar 29, 2026</div>
          </div>
          <div>
            <p>This is the first of a series of articles in which you will learn what happened.</p>
          </div>
        </article>
      </body>
    </html>
    "#;

    let result = parse_html(
        html,
        Some("https://isolveproblems.substack.com/p/how-microsoft-vaporized-a-trillion"),
        DistillerOptions::default(),
    );
    let md = result.content_markdown.unwrap_or_default();

    assert!(md.contains("[Axel Rietschin](https://substack.com/@isolveproblems)"));
    assert!(md.contains("Mar 29, 2026"));
    let date_idx = md.find("Mar 29, 2026").unwrap_or(usize::MAX);
    let body_idx = md
        .find("This is the first of a series")
        .unwrap_or(usize::MAX);
    assert!(date_idx < body_idx);
    assert!(!md.contains("Mar 29, 2026This is the first of a series"));
}

#[test]
fn uses_substack_preload_extractor_for_body_and_metadata() {
    let html = r#"
    <!doctype html>
    <html>
      <head>
        <meta property="og:title" content="Fallback Title" />
      </head>
      <body>
        <script>
          window._preloads = JSON.parse("{\"feedData\":{\"initialPost\":{\"post\":{\"title\":\"How Microsoft Vaporized a Trillion-Dollar Bet\",\"subtitle\":\"A Substack post\",\"body_html\":\"<p>This is the first paragraph.</p><p>Second paragraph with details.</p>\",\"post_date\":\"2026-03-29T00:00:00Z\",\"publishedBylines\":[{\"name\":\"Axel Rietschin\"}]}}}}");
        </script>
      </body>
    </html>
    "#;

    let resp = parse_html(
        html,
        Some("https://isolveproblems.substack.com/p/how-microsoft-vaporized-a-trillion"),
        DistillerOptions::default(),
    );
    let md = resp
        .content_markdown
        .expect("markdown should be generated from extracted substack body");

    assert!(md.contains("# How Microsoft Vaporized a Trillion-Dollar Bet"));
    assert!(md.contains("This is the first paragraph."));
    assert!(md.contains("Second paragraph with details."));
    assert_eq!(resp.author, "Axel Rietschin");
    assert_eq!(resp.site, "Substack");
    assert_eq!(resp.published, "2026-03-29T00:00:00Z");
}

#[test]
fn uses_github_extractor_on_markdown_body() {
    let html = r#"
    <html><body>
      <article class="markdown-body">
        <h1>Project Title</h1>
        <p>This README includes substantial usage documentation and setup details.</p>
      </article>
    </body></html>
    "#;
    let resp = parse_html(
        html,
        Some("https://github.com/acme/project"),
        DistillerOptions::default(),
    );
    let md = resp.content_markdown.unwrap_or_default();
    assert!(md.contains("Project Title"));
    assert!(md.contains("substantial usage documentation"));
}

#[test]
fn uses_x_extractor_for_tweet_text() {
    let html = r#"
    <html><body>
      <article>
        <div data-testid="tweetText">This is a long-form tweet thread opener with enough words to pass extraction quality.</div>
      </article>
    </body></html>
    "#;
    let resp = parse_html(
        html,
        Some("https://x.com/someone/status/123"),
        DistillerOptions::default(),
    );
    let md = resp.content_markdown.unwrap_or_default();
    assert!(md.contains("long-form tweet thread opener"));
}
