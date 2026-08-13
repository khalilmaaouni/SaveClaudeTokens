# token-shield-mcp

The Token Shield MCP server: a read-only wrapper (plus two guarded write
tools) over the existing `scripts/` modules, stdio transport, official MCP
Python SDK. Wave 1 ships nine tools and three resources.

See the repository root `README.md`, section "MCP server (optional)", for
the install config and the full tool list. This package is a separate,
opt-in install: the Claude Code plugin itself gains zero dependencies, zero
hooks, and zero always-on cost from it.

```bash
python3 src/token_shield_mcp/server.py
```

Design: `docs/superpowers/specs/2026-08-12-token-shield-mcp-design.md` and
`docs/superpowers/specs/2026-08-13-consumption-report-design.md`.
