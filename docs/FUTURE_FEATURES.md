# Future Features — Backlog

Items explicitly deferred from the main milestone plan.  
These live in the roadmap but are **not** scheduled for the current sprint.

Status legend:
- 📦 = spec complete, not yet scheduled
- 🎬 = story-mode content, depends on core mechanics being done first
- 💡 = idea, not fully designed

---

## F1. Team Play & Covert Signals 📦🎬
*Inspired by: 21 (2008) — MIT Blackjack Team*

**Premise**: Multi-player coordination where human + NPC teammates play roles
to beat the house:

- **Spotter**: plays min-bets at a table, counts cards, signals when shoe gets hot.
- **Big Player (BP)**: moves between tables responding to signals, bets big on
  hot shoes, looks like a careless whale.
- **Gorilla BP**: pretends to be a drunken high-roller, plays badly on purpose
  to draw pit-boss attention away from the real counters.

**Signal vocabulary** (player and NPC teammates share):
- Touching nose twice → "count is +4 or higher, come in"
- Holding drink near shoulder → "count neutral, stay"
- Crossing legs → "heat rising, leave now"
- "This table's running cold" → leave
- "I like the energy here" → hot, come in
- "Where's that waitress?" → immediate extract

**Mechanics required (not yet built)**:
- Multi-table map, ability to move between 3–4 tables
- Signal send/receive UI for human player
- NPC teammate AI that sends signals based on the actual (hidden) count
- Pit-boss AI that watches for inter-table migration patterns (heat escalation)
- Reverse: pit boss can plant a "steamer" fake counter to catch real teams

**Depends on**: M1 (multi-seat), M3a (heat system) must ship first.

---

## F2. Rigged Dealer / Cheating Mode 🎬
*Inspired by: Ocean's Thirteen (2007), Casino (1995)*

**Variant A — Dealer peeks at the hole card**
- Every round the dealer secretly observes the hole card before the player
  decides. The dealer's play deviates from the fixed 17-rule in a way that
  *costs the player*, but plausibly (still looks like legal play).
- Player can watch the dealer's micro-expressions. If eyes flick down before
  dealing the hole card → tell. 3 confirmed sightings = trigger "confront"
  dialogue, proof unlocks a story beat.

**Variant B — Rigged shuffle machine**
- A specific table's shoe has been doctored: the 10th card every shoe is always
  a low card. Statistically detectable over ~30 rounds.
- Player who notices can report to the pit boss (leads to story branch) OR
  exploit it by betting the pattern.

**Variant C — Short pay**
- Dealer occasionally underpays on wins by one chip and pretends it was a
  miscalculation. "Sorry, let me recount." Some dealers do this deliberately.
- Player must watch the chip count every payout — UI support needed.

**Variant D — Card marking**
- Dealer or collaborator has marked certain cards (bent corners, daub).
  Player who notices gains an info edge.

**Required infra (not yet built)**:
- Tell/micro-expression UI on the dealer NPC
- Per-table shoe rigging toggle
- Chip-payout inspection view
- Story system hooks (branches on player catching vs missing)

---

## F3. Comps & Impairment 💡
*Inspired by: Casino (1995)*

Free drinks and comps are used by real casinos to dull judgement. In-game:

- After winning ≥ 3x minimum bet, a waitress NPC walks over: "Compliments of
  the house". Choice: **Accept** / **Decline** / **Request water**.
- **Accept**: subtle degradation over the next 5 rounds — button response
  delay +100 ms, total display occasionally flickers off for 0.5 s, screen
  slightly hazy. Bonus: the pit boss actively *likes* you as a drinker, heat
  does **not** rise even on wins.
- **Decline** / **Request water**: no impairment. But the pit-boss Suspicion
  counter ticks up — seasoned counters are famous for refusing comps.
- Cumulative: 3+ comps → "comped room" unlocks (story), 5+ → you're offered a
  private high-stakes room.

**Tie-in**: Only meaningful after Heat (M3a) ships.

---

## F4. Raymond Mode / Focus ⚙️ 💡
*Inspired by: Rain Man (1988)*

A human-player superpower that must be used carefully:

- "Focus" toggle: shoe-count accuracy improves dramatically (display full
  running count and true count on HUD), but:
  - Decision timer halves (forcing speed)
  - Pit-boss suspicion rises 2× per round
  - Player character visibly "zones out" — other NPCs notice

Good for pushing through a high-count moment, risky to leave on.

---

## F5. Mahowny Mode / Compulsion 🎬
*Inspired by: Owning Mahowny (2003)*

A story/hardcore mode where:

- Player can borrow against future bankroll (credit line from the house)
- Losing a borrowed bet doesn't just deplete bankroll — it triggers a
  countdown: must win it back in 10 rounds or a "creditor" scene triggers
- Encourages the tilt/chase pathology the film is about
- Achievement: "Walk away with the borrowed money" (very hard)

---

## F6. VIP / Molly's Game Rooms 🎬
*Inspired by: Molly's Game (2017), Casino Royale*

Unlocks as player's bankroll / reputation grows:

- Invite-only rooms with higher min/max, no side bets, exotic rules (single-deck
  European no-hole, Spanish 21 high-limit, etc)
- NPCs in VIP are all `counter` or `optimal` personality — much harder tables
- Host NPC with her own dialogue arc
- **Leaky info**: NPCs here gossip about market/players between hands, usable
  as story hooks

---

## F7. Hard Eight Mentor Mode 💡
*Inspired by: Hard Eight (1996)*

Tutorial / onboarding character:

- An old-hand NPC sits at your table, silent, watches
- On request ("what would you do?"), gives basic-strategy advice, occasionally
  tells a story about a past mistake
- Graduates from "helpful" to "absent" as player's accuracy improves — they
  leave when the student is ready
- Achievement: playing 20 rounds after he "left", without a single strategy
  deviation

---

## F8. Mahjong / Pai Gow Sister Games 💡

Several movies (赌神 series) show blackjack players crossing into other games.
Pai Gow Poker and Mahjong are also "solvable" but have more bluffing room
because of tile-reveal mechanics.

Potential expansion: the same dealer-ai + NPC-personality engine could drive a
Pai Gow table or a Hong Kong 5-card stud (梭哈) table as a later product.

---

## F9. Generational / Seasonal Tournaments 🎬

- Weekly / monthly in-game tournaments with leaderboard (persistent save)
- Seasonal events (Chinese New Year table: all 红色 chips pay 1.5×)
- Crossover NPCs: recurring rivals appear across tables

---

## Scheduling Notes

These features assume:
- M1–M3 shipped (multi-seat, basic NPC AI, heat + morale)
- UE plugin has matured past the source-complete stage and been validated
- The dealer-ai service has been tested with a real Qwen model on user GPU

Pick 1–2 at a time when revisiting — none of them are required for v1
shipping. Team Play (F1) and Rigged Dealer (F2) are the two with most
story-mode potential and should probably be v1.5 / v1.6 targets.
