---
name: knowledge-setup
description: Bootstrap an isolated knowledge toolchain and inspect existing skill
  bundles without overwriting or activating them.
metadata:
  skill-graph-id: global/knowledge-setup
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Bootstrap this clone

Read the root README and ARCHITECTURE.md. Run `./knowledge plan --prefix NEW_DIR`
and fix any failed `build_checks` (its `fix` field gives a one-line command),
then `./knowledge setup --prefix NEW_DIR`. Builds use locked source dependencies.
Source the printed env.sh explicitly; setup never edits shell profiles or global
instructions. Run `./knowledge doctor` to verify installed artifacts; it checks
`$AGENT_KNOWLEDGE_HOME` (or `--prefix DIR`) and prints the path it checked.
After pulling a new revision, install into a fresh prefix and carry the user's
library and state over with `./knowledge setup --prefix NEW_DIR --from OLD_DIR`.

`knowledge-intake --root harness=/absolute/skills` inspects metadata, full-bundle
hashes, aliases, conflicts and limitations without executing helpers. Review its
report before adding `--index`: graph registration is read-only and namespaced,
not activation or acceptance. Existing source files stay unchanged.

Search with `skill-search search 'task' --limit 5`, inspect selected entrypoints,
then navigate neighbors, path or graph. Choose the smallest useful route. Each tool
owns its store and exchanges versioned records/files through pipes. Configure models,
connectors, Dagu and media tools separately. Run session indexing, imports and
publication as explicit operations after setup.
