# assist-mcp

An MCP (Model Context Protocol) server that gives Claude and other MCP clients
live access to **California ASSIST articulation agreements** (assist.org) —
which community-college courses transfer to which CSU/UC requirements.

It talks to the internal API behind the assist.org site, so **no API key or
account is required**. The server handles assist.org's XSRF cookie handshake
transparently, retries it once if the session expires, and caches responses
in memory for 24 hours (articulation data changes on an academic-year cadence).

## Tools

| Tool | Purpose |
|---|---|
| `search_institutions(query, community_colleges_only)` | Find institution IDs by name or code |
| `list_academic_years()` | Available academic years (fall_year 2025 = 2025–2026) |
| `list_transfer_partners(institution_id)` | Which institutions have agreements with a given one, and for which years |
| `list_agreements(sending_institution_id, receiving_institution_id, academic_year, category, query)` | Agreement reports for a pair+year; categories: `major`, `dept`, `prefix`, `breadth` |
| `get_articulation_agreement(key)` | Parsed course-to-course articulations for one agreement, with And/Or logic rendered |

Typical flow: `search_institutions` → `list_agreements` → `get_articulation_agreement`.

Example: *"Which De Anza courses cover the UCSD Philosophy B.A. requirements?"*
→ `search_institutions("de anza")` = 113, `search_institutions("san diego")` = 7,
`list_agreements(113, 7, 2025, query="philosophy")` →
`get_articulation_agreement("76/113/to/7/Major/…")` →
`PHIL 10 — Introduction to Logic (4.0 units) ⇐ PHIL 7H OR PHIL 7`.

## Install

Requires Python ≥ 3.10. The only dependency is the `mcp` SDK.

```bash
pip install /path/to/assist-api/mcp        # or: uv tool install
```

### Claude Code

```bash
claude mcp add assist -- assist-mcp
# or without installing:
claude mcp add assist -- uv run --directory /path/to/assist-api/mcp assist-mcp
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "assist": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/assist-api/mcp", "assist-mcp"]
    }
  }
}
```

## Caveats

- The internal assist.org API is undocumented and unversioned; it has changed
  before (the XSRF requirement) and may change again. The official keyed API
  (`prod.assistng.org`) uses the same shapes, so migrating this server to it
  later is a base-URL + auth-header swap.
- Responses are cached per-process for 24 h; restart the server to force fresh
  data.
- Be a good citizen: this is a public state-funded service. The server sends a
  descriptive User-Agent and makes one upstream request per uncached tool call.
