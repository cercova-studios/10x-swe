# Provenance and third-party material

The repository owner's code and substantive local adaptations use the root MIT
license. Retain existing upstream notices and licenses; this does not relicense
third-party material.

- The original `10x-swe` plugin credits [Armin Ronacher's agent-stuff](https://github.com/mitsuhiko/agent-stuff),
  [Peter Steinberger's OpenClaw](https://github.com/steipete/openclaw), and
  [Will Hobson's agents](https://github.com/wshobson/agents). Those credits remain
  in the plugin README. The included OpenAI documentation skill retains its license.
- Skill-authoring helpers retain their Apache-2.0 license in
  `plugins/10x-swe/skills/create-agent-skills/references/skill-creator-LICENSE.txt`.
  The frontend-design bundle retains its own `LICENSE.txt`.
- Turnstile guidance and helpers derive from
  [Cloudflare skills](https://github.com/cloudflare/skills/tree/main/skills/turnstile-spin)
  with local safety and workflow adaptations. Product documentation remains the
  authority for Cloudflare behavior; this bundle is maintained independently of
  the hosted Spin prompt.
- Distiller includes Noto Sans Bold with its retained SIL Open Font License in
  `plugins/knowledge/tools/distiller/assets/NotoSans-LICENSE.txt`.
- Distiller HTML regression fixtures retain their original source URLs and content;
  they are test evidence, not newly authored articles or material relicensed as MIT.
- Cargo dependencies are resolved from their retained Cargo.lock files. Python
  distributions are pinned by version and upstream artifact hashes in requirements.lock.
  Their respective upstream licenses apply. No model weights or native third-party
  application bundles ship here.
- `plugins/knowledge/provenance.json` records original source-file digests before
  portability edits. They are origin evidence, not the current files' hashes and
  not scanner acceptance. Installation receipts bind the final built distribution.

The knowledge components were maintained locally by the repository owner; source
hashes establish the copied revision where no independent upstream repository was
available. Existing external skill intake preserves locations, hashes, original IDs,
aliases and conflicts as unreviewed data. It never transfers another bundle's review.
