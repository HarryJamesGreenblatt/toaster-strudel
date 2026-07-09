# strudel-mcp

A lean **Strudel knowledge server** (MCP) that grounds AI-assisted composition in
the *official* Strudel API/docs. It does not host audio or edit files — that's
handled by the IDE.

## All-IDE workflow

- **Host:** the [`cmillsdev.strudelvs`](https://marketplace.visualstudio.com/items?itemName=cmillsdev.strudelvs)
  VS Code extension runs the real Strudel engine in a webview and plays the active
  `.strudel.js` file — **Ctrl+Enter** play, **Ctrl+.** stop, all instruments
  (dirt-samples, tidal-drum-machines, piano, VCSL, mridangam, synths, soundfonts),
  pianoroll, and live note highlighting.
- **Compose:** the agent edits `.strudel.js` files with normal editor tools; you
  press Ctrl+Enter to play, Ctrl+. to stop.
- **Ground:** the agent consults this MCP's `strudel_docs` tool for the real API
  before writing patterns.

## MCP surface

| Tool / resource | Purpose |
|---|---|
| `strudel_docs({ topic })` | Fetch official Strudel docs live from strudel.cc (topic key or path like `learn/tonal`). |
| `strudel_topics()` | List known doc topics. |
| `strudel://reference` | Quick Strudel cheat sheet (resource). |

## Setup

```powershell
cd mcp-server
npm install
```

The server is wired into VS Code via [.vscode/mcp.json](../.vscode/mcp.json).
After changing the server, restart the `strudel` MCP server (Command Palette →
"MCP: List Servers" → Restart).

## Notes

- Deps: `@modelcontextprotocol/sdk`, `zod` only. Node 18+ (uses global `fetch`).
- Strudel is AGPL-3.0; the `strudelvs` extension bundles the engine under AGPL.
