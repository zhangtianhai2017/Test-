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

```powershell
$env:RELAY_URL   = "http://your-host/relay.jsp"
$env:AGENT_TOKEN = "<agent token from step 1>"
cd C:\work\2026\Claude\test-     # whatever working dir you want
.\server\agent.ps1
# leave running; commands execute as they arrive
```

To run as a Windows service: install [nssm](https://nssm.cc/) and
`nssm install RelayAgent powershell.exe -File C:\…\agent.ps1`.

### 4. Operator (Claude sandbox)

Claude `curl`s the relay with the OPERATOR_TOKEN — no client install
needed:

```bash
# push a command
curl -sS -X POST "http://your-host/relay.jsp?action=enqueue" \
  -H "X-Token: $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id":"job-001","script":"git status; (Get-Date).ToString()","timeout":30}'

# wait for result (long-polls up to 60s server-side, repeat if "ready":false)
curl -sS "http://your-host/relay.jsp?action=result&id=job-001" \
  -H "X-Token: $OPERATOR_TOKEN"
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
