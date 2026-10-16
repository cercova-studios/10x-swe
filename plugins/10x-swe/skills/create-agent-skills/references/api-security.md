# Credential and API boundaries

Require credentials through explicitly injected environment variables or a
user-configured credential provider. Never search shell history, project secret
files, sessions or other agents' environments. Never create a central .env file or
credential placeholders as a side effect of skill creation.

Environment-variable expansion does not automatically print a secret, but shell
tracing, process arguments, debug logs and tool outputs can expose it. Prefer a
small reviewed client that reads an allowlisted variable internally and sends it
only to the intended authenticated endpoint. Disable credential-bearing diagnostics;
errors must describe the missing configuration without printing values.

Do not assume a shared secure-api wrapper or account-profile registry exists.
Use an existing approved client where appropriate. Otherwise expose one bounded
operation, pass arguments without shell interpolation, validate URLs/identifiers,
set timeouts and response limits, reject unexpected redirects, and retain useful
redacted errors. Do not use eval to select an account or construct commands.

Bind the destination/account, authorization scope and external effect before a
write. A selected credential is not permission to publish, message, delete or
change permissions. Keep credentials out of records, receipts, exports and fixtures.
Test missing credentials, invalid inputs and provider failures without real secrets.
