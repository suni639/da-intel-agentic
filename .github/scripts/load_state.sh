#!/usr/bin/env bash
# Restore system_state.json from the dedicated state branch.
# Bootstrap: if the branch does not exist yet, fall back to the last copy that
# was committed on the default branch (before state moved off main).
set -euo pipefail
BRANCH="${STATE_BRANCH:-pipeline-state}"
FILE=system_state.json

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch -q origin "$BRANCH"
  git show "FETCH_HEAD:$FILE" > "$FILE"
  echo "Loaded $FILE from branch $BRANCH"
elif [ -f "$FILE" ]; then
  echo "State branch $BRANCH not found; using $FILE from the checkout"
else
  last=$(git rev-list -1 HEAD -- "$FILE" || true)
  if [ -n "$last" ] && git show "$last^:$FILE" > "$FILE" 2>/dev/null; then
    echo "State branch $BRANCH not found; restored $FILE from history ($last^)"
  else
    rm -f "$FILE"
    echo "No prior state found; starting fresh (lookback window limits re-processing)"
  fi
fi
