#!/usr/bin/env bash
# Restore or save paper-trading state on the `paper-state` branch (GitHub Actions).
# Usage: scripts/paper_state.sh restore | save "<message>"
# State = simulated paper journals and engine state; never credentials.
set -euo pipefail
PATHS="data/journal_paper.db data/paper_venue data/paper data/intraday data/events/events.sqlite data/dashboard"

# 0 = branch exists, 2 = branch absent; anything else (network, auth) is an error and must stop the job,
# otherwise a failed fetch would look like "no state yet" and the save would overwrite the real state.
remote_state() {
  set +e; git ls-remote --exit-code --heads origin paper-state >/dev/null 2>&1; local rc=$?; set -e
  case $rc in 0) echo present ;; 2) echo absent ;; *) echo "cannot reach origin (ls-remote rc=$rc)" >&2; exit 1 ;; esac
}
case "${1:-}" in
  restore)
    st=$(remote_state)            # an assignment propagates the failure, so set -e stops the job here
    if [ "$st" = present ]; then
      git fetch -q origin +refs/heads/paper-state:refs/remotes/origin/paper-state --depth=1
      for p in $PATHS; do git checkout origin/paper-state -- "$p" 2>/dev/null || true; done   # a path may not exist yet
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
    st=$(remote_state)
    # The state is already copied to $tmp, so local changes in the checkout can be discarded (-f).
    if [ "$st" = present ]; then
      git fetch -q origin +refs/heads/paper-state:refs/remotes/origin/paper-state
      git checkout -q -f -B paper-state origin/paper-state
    else
      git checkout -q -f --orphan paper-state && { git rm -rqf --cached . >/dev/null 2>&1 || true; }
    fi
    find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    cp -r "$tmp"/. .
    printf "# paper-state\n\nSimulated paper-trading state written by GitHub Actions. Fills are SIMULATED by tradelab,\nnot broker paper fills and not live results. Nothing here is real money.\n" > README.md
    git add -A -f
    if git diff --cached --quiet; then echo "nothing to save"; exit 0; fi
    git commit -qm "$msg"
    git push -q origin paper-state      # a failed push fails the job; it is never reported as "nothing to save"
    echo "saved state as paper-state@$(git rev-parse --short HEAD)"
    ;;
  *) echo "usage: $0 restore|save <msg>"; exit 2 ;;
esac
