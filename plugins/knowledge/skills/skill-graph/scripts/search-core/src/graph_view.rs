//! Read-only spatial exploration of recorded skill relationships.
use anyhow::{Context, Result, ensure};
use crossterm::{
    event::{
        self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEvent, KeyEventKind,
        KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
    },
    execute,
};
use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
    text::Span,
    widgets::{
        Block, Clear, List, ListItem, ListState, Paragraph, Wrap,
        canvas::{Canvas, Line, Points, Rectangle},
    },
};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    io::{self, IsTerminal},
    time::{Duration, Instant},
};

#[derive(Debug)]
struct Node {
    id: String,
    name: String,
    scope: String,
    description: String,
    cluster: String,
}
struct Model {
    nodes: Vec<Node>,
    edges: Vec<(usize, usize)>,
    adjacent: Vec<BTreeSet<usize>>,
    positions: Vec<(f64, f64)>,
    aliases: BTreeMap<String, usize>,
    relations: BTreeMap<(usize, usize), Vec<(String, String)>>,
    mapped: bool,
    cluster_labels: BTreeMap<String, String>,
}

fn clean(s: &str) -> String {
    s.chars().filter(|c| !c.is_control()).take(4096).collect()
}

impl Model {
    fn new(graph: &Value) -> Result<Self> {
        let raw = graph["nodes"].as_array().context("graph lacks nodes")?;
        ensure!(raw.len() <= 2048, "graph view supports at most2048nodes");
        let mut nodes = Vec::new();
        for node in raw {
            let field = |key: &str| -> Result<String> {
                Ok(clean(
                    node[key]
                        .as_str()
                        .with_context(|| format!("node lacks {key}"))?,
                ))
            };
            nodes.push(Node {
                id: field("id")?,
                name: if node["kind"] == "workflow" {
                    format!("↳ {} [workflow]", field("name")?)
                } else {
                    field("name")?
                },
                scope: field("scope")?,
                description: field("description")?,
                cluster: clean(node["cluster"].as_str().unwrap_or("unmapped")),
            });
        }
        nodes.sort_by(|a, b| a.id.cmp(&b.id));
        let mut aliases: BTreeMap<String, usize> = nodes
            .iter()
            .enumerate()
            .map(|(i, n)| (n.id.clone(), i))
            .collect();
        ensure!(aliases.len() == nodes.len(), "duplicate node identity");
        for alias in graph["aliases"].as_array().into_iter().flatten() {
            let target = alias["target"].as_str().context("alias lacks target")?;
            let index = *aliases.get(target).context("alias target absent")?;
            aliases.insert(
                alias["id"]
                    .as_str()
                    .context("alias lacks identity")?
                    .to_owned(),
                index,
            );
        }
        let raw_edges = graph["edges"].as_array().context("graph lacks edges")?;
        ensure!(
            raw_edges.len() <= 16384,
            "graph view supports at most16384edges"
        );
        let mut edges = BTreeSet::new();
        let mut relations: BTreeMap<(usize, usize), Vec<(String, String)>> = BTreeMap::new();
        let mut adjacent = vec![BTreeSet::new(); nodes.len()];
        for edge in raw_edges {
            let source = *aliases
                .get(edge["source"].as_str().context("edge lacks source")?)
                .context("edge source absent")?;
            let target = *aliases
                .get(edge["target"].as_str().context("edge lacks target")?)
                .context("edge target absent")?;
            edges.insert((source, target));
            let kind = edge["relation"].as_str().context("edge lacks relation")?;
            ensure!(
                matches!(
                    kind,
                    "uses" | "references" | "related" | "associated_workflow" | "uses_skill"
                ),
                "unsupported relationship"
            );
            relations.entry((source, target)).or_default().push((
                kind.to_owned(),
                edge["status"].as_str().unwrap_or("declared").to_owned(),
            ));
            adjacent[source].insert(target);
            adjacent[target].insert(source);
        }
        let mut positions = vec![(0., 0.); nodes.len()];
        if graph["concepts"]["status"] == "fresh" {
            crate::topics::validate(graph)?;
            let mut clusters: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
            for (i, node) in nodes.iter().enumerate() {
                clusters.entry(&node.cluster).or_default().push(i);
            }
            for (group, (_, members)) in clusters.into_iter().enumerate() {
                let angle = group as f64 * 2.399963;
                let radius = 20. * (group as f64).sqrt();
                let center = (radius * angle.cos(), radius * angle.sin());
                let ring = 2. + (members.len() as f64).sqrt();
                for (k, &i) in members.iter().enumerate() {
                    let angle = k as f64 * std::f64::consts::TAU / members.len() as f64;
                    positions[i] = (center.0 + ring * angle.cos(), center.1 + ring * angle.sin());
                }
            }
        }
        // Stable connected-component islands; isolated nodes remain real nodes.
        let mut visited = BTreeSet::new();
        let mut group = 0usize;
        for start in 0..nodes.len() {
            if graph["concepts"]["status"] == "fresh" {
                break;
            }
            if visited.contains(&start) {
                continue;
            }
            let mut queue = VecDeque::from([start]);
            let mut members = Vec::new();
            visited.insert(start);
            while let Some(i) = queue.pop_front() {
                members.push(i);
                for &j in &adjacent[i] {
                    if visited.insert(j) {
                        queue.push_back(j);
                    }
                }
            }
            let angle = group as f64 * 2.399963;
            let radius = 7. * (group as f64).sqrt();
            let center = (radius * angle.cos(), radius * angle.sin());
            group += 1;
            let ring = if members.len() == 1 {
                0.
            } else {
                4. + (members.len() as f64).sqrt() * 1.5
            };
            let count = members.len();
            for (k, i) in members.into_iter().enumerate() {
                let angle = k as f64 * std::f64::consts::TAU / count as f64;
                positions[i] = (center.0 + ring * angle.cos(), center.1 + ring * angle.sin());
            }
        }
        Ok(Self {
            nodes,
            edges: edges.into_iter().collect(),
            adjacent,
            positions,
            aliases,
            relations,
            mapped: graph["concepts"]["status"] == "fresh",
            cluster_labels: graph["clusters"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|c| Some((clean(c["id"].as_str()?), clean(c["label"].as_str()?))))
                .collect(),
        })
    }
}

struct App {
    model: Model,
    selected: Option<usize>,
    query: String,
    editing: bool,
    focus: bool,
    isolates: bool,
    labels: bool,
    scope: Option<String>,
    pan: (f64, f64),
    scale: f64,
    target_pan: (f64, f64),
    target_scale: f64,
    viewport: Rect,
    drag: Option<(u16, u16, Option<usize>)>,
    pinned: BTreeSet<usize>,
    anchors: Vec<(f64, f64)>,
    velocity: Vec<(f64, f64)>,
    physics_ticks: usize,
    quiet_ticks: usize,
    motion: bool,
    overview: bool,
    fit_pending: bool,
    initialized: bool,
    show_list: bool,
    show_detail: bool,
    show_help: bool,
}

struct Glyph {
    members: Vec<usize>,
    position: (f64, f64),
    label: String,
    cluster: String,
}
struct Scene {
    glyphs: Vec<Glyph>,
    // Geometry is aggregated only for drawing; canonical typed edges remain intact.
    edges: Vec<(usize, usize, bool, bool)>,
}

fn aspect(rect: Rect) -> f64 {
    (rect.height.max(1) as f64 * 2. / rect.width.max(1) as f64).clamp(0.3, 2.)
}

fn clipped(text: &str, max_width: usize) -> String {
    if Span::raw(text).width() <= max_width {
        return text.to_owned();
    }
    let mut out = String::new();
    for c in text.chars() {
        out.push(c);
        if Span::raw(out.as_str()).width() >= max_width {
            out.pop();
            break;
        }
    }
    out.push('…');
    out
}

fn cluster_color(cluster: &str) -> Color {
    let palette = [
        Color::Cyan,
        Color::Green,
        Color::Magenta,
        Color::Blue,
        Color::Red,
        Color::White,
    ];
    let hash = cluster
        .bytes()
        .fold(0usize, |a, b| a.wrapping_mul(31).wrapping_add(b as usize));
    palette[hash % palette.len()]
}
impl App {
    fn new(model: Model, id: Option<&str>) -> Result<Self> {
        let selected = if let Some(id) = id {
            Some(
                *model
                    .aliases
                    .get(id)
                    .context("unknown skill ID; use a scoped identity")?,
            )
        } else {
            model
                .nodes
                .iter()
                .enumerate()
                .find(|(i, _)| !model.adjacent[*i].is_empty())
                .map(|(i, _)| i)
                .or(if model.nodes.is_empty() {
                    None
                } else {
                    Some(0)
                })
        };
        let anchors = model.positions.clone();
        let velocity = vec![(0., 0.); model.nodes.len()];
        let mut app = Self {
            model,
            selected,
            query: String::new(),
            editing: false,
            focus: id.is_some(),
            isolates: true,
            labels: false,
            scope: None,
            pan: (0., 0.),
            scale: 110.,
            target_pan: (0., 0.),
            target_scale: 110.,
            viewport: Rect::default(),
            drag: None,
            pinned: BTreeSet::new(),
            anchors,
            velocity,
            physics_ticks: 120,
            quiet_ticks: 0,
            motion: true,
            overview: true,
            fit_pending: id.is_none(),
            initialized: false,
            show_list: false,
            show_detail: false,
            show_help: false,
        };
        if id.is_some() {
            app.center();
        }
        Ok(app)
    }
    fn visible(&self) -> Vec<usize> {
        (0..self.model.nodes.len())
            .filter(|&i| {
                let n = &self.model.nodes[i];
                (self.isolates || !self.model.adjacent[i].is_empty())
                    && self.scope.as_ref().is_none_or(|s| s == &n.scope)
                    && (!self.focus
                        || self
                            .selected
                            .is_some_and(|s| s == i || self.model.adjacent[s].contains(&i)))
            })
            .collect()
    }
    fn matches(&self) -> Vec<usize> {
        let query = self.query.to_lowercase();
        self.visible()
            .into_iter()
            .filter(|&i| {
                let n = &self.model.nodes[i];
                n.id.to_lowercase().contains(&query)
                    || n.description.to_lowercase().contains(&query)
            })
            .collect()
    }
    fn center(&mut self) {
        if let Some(i) = self.selected {
            self.target_pan = self.model.positions[i];
            self.target_scale = 22.;
        }
    }
    fn animating(&self) -> bool {
        self.motion
            && (self.physics_ticks > 0
                || (self.pan.0 - self.target_pan.0).abs() > 0.001
                || (self.pan.1 - self.target_pan.1).abs() > 0.001
                || (self.scale - self.target_scale).abs() > 0.001)
    }
    fn tick(&mut self, elapsed: f64) {
        if !self.motion {
            return;
        }
        let mix = 1. - (-18. * elapsed.clamp(0., 0.1)).exp();
        self.pan.0 += (self.target_pan.0 - self.pan.0) * mix;
        self.pan.1 += (self.target_pan.1 - self.pan.1) * mix;
        self.scale += (self.target_scale - self.scale) * mix;
        if (self.pan.0 - self.target_pan.0).abs() < 0.001 {
            self.pan.0 = self.target_pan.0;
        }
        if (self.pan.1 - self.target_pan.1).abs() < 0.001 {
            self.pan.1 = self.target_pan.1;
        }
        if (self.scale - self.target_scale).abs() < 0.001 {
            self.scale = self.target_scale;
        }
        if self.physics_ticks == 0 {
            return;
        }
        self.physics_ticks -= 1;
        // Local repulsion uses a spatial grid, avoiding an all-pairs allocation.
        let mut grid: BTreeMap<(i32, i32), Vec<usize>> = BTreeMap::new();
        for (i, &(x, y)) in self.model.positions.iter().enumerate() {
            grid.entry(((x / 8.).floor() as i32, (y / 8.).floor() as i32))
                .or_default()
                .push(i);
        }
        let mut forces = vec![(0., 0.); self.model.nodes.len()];
        for (i, &(x, y)) in self.model.positions.iter().enumerate() {
            forces[i] = (
                (self.anchors[i].0 - x) * 0.035,
                (self.anchors[i].1 - y) * 0.035,
            );
            let cell = ((x / 8.).floor() as i32, (y / 8.).floor() as i32);
            // Limit work per node even for adversarially coincident inputs.
            let mut compared = 0;
            for dx in -1..=1 {
                for dy in -1..=1 {
                    if let Some(near) = grid.get(&(cell.0 + dx, cell.1 + dy)) {
                        for &j in near.iter().take(128) {
                            if i == j || compared >= 128 {
                                continue;
                            }
                            compared += 1;
                            let q = self.model.positions[j];
                            let mut d = (x - q.0, y - q.1);
                            if d.0 * d.0 + d.1 * d.1 < 0.0001 {
                                d = if i < j { (-0.01, 0.01) } else { (0.01, -0.01) };
                            }
                            let squared = (d.0 * d.0 + d.1 * d.1).max(0.25);
                            if squared < 64. {
                                forces[i].0 += d.0 * 0.65 / squared;
                                forces[i].1 += d.1 * 0.65 / squared;
                            }
                        }
                    }
                }
            }
        }
        for &(i, j) in &self.model.edges {
            if self.model.nodes[i].cluster != self.model.nodes[j].cluster {
                continue;
            }
            let p = self.model.positions[i];
            let q = self.model.positions[j];
            let distance = ((q.0 - p.0).powi(2) + (q.1 - p.1).powi(2)).sqrt().max(0.01);
            let spring = (distance - 4.) * 0.012 / distance;
            let f = ((q.0 - p.0) * spring, (q.1 - p.1) * spring);
            forces[i].0 += f.0;
            forces[i].1 += f.1;
            forces[j].0 -= f.0;
            forces[j].1 -= f.1;
        }
        let mut movement = 0_f64;
        for (i, force) in forces.iter().enumerate() {
            if self.pinned.contains(&i) {
                self.velocity[i] = (0., 0.);
                continue;
            }
            self.velocity[i].0 = (self.velocity[i].0 * 0.65 + force.0 * 0.18).clamp(-0.25, 0.25);
            self.velocity[i].1 = (self.velocity[i].1 * 0.65 + force.1 * 0.18).clamp(-0.25, 0.25);
            self.model.positions[i].0 += self.velocity[i].0;
            self.model.positions[i].1 += self.velocity[i].1;
            movement = movement.max(self.velocity[i].0.abs() + self.velocity[i].1.abs());
        }
        self.quiet_ticks = if movement < 0.004 {
            self.quiet_ticks + 1
        } else {
            0
        };
        if self.quiet_ticks >= 8 {
            self.physics_ticks = 0;
        }
    }
    fn scene(&self) -> Scene {
        let visible = self.visible();
        let collapsed = self.model.mapped
            && self.overview
            && !self.focus
            && self.query.is_empty()
            && self.scale > 45.;
        let mut groups: BTreeMap<String, Vec<usize>> = BTreeMap::new();
        for i in visible {
            let n = &self.model.nodes[i];
            let key = if collapsed && n.cluster != "unmapped" {
                format!("cluster:{}", n.cluster)
            } else {
                format!("skill:{}", n.id)
            };
            groups.entry(key).or_default().push(i);
        }
        let mut owner = vec![None; self.model.nodes.len()];
        let glyphs: Vec<_> = groups
            .into_values()
            .enumerate()
            .map(|(index, members)| {
                let mut position = (0., 0.);
                for &i in &members {
                    owner[i] = Some(index);
                    position.0 += self.model.positions[i].0;
                    position.1 += self.model.positions[i].1;
                }
                position.0 /= members.len() as f64;
                position.1 /= members.len() as f64;
                let first = &self.model.nodes[members[0]];
                let label = if members.len() > 1 {
                    format!(
                        "{} · {}",
                        clipped(
                            self.model
                                .cluster_labels
                                .get(&first.cluster)
                                .map(String::as_str)
                                .unwrap_or(&first.cluster),
                            20
                        ),
                        members.len()
                    )
                } else {
                    first.name.clone()
                };
                Glyph {
                    members,
                    position,
                    label,
                    cluster: first.cluster.clone(),
                }
            })
            .collect();
        let mut edges: BTreeMap<(usize, usize), (bool, bool)> = BTreeMap::new();
        for &(a, b) in &self.model.edges {
            let (Some(i), Some(j)) = (owner[a], owner[b]) else {
                continue;
            };
            if i == j {
                continue;
            }
            let types = &self.model.relations[&(a, b)];
            let flags = edges.entry((i.min(j), i.max(j))).or_insert((false, true));
            flags.0 |= types.iter().any(|(r, _)| r == "uses");
            flags.1 &= types.iter().all(|(_, s)| s == "inferred");
        }
        Scene {
            glyphs,
            edges: edges
                .into_iter()
                .map(|((a, b), (uses, inferred))| (a, b, uses, inferred))
                .collect(),
        }
    }
    fn world(&self, column: u16, row: u16) -> (f64, f64) {
        let r = self.viewport;
        let fx = (column.saturating_sub(r.x)) as f64 / (r.width.saturating_sub(1).max(1)) as f64;
        let fy = (row.saturating_sub(r.y)) as f64 / (r.height.saturating_sub(1).max(1)) as f64;
        (
            self.pan.0 + (fx * 2. - 1.) * self.scale,
            self.pan.1 + (1. - fy * 2.) * self.scale * aspect(r),
        )
    }
    fn screen(&self, p: (f64, f64)) -> Option<(u16, u16)> {
        let r = self.viewport;
        if r.width == 0 || r.height == 0 {
            return None;
        }
        let fx = (p.0 - self.pan.0) / self.scale / 2. + 0.5;
        let fy = 0.5 - (p.1 - self.pan.1) / (self.scale * aspect(r) * 2.);
        if !(0. ..=1.).contains(&fx) || !(0. ..=1.).contains(&fy) {
            return None;
        }
        Some((
            r.x + (fx * (r.width - 1) as f64).round() as u16,
            r.y + (fy * (r.height - 1) as f64).round() as u16,
        ))
    }
    fn mouse(&mut self, event: MouseEvent) {
        if matches!(event.kind, MouseEventKind::Up(MouseButton::Left)) {
            self.drag = None;
            return;
        }
        if !self.viewport.contains((event.column, event.row).into()) {
            return;
        }
        if self
            .overlay_areas()
            .iter()
            .any(|r| r.contains((event.column, event.row).into()))
        {
            return;
        }
        if self
            .minimap_area()
            .is_some_and(|r| r.contains((event.column, event.row).into()))
        {
            return;
        }
        match event.kind {
            MouseEventKind::ScrollUp | MouseEventKind::ScrollDown => {
                let anchor = self.world(event.column, event.row);
                let factor = if event.kind == MouseEventKind::ScrollUp {
                    1. / 1.25
                } else {
                    1.25
                };
                let scale = (self.target_scale * factor).clamp(2., 500.);
                let ratio = scale / self.scale;
                self.target_pan = (
                    anchor.0 + (self.pan.0 - anchor.0) * ratio,
                    anchor.1 + (self.pan.1 - anchor.1) * ratio,
                );
                self.target_scale = scale;
            }
            MouseEventKind::Down(MouseButton::Left) => {
                let scene = self.scene();
                let hit = scene
                    .glyphs
                    .iter()
                    .filter_map(|g| self.screen(g.position).map(|p| (g, p)))
                    .filter(|(_, p)| {
                        p.0.abs_diff(event.column) <= 2 && p.1.abs_diff(event.row) <= 1
                    })
                    .min_by_key(|(_, p)| p.0.abs_diff(event.column) + p.1.abs_diff(event.row));
                let mut node = None;
                if let Some((g, _)) = hit {
                    self.selected = Some(g.members[0]);
                    if g.members.len() > 1 {
                        self.target_pan = g.position;
                        self.target_scale = 22.;
                    } else {
                        node = self.selected;
                    }
                }
                self.drag = Some((event.column, event.row, node));
            }
            MouseEventKind::Drag(MouseButton::Left) => {
                if let Some((x, y, node)) = self.drag {
                    if let Some(i) = node {
                        self.model.positions[i] = self.world(event.column, event.row);
                        self.pinned.insert(i);
                        self.physics_ticks = 90;
                        self.quiet_ticks = 0;
                    } else {
                        let a = self.world(x, y);
                        let b = self.world(event.column, event.row);
                        self.pan.0 += a.0 - b.0;
                        self.pan.1 += a.1 - b.1;
                        self.target_pan = self.pan;
                    }
                    self.drag = Some((event.column, event.row, node));
                }
            }
            _ => {}
        }
        if !self.motion {
            self.pan = self.target_pan;
            self.scale = self.target_scale;
        }
    }
    fn minimap_area(&self) -> Option<Rect> {
        if self.viewport.width < 45 || self.viewport.height < 12 || self.model.positions.is_empty()
        {
            return None;
        }
        let positions: Vec<_> = self
            .scene()
            .glyphs
            .iter()
            .filter_map(|g| {
                self.screen(g.position)
                    .map(|p| (p, g.members.iter().any(|i| Some(*i) == self.selected)))
            })
            .collect();
        [
            (self.viewport.right() - 18, self.viewport.bottom() - 6),
            (self.viewport.x, self.viewport.bottom() - 6),
            (self.viewport.right() - 18, self.viewport.y),
            (self.viewport.x, self.viewport.y),
        ]
        .into_iter()
        .map(|(x, y)| Rect::new(x, y, 18, 6))
        .min_by_key(|r| {
            positions
                .iter()
                .filter(|(p, _)| r.contains((*p).into()))
                .map(|(_, selected)| if *selected { 10000usize } else { 1 })
                .sum::<usize>()
        })
    }
    fn draw_minimap(&self, frame: &mut Frame) {
        let Some(r) = self.minimap_area() else {
            return;
        };
        let mut low = (f64::INFINITY, f64::INFINITY);
        let mut high = (f64::NEG_INFINITY, f64::NEG_INFINITY);
        for &(x, y) in &self.model.positions {
            low.0 = low.0.min(x);
            low.1 = low.1.min(y);
            high.0 = high.0.max(x);
            high.1 = high.1.max(y);
        }
        let x = [low.0 - 5., high.0 + 5.];
        let y = [low.1 - 5., high.1 + 5.];
        let canvas = Canvas::default()
            .block(Block::bordered().title("Map"))
            .x_bounds(x)
            .y_bounds(y)
            .paint(|ctx| {
                ctx.draw(&Points {
                    coords: &self.model.positions,
                    color: Color::DarkGray,
                });
                let left = (self.pan.0 - self.scale).max(x[0]);
                let right = (self.pan.0 + self.scale).min(x[1]);
                let bottom = (self.pan.1 - self.scale * aspect(self.viewport)).max(y[0]);
                let top = (self.pan.1 + self.scale * aspect(self.viewport)).min(y[1]);
                if right > left && top > bottom {
                    ctx.draw(&Rectangle {
                        x: left,
                        y: bottom,
                        width: right - left,
                        height: top - bottom,
                        color: Color::Cyan,
                    });
                }
                if let Some(i) = self.selected {
                    ctx.draw(&Points {
                        coords: &[self.model.positions[i]],
                        color: Color::Yellow,
                    });
                }
            });
        frame.render_widget(canvas, r);
    }
    fn key(&mut self, key: KeyEvent) -> bool {
        if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
            return false;
        }
        if self.editing {
            match key.code {
                KeyCode::Esc => {
                    self.editing = false;
                    self.show_list = false;
                }
                KeyCode::Enter => self.editing = false,
                KeyCode::Backspace => {
                    self.query.pop();
                }
                KeyCode::Char(c) if self.query.len() < 256 => self.query.push(c),
                _ => {}
            }
            let matched = self.matches();
            if !self.selected.is_some_and(|i| matched.contains(&i)) {
                self.selected = matched.first().copied();
            }
            return true;
        }
        match key.code {
            KeyCode::Char('q') => return false,
            KeyCode::Esc => {
                if self.show_list || self.show_detail || self.show_help {
                    self.show_list = false;
                    self.show_detail = false;
                    self.show_help = false;
                } else {
                    return false;
                }
            }
            KeyCode::Char('s') => self.show_list = !self.show_list,
            KeyCode::Char('d') => self.show_detail = !self.show_detail,
            KeyCode::Char('?') => self.show_help = !self.show_help,
            KeyCode::Char('/') => {
                self.editing = true;
                self.show_list = true;
                self.focus = false;
            }
            KeyCode::Char('j') | KeyCode::Char('k') => {
                let choices = self.matches();
                if !choices.is_empty() {
                    let pos = choices
                        .iter()
                        .position(|&i| Some(i) == self.selected)
                        .unwrap_or(0);
                    let next = if key.code == KeyCode::Char('j') {
                        (pos + 1) % choices.len()
                    } else {
                        (pos + choices.len() - 1) % choices.len()
                    };
                    self.selected = Some(choices[next]);
                }
            }
            KeyCode::Char('g') | KeyCode::Enter => {
                self.focus = !self.focus;
                if self.focus {
                    self.center();
                }
            }
            KeyCode::Char('i') => self.isolates = !self.isolates,
            KeyCode::Char('l') => self.labels = !self.labels,
            KeyCode::Char('o') => self.overview = !self.overview,
            KeyCode::Char(' ') => {
                self.motion = !self.motion;
                if !self.motion {
                    self.pan = self.target_pan;
                    self.scale = self.target_scale;
                }
            }
            KeyCode::Char('p') => {
                if let Some(i) = self.selected {
                    self.pinned.remove(&i);
                    self.physics_ticks = 90;
                    self.quiet_ticks = 0;
                }
            }
            KeyCode::Char('c') => self.center(),
            KeyCode::Char('r') => {
                self.target_pan = (0., 0.);
                self.target_scale = 110.;
                self.focus = false;
                self.scope = None;
                self.query.clear();
                self.isolates = true;
                self.overview = true;
                self.fit_pending = true;
                self.show_list = false;
                self.show_detail = false;
                self.show_help = false;
            }
            KeyCode::Char('+') | KeyCode::Char('=') => {
                self.target_scale = (self.target_scale / 1.25).max(2.)
            }
            KeyCode::Char('-') => self.target_scale = (self.target_scale * 1.25).min(500.),
            KeyCode::Left => self.target_pan.0 -= self.target_scale / 8.,
            KeyCode::Right => self.target_pan.0 += self.target_scale / 8.,
            KeyCode::Up => self.target_pan.1 += self.target_scale / 8.,
            KeyCode::Down => self.target_pan.1 -= self.target_scale / 8.,
            KeyCode::Tab => {
                let scopes: Vec<_> = self
                    .model
                    .nodes
                    .iter()
                    .map(|n| n.scope.clone())
                    .collect::<BTreeSet<_>>()
                    .into_iter()
                    .collect();
                self.scope = match &self.scope {
                    None => scopes.first().cloned(),
                    Some(s) => scopes
                        .iter()
                        .position(|v| v == s)
                        .and_then(|i| scopes.get(i + 1).cloned()),
                };
                self.focus = false;
            }
            _ => {}
        }
        let choices = self.matches();
        if !self.selected.is_some_and(|i| choices.contains(&i)) {
            self.selected = choices.first().copied();
        }
        if !self.motion {
            self.pan = self.target_pan;
            self.scale = self.target_scale;
        }
        true
    }
    fn draw(&mut self, frame: &mut Frame) {
        let area = frame.area();
        if area.width < 65 || area.height < 18 {
            self.viewport = Rect::default();
            self.drag = None;
            frame.render_widget(
                Paragraph::new(
                    "Graph view needs at least65columns ×18rows. Resize or press q to exit.",
                )
                .wrap(Wrap { trim: true }),
                area,
            );
            return;
        }
        let visible = self.visible();
        let set: BTreeSet<_> = visible.iter().copied().collect();
        let count = self
            .model
            .edges
            .iter()
            .filter(|(a, b)| set.contains(a) && set.contains(b))
            .count();
        self.viewport = Rect::new(area.x, area.y + 1, area.width, area.height - 2);
        if self.fit_pending {
            let mut low = (f64::INFINITY, f64::INFINITY);
            let mut high = (f64::NEG_INFINITY, f64::NEG_INFINITY);
            for i in self.visible() {
                let p = self.model.positions[i];
                low.0 = low.0.min(p.0);
                low.1 = low.1.min(p.1);
                high.0 = high.0.max(p.0);
                high.1 = high.1.max(p.1);
            }
            if low.0.is_finite() {
                self.target_pan = ((low.0 + high.0) / 2., (low.1 + high.1) / 2.);
                self.target_scale = (((high.0 - low.0) / 2.)
                    .max((high.1 - low.1) / (2. * aspect(self.viewport)))
                    * 1.15
                    + 4.)
                    .clamp(2., 500.);
            }
            if !self.initialized {
                self.pan = self.target_pan;
                self.scale = self.target_scale;
            }
            self.fit_pending = false;
        }
        self.initialized = true;
        let aspect = aspect(self.viewport);
        let x = [self.pan.0 - self.scale, self.pan.0 + self.scale];
        let y = [
            self.pan.1 - self.scale * aspect,
            self.pan.1 + self.scale * aspect,
        ];
        let scene = self.scene();
        let highlighted: BTreeSet<_> = self
            .selected
            .map(|i| self.model.adjacent[i].iter().copied().chain([i]).collect())
            .unwrap_or_default();
        let canvas = Canvas::default().x_bounds(x).y_bounds(y).paint(|ctx| {
            for &(a, b, uses, inferred) in &scene.edges {
                let p = scene.glyphs[a].position;
                let q = scene.glyphs[b].position;
                let selected = scene.glyphs[a]
                    .members
                    .iter()
                    .chain(&scene.glyphs[b].members)
                    .any(|i| Some(*i) == self.selected);
                let color = if selected && uses {
                    Color::Yellow
                } else if selected && !inferred {
                    Color::Cyan
                } else {
                    Color::DarkGray
                };
                if inferred {
                    for segment in (0..12).step_by(2) {
                        let t = segment as f64 / 12.;
                        let u = (segment + 1) as f64 / 12.;
                        ctx.draw(&Line {
                            x1: p.0 + (q.0 - p.0) * t,
                            y1: p.1 + (q.1 - p.1) * t,
                            x2: p.0 + (q.0 - p.0) * u,
                            y2: p.1 + (q.1 - p.1) * u,
                            color,
                        });
                    }
                } else {
                    ctx.draw(&Line {
                        x1: p.0,
                        y1: p.1,
                        x2: q.0,
                        y2: q.1,
                        color,
                    });
                }
            }
            for g in &scene.glyphs {
                let color = if g.members.iter().any(|i| Some(*i) == self.selected) {
                    Color::Yellow
                } else {
                    cluster_color(&g.cluster)
                };
                ctx.draw(&Points {
                    coords: &[g.position],
                    color,
                });
            }
        });
        frame.render_widget(canvas, self.viewport);
        // Paint readable node glyphs and labels in terminal cells, after fine Braille edges.
        let mut occupied = Vec::new();
        occupied.extend(self.overlay_areas());
        if let Some(r) = self.minimap_area() {
            occupied.push(r);
        }
        let mut ordered: Vec<_> = scene.glyphs.iter().collect();
        ordered.sort_by_key(|g| {
            (
                !g.members.iter().any(|i| Some(*i) == self.selected),
                !g.members.iter().any(|i| highlighted.contains(i)),
            )
        });
        for g in &ordered {
            if let Some((column, row)) = self.screen(g.position) {
                occupied.push(Rect::new(column, row, 1, 1));
            }
        }
        for g in ordered {
            let Some((column, row)) = self.screen(g.position) else {
                continue;
            };
            let selected = g.members.iter().any(|i| Some(*i) == self.selected);
            let near = g.members.iter().any(|i| highlighted.contains(i));
            let color = if selected {
                Color::Yellow
            } else if near || self.selected.is_none() {
                cluster_color(&g.cluster)
            } else {
                Color::DarkGray
            };
            frame.render_widget(
                Paragraph::new(if g.members.len() > 1 {
                    "◉"
                } else if selected {
                    "◆"
                } else {
                    "•"
                })
                .style(Style::default().fg(color)),
                Rect::new(column, row, 1, 1),
            );
            if !(selected || near || self.labels || g.members.len() > 1) {
                continue;
            }
            let label = clipped(&g.label, 28);
            let width = Span::raw(&label).width() as u16;
            for candidate in [
                Rect::new(column.saturating_add(2), row, width, 1),
                Rect::new(column.saturating_sub(width + 1), row, width, 1),
                Rect::new(column.saturating_add(1), row.saturating_sub(1), width, 1),
            ] {
                if candidate.x < self.viewport.x
                    || candidate.y < self.viewport.y
                    || candidate.right() > self.viewport.right()
                    || candidate.bottom() > self.viewport.bottom()
                    || occupied.iter().any(|r: &Rect| r.intersects(candidate))
                {
                    continue;
                }
                frame.render_widget(
                    Paragraph::new(label.clone()).style(Style::default().fg(color)),
                    candidate,
                );
                occupied.push(candidate);
                break;
            }
        }
        self.draw_minimap(frame);
        frame.render_widget(
            Paragraph::new(format!(
                "Skill graph · Unified graph · {}/{} skills · {} links · scope {}",
                visible.len(),
                self.model.nodes.len(),
                count,
                self.scope.as_deref().unwrap_or("all")
            ))
            .style(Style::default().fg(Color::Cyan)),
            Rect::new(area.x, area.y, area.width, 1),
        );
        frame.render_widget(
            Paragraph::new(format!(
                "s list · d details · / search · ? help · Space motion {} · q quit",
                if self.motion { "on" } else { "off" }
            )),
            Rect::new(area.x, area.bottom() - 1, area.width, 1),
        );
        if self.show_list {
            let rect = self.list_area();
            frame.render_widget(Clear, rect);
            let choices = self.matches();
            let mut state = ListState::default()
                .with_selected(choices.iter().position(|&i| Some(i) == self.selected));
            let items: Vec<_> = choices
                .iter()
                .map(|&i| ListItem::new(self.model.nodes[i].id.clone()))
                .collect();
            frame.render_stateful_widget(
                List::new(items)
                    .block(
                        Block::bordered()
                            .title(format!("Filter: {} · j/k select · Esc close", self.query)),
                    )
                    .highlight_style(Style::default().fg(Color::Yellow))
                    .highlight_symbol("› "),
                rect,
                &mut state,
            );
        }
        if self.show_detail {
            let detail = if let Some(i) = self.selected {
                let n = &self.model.nodes[i];
                let outgoing: Vec<_> = self
                    .model
                    .edges
                    .iter()
                    .filter(|(a, b)| {
                        *a == i
                            && self.model.relations[&(*a, *b)]
                                .iter()
                                .any(|(r, _)| r == "uses")
                    })
                    .map(|(_, b)| self.model.nodes[*b].id.as_str())
                    .collect();
                let incoming: Vec<_> = self
                    .model
                    .edges
                    .iter()
                    .filter(|(a, b)| {
                        *b == i
                            && self.model.relations[&(*a, *b)]
                                .iter()
                                .any(|(r, _)| r == "uses")
                    })
                    .map(|(a, _)| self.model.nodes[*a].id.as_str())
                    .collect();
                let links: Vec<_> = self
                    .model
                    .relations
                    .iter()
                    .filter(|((a, b), _)| *a == i || *b == i)
                    .filter_map(|((a, b), types)| {
                        let kinds: Vec<_> = types
                            .iter()
                            .filter(|(r, _)| r != "uses")
                            .map(|(r, s)| format!("{r}/{s}"))
                            .collect();
                        if kinds.is_empty() {
                            None
                        } else {
                            Some(format!(
                                "{} [{}]",
                                self.model.nodes[if *a == i { *b } else { *a }].name,
                                kinds.join(",")
                            ))
                        }
                    })
                    .take(8)
                    .collect();
                format!(
                    "{} · cluster {}\nUses → {}\nUsed by ← {}\nConnections: {}\n{}",
                    n.id,
                    n.cluster,
                    if outgoing.is_empty() {
                        "none recorded".into()
                    } else {
                        outgoing.join(", ")
                    },
                    if incoming.is_empty() {
                        "none recorded".into()
                    } else {
                        incoming.join(", ")
                    },
                    links.join("; "),
                    n.description
                )
            } else {
                "No matching skills. / edits filter; r resets.".into()
            };
            let rect = self.detail_area();
            frame.render_widget(Clear, rect);
            frame.render_widget(
                Paragraph::new(detail)
                    .block(Block::bordered().title("Selected skill"))
                    .wrap(Wrap { trim: true }),
                rect,
            );
        }
        if self.show_help {
            let rect = self.help_area();
            frame.render_widget(Clear, rect);
            frame.render_widget(Paragraph::new("Arrows / background drag: pan · +/- / wheel: zoom · c: center\nj/k: select · g / Enter: neighborhood · o: cluster overview\n/: search · s: list · d: details · l: labels · i: unlinked · Tab: scope\nClick: select / expand · drag skill: pin · p: unpin · Space: motion\nr: reset · Esc: close overlays / quit · q / Ctrl-C: quit\nDotted: inferred-only · solid: recorded · unlinked does not mean unrelated").block(Block::bordered().title("Controls · ? / Esc close")).wrap(Wrap{trim:true}),rect);
        }
    }
    fn list_area(&self) -> Rect {
        Rect::new(
            self.viewport.x + 1,
            self.viewport.y + 1,
            (self.viewport.width / 2).clamp(30, 60),
            self.viewport.height.saturating_sub(2),
        )
    }
    fn detail_area(&self) -> Rect {
        let width = self.viewport.width.saturating_sub(2).min(100);
        let height = self.viewport.height.saturating_sub(2).min(10);
        Rect::new(
            self.viewport.right() - width - 1,
            self.viewport.bottom() - height - 1,
            width,
            height,
        )
    }
    fn help_area(&self) -> Rect {
        let width = self.viewport.width.saturating_sub(4).min(100);
        let height = self.viewport.height.saturating_sub(2).min(10);
        Rect::new(
            self.viewport.x + (self.viewport.width - width) / 2,
            self.viewport.y + (self.viewport.height - height) / 2,
            width,
            height,
        )
    }
    fn overlay_areas(&self) -> Vec<Rect> {
        let mut rects = Vec::new();
        if self.show_list {
            rects.push(self.list_area());
        }
        if self.show_detail {
            rects.push(self.detail_area());
        }
        if self.show_help {
            rects.push(self.help_area());
        }
        rects
    }
}

struct Restore;
impl Drop for Restore {
    fn drop(&mut self) {
        let _ = execute!(io::stdout(), DisableMouseCapture);
        ratatui::restore();
    }
}

pub fn run(graph: &Value, id: Option<&str>) -> Result<()> {
    ensure!(
        io::stdin().is_terminal() && io::stdout().is_terminal(),
        "graph view requires an interactive terminal; run skill-search graph in your terminal"
    );
    let mut app = App::new(Model::new(graph)?, id)?;
    let mut terminal = ratatui::try_init()?;
    let _restore = Restore;
    execute!(io::stdout(), EnableMouseCapture)?;
    terminal.draw(|f| app.draw(f))?;
    let frame_time = Duration::from_millis(33);
    let mut last_frame = Instant::now();
    loop {
        let active = app.animating();
        let timeout = if active {
            frame_time.saturating_sub(last_frame.elapsed())
        } else {
            Duration::from_millis(250)
        };
        let mut redraw = false;
        if event::poll(timeout)? {
            match event::read()? {
                Event::Key(key) if key.kind != KeyEventKind::Release => {
                    if !app.key(key) {
                        break;
                    }
                    redraw = true;
                }
                Event::Mouse(event) => {
                    app.mouse(event);
                    redraw = true;
                }
                Event::Resize(_, _) => {
                    app.drag = None;
                    redraw = true;
                }
                _ => continue,
            }
        }
        if !active {
            last_frame = Instant::now();
        }
        if app.animating() && last_frame.elapsed() >= frame_time {
            app.tick(last_frame.elapsed().as_secs_f64());
            last_frame = Instant::now();
            redraw = true;
        }
        if redraw {
            terminal.draw(|f| app.draw(f))?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{Terminal, backend::TestBackend};
    use serde_json::json;
    fn fixture() -> Value {
        json!({"nodes":[{"id":"global/a","name":"a","scope":"global","description":"First"},{"id":"global/b","name":"b","scope":"global","description":"Second"},{"id":"project/c","name":"c","scope":"project","description":"Unlinked"}],"edges":[{"source":"global/a","target":"global/b","relation":"uses"}],"aliases":[{"id":"project/a","target":"global/a"}]})
    }
    #[test]
    fn workflow_layer_is_labeled_and_navigable() {
        let mut graph = fixture();
        graph["nodes"][1]["kind"] = json!("workflow");
        graph["edges"][0]["relation"] = json!("associated_workflow");
        graph["edges"]
            .as_array_mut()
            .unwrap()
            .push(json!({"source":"global/b","target":"global/a","relation":"uses_skill"}));
        let model = Model::new(&graph).unwrap();
        assert!(model.nodes[1].name.contains("[workflow]"));
        assert!(model.adjacent[0].contains(&1));
        assert_eq!(model.relations[&(0, 1)][0].0, "associated_workflow");
        let mut app = App::new(model, Some("global/b")).unwrap();
        let mut terminal = Terminal::new(TestBackend::new(110, 32)).unwrap();
        terminal.draw(|f| app.draw(f)).unwrap();
    }
    #[test]
    fn navigation_and_alias_focus() {
        let mut a = App::new(Model::new(&fixture()).unwrap(), Some("project/a")).unwrap();
        assert_eq!(a.visible().len(), 2);
        a.key(KeyEvent::new(KeyCode::Char('g'), KeyModifiers::NONE));
        assert_eq!(a.visible().len(), 3);
        a.key(KeyEvent::new(KeyCode::Char('i'), KeyModifiers::NONE));
        assert_eq!(a.visible().len(), 2);
        a.key(KeyEvent::new(KeyCode::Char('/'), KeyModifiers::NONE));
        for c in "Second".chars() {
            a.key(KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
        }
        assert_eq!(a.matches().len(), 1);
        assert_eq!(a.model.nodes[a.selected.unwrap()].id, "global/b");
    }
    #[test]
    fn rendering_and_small_terminal_are_safe() {
        let mut a = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        a.show_detail = true;
        a.show_help = true;
        let mut t = Terminal::new(TestBackend::new(110, 32)).unwrap();
        t.draw(|f| a.draw(f)).unwrap();
        let text = t
            .backend()
            .buffer()
            .content
            .iter()
            .map(|c| c.symbol())
            .collect::<String>();
        assert!(text.contains("Uses → global/b"));
        assert!(text.contains("unlinked does not mean unrelated"));
        let mut t = Terminal::new(TestBackend::new(20, 6)).unwrap();
        t.draw(|f| a.draw(f)).unwrap();
        let small = t
            .backend()
            .buffer()
            .content
            .iter()
            .map(|c| c.symbol())
            .collect::<String>();
        assert!(small.contains("exit."));
    }
    #[test]
    fn missing_endpoints_and_empty_graph() {
        let mut graph = fixture();
        graph["edges"][0]["target"] = json!("absent");
        assert!(Model::new(&graph).is_err());
        let a = App::new(
            Model::new(&json!({"nodes":[],"edges":[],"aliases":[]})).unwrap(),
            None,
        )
        .unwrap();
        assert!(a.visible().is_empty());
        assert!(!a.selected.is_some());
    }
    #[test]
    fn camera_eases_to_target_and_sleeps_after_settling() {
        let mut app = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        app.physics_ticks = 0;
        app.key(KeyEvent::new(KeyCode::Right, KeyModifiers::NONE));
        assert_eq!(app.pan, (0., 0.));
        assert!(app.animating());
        app.tick(0.033);
        assert!(app.pan.0 > 0. && app.pan.0 < app.target_pan.0);
        for _ in 0..100 {
            app.tick(0.033);
        }
        assert!(!app.animating());
        app.key(KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        app.key(KeyEvent::new(KeyCode::Left, KeyModifiers::NONE));
        assert_eq!(app.pan, app.target_pan);
        assert!(!app.animating());
    }
    #[test]
    fn mouse_zoom_anchors_cursor_and_drag_pins_node() {
        let mut app = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        app.viewport = Rect::new(32, 3, 70, 20);
        let mouse = |kind, column, row| MouseEvent {
            kind,
            column,
            row,
            modifiers: KeyModifiers::NONE,
        };
        let before = app.world(80, 10);
        app.mouse(mouse(MouseEventKind::ScrollUp, 80, 10));
        for _ in 0..100 {
            app.tick(0.033);
        }
        let after = app.world(80, 10);
        assert!((before.0 - after.0).abs() < 0.01 && (before.1 - after.1).abs() < 0.01);
        app.motion = false;
        app.pan = app.model.positions[0];
        app.target_pan = app.pan;
        app.scale = 10.;
        app.target_scale = 10.;
        let (x, y) = app.screen(app.model.positions[0]).unwrap();
        app.mouse(mouse(MouseEventKind::Down(MouseButton::Left), x, y));
        app.mouse(mouse(MouseEventKind::Drag(MouseButton::Left), x + 3, y + 2));
        app.mouse(mouse(MouseEventKind::Up(MouseButton::Left), x + 3, y + 2));
        assert!(app.pinned.contains(&0));
        let pinned = app.model.positions[0];
        app.motion = true;
        for _ in 0..150 {
            app.tick(0.033);
        }
        assert_eq!(app.model.positions[0], pinned);
        assert!(app.drag.is_none());
    }
    #[test]
    fn overview_aggregates_geometry_without_losing_typed_relationships() {
        let mut model = Model::new(&fixture()).unwrap();
        model.mapped = true;
        model.nodes[0].cluster = "one".into();
        model.nodes[1].cluster = "one".into();
        model.nodes[2].cluster = "two".into();
        let mut app = App::new(model, None).unwrap();
        let scene = app.scene();
        assert_eq!(scene.glyphs.len(), 2);
        assert_eq!(
            scene.glyphs.iter().map(|g| g.members.len()).sum::<usize>(),
            3
        );
        assert!(scene.edges.is_empty());
        assert_eq!(app.model.relations[&(0, 1)][0].0, "uses");
        app.scale = 22.;
        assert_eq!(app.scene().glyphs.len(), 3);
        app.scale = 110.;
        app.query = "First".into();
        assert_eq!(app.scene().glyphs.len(), 3);
    }
    #[test]
    fn layout_is_deterministic_bounded_and_finite() {
        let mut a = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        let mut b = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        for _ in 0..150 {
            a.tick(0.033);
            b.tick(0.033);
        }
        assert_eq!(a.model.positions, b.model.positions);
        assert!(!a.animating());
        assert!(
            a.model
                .positions
                .iter()
                .all(|p| p.0.is_finite() && p.1.is_finite())
        );
        assert!(
            a.model
                .positions
                .iter()
                .zip(&a.anchors)
                .all(|(p, q)| (p.0 - q.0).abs() < 30. && (p.1 - q.1).abs() < 30.)
        );
    }
    #[test]
    fn labels_clip_unicode_and_render_at_zoom_without_overlap_panics() {
        assert!(Span::raw(clipped("界界界界界界界", 7)).width() <= 7);
        let mut app = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        app.labels = true;
        app.scale = 12.;
        let mut terminal = Terminal::new(TestBackend::new(110, 32)).unwrap();
        terminal.draw(|f| app.draw(f)).unwrap();
        let text = terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|c| c.symbol())
            .collect::<String>();
        assert!(text.contains("Space motion on"));
        assert!(text.contains("Map"));
        assert!(text.contains("◆"));
    }
    #[test]
    fn full_screen_overlays_do_not_resize_camera_or_accept_graph_clicks() {
        let mut app = App::new(Model::new(&fixture()).unwrap(), None).unwrap();
        let mut terminal = Terminal::new(TestBackend::new(110, 32)).unwrap();
        terminal.draw(|f| app.draw(f)).unwrap();
        assert_eq!(app.viewport, Rect::new(0, 1, 110, 30));
        let text = terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|c| c.symbol())
            .collect::<String>();
        assert!(!text.contains("Filter:") && !text.contains("Selected skill"));
        app.key(KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE));
        app.key(KeyEvent::new(KeyCode::Char('d'), KeyModifiers::NONE));
        terminal.draw(|f| app.draw(f)).unwrap();
        assert_eq!(app.viewport, Rect::new(0, 1, 110, 30));
        let rect = app.list_area();
        let selected = app.selected;
        app.mouse(MouseEvent {
            kind: MouseEventKind::Down(MouseButton::Left),
            column: rect.x + 2,
            row: rect.y + 2,
            modifiers: KeyModifiers::NONE,
        });
        assert_eq!(app.selected, selected);
        assert!(app.drag.is_none());
        assert!(app.key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)));
        assert!(!app.show_list && !app.show_detail && !app.show_help);
        app.key(KeyEvent::new(KeyCode::Char('/'), KeyModifiers::NONE));
        assert!(app.editing && app.show_list);
        app.key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        assert!(!app.editing && !app.show_list);
        assert!(!app.key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)));
    }
    #[test]
    #[ignore = "requires explicit public/local fixture and output paths"]
    fn real_inventory_layout_smoke() {
        let path = std::env::var("SKILL_GRAPH_TEST_FIXTURE").unwrap();
        let output = std::env::var("SKILL_GRAPH_TEST_OUTPUT").unwrap();
        let graph: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        let mut app = App::new(Model::new(&graph).unwrap(), None).unwrap();
        let before = app.scene().glyphs.len();
        let started = Instant::now();
        for _ in 0..150 {
            app.tick(0.033);
        }
        let elapsed = started.elapsed();
        assert!(!app.animating());
        let mut terminal = Terminal::new(TestBackend::new(140, 44)).unwrap();
        terminal.draw(|f| app.draw(f)).unwrap();
        let buffer = terminal.backend().buffer();
        let mut text = String::new();
        for row in buffer.content.chunks(140) {
            for cell in row {
                text.push_str(cell.symbol());
            }
            text.push('\n');
        }
        std::fs::write(&output, text).unwrap();
        println!(
            "nodes={} overview_glyphs={} physics_ms={:.2}",
            app.model.nodes.len(),
            before,
            elapsed.as_secs_f64() * 1000.
        );
        assert!(before < app.model.nodes.len());
        app.center();
        for _ in 0..150 {
            app.tick(0.033);
        }
        assert_eq!(app.scene().glyphs.len(), app.visible().len());
    }
}
