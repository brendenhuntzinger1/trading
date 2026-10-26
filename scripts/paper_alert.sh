#!/usr/bin/env bash
# Deliver or clear a paper-operation alert.
#   scripts/paper_alert.sh open <key> <title> <body>
#   scripts/paper_alert.sh resolve <key> <note>
# Delivery happens only to the destination approved in config/alerts.toml. Without an approval the alert is
# written to the run log (as a warning annotation) and the job summary, and nothing leaves GitHub Actions.
# One open issue per key: repeated alerts add a comment instead of a new issue; a later success closes it.
set -euo pipefail
CONFIG="${ALERTS_CONFIG:-config/alerts.toml}"
read -r approved dest < <(python3 -c "import tomllib, sys; d = tomllib.load(open(sys.argv[1], 'rb'))['destination']; print('yes' if d.get('approved') else 'no', d.get('type', ''))" "$CONFIG")
cmd="${1:-}"; key="${2:?key}"
title="[paper-alert] $key"
summary() { [ -n "${GITHUB_STEP_SUMMARY:-}" ] && printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY" || true; }

case "$cmd" in
  open)
    text="${3:?title}"; body="${4:-}"
    if [ "$approved" != yes ]; then
      echo "::warning title=Paper alert NOT DELIVERED (no approved destination)::$key: $text"
      summary "**Paper alert (not delivered; no approved destination):** $key: $text"$'\n\n'"$body"
      exit 0
    fi
    [ "$dest" = github_issue ] || { echo "unsupported destination: $dest" >&2; exit 1; }
    gh label create paper-alert --color B60205 --description "Paper-trading operations alert" --force >/dev/null
    num=$(gh issue list --label paper-alert --state open --limit 100 --json number,title \
          --jq ".[] | select(.title == \"$title\") | .number" | head -n1)
    if [ -n "$num" ]; then
      gh issue comment "$num" --body "$text"$'\n\n'"$body"
    else
      gh issue create --label paper-alert --title "$title" --body "$text"$'\n\n'"$body"$'\n\n'"Paper trading only. Simulated fills; no real orders."
    fi
    summary "**Paper alert delivered:** $key: $text" ;;
  resolve)
    note="${3:-resolved}"
    [ "$approved" = yes ] && [ "$dest" = github_issue ] || exit 0
    for num in $(gh issue list --label paper-alert --state open --limit 100 --json number,title \
                 --jq ".[] | select(.title == \"$title\") | .number"); do
      gh issue close "$num" --comment "$note"
    done ;;
  *) echo "usage: $0 open <key> <title> <body> | resolve <key> <note>" >&2; exit 2 ;;
esac
