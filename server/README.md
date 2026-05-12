# GitHub-based command relay

A tiny PowerShell agent that polls a dedicated GitHub branch
(`claude-relay`) for commands, executes them on the local Windows
machine, and pushes the results back to the same branch.

## Files

```
server/
├── agent.ps1            polling + executing + pushing loop
├── start-agent.bat      double-click launcher
└── README.md            this file
```

The bundled zip is at `dist/relay-deploy.zip` (3 files).

## Setup (once)

1. Extract the zip somewhere on the Windows machine that should
   execute the commands.
2. Make sure Git for Windows is installed and your GitHub credentials
   are cached (you've git-pushed to this repo from this account once).
3. Double-click `start-agent.bat`. It will clone the `claude-relay`
   branch into `.relay-clone/` next to itself on first run, then start
   polling every 5 seconds.

The agent logs to `agent.log` next to the .bat. Press Ctrl+C to stop.

## Protocol

```
claude-relay branch
├── inbox.json   {"id":"<uuid>","script":"...","timeout":600}
└── outbox.json  {"id":"<uuid>","stdout":"...","stderr":"...","exit":0}
```

Both files are plain JSON, no BOM. Encoding is UTF-8 throughout —
child PowerShell captures its output inside .NET and writes it via
`[IO.File]::WriteAllText` to avoid Windows console-redirect encoding
quirks.

## Updating the agent

```powershell
cd C:\path\to\extracted\folder
Invoke-WebRequest https://raw.githubusercontent.com/zhangtianhai2017/Test-/COMMIT_HASH/server/agent.ps1 -OutFile agent.ps1
```

Replace `COMMIT_HASH` with the SHA from the agent.ps1 commit you want.
Ctrl+C the agent window, then double-click `start-agent.bat` again.
