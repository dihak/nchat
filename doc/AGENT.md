# Agent control

nchat can expose a local control socket while the TUI is running so agents and
scripts can list chats, read history, and send messages without driving
keystrokes or starting a second nchat process.

A second nchat instance still cannot open the same confdir (profile lock). The
control socket is the supported out-of-process API for a *running* TUI.

## Socket

Path: `$confdir/control.sock` (mode `0600`).

- Created when the TUI is up and the profile is loaded.
- Removed on clean exit (stale sockets are unlinked on start).
- Only present in builds that include this feature. The stock/installed binary
  must be rebuilt from a branch that contains agent control.

Example confdirs on this setup:

- Telegram: `~/.config/nchat-telegram/control.sock`
- WhatsApp: `~/.config/nchat-whatsapp/control.sock`

## Protocol

Newline-delimited JSON over a Unix stream socket. One request line, one response
line. Connections may send multiple requests sequentially.

Request:

```json
{"id":"1","method":"chats","params":{}}
```

Success:

```json
{"id":"1","ok":true,"result":{"chats":[{"id":"...","title":"...","unread":false,"muted":false,"pinned":false,"lastMessageTime":0}]}}
```

Error:

```json
{"id":"...","ok":false,"error":"..."}
```

Malformed JSON yields `ok:false` and the connection stays open. Unknown methods
yield `ok:false`.

### Methods

| Method | Params | Result |
| --- | --- | --- |
| `chats` | `{}` | `{ "chats": [ { id, title, unread, muted, pinned, lastMessageTime } ] }` |
| `history` | `chat` (id), `limit` optional (default 30, clamp 1..100) | `{ "messages": [ { id, senderId, text, timeSent, isOutgoing, quotedId } ] }` |
| `send` | `chat`, `text`, `replyTo` optional | `{ "sent": true }` |
| `send_file` | `chat`, `path` (existing regular file) | `{ "sent": true }` |

Notes:

- `chats` / `history` use the UI model/cache. They do **not** mark chats read.
- `history` may issue a protocol `GetMessages` fetch if the cache is short. The
  user's selected chat is not changed permanently for that fetch.
- `send` / `send_file` reuse the same `SendMessageRequest` path as the UI. They
  send by chat id and do **not** steal the selected chat when the protocol
  allows it. Empty `text` is an error. `path` must exist and be a regular file.
- Work runs on the UI thread (self-pipe wake from the accept thread). Requests
  time out after about 30 seconds if the UI cannot service them.

## `nchat-ctl`

Installed next to `nchat` (e.g. `~/.local/bin/nchat-ctl`):

```bash
nchat-ctl --confdir DIR chats
nchat-ctl --confdir DIR history --chat ID [--limit N]
nchat-ctl --confdir DIR send --chat ID --text TEXT [--reply-to ID]
nchat-ctl --confdir DIR send-file --chat ID --path FILE
```

- Exit `0` on success (pretty-prints the `result` object on stdout).
- Exit `1` on protocol/API error (message on stderr).
- Exit `2` if the socket is missing / not connectable (TUI not running for that
  confdir). Does not start nchat and does not fall back to a second process.

## MCP server (Grok)

`nchat_mcp.py` is a stdlib-only MCP stdio server that shells out to `nchat-ctl`
(override path with `NCHAT_CTL`).

Tools:

- `nchat_chats` — `protocol`: `telegram` \| `whatsapp`
- `nchat_history` — `protocol`, `chat_id`, `limit` optional
- `nchat_send` — `protocol`, `chat_id`, `text`, `reply_to` optional
- `nchat_send_file` — `protocol`, `chat_id`, `path`

Confdir map:

- telegram → `$NCHAT_TELEGRAM_DIR` or `~/.config/nchat-telegram`
- whatsapp → `$NCHAT_WHATSAPP_DIR` or `~/.config/nchat-whatsapp`

Grok `config.toml` snippet (after install to `~/.local/bin`):

```toml
[mcp_servers.nchat]
command = "python3"
args = ["$HOME/.local/bin/nchat_mcp.py"]
enabled = true
```

Do not enable this against an older nchat binary that has no control socket.

## Safety

- Read tools (`chats`, `history`) are fine whenever the TUI is up.
- Send only when the user asked to send that text/file to that chat. A send is
  the user's linked-device account.
- QR / pairing login stays manual (`nchat -s` / `telegram -s` / `whatsapp -s` in
  a real terminal).
