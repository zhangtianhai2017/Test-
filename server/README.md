# Command Relay — Tomcat JSP + Windows PowerShell Agent

Lets a remote operator (Claude in a sandbox) execute commands on a
local Windows machine via a public Tomcat server as a relay. Zero
external dependencies on either end — the server is one JSP, the agent
is one PowerShell script.

## Flow

```
  operator                Tomcat (your cloud)               Windows
  ────────                ───────────────────               ───────
  POST /relay.jsp                                          GET  /relay.jsp
       ?action=enqueue   ─────► pending queue ◄─────────       ?action=pull
       (script, id)             (LinkedBlockingQueue)           (long-poll 30s)
                                       │
                                       │ pull returns cmd
                                       ▼
                                                                executes via
                                                                powershell.exe
                                                                       │
  GET  /relay.jsp                                          POST /relay.jsp
       ?action=result   ◄─────  results map ◄──────────       ?action=result
       ?id=...                  (ConcurrentHashMap)          (stdout, stderr, exit)
       (long-poll 60s)
```

## Deploy

### 1. Generate two tokens

```bash
# operator token (Claude side):
python -c "import secrets; print(secrets.token_urlsafe(32))"
# agent token (Windows side):
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Server: drop relay.jsp into Tomcat

```bash
# edit OPERATOR_TOKEN and AGENT_TOKEN constants near the top of
# relay.jsp, paste in the two tokens from step 1.
scp server/relay.jsp  user@your-host:/path/to/tomcat/webapps/ROOT/relay.jsp
# (Tomcat auto-reloads JSPs; no restart needed.)

# verify:
curl http://your-host/relay.jsp?action=ping
# → {"ok":true,"version":"1","pendingQueue":0,"resultsHeld":0}
```

### 3. Windows: start the agent

**Easy way** (no admin needed):

1. Edit `server/start-agent.bat`, fill in `RELAY_URL` and the
   `AGENT_TOKEN` from step 1.
2. Double-click `start-agent.bat`. The window stays open, logs to
   `agent.log` next to the batch.

**Manual way**:

```powershell
cd C:\work\2026\Claude\test-
powershell -NoProfile -ExecutionPolicy Bypass -File .\server\agent.ps1 `
    -RelayUrl http://your-host/relay.jsp `
    -AgentToken "<agent token from step 1>"
```

`-ExecutionPolicy Bypass` is the no-admin workaround for a locked-down
`Get-ExecutionPolicy`. It only applies to this one invocation; nothing
is written to registry.

To run as a service: install [nssm](https://nssm.cc/) and
`nssm install RelayAgent powershell.exe ...`. (Requires admin.)

### 4. Operator (Claude sandbox)

Easiest: `server/relay_send.sh` — pipes stdin → enqueue → polls result.

```bash
export RELAY_URL=http://your-host/relay.jsp
export OPERATOR_TOKEN="<operator token from step 1>"

echo 'git status; (Get-Date).ToString()' | ./server/relay_send.sh
# prints:
#   ---STDOUT---
#   On branch claude/...
#   2026-05-12 14:21:33
#   ---STDERR---
#   ---EXIT---
#   0
```

Raw curl works too:

```bash
curl -sS -X POST "$RELAY_URL?action=enqueue" \
    -H "X-Token: $OPERATOR_TOKEN" -H "Content-Type: application/json" \
    -d '{"id":"job-001","script":"git status","timeout":30}'

curl -sS "$RELAY_URL?action=result&id=job-001" -H "X-Token: $OPERATOR_TOKEN"
```

## Security

- Two separate tokens — even if the agent leaks its token, an attacker
  can only pull commands, not enqueue them.
- Tokens are checked on every request via `X-Token` header. No cookies
  / sessions.
- The relay does **not** authenticate the script content — anything an
  operator enqueues will run on the Windows box. Treat OPERATOR_TOKEN
  like an SSH private key.
- **Strongly recommend** putting Tomcat behind HTTPS (otherwise tokens
  travel in cleartext). If your Tomcat doesn't have HTTPS, stick an
  Nginx / Caddy reverse proxy in front, or use a self-signed cert via
  Tomcat's connector config.
- State is in-memory: Tomcat restart loses pending queue + held
  results. For the use case (interactive ops) this is fine.
- No persistence layer = no disk leak of script contents.

## Limits

- Stdout / stderr capped at 1 MB each (agent-side truncation).
- One Windows agent assumed. Multiple agents will race for jobs (also
  fine, but you can't target a specific one without code changes).
- Job timeout default 600 s; pass `"timeout":N` in the enqueue body to
  override (seconds). Agent kills the process if exceeded.
