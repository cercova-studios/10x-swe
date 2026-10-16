---
name: bkd
description: Search bookmarks and explicit piped knowledge records with separate corpus
  ranks, citations and graph navigation.
metadata:
  skill-graph-id: global/bkd
---

# Search and review bookmarks

`bkd search 'topic' --lexical-only --list` ranks bookmarks without a neural model.
`bkd --records FILE search 'topic' --lexical-only --list` joins supplied snapshots
without opening other tools' stores; `--records -` accepts stdin. Keep corpus ranks
separate; scores are not calibrated across producers. Inspect citations and coverage.

The default `bkd` opens capture/review in the terminal; `bkd ui` is an optional local
viewer. Browser-drop transport must be tested in the current terminal. Inspect
`bkd --help` for available commands. BKD_HOME isolates local state.

Connectors require explicitly injected credentials. Setup never connects or imports.
Neon imports can become public: preview selection, deduplication and destination,
then obtain explicit approval before apply. Neural ranking is an optional local
model capability; missing prerequisites must remain visible.
