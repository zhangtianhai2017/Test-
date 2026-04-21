# DISPATCH PROTOCOL — how the PM brief subagents

> This is the contract between PM and subagents. Every dispatch follows this
> template. Deviations go into a new session log entry with justification.

## Dispatch template

When dispatching a subagent via the Agent tool, the `prompt` parameter must
contain the following sections in this order:

```
### Role
You are a <module name> subagent. Your scope is defined by
`coordination/modules/<module>/AGENT.md`. Read that file first.

### Mission (this task)
<one paragraph, concrete, bounded>

### Input contracts
<files, interfaces, types the subagent may rely on>

### Output contracts
<files the subagent must produce or modify, tests it must pass,
success criteria>

### Out of scope
<things the subagent must NOT touch this task>

### Success check
Run these locally and all must pass before returning:
  <commands>

### If you get stuck
Do NOT guess. Append an entry to `coordination/PENDING_QUESTIONS.md`
with format per the file's header. Return a short summary saying
"escalation pending" and stop. The PM will resume you when the
user answers.

### State update
After success, update `coordination/modules/<module>/STATE.md`
with:
  - what changed in this task
  - current file counts / test counts
  - anything the next subagent in this module should know

### Return format
Return a short text message to the PM with:
  - What you did (1-3 bullets)
  - Files changed (paths)
  - Tests passing (count)
  - Any deferrals or escalations
```

## PM responsibilities after subagent returns

1. **Read the diff** (`git diff`, `git status`) — do not trust the subagent's
   own summary blindly.
2. **Run the success commands yourself** if the subagent's environment
   differs from yours.
3. **Update `PROJECT_STATE.md`** — move milestone forward, or note why not.
4. **Commit and push** with a clear message that cites the milestone id.
5. **Dispatch the next subagent** OR **escalate** to the user if questions
   were raised.

## Subagent isolation

- Default: subagent works in the main worktree (`/home/user/Test-`) and PM
  reviews the diff before any commit.
- Large refactors (engine, C++ port): use `isolation: "worktree"` so the
  subagent gets an isolated copy. PM merges manually.
- Reason: protects the main tree from a subagent going off the rails.

## Dispatching multiple subagents in parallel

- Allowed when their scopes **do not overlap** in the module dependency
  graph (see below).
- Never dispatch two subagents that touch the same module in parallel.
- Each parallel dispatch must have its own task id (derive from milestone
  number, e.g. M7a / M7b).

## Module dependency graph

```
    engine (TS rules, reference)
       │
       ├──▶ ai-npc (TS AI lib)
       │       │
       │       └──▶ ue-plugin/BlackjackCore (C++ port of both)
       │                   │
       │                   └──▶ ue-plugin/BlackjackUE (actors, BP, scene)
       │
       └──▶ (ui-web, ui-3d)   ← FROZEN in v1, bug fix only

    dealer-ai (Python service) ←── ue-plugin/BlackjackUE (HTTP client)
```

Parallelism rules derived from the graph:
- Never refactor `engine` in parallel with anything downstream.
- `dealer-ai` and `ue-plugin/BlackjackUE` scene work can proceed in parallel
  (scene work uses the protocol; service work implements the protocol).
- C++ port should lag one milestone behind TS so conformance stays useful.

## Escalation categories

| Category | Example | Where it goes |
|---|---|---|
| Clarifying product intent | "Should heat decay during shuffle?" | PENDING_QUESTIONS.md → user |
| Missing input | "Protocol for X is undefined" | PM defines → DECISIONS.md |
| Breaking test | "Two seeds disagree after refactor" | PM debugs or reassigns |
| Exceeds scope | "I realized I need to change engine too" | PM re-plans milestones |

## Session hygiene

- At end of every dispatch session, PM writes a new file in
  `coordination/sessions/` with YYYY-MM-DD-session-N.md naming.
- Session log captures: what was dispatched, what came back, decisions made,
  commits pushed.
- Commit all coordination/ changes together with a message that references
  the milestone.
