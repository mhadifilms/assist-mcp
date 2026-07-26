# assist-mcp

**Ask Claude which of your community-college courses transfer.**

An [MCP](https://modelcontextprotocol.io) server that gives Claude (and any
other MCP client) live access to **California ASSIST articulation agreements**
from [assist.org](https://assist.org) — the official source of truth for
course transferability between California community colleges, CSUs, and UCs.

**No API key. No account. No setup beyond installing it.** The server talks to
the same backend the assist.org website uses and transparently handles its
XSRF cookie handshake, so it works out of the box.

```text
You:    Which De Anza courses do I need for UCSD's Philosophy B.A.?
Claude: → search_institutions("de anza") → search_institutions("san diego")
        → list_agreements(113, 7, 2025, query="philosophy")
        → get_articulation_agreement("76/113/to/7/Major/…")

        UCSD requires PHIL 10 (Introduction to Logic, 4 units) —
        satisfied at De Anza by PHIL 7 or PHIL 7H.
```

## Install

Requires Python ≥ 3.10. The recommended way is [uv](https://docs.astral.sh/uv/)
(`uvx` runs it straight from GitHub, nothing to clone):

### Claude Code

```bash
claude mcp add assist -- uvx --from git+https://github.com/mhadifilms/assist-mcp assist-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "assist": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mhadifilms/assist-mcp", "assist-mcp"]
    }
  }
}
```

### Cursor / other MCP clients

Any client that speaks MCP over stdio works with the same command:

```json
{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/mhadifilms/assist-mcp", "assist-mcp"]
}
```

### pip

```bash
pip install git+https://github.com/mhadifilms/assist-mcp
assist-mcp   # starts the stdio server; point your MCP client at this command
```

## Tools

| Tool | What it does |
|---|---|
| `search_institutions(query, community_colleges_only)` | Find institution IDs by name or code (~240 CA institutions, matches historical names too) |
| `list_academic_years()` | Academic years on ASSIST (`fall_year` 2025 = 2025–2026) |
| `list_transfer_partners(institution_id)` | Which institutions have agreements with a given one, and for which years |
| `list_agreements(sending_id, receiving_id, academic_year, category, query)` | Agreement reports for a college pair + year; categories: `major`, `dept`, `prefix`, `breadth` |
| `get_articulation_agreement(key)` | Parsed course-to-course articulations for one agreement |

Typical chain: `search_institutions` → `list_agreements` → `get_articulation_agreement`.

Articulations come back with the And/Or requirement logic already rendered —
including nested cases like:

```text
COMPSCI 61A — The Structure and Interpretation of Computer Programs (4.0 units)
  ⇐ COMSC 140 OR (COMSC 240 and MATH 192)
```

plus advisement notes when ASSIST includes them (e.g. *"Must complete an
additional university course after transfer to satisfy this requirement"*).

## Things to ask

- *"I'm at Diablo Valley College. What do I need for EECS at Berkeley?"*
- *"Compare the CS transfer requirements at UCLA vs UCSD from Santa Monica College."*
- *"Which UCs does De Anza have articulation agreements with?"*
- *"Does PHIL 7 at De Anza articulate anywhere at UCSD?"*

## How it works

- assist.org's internal API requires an ASP.NET antiforgery (XSRF) handshake:
  the server fetches the site shell once to obtain the cookie pair, then echoes
  the `X-XSRF-TOKEN` header on every request, re-handshaking automatically if
  the session expires.
- Several payload fields arrive as JSON strings nested inside JSON
  (`articulations`, `templateAssets`, institutions, academic year) — the
  server decodes all of them before returning results.
- Responses are cached in memory for 24 hours; articulation data only changes
  on an academic-year cadence. Restart the server to force fresh data.
- Stdlib-only HTTP; the sole dependency is the official `mcp` SDK.

## Caveats

- This uses assist.org's **undocumented internal API** — the one their own
  website runs on. It has changed before (the XSRF requirement) and may change
  again without notice. ASSIST's official keyed API
  ([prod.assistng.org/apidocs](https://prod.assistng.org/apidocs/docs/gettingstarted))
  uses the same data shapes, so this server can migrate to it with a base-URL
  and auth-header swap once keys are generally available.
- Be kind to a public, state-funded service: the server sends a descriptive
  User-Agent and makes at most one upstream request per uncached tool call.
- Not affiliated with or endorsed by ASSIST. Always confirm plans with a
  counselor — articulation ≠ admission.

## License

[MIT](LICENSE)
