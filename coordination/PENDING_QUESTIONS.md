# PENDING QUESTIONS — awaiting user answer

> When a subagent hits a design question it cannot resolve from its
> `AGENT.md`, it must **not** invent an answer. It appends to this file and
> stops. The PM reviews and relays to the user. User's answer gets recorded
> in `DECISIONS.md` with a new `D-NNN` id, and this file's entry is deleted.
>
> Format per entry:
>
> ```
> ## Q-NNN — short title
> Raised: YYYY-MM-DD by <subagent task id or PM>
> From: <module or milestone>
> Question: clear, self-contained, no context references
> Options considered:
>   - A) ... (implications)
>   - B) ... (implications)
> Subagent recommendation: A / B / none
> PM recommendation: (filled by PM before relay)
> ```

(no open questions right now)

---

## Resolved (historical — do not re-open)

- **Q-001** — `seat()` helper hardcoded to seats[0]. PM self-resolved as
  Option A. Recorded in DECISIONS.md as D-023 (2026-04-21). Scheduled as
  subtask M1c.5.
