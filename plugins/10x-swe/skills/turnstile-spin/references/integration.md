# Integration, migration, and edge cases

The original sections below refer to Step 9 in [creation wizard](creation-wizard.md). For an existing widget, follow [guarded recovery](existing-widget.md) before edits and destination validation.

### The frontend-edit contract

When wiring an existing form or user-triggered endpoint (Step 9), the contract is: **gate, don't replace.** The user's existing handler keeps doing what it did. Spin only adds a validation step before it.

Frontend (embeds the widget; submits to the user's existing endpoint):

```html
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>

<form action="/signup" method="POST">
  <!-- existing inputs unchanged -->
  <div class="cf-turnstile" data-sitekey="<SITEKEY>" data-action="signup"></div>
  <button type="submit">Sign up</button>
</form>
```

Backend: use the canonical siteverify fetch from Step 9 inside the existing handler. Read the token from `req.body['cf-turnstile-response']`, require `success === true`, compare `action` with the surface's action, compare `hostname` with the deployment-specific frontend hostname allowlist, and leave the rest of the handler alone. If the existing handler was a stub, Spin leaves it a stub gated on those checks. The user can replace the stub later; that's not Spin's job.

**Token lifecycle: tokens are single-use.** A `cf-turnstile-response` token is redeemed exactly once at Siteverify. A native form that navigates away does not need reset logic. If the page remains active after a submission attempt, render the widget explicitly, retain that widget's ID, and call `window.turnstile.reset(widgetId)` after the request completes before allowing a retry. Each protected surface must retain and reset its own widget ID. The framework references show the appropriate lifecycle hook.

## Migrating from another CAPTCHA

During the Step 6 codebase scan, also look for existing reCAPTCHA or hCaptcha. If found, switch Step 7 to a migration plan.

Detection signals:
- reCAPTCHA: `https://www.google.com/recaptcha/api.js`, `class="g-recaptcha"`, `data-sitekey="6L..."`, backend POST to `/recaptcha/api/siteverify`
- hCaptcha: `https://js.hcaptcha.com/1/api.js`, `class="h-captcha"`, backend POST to `https://hcaptcha.com/siteverify`

Substitution:
- Replace script tags with `https://challenges.cloudflare.com/turnstile/v0/api.js` (`async defer`).
- Replace `class="g-recaptcha"` / `class="h-captcha"` divs with `class="cf-turnstile"`, update `data-sitekey` to the new Turnstile sitekey, and set a meaningful `data-action` for the protected surface.
- Token field changes from `g-recaptcha-response` to `cf-turnstile-response`.
- Backend siteverify URL points at `https://challenges.cloudflare.com/turnstile/v0/siteverify`. Drop `RECAPTCHA_SECRET` / `HCAPTCHA_SECRET` env vars; add `TURNSTILE_SECRET`.

Edge cases to surface to the user:
- **reCAPTCHA v3 score thresholds.** Turnstile has no score. Tell the user explicitly that migrated code will reject on `success === false`.
- **reCAPTCHA Enterprise.** Don't auto-migrate. Point at [developers.cloudflare.com/turnstile/migration/recaptcha/](https://developers.cloudflare.com/turnstile/migration/recaptcha/).
- **Custom `action=` values.** Preserve any valid custom action the user passed to `grecaptcha.execute` as `data-action` on the widget. Otherwise, use the stable action assigned in Step 7. In both cases, validate the returned action in the backend.

## Edge cases

| Situation                                      | Action                                                                                                                                                                                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Account enumeration is unavailable             | Ask the user for the account ID and export `CLOUDFLARE_ACCOUNT_ID`, or obtain approval for canonical absolute `WRANGLER_BIN` and exact `WRANGLER_VERSION`. Do not install or run a project-local Wrangler. |
| Multiple Cloudflare accounts                   | `scripts/auth-probe.sh` returns all accounts; ask the user to choose, export `CLOUDFLARE_ACCOUNT_ID`                                                                                                                                  |
| Cloudflare Pages project                       | Wire siteverify inside a Pages Function (or the equivalent for your framework). The Pages Plugin at [developers.cloudflare.com/pages/functions/plugins/turnstile](https://developers.cloudflare.com/pages/functions/plugins/turnstile/) is a shortcut. |
| Cloudflare Workers backend                     | Use the canonical fetch idiom from Step 9 inside the Worker's request handler. `fetch` to `challenges.cloudflare.com` works the same way it does in Node.                                                                             |
| `EXPECTED_HOSTNAME` mismatch                   | Update widget domains via PUT, not PATCH (PATCH returns `10405 Method not allowed`): `curl -X PUT .../widgets/$SITEKEY -d '{"name":"...","mode":"managed","domains":[...]}'`                                                          |
| Token expired mid-flow                         | Stop, re-run `scripts/auth-probe.sh`, prompt for fresh credentials                                                                                                                                                                    |
| Validation returns `invalid-input-secret`      | The secret didn't reach the backend. Re-check `TURNSTILE_SECRET` in the customer's env / secret manager. If it's a Workers backend, run `wrangler secret list` to confirm the secret is bound to the right script.                    |
| Validation returns `invalid-input-response`    | Expected for a dummy probe token; that means the secret IS valid. validate.sh treats this as success.                                                                                                                                 |
