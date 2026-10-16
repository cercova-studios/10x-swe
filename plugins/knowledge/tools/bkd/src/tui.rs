use crate::{graph::Graph, model::clean};
use anyhow::{Result, ensure};
use crossterm::{
    event::{
        self, DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture,
        Event, KeyCode, MouseEventKind,
    },
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    Terminal,
    backend::CrosstermBackend,
    layout::{Constraint, Layout},
    style::{Color, Style},
    text::Span,
    widgets::{
        Block, Borders, Paragraph,
        canvas::{Canvas, Line, Points},
    },
};
use std::{
    io::{self, IsTerminal},
    time::Duration,
};
struct Guard;
impl Drop for Guard {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = execute!(
            io::stdout(),
            DisableBracketedPaste,
            DisableMouseCapture,
            LeaveAlternateScreen
        );
    }
}
pub fn run(graph: Graph) -> Result<()> {
    view(graph, false).map(|_| ())
}
pub fn run_capture(graph: Graph) -> Result<Option<String>> {
    view(graph, true)
}
fn view(graph: Graph, capture: bool) -> Result<Option<String>> {
    ensure!(
        io::stdin().is_terminal() && io::stdout().is_terminal(),
        "Graph view requires a terminal; use --json for agents"
    );
    enable_raw_mode()?;
    let _guard = Guard;
    execute!(io::stdout(), EnterAlternateScreen, EnableMouseCapture)?;
    if capture {
        execute!(io::stdout(), EnableBracketedPaste)?;
    }
    let mut terminal = Terminal::new(CrosstermBackend::new(io::stdout()))?;
    let mut page = 0usize;
    let mut selected = 0usize;
    let mut detail = false;
    let mut list = false;
    let mut help = false;
    let mut zoom = 1.;
    let mut pan = (0., 0.);
    let mut query = String::new();
    let mut typing = false;
    let mut scroll = 0u16;
    let mut neighbor_index = 0usize;
    loop {
        let matching: Vec<_> = graph
            .nodes
            .iter()
            .filter(|n| n.label.to_lowercase().contains(&query.to_lowercase()))
            .collect();
        let size = terminal.size()?;
        let width = size.width.max(24) as f64;
        let height = size.height.saturating_sub(3).max(5) as f64;
        let columns = (size.width as usize / 24).clamp(1, 10);
        let page_size = (columns * (height as usize / 5).max(1)).min(100);
        let pages = matching.len().div_ceil(page_size).max(1);
        page = page.min(pages - 1);
        let nodes: Vec<_> = matching
            .iter()
            .skip(page * page_size)
            .take(page_size)
            .copied()
            .collect();
        selected = selected.min(nodes.len().saturating_sub(1));
        let mut positions = std::collections::BTreeMap::new();
        for (i, n) in nodes.iter().enumerate() {
            positions.insert(
                n.id.as_str(),
                (
                    1. + (i % columns) as f64 * width / columns as f64,
                    height - 3. - (i / columns) as f64 * 5.,
                ),
            );
        }
        terminal.draw(|f|{
            let areas=Layout::vertical([Constraint::Length(1),Constraint::Min(1),Constraint::Length(2)]).split(f.area());
            f.render_widget(Paragraph::new(format!("BookmarkDrop · generation {} · {} nodes / {} edges · page {}/{}",graph.generation,matching.len(),graph.edges.len(),page+1,pages)),areas[0]);
            let canvas=Canvas::default().block(Block::default().borders(Borders::NONE))
                .x_bounds([pan.0,pan.0+width/zoom]).y_bounds([pan.1,pan.1+height/zoom])
                .paint(|ctx|{
                    for e in &graph.edges{
                        if let (Some(&(x1,y1)),Some(&(x2,y2)))=(positions.get(e.a.as_str()),positions.get(e.b.as_str())){
                            ctx.draw(&Line{x1,y1,x2,y2,color:if e.status=="inferred"{Color::DarkGray}else{Color::Green}});
                        }
                    }
                    for (i,n) in nodes.iter().enumerate(){
                        let &(x,y)=positions.get(n.id.as_str()).unwrap();ctx.draw(&Points{coords:&[(x,y)],color:if i==selected{Color::Yellow}else{Color::Cyan}});
                        ctx.print(x,y+1.,Span::styled(clean(&n.label).chars().take((width as usize/columns).saturating_sub(2)).collect::<String>(),Style::default().fg(if i==selected{Color::Yellow}else{Color::White})));
                    }
                });
            f.render_widget(canvas,areas[1]);
            let overlay=if help {
                Some("j/k select · n/p page · +/- zoom · arrows pan · / filter\ns list · d details · g neighbors · Esc close · q quit\nGreen edges: recorded/user · gray edges: inferred. Cross-page paths: bkd path.".into())
            }else if detail {
                nodes.get(selected).map(|n|format!("{}\n{}\n{}\n{}\nRelationships ([ / ] choose, g follows):\n{}",clean(&n.label),n.url.as_deref().unwrap_or("Local entity"),n.bookmark_kind.as_deref().unwrap_or(&n.kind),n.details.as_ref().map(|d|serde_json::to_string_pretty(d).unwrap()).unwrap_or_default(),graph.adjacent(&n.id).iter().enumerate().map(|(i,(to,e))|format!("{} {} ({}) → {}\nEvidence: {}",if i==neighbor_index{">"}else{" "},e.kind,e.status,to,e.evidence)).collect::<Vec<_>>().join("\n")))
            }else if list{Some(nodes.iter().enumerate().map(|(i,n)|format!("{} {} [{}] {}",if i==selected{">"}else{" "},i+1,n.kind,clean(&n.label))).collect::<Vec<_>>().join("\n"))}else{None};
            if let Some(text)=overlay {
                let area=ratatui::layout::Rect{x:areas[1].x+2,y:areas[1].y+1,width:areas[1].width.saturating_sub(4),height:areas[1].height.saturating_sub(2)};
                f.render_widget(ratatui::widgets::Clear,area);
                f.render_widget(Paragraph::new(text).block(Block::bordered()).wrap(ratatui::widgets::Wrap{trim:false}).scroll((scroll,0)),area);
            }
            f.render_widget(Paragraph::new(format!("{}\n{}",if typing{format!("Filter: {query}_")}else{format!("/ filter: {query} · s list · d details · ? help · q quit")},"Graph relationships show recorded evidence or marked suggestions; visual proximity has no meaning.")),areas[2]);
        })?;
        while !event::poll(Duration::from_millis(250))? {}
        match event::read()? {
            Event::Paste(text) if capture => return Ok(Some(crate::model::validate_url(&text)?)),
            Event::Key(k) => {
                if k.modifiers.contains(event::KeyModifiers::CONTROL)
                    && k.code == KeyCode::Char('c')
                {
                    break;
                }
                if typing {
                    match k.code {
                        KeyCode::Enter | KeyCode::Esc => typing = false,
                        KeyCode::Backspace => {
                            query.pop();
                        }
                        KeyCode::Char(c) => {
                            query.push(c);
                            page = 0;
                        }
                        _ => {}
                    }
                    continue;
                }
                match k.code {
                    KeyCode::Char('q') => break,
                    KeyCode::Esc => {
                        detail = false;
                        list = false;
                        help = false;
                        scroll = 0;
                    }
                    KeyCode::Char('/') => {
                        typing = true;
                        query.clear();
                    }
                    KeyCode::Char('j') => {
                        selected = (selected + 1).min(nodes.len().saturating_sub(1))
                    }
                    KeyCode::Char('k') => selected = selected.saturating_sub(1),
                    KeyCode::Char('n') => {
                        page = (page + 1).min(pages - 1);
                        selected = 0;
                    }
                    KeyCode::Char('p') => {
                        page = page.saturating_sub(1);
                        selected = 0;
                    }
                    KeyCode::Char('d') | KeyCode::Enter => detail = !detail,
                    KeyCode::Char('s') => list = !list,
                    KeyCode::Char('?') => help = !help,
                    KeyCode::Char('+') | KeyCode::Char('=') => zoom = (zoom * 1.2f64).min(8.),
                    KeyCode::Char('-') => zoom = (zoom / 1.2f64).max(0.25),
                    KeyCode::Left => pan.0 -= 5.,
                    KeyCode::Right => pan.0 += 5.,
                    KeyCode::Up => pan.1 += 5.,
                    KeyCode::Down => pan.1 -= 5.,
                    KeyCode::Char(']') => {
                        neighbor_index = neighbor_index.saturating_add(1);
                        if let Some(n) = nodes.get(selected) {
                            neighbor_index =
                                neighbor_index.min(graph.adjacent(&n.id).len().saturating_sub(1));
                        }
                    }
                    KeyCode::Char('[') => neighbor_index = neighbor_index.saturating_sub(1),
                    KeyCode::Char('g') => {
                        if detail
                            && let Some(n) = nodes.get(selected)
                            && let Some((target, _)) = graph.adjacent(&n.id).get(neighbor_index)
                            && let Some(index) = graph.nodes.iter().position(|n| n.id == *target)
                        {
                            query.clear();
                            page = index / page_size;
                            selected = index % page_size;
                            scroll = 0;
                            neighbor_index = 0;
                        }
                        detail = true;
                    }
                    KeyCode::PageDown => scroll = scroll.saturating_add(10),
                    KeyCode::PageUp => scroll = scroll.saturating_sub(10),
                    _ => {}
                }
            }
            Event::Mouse(m) => match m.kind {
                MouseEventKind::ScrollUp => zoom = (zoom * 1.1f64).min(8.),
                MouseEventKind::ScrollDown => zoom = (zoom / 1.1f64).max(0.25),
                _ => {}
            },
            _ => {}
        }
    }
    Ok(None)
}
