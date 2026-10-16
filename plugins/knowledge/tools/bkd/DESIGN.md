# BookmarkDrop viewer conventions

The browser is a quiet file viewer. Use the existing vanilla HTML/CSS/JavaScript
and loopback server; do not introduce a UI framework or a hosted application.

- A 180px source sidebar, compact toolbar, 52px bookmark rows and quiet footer
  provide a Finder-like hierarchy. Names sort alphabetically in library browsing;
  search retains relevance order. Kinds are text, not decorative badges.
- Use CSS palette tokens in `web/style.css`: warm paper `--bg`, sidebar,
  ink, muted text, line, selection and accent. A system dark preference swaps
  the palette. Native system type suits the file viewer; Georgia suits reading.
- Icon controls have accessible names, tooltips and visible focus. Use native
  buttons, select controls, tables and modal dialogs. Do not simulate macOS
  window controls. Preserve browser zoom and keyboard navigation.
- Capture stays hidden until +, a link drop or URL paste. Drops are data, not
  publication. Editing URL/title/type clears the publication checkbox.
- Space or double-click opens Quick Look; Escape closes it. The source link
  remains visible when a site blocks iframe embedding. Reader and saved notes
  are explicit modes. Keep iframe sandbox restrictions; never bypass site headers.
- Reader uses a narrow text column and inert text nodes. Conversion is temporary,
  can omit peripheral content, and is not an evidence-ingestion workflow.
- Below 700px, the source list becomes a native dropdown and Source moves out
  of the visible table. Keep title/domain and kind visible without horizontal scroll.

`web/index.html` defines the surface; `web/app.js` owns behavior; `src/ui.rs`
owns authenticated data/publication routes; `src/reader.rs` owns checked public
fetches. `tests/browser.mjs` exercises fixture browser drag, previews, reader
inertness, citations, graph navigation, pagination and desktop/mobile layouts.
Screenshots use synthetic records, never the real bookmark collection.

Supplied session records use the same rows, Quick Look citation details and graph
navigation as supplied insights and skills. Session labels identify their kind;
no new screen, visual taxonomy or automatic source-store access is introduced.
