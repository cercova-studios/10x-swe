//! Terminal capture owns drafts; the importer alone owns publication authority.
use crate::{Cli, Cmd, Filters, importer, index, knowledge, model, search, state, tui};
use anyhow::{Result, ensure};
use crossterm::{
    event::{self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    Terminal,
    backend::CrosstermBackend,
    layout::{Alignment, Constraint, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Clear, List, ListItem, ListState, Paragraph, Wrap},
};
use serde_json::{Value, json};
use std::{
    io::{self, IsTerminal},
    path::Path,
    time::Duration,
};

struct Guard;
impl Drop for Guard {
    fn drop(&mut self) {
        let _ = execute!(io::stdout(), DisableBracketedPaste, LeaveAlternateScreen);
        let _ = disable_raw_mode();
    }
}
fn enter() -> Result<()> {
    enable_raw_mode()?;
    execute!(io::stdout(), EnterAlternateScreen, EnableBracketedPaste)?;
    Ok(())
}
#[derive(Default)]
struct Draft {
    fields: [String; 3],
    field: usize,
}
impl Draft {
    fn from_drop(text: &str) -> Result<Self> {
        // A drop is data, never a shell command or implicit publication approval.
        let url = model::validate_url(text)?;
        let kind = model::classify(&url).0.to_owned();
        Ok(Self {
            fields: [url, String::new(), kind],
            field: 1,
        })
    }
    fn record(&self, account: &str) -> Result<model::Record> {
        let mut r = model::Record::new(
            "manual",
            account,
            &model::hash(self.fields[0].trim()),
            &self.fields[0],
        )?;
        r.title = self.fields[1].clone();
        if !self.fields[2].is_empty() {
            r.kind = self.fields[2].clone();
            r.kind_source = "manual".into();
        }
        r.validate()?;
        Ok(r)
    }
}
struct Review {
    plan: importer::Plan,
    at: usize,
    confirmation: Option<String>,
    edit: Option<Draft>,
}
impl Review {
    fn new(mut plan: importer::Plan) -> Self {
        for c in &mut plan.candidates {
            c.selected = false;
        }
        Self {
            plan,
            at: 0,
            confirmation: None,
            edit: None,
        }
    }
    fn approve(&self) -> Result<String> {
        let n = self.plan.candidates.iter().filter(|c| c.selected).count();
        ensure!(
            n > 0 && self.confirmation.as_deref() == Some(&format!("PUBLISH {n}")),
            "Type the exact PUBLISH count; nothing written"
        );
        self.plan.selected()?;
        self.plan.id()
    }
    fn toggle(&mut self) {
        if let Some(c) = self.plan.candidates.get_mut(self.at)
            && c.status != "pruned"
        {
            c.selected = !c.selected;
        }
        self.confirmation = None;
    }
}
enum Panel {
    Browse,
    Query(String),
    Filters([String; 3], usize),
    Draft(Draft),
    Review(Review),
    Details(String),
    Help,
}
struct App {
    panel: Panel,
    rows: Vec<Value>,
    selected: usize,
    filter: search::Filter,
    query: String,
    message: String,
    scroll: u16,
}
impl App {
    fn drop_link(&mut self, text: &str) -> Result<()> {
        ensure!(
            matches!(self.panel, Panel::Browse),
            "Finish or cancel the current panel before dropping another link"
        );
        self.panel = Panel::Draft(Draft::from_drop(text)?);
        Ok(())
    }
}
fn markdown(input: &str) -> Text<'static> {
    use pulldown_cmark::{Event as M, Parser, Tag, TagEnd};
    let mut lines = vec![Line::default()];
    let (mut bold, mut italic, mut code) = (false, false, false);
    for e in Parser::new(input) {
        match e {
            M::Start(Tag::Heading { .. } | Tag::Strong) => bold = true,
            M::End(TagEnd::Heading(_) | TagEnd::Strong) => {
                bold = false;
                lines.push(Line::default());
            }
            M::Start(Tag::Emphasis) => italic = true,
            M::End(TagEnd::Emphasis) => italic = false,
            M::Start(Tag::CodeBlock(_)) => code = true,
            M::End(TagEnd::CodeBlock) => {
                code = false;
                lines.push(Line::default());
            }
            M::Start(Tag::Item) => lines.last_mut().unwrap().spans.push(Span::raw("• ")),
            M::Text(t) | M::Code(t) => {
                let mut style = Style::default();
                if bold {
                    style = style.add_modifier(Modifier::BOLD);
                }
                if italic {
                    style = style.add_modifier(Modifier::ITALIC);
                }
                if code {
                    style = style.fg(Color::Cyan);
                }
                let cleaned = model::clean(&t);
                for (i, part) in cleaned.split('\n').enumerate() {
                    if i > 0 {
                        lines.push(Line::default());
                    }
                    lines
                        .last_mut()
                        .unwrap()
                        .spans
                        .push(Span::styled(part.to_owned(), style));
                }
            }
            M::End(TagEnd::Paragraph | TagEnd::Item) | M::SoftBreak | M::HardBreak => {
                lines.push(Line::default())
            }
            _ => {} // Raw HTML, image fetches and link destinations remain inert.
        }
    }
    Text::from(lines)
}
fn call(home: &Path, config: &knowledge::Config, include: bool, command: Cmd) -> Result<Value> {
    let empty = knowledge::Config::default();
    crate::run_with_records(
        &Cli {
            home: Some(home.into()),
            json: true,
            records: None,
            plan: None,
            lexical_only: false,
            command: Some(command),
        },
        if include { config } else { &empty },
    )
}
fn filters(f: &search::Filter) -> Filters {
    Filters {
        sources: f.sources.clone(),
        kinds: f.kinds.clone(),
        domain: f.domain.clone(),
    }
}
fn refresh(
    app: &mut App,
    home: &Path,
    config: &knowledge::Config,
    include: bool,
    lexical: bool,
) -> Result<()> {
    app.rows.clear();
    app.selected = 0;
    let rows = if app.query.trim().is_empty() {
        app.filter
            .books(&state::db(home)?)?
            .into_iter()
            .map(serde_json::to_value)
            .collect::<std::result::Result<Vec<_>, _>>()?
    } else {
        let value = call(
            home,
            config,
            include,
            Cmd::Search {
                query: app.query.clone(),
                filters: filters(&app.filter),
                limit: 100,
                lexical_only: lexical,
                no_graph: false,
                list: true,
                rich: false,
            },
        )?;
        let mut rows = value[if include { "bookmarks" } else { "results" }]
            .as_array()
            .cloned()
            .unwrap_or_default();
        if include {
            for key in ["insights", "skills", "sessions"] {
                for hit in value[key].as_array().into_iter().flatten() {
                    rows.push(hit["node"].clone());
                }
            }
        }
        rows
    };
    app.rows = rows;
    app.selected = 0;
    app.message = format!(
        "{} results · {} · {}",
        app.rows.len(),
        if lexical { "keyword" } else { "local hybrid" },
        if include {
            "combined knowledge; separate corpus ranks"
        } else {
            "bookmarks"
        }
    );
    Ok(())
}
fn text(v: &Value, key: &str) -> String {
    model::clean(v[key].as_str().unwrap_or(""))
}
fn draw(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, app: &App) -> Result<()> {
    terminal.draw(|f| {
        let areas = Layout::vertical([Constraint::Min(1), Constraint::Length(3)]).margin(2).split(f.area());
        if app.rows.is_empty() && app.query.is_empty() {
            let center = Layout::vertical([Constraint::Fill(1), Constraint::Length(3), Constraint::Fill(1)]).split(areas[0])[1];
            f.render_widget(Paragraph::new(vec![Line::from("bookmarkdrop").style(Style::default().fg(Color::Gray)), Line::from(""), Line::from("drop or paste a link").style(Style::default().fg(Color::DarkGray))]).alignment(Alignment::Center), center);
        }
        let items: Vec<_> = app.rows.iter().map(|v| ListItem::new(format!("{} [{}]\n{}", text(v, "title").chars().chain(text(v,"label").chars()).collect::<String>().replace('\n', " "), text(v,"kind"), text(v,"url")))).collect();
        let mut selection = ListState::default().with_selected(if items.is_empty() {None} else {Some(app.selected)});
        if !items.is_empty() {
            f.render_stateful_widget(List::new(items).highlight_style(Style::default().fg(Color::Cyan)).highlight_symbol("› "), areas[0], &mut selection);
        }
        f.render_widget(Paragraph::new(format!("{}\n/ search    a capture    ? help    q quit", model::clean(&app.message))).style(Style::default().fg(Color::DarkGray)).wrap(Wrap {trim:false}), areas[1]);
        let overlay = match &app.panel {
            Panel::Browse => None,
            Panel::Help => Some(("Keys", Text::raw("/ search · f filters · a capture · r import review · g graph\nEnter details · o open · j/k select · PgUp/PgDn scroll\nPaste one HTTP(S) URL · Tab switches capture fields\nEsc cancels · q/Ctrl+C quits\n\nSafari URL drag requires support from the terminal emulator.\nWezTerm on macOS accepts file drops, not Safari URL drops.\nCopy the link and paste it here instead. Nothing publishes until reviewed."))),
            Panel::Query(q) => Some(("Search", Text::raw(format!("{q}_\nEnter search · Esc cancel")))),
            Panel::Filters(fields, at) => Some(("Bookmark filters", Text::raw(format!("{} Sources (comma separated): {}\n{} Kinds: {}\n{} Domain: {}\nTab changes field · Enter apply · Esc cancel", if *at==0 {">"} else {" "}, fields[0], if *at==1 {">"} else {" "}, fields[1], if *at==2 {">"} else {" "}, fields[2])))),
            Panel::Draft(d) => Some(("Capture · draft only", draft_text(d))),
            Panel::Review(r) => {
                let selected = r.plan.candidates.iter().filter(|c|c.selected).count();
                let body = if let Some(d) = &r.edit { draft_text(d) }
                else if let Some(confirm) = &r.confirmation {
                    Text::raw(format!("PUBLIC: rsnair.tech · {} selected URLs\n{}\nType PUBLISH {selected}: {confirm}_\nEnter confirms · Esc returns to review", selected, r.plan.candidates.iter().filter(|c|c.selected).map(|c|format!("{} — {}", model::clean(&c.title), c.url)).collect::<Vec<_>>().join("\n")))
                } else if let Some(c) = r.plan.candidates.get(r.at) {
                    markdown(&format!("# {} / {} · [{}] {}\n\n{}\n\nType: {} · selected: {}\n\nPublic: rsnair.tech (URLs and titles). Metadata stays outside the feed.\n\n{}\n\nEvidence: {}\n\nSpace include/exclude · j/k next/previous · e edit title/type · p final review · Esc cancel", r.at+1, r.plan.candidates.len(), c.status, model::clean(&c.title), c.url, c.kind, c.selected, c.origins.iter().map(|o|format!("## {} / {}\nTags: {}\n\n{}\n\n{}", model::clean(&o.provider), model::clean(&o.account), model::clean(&o.tags.join(", ")), o.excerpt, o.note)).collect::<Vec<_>>().join("\n\n"), c.evidence))
                } else { Text::raw("No candidates; Esc returns without writes") };
                Some(("Publication review · nothing selected by default", body))
            }
            Panel::Details(s) => Some(("Details · PgUp/PgDn scroll · Esc close", markdown(s))),
        };
        if let Some((title, body)) = overlay {
            let rect = areas[0];
            f.render_widget(Clear, rect);
            f.render_widget(Paragraph::new(body).block(Block::bordered().title(title)).wrap(Wrap{trim:false}).scroll((app.scroll,0)), rect);
        }
    })?;
    Ok(())
}
fn draft_text(d: &Draft) -> Text<'static> {
    Text::raw(format!(
        "{} URL: {}\n{} Public title: {}\n{} Type: {}\n\nTab changes field · left/right cycles type · Enter preview · Esc cancel\nKinds: {}\nNo publication occurs before final PUBLISH confirmation.",
        if d.field == 0 { ">" } else { " " },
        model::clean(&d.fields[0]),
        if d.field == 1 { ">" } else { " " },
        model::clean(&d.fields[1]),
        if d.field == 2 { ">" } else { " " },
        d.fields[2],
        model::KINDS.join(", ")
    ))
}
fn edit(fields: &mut [String], at: &mut usize, code: KeyCode, max: usize) {
    match code {
        KeyCode::Tab => *at = (*at + 1) % fields.len(),
        KeyCode::BackTab => *at = (*at + fields.len() - 1) % fields.len(),
        KeyCode::Backspace => {
            fields[*at].pop();
        }
        KeyCode::Char(c) if !c.is_control() && fields[*at].len() + c.len_utf8() <= max => {
            fields[*at].push(c)
        }
        _ => {}
    }
}
fn edit_draft(d: &mut Draft, code: KeyCode) {
    if d.field == 2 && matches!(code, KeyCode::Left | KeyCode::Right) {
        let at = model::KINDS
            .iter()
            .position(|k| *k == d.fields[2])
            .unwrap_or(6);
        let next = if code == KeyCode::Right {
            (at + 1) % 7
        } else {
            (at + 6) % 7
        };
        d.fields[2] = model::KINDS[next].into();
    } else {
        edit(&mut d.fields, &mut d.field, code, 8192);
    }
}
fn preview(home: &Path, d: &Draft) -> Result<importer::Plan> {
    let record = d.record(&state::account(home, "neon")?)?;
    importer::preview(
        index::merge(vec![record], &[], &[], None),
        json!({"action":"tui-capture"}),
        &crate::store(home)?,
        json!({}),
    )
}
fn publish(home: &Path, review: &Review) -> Result<Value> {
    let approval = review.approve()?;
    let store = crate::store(home)?;
    let result = importer::apply(home, &review.plan, &approval, &store)?;
    receipt_summary(&result)?;
    Ok(result)
}
fn receipt_summary(result: &Value) -> Result<String> {
    let batches = result["batches"]
        .as_array()
        .filter(|b| !b.is_empty())
        .ok_or_else(|| {
            anyhow::anyhow!("Missing confirmed publication receipts; inspect pending writes")
        })?;
    let mut totals = [0u64; 3];
    for batch in batches {
        for (i, key) in ["new", "duplicate", "pruned"].iter().enumerate() {
            totals[i] += batch[key].as_u64().ok_or_else(|| {
                anyhow::anyhow!("Invalid publication receipt; inspect pending writes")
            })?;
        }
    }
    Ok(format!(
        "Confirmed receipts: {} new, {} existing (public titles preserved), {} blocked by cleanup",
        totals[0], totals[1], totals[2]
    ))
}
pub fn run(
    home: &Path,
    config: &knowledge::Config,
    include: bool,
    filter: search::Filter,
    lexical: bool,
    plan: Option<&Path>,
) -> Result<()> {
    ensure!(
        io::stdin().is_terminal() && io::stdout().is_terminal(),
        "TUI requires a terminal; use --json commands for agents"
    );
    let mut app = App {
        panel: Panel::Browse,
        rows: vec![],
        selected: 0,
        filter,
        query: String::new(),
        message: String::new(),
        scroll: 0,
    };
    if let Some(path) = plan {
        let plan: importer::Plan = state::read_json(path)?;
        ensure!(
            plan.schema == 1 && plan.destination.len() == 64 && plan.candidates.len() <= 10000,
            "Invalid review plan"
        );
        app.panel = Panel::Review(Review::new(plan));
    }
    let _guard = Guard;
    enter()?;
    let mut terminal = Terminal::new(CrosstermBackend::new(io::stdout()))?;
    loop {
        draw(&mut terminal, &app)?;
        while !event::poll(Duration::from_millis(100))? {}
        let result = (|| -> Result<bool> {
            match event::read()? {
                Event::Paste(s) => {
                    match &mut app.panel {
                        Panel::Browse => app.drop_link(&s)?,
                        Panel::Draft(d) => {
                            ensure!(
                                s.len() <= 8192
                                    && model::valid_text(&s, 8192)
                                    && !s.contains(['\n', '\r']),
                                "Paste one field at a time; no commands or multiple links"
                            );
                            d.fields[d.field] = s;
                        }
                        Panel::Query(q) => {
                            ensure!(
                                s.len() <= 4096 && model::valid_text(&s, 4096),
                                "Invalid query"
                            );
                            *q = s;
                        }
                        // Pasted text never counts as a publication confirmation.
                        _ => anyhow::bail!(
                            "Paste is available in search or capture; confirmation must be typed"
                        ),
                    }
                }
                Event::Key(k) if k.kind != event::KeyEventKind::Release => {
                    if k.modifiers.contains(KeyModifiers::CONTROL) && k.code == KeyCode::Char('c') {
                        return Ok(false);
                    }
                    if k.code == KeyCode::Esc {
                        match &mut app.panel {
                            Panel::Review(r) if r.edit.is_some() => r.edit = None,
                            Panel::Review(r) if r.confirmation.is_some() => r.confirmation = None,
                            _ => app.panel = Panel::Browse,
                        }
                        app.scroll = 0;
                        return Ok(true);
                    }
                    if matches!(k.code, KeyCode::PageDown | KeyCode::PageUp) {
                        app.scroll = if k.code == KeyCode::PageDown {
                            app.scroll.saturating_add(10)
                        } else {
                            app.scroll.saturating_sub(10)
                        };
                        return Ok(true);
                    }
                    match &mut app.panel {
                        Panel::Query(q) => {
                            if k.code == KeyCode::Enter {
                                app.query = q.clone();
                                refresh(&mut app, home, config, include, lexical)?;
                                app.panel = Panel::Browse;
                            } else {
                                let mut fields = [q.clone()];
                                edit(&mut fields, &mut 0, k.code, 4096);
                                *q = fields[0].clone();
                            }
                        }
                        Panel::Filters(fields, at) => {
                            if k.code == KeyCode::Enter {
                                let csv = |s: &str| {
                                    s.split(',')
                                        .map(str::trim)
                                        .filter(|s| !s.is_empty())
                                        .map(str::to_owned)
                                        .collect()
                                };
                                let mut filter = search::Filter {
                                    sources: csv(&fields[0]),
                                    kinds: csv(&fields[1]),
                                    domain: if fields[2].trim().is_empty() {
                                        None
                                    } else {
                                        Some(fields[2].trim().into())
                                    },
                                };
                                filter.validate()?;
                                app.filter = filter;
                                refresh(&mut app, home, config, include, lexical)?;
                                app.panel = Panel::Browse;
                            } else {
                                edit(fields, at, k.code, 4096);
                            }
                        }
                        Panel::Draft(d) => {
                            if k.code == KeyCode::Enter {
                                d.record("draft")?;
                                app.message =
                                    "Checking destination duplicates and tombstones…".into();
                                draw(&mut terminal, &app)?;
                                let Panel::Draft(d) = &app.panel else {
                                    unreachable!()
                                };
                                app.panel = Panel::Review(Review::new(preview(home, d)?));
                                app.scroll = 0;
                            } else {
                                edit_draft(d, k.code);
                            }
                        }
                        Panel::Review(r) => {
                            if let Some(d) = &mut r.edit {
                                if k.code == KeyCode::Enter {
                                    d.record("draft")?;
                                    let c = &mut r.plan.candidates[r.at];
                                    ensure!(
                                        d.fields[0] == c.url,
                                        "Review URLs cannot change; start a new capture"
                                    );
                                    c.title = d.fields[1].clone();
                                    c.kind = d.fields[2].clone();
                                    r.edit = None;
                                    r.confirmation = None;
                                } else {
                                    edit_draft(d, k.code);
                                }
                            } else if let Some(c) = &mut r.confirmation {
                                if k.code == KeyCode::Enter {
                                    r.approve()?;
                                    app.message =
                                        "Publishing reviewed selection; waiting for receipts…"
                                            .into();
                                    draw(&mut terminal, &app)?;
                                    let Panel::Review(r) = &app.panel else {
                                        unreachable!()
                                    };
                                    let result = publish(home, r)?;
                                    let summary = receipt_summary(&result)?;
                                    app.panel = Panel::Browse;
                                    // Refresh from Neon, so preserved titles and pruning outcomes remain authoritative.
                                    let cache = call(
                                        home,
                                        config,
                                        false,
                                        Cmd::Sync {
                                            sources: vec!["neon".into()],
                                            lexical_only: true,
                                            offline: false,
                                        },
                                    );
                                    if let Err(e) = cache {
                                        app.message = format!(
                                            "{summary}. Cache refresh failed: {e}; run bkd sync --source neon. Publication is already confirmed."
                                        );
                                    } else {
                                        let refreshed =
                                            refresh(&mut app, home, config, include, lexical);
                                        app.message = format!(
                                            "{summary}. Cache refreshed; bkd sync --offline builds new vectors.{}",
                                            refreshed
                                                .err()
                                                .map(|e| format!(" Search refresh failed: {e}"))
                                                .unwrap_or_default()
                                        );
                                    }
                                } else {
                                    let mut fields = [c.clone()];
                                    edit(&mut fields, &mut 0, k.code, 40);
                                    *c = fields[0].clone();
                                }
                            } else {
                                match k.code {
                                    KeyCode::Char(' ') => r.toggle(),
                                    KeyCode::Char('j') | KeyCode::Down => {
                                        r.at = (r.at + 1)
                                            .min(r.plan.candidates.len().saturating_sub(1));
                                        app.scroll = 0;
                                    }
                                    KeyCode::Char('k') | KeyCode::Up => {
                                        r.at = r.at.saturating_sub(1);
                                        app.scroll = 0;
                                    }
                                    KeyCode::Char('e') => {
                                        if let Some(c) = r.plan.candidates.get(r.at) {
                                            r.edit = Some(Draft {
                                                fields: [
                                                    c.url.clone(),
                                                    c.title.clone(),
                                                    c.kind.clone(),
                                                ],
                                                field: 1,
                                            });
                                            app.scroll = 0;
                                        }
                                    }
                                    KeyCode::Char('p') => {
                                        ensure!(
                                            r.plan.candidates.iter().any(|c| c.selected),
                                            "Nothing selected; nothing written"
                                        );
                                        r.confirmation = Some(String::new());
                                        app.scroll = 0;
                                    }
                                    _ => {}
                                }
                            }
                        }
                        Panel::Details(_) | Panel::Help => {}
                        Panel::Browse => match k.code {
                            KeyCode::Char('q') => return Ok(false),
                            KeyCode::Char('?') => app.panel = Panel::Help,
                            KeyCode::Char('/') => {
                                app.panel = Panel::Query(app.query.clone());
                                app.scroll = 0;
                            }
                            KeyCode::Char('f') => {
                                app.panel = Panel::Filters(
                                    [
                                        app.filter.sources.join(","),
                                        app.filter.kinds.join(","),
                                        app.filter.domain.clone().unwrap_or_default(),
                                    ],
                                    0,
                                );
                                app.scroll = 0;
                            }
                            KeyCode::Char('a') => {
                                app.panel = Panel::Draft(Draft {
                                    fields: [String::new(), String::new(), String::new()],
                                    field: 0,
                                });
                                app.scroll = 0;
                            }
                            // Some emulators deliver drops as ordinary key events.
                            KeyCode::Char(c @ ('h' | 'H')) => {
                                app.panel = Panel::Draft(Draft {
                                    fields: [c.to_string(), String::new(), String::new()],
                                    field: 0,
                                });
                                app.scroll = 0;
                            }
                            KeyCode::Char('j') | KeyCode::Down => {
                                app.selected =
                                    (app.selected + 1).min(app.rows.len().saturating_sub(1))
                            }
                            KeyCode::Char('k') | KeyCode::Up => {
                                app.selected = app.selected.saturating_sub(1)
                            }
                            KeyCode::Enter => {
                                if let Some(row) = app.rows.get(app.selected) {
                                    let detail = call(
                                        home,
                                        config,
                                        include,
                                        Cmd::Inspect {
                                            id: text(row, "id"),
                                        },
                                    )?;
                                    let origins = row["origins"]
                                        .as_array()
                                        .into_iter()
                                        .flatten()
                                        .map(|o| {
                                            format!("{}\n\n{}", text(o, "excerpt"), text(o, "note"))
                                        })
                                        .collect::<Vec<_>>()
                                        .join("\n\n");
                                    app.panel = Panel::Details(format!(
                                        "# {}{}\n\n{}\n\n{}\n\n{}",
                                        text(row, "title"),
                                        text(row, "label"),
                                        text(row, "url"),
                                        origins,
                                        serde_json::to_string_pretty(&detail)?
                                    ));
                                    app.scroll = 0;
                                }
                            }
                            KeyCode::Char('o') => {
                                if let Some(row) = app.rows.get(app.selected) {
                                    let url = model::validate_url(&text(row, "url"))?;
                                    std::process::Command::new("open").arg(url).spawn()?;
                                }
                            }
                            KeyCode::Char('g') => {
                                let mut db = state::db(home)?;
                                let mut graph = crate::snapshot_graph(&mut db, &app.filter, false)?;
                                if include {
                                    graph = knowledge::Snapshot::load(home, config)?
                                        .enrich(home, graph)?;
                                }
                                execute!(
                                    io::stdout(),
                                    DisableBracketedPaste,
                                    LeaveAlternateScreen
                                )?;
                                disable_raw_mode()?;
                                let result = tui::run_capture(graph);
                                enter()?;
                                terminal.clear()?;
                                if let Some(url) = result? {
                                    app.drop_link(&url)?;
                                }
                            }
                            KeyCode::Char('r') => {
                                let books = app.filter.books(&state::db(home)?)?;
                                ensure!(!books.is_empty(), "No structurally eligible bookmarks");
                                let mut evidence = json!({});
                                if !app.query.trim().is_empty() {
                                    for h in search::search(
                                        &mut state::db(home)?,
                                        &app.query,
                                        &app.filter,
                                        10000,
                                        !lexical,
                                        true,
                                    )?
                                    .hits
                                    {
                                        evidence[&h.book.id] = json!({"rank":h.rank,"cosine":h.cosine,"matched_by":h.matched_by,"graph_path":h.graph_path});
                                    }
                                }
                                app.panel = Panel::Review(Review::new(importer::preview(
                                    books,
                                    json!({"action":"tui-import","filters":app.filter,"query":app.query,"semantic_match":"requires review"}),
                                    &crate::store(home)?,
                                    evidence,
                                )?));
                                app.scroll = 0;
                            }
                            _ => {}
                        },
                    }
                }
                _ => {}
            }
            Ok(true)
        })();
        match result {
            Ok(false) => break,
            Ok(true) => {}
            Err(e) => {
                app.message = format!(
                    "{} · no automatic retry; bkd doctor/retry inspect pending writes",
                    model::clean(&e.to_string())
                );
            }
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn receipt_summary_distinguishes_duplicates_and_commit_time_pruning() {
        let text =
            receipt_summary(&json!({"batches":[{"new":1,"duplicate":2,"pruned":3}]})).unwrap();
        assert!(
            text.contains("1 new") && text.contains("2 existing") && text.contains("3 blocked")
        );
        assert!(receipt_summary(&json!({"batches":[]})).is_err());
        assert!(receipt_summary(&json!({"batches":[{"new":1}]})).is_err());
        let mut d = Draft::from_drop("https://example.org/").unwrap();
        d.fields[1] = "Reviewed title".into();
        assert_eq!(d.record("draft").unwrap().title, "Reviewed title");
    }
    fn plan() -> importer::Plan {
        let r = Draft::from_drop("https://openai.com/index/research/")
            .unwrap()
            .record("draft")
            .unwrap();
        importer::Plan {
            schema: 1,
            destination: "a".repeat(64),
            criteria: json!({}),
            candidates: vec![importer::Candidate {
                url: r.url.clone(),
                title: "Research".into(),
                kind: r.kind.clone(),
                origins: vec![r],
                status: "new".into(),
                evidence: json!({}),
                selected: true,
            }],
        }
    }
    #[test]
    fn drops_are_single_validated_data_and_never_approval() {
        for bad in [
            "javascript:alert(1)",
            "file:///tmp/a",
            "https://a.com\nhttps://b.com",
            "https://a.com; echo hello",
            "https://user:password@a.com",
            "\x1b[31mhttps://a.com",
        ] {
            assert!(Draft::from_drop(bad).is_err(), "{bad:?}");
        }
        let d = Draft::from_drop("https://openai.com/index/research/?a=1&b=2#section").unwrap();
        assert_eq!(
            d.fields[0],
            "https://openai.com/index/research/?a=1&b=2#section"
        );
        assert_eq!(d.fields[2], "blog");
        let mut app = App {
            panel: Panel::Review(Review::new(plan())),
            rows: vec![],
            selected: 0,
            filter: search::Filter::default(),
            query: String::new(),
            message: String::new(),
            scroll: 0,
        };
        assert!(app.drop_link("https://b.com").is_err());
    }
    #[test]
    fn review_requires_selection_exact_count_and_current_checksum() {
        let mut r = Review::new(plan());
        assert!(!r.plan.candidates[0].selected);
        assert!(r.approve().is_err());
        r.toggle();
        r.confirmation = Some("PUBLISH 2".into());
        assert!(r.approve().is_err());
        r.confirmation = Some("PUBLISH 1".into());
        let first = r.approve().unwrap();
        r.plan.candidates[0].title = "Changed".into();
        assert_ne!(first, r.approve().unwrap());
        r.toggle();
        assert!(r.confirmation.is_none());
        assert!(r.approve().is_err());
        r.plan.candidates[0].status = "pruned".into();
        r.toggle();
        assert!(!r.plan.candidates[0].selected);
    }
    #[test]
    fn rich_text_sanitizes_terminal_controls_and_does_not_emit_html() {
        let text = markdown("**bold** <script>bad()</script>\n\n\x1b]52;c;secret\x07");
        assert!(
            text.lines
                .iter()
                .flat_map(|l| &l.spans)
                .any(|s| s.style.add_modifier.contains(Modifier::BOLD))
        );
        assert!(
            text.lines
                .iter()
                .flat_map(|l| &l.spans)
                .all(|s| !s.content.contains(['\x1b', '\x07']))
        );
    }
}
