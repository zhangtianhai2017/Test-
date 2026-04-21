# layout — where things live on disk after install

After `packaging/installer/install.ps1` runs, the target Windows box looks
like this. (Paths reflect a default install; env vars can redirect them.)

```
%ProgramFiles%\Blackjack\
├── dealer-ai\
│   ├── dealer-ai.exe             (PyInstaller onedir)
│   ├── _internal\                (Python DLLs, site-packages)
│   ├── dealer_ai\
│   │   ├── personas\*.json
│   │   ├── fallback\quips_zh.json
│   │   └── fallback\quips_en.json
│   └── models\                   (optional — a .gguf if bundled)
│       └── qwen2.5-*.gguf
├── game-server\
│   ├── game-server.exe           (pkg-compiled Node 20 x64)
│   └── server-config.json        (mirror of ProgramData copy)
└── ue-game\                      (user-dropped UE build; see ../ue-game/)
    ├── BlackjackGame.exe
    ├── Engine\...
    └── BlackjackGame\...

%ProgramData%\Blackjack\
├── server-config.json            (canonical shipping config)
└── logs\
    ├── BlackjackDealerAI.out.log
    ├── BlackjackDealerAI.err.log
    ├── BlackjackGameServer.out.log
    └── BlackjackGameServer.err.log

%LOCALAPPDATA%\Blackjack\
└── logs\                         (only populated if launch-local.ps1 is used)
    ├── dealer-ai.out.log
    ├── dealer-ai.err.log
    ├── dealer-ai.pid
    ├── game-server.out.log
    ├── game-server.err.log
    └── game-server.pid
```

## Services registered

| Service | Binary | Depends on | Default state |
|---|---|---|---|
| `BlackjackDealerAI`   | `dealer-ai\dealer-ai.exe`     | —                    | Auto, running |
| `BlackjackGameServer` | `game-server\game-server.exe` | `BlackjackDealerAI`  | Auto, running |

## Ports

| Port | Proto | Purpose | Firewall scope |
|---|---|---|---|
| 8787 | TCP (HTTP)      | dealer-ai REST API    | Loopback only |
| 7878 | TCP (WebSocket) | game-server `/game`   | LocalSubnet (LAN) |

## Env vars set by installer (Machine scope)

| Var | Value |
|---|---|
| `DEALER_AI_HOST` | `127.0.0.1` |
| `DEALER_AI_PORT` | `8787` |
| `DEALER_AI_MODEL` | absolute path to bundled `.gguf`, if any |
| `DEALER_AI_USE_MOCK` | `1` iff no `.gguf` is bundled |

`DEALER_AI_GPU_LAYERS` is deliberately **not** set by the installer — the
user toggles it manually if they've installed a CUDA wheel (see
`docs/DEPLOY_V1.md` §Prerequisites).
