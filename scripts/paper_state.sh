#!/usr/bin/env bash
# Restore or save paper-trading state on the `paper-state` branch (GitHub Actions).
# Usage: scripts/paper_state.sh restore | save "<message>"
# State = simulated paper journals and engine state; never credentials.
set -euo pipefail
PATHS="data/journal_paper.db data/paper_venue data/paper data/intraday data/events/events.sqlite data/dashboard"
case "${1:-}" in
  restore)
    if git fetch -q origin paper-state --depth=1 2>/dev/null; then
      for p in $PATHS; do git checkout origin/paper-state -- "$p" 2>/dev/null || true; done
      echo "restored state from paper-state@$(git rev-parse --short origin/paper-state)"
    else
      echo "no paper-state branch yet; starting fresh"
    fi ;;
  save)
    msg="${2:-paper state}"
    tmp=$(mktemp -d)
    for p in $PATHS; do [ -e "$p" ] && mkdir -p "$tmp/$(dirname "$p")" && cp -r "$p" "$tmp/$p"; done
    git config user.name "tradelab-paper-bot"
    git config user.email "tradelab-paper-bot@users.noreply.github.com"
    if git fetch -q origin paper-state 2>/dev/null; then git checkout -q -B paper-state origin/paper-state; else git checkout -q --orphan paper-state && git rm -rqf --cached . >/dev/null 2>&1 || true; fi
    find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    cp -r "$tmp"/. .
    printf "# paper-state\n\nSimulated paper-trading state written by GitHub Actions. Fills are SIMULATED by tradelab,\nnot broker paper fills and not live results. Nothing here is real money.\n" > README.md
    git add -A -f
    git commit -qm "$msg" && git push -q origin paper-state || echo "nothing to save"
    ;;
  *) echo "usage: $0 restore|save <msg>"; exit 2 ;;
esac
