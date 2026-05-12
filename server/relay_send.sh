#!/usr/bin/env bash
# relay_send.sh — operator-side helper. Reads a PowerShell script from
# stdin, enqueues it, polls until the result arrives, prints stdout /
# stderr / exit-code.
#
# Env vars required:
#   RELAY_URL        e.g. http://your-host/relay.jsp
#   OPERATOR_TOKEN   the operator (not agent) token from relay.jsp
#
# Optional:
#   RELAY_TIMEOUT    job timeout in seconds (default 600)
#
# Examples:
#   echo 'git status' | ./server/relay_send.sh
#   ./server/relay_send.sh < my-script.ps1

set -euo pipefail
: "${RELAY_URL:?set RELAY_URL}"
: "${OPERATOR_TOKEN:?set OPERATOR_TOKEN}"
TIMEOUT="${RELAY_TIMEOUT:-600}"

script="$(cat)"
if [[ -z "$script" ]]; then
    echo "relay_send: empty script on stdin" >&2
    exit 2
fi

id="job-$(date +%s)-$RANDOM"

# build JSON payload (jq if available, else manual escape)
if command -v jq >/dev/null 2>&1; then
    payload=$(jq -nc --arg id "$id" --arg s "$script" --argjson t "$TIMEOUT" \
              '{id:$id, script:$s, timeout:$t}')
else
    esc=$(printf '%s' "$script" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')
    payload=$(printf '{"id":"%s","script":%s,"timeout":%s}' "$id" "$esc" "$TIMEOUT")
fi

curl -sS -X POST "$RELAY_URL?action=enqueue" \
    -H "X-Token: $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null

# poll for result (server long-polls 60s, so just loop)
deadline=$(( $(date +%s) + TIMEOUT + 30 ))
while :; do
    resp=$(curl -sS "$RELAY_URL?action=result&id=$id" -H "X-Token: $OPERATOR_TOKEN")
    ready=$(printf '%s' "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ready", False))')
    if [[ "$ready" == "True" ]]; then
        printf '%s\n' "$resp" | python3 -c '
import json, sys
d = json.load(sys.stdin)
sys.stdout.write("---STDOUT---\n" + d.get("stdout","") + "\n")
sys.stderr.write("---STDERR---\n" + d.get("stderr","") + "\n")
print("---EXIT---")
print(d.get("exit",-1))
'
        exit 0
    fi
    if (( $(date +%s) > deadline )); then
        echo "relay_send: timed out waiting for $id" >&2
        exit 3
    fi
done
