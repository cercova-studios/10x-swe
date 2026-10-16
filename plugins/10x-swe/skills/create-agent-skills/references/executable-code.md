# Helpers that earn their keep

Use a script only when it makes a repeated operation clearer, safer or verifiable.
Keep it in the owning bundle's scripts directory. Resolve paths from the selected
SKILL_DIR; do not depend on the caller's working directory or a global wrapper.

State whether a resource is reference data or executable code. Inspect untrusted
helpers before execution; their presence in a graph is not approval. Document inputs,
outputs, dependencies, external effects and failure behavior. Pin build inputs and
check prerequisites explicitly rather than downloading packages during discovery.

Pass structured arguments without shell evaluation. Bound files, subprocesses and
network operations. Preserve useful errors and cleanup. Missing input or permission
failure must not silently become empty successful data. Avoid overwriting outputs;
use owned temporary files and atomic publication when needed. Do not hide a provider
failure behind a default value unless that fallback is an explicit public contract.

Exercise the real helper with a small fixture, invalid input, interruption where
relevant and an external-failure case. A skipped check remains unverified. Name
actual available harness tools; do not assume universal MCP server/tool identifiers.
