# Terminal graph

Run `skill-search graph` in a terminal of at least 65 columns × 18 rows. The viewer reads local metadata only. It does not load skill instructions, call providers or save layout state.

The graph fills the terminal, with one status row and one controls row. The skill list, details and help are hidden by default. Press `s`, `d` or `?` to toggle their overlays. `/` opens the list for search. Escape closes open overlays before quitting. Overlays do not resize the graph or move the camera; mouse events over them do not affect the graph beneath.

The overview groups skills by provisional topic cluster. Zoom in or click a cluster to reveal its members. Without a fresh topic map, the viewer shows individual skills in connected-component islands. Cluster labels and positions are heuristic; they do not establish workflow applicability.

| Action | Mouse | Keyboard |
| --- | --- | --- |
| Pan | Drag background | Arrow keys |
| Zoom | Wheel, anchored at cursor | `+` / `-` |
| Select | Click skill | `j` / `k` |
| Center selected skill | — | `c` |
| Focus neighborhood | — | `g` / Enter |
| Toggle cluster overview | — | `o` |
| Show additional labels | — | `l` |
| Filter list | — | `/`, type, Enter |
| Toggle skill list | — | `s` |
| Toggle selected-skill details | — | `d` |
| Toggle full keyboard help | — | `?` |
| Cycle project scope | — | Tab |
| Toggle unlinked skills | — | `i` |
| Disable or resume motion | — | Space |
| Pin skill for this session | Drag skill | — |
| Unpin selected skill | — | `p` |
| Reset camera and filters | — | `r` |
| Close overlays, then exit | — | Escape |
| Exit immediately | — | `q`, Ctrl-C |

Inferred-only connections use dotted lines; recorded connections use solid lines. Selection highlights incident links and neighboring skills. Details preserve directed `uses`, `references`, `related`, and inferred status even when overview geometry merges multiple connections. Hidden labels do not hide skills from the list. The minimap shows the viewport within the full layout.

Camera movement eases toward its target. A deterministic layout starts from cluster/component islands and settles using local repulsion, springs and anchor forces. Physics has a finite tick budget and stops early after low movement. Idle frames do not redraw. Space stops physics and makes camera controls immediate. Pins and positions last only for this session; no disk cache or terminal-specific pixel protocol is required.

Terminal restoration runs on normal exit and handled errors, including disabling mouse capture. SIGKILL cannot run cleanup; use `reset` if a forced kill leaves the terminal altered. Mouse support depends on the terminal; keyboard controls remain available.
