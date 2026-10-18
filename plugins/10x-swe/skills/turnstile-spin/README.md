# Turnstile Spin

Add Cloudflare Turnstile to an existing frontend and backend. Start with
[SKILL.md](SKILL.md), then read the required creation or existing-widget recovery
procedure and the relevant framework reference.

The helpers emit structured statuses for authentication, widget creation and
validation. Branch on those statuses. Existing-widget recovery preserves the
sitekey and requires a confirmed account, executable, target and write manifest
before secret retrieval or storage. A failed probe cleanup stops creation.

Run `python3 tests/test_helpers.py` for isolated helper regressions. Live validation
requires an approved widget and backend, a fresh real token and a rejected replay;
dummy validation does not establish end-to-end success.

Derived from [Cloudflare skills](https://github.com/cloudflare/skills/tree/main/skills/turnstile-spin).
Consult [Turnstile documentation](https://developers.cloudflare.com/turnstile/) for
the product contract. Fetched bundles require quarantine and exact-bundle review
before activation.
