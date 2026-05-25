"""Summarize a train_log.jsonl file."""
import json
import sys

path = sys.argv[1]
iters = []
for line in open(path, encoding="utf-8"):
    j = json.loads(line)
    n_pass = sum(1 for r in j.get("judge_results", [])
                 if r.get("is_valid_swimsuit"))
    iters.append((
        j["iter"], j["mean_fitness"], j["mean_reward"],
        n_pass, len(j.get("judge_results", [])),
    ))

print(f"{'iter':>4} | {'fit':>5} | {'reward':>6} | pass")
for it, f, r, p, n in iters:
    print(f"{it:4d} | {f:.3f} | {r:.3f}  | {p}/{n}")

# Summary
print()
n = len(iters)
first_p = iters[0][3] / iters[0][4] if iters[0][4] else 0
last_p = iters[-1][3] / iters[-1][4] if iters[-1][4] else 0
print(f"iters: {n}")
print(f"fitness: {iters[0][1]:.3f} -> {iters[-1][1]:.3f}  (delta {iters[-1][1] - iters[0][1]:+.3f})")
print(f"reward : {iters[0][2]:.3f} -> {iters[-1][2]:.3f}  (delta {iters[-1][2] - iters[0][2]:+.3f})")
print(f"pass%  : {100*first_p:.1f}% -> {100*last_p:.1f}%")
