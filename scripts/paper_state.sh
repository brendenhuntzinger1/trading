#!/usr/bin/env bash
# Restore or save paper-trading state on the `paper-state` branch (GitHub Actions).
# Usage: scripts/paper_state.sh restore | save "<message>"
# State = simulated paper journals and engine state; never credentials.
set -euo pipefail
PATHS="data/journal_paper.db data/paper_venue data/paper data/intraday data/events/events.sqlite data/dashboard data/heartbeat"

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
    # SQLite journals run in WAL mode: committed rows can sit in <db>-wal until a checkpoint. Fold them into
    # the main file before copying, or a crash-free run could still lose its last writes.
    for p in $PATHS; do
      [ -e "$p" ] || continue
      find "$p" -type f \( -name '*.db' -o -name '*.sqlite' \) -print0 | while IFS= read -r -d '' db; do
        python3 -c "import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()" "$db"
      done
    done
    tmp=$(mktemp -d)
    for p in $PATHS; do [ -e "$p" ] && mkdir -p "$tmp/$(dirname "$p")" && cp -r "$p" "$tmp/$p"; done
    st=$(remote_state)
    # Commit from a separate worktree so this checkout (scripts, config) stays intact for later job steps.
    wt=$(mktemp -d)
    if [ "$st" = present ]; then
      git fetch -q origin +refs/heads/paper-state:refs/remotes/origin/paper-state
      git worktree add -q -f -B paper-state "$wt" origin/paper-state
    else
      git worktree add -q -f --detach "$wt"
      git -C "$wt" checkout -q --orphan paper-state
      git -C "$wt" rm -rqf . >/dev/null 2>&1 || true
    fi
    trap 'git worktree remove --force "$wt" >/dev/null 2>&1 || true' EXIT
    find "$wt" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    cp -r "$tmp"/. "$wt"/
    printf "# paper-state\n\nSimulated paper-trading state written by GitHub Actions. Fills are SIMULATED by tradelab,\nnot broker paper fills and not live results. Nothing here is real money.\n" > "$wt/README.md"
    git -C "$wt" -c user.name="tradelab-paper-bot" -c user.email="tradelab-paper-bot@users.noreply.github.com" add -A -f
    if git -C "$wt" diff --cached --quiet; then echo "nothing to save"; exit 0; fi
    git -C "$wt" -c user.name="tradelab-paper-bot" -c user.email="tradelab-paper-bot@users.noreply.github.com" commit -qm "$msg"
    git -C "$wt" push -q origin paper-state     # a failed push fails the job; it is never reported as "nothing to save"
    echo "saved state as paper-state@$(git -C "$wt" rev-parse --short HEAD)"
    ;;
  *) echo "usage: $0 restore|save <msg>"; exit 2 ;;
esac
