#!/usr/bin/env bash
# Commit system_state.json to the dedicated state branch (created on first use),
# keeping the default branch free of weekly state commits.
set -euo pipefail
BRANCH="${STATE_BRANCH:-pipeline-state}"
FILE=system_state.json

if [ ! -f "$FILE" ]; then
  echo "$FILE does not exist; nothing to save."
  exit 0
fi

WORKTREE="$(mktemp -d)/state"
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch -q origin "$BRANCH"
  git worktree add -q --detach "$WORKTREE" FETCH_HEAD
else
  git worktree add -q --detach "$WORKTREE"
  git -C "$WORKTREE" checkout -q --orphan "$BRANCH-new"
  git -C "$WORKTREE" rm -rq --cached . >/dev/null
  git -C "$WORKTREE" clean -fdq
fi

cp "$FILE" "$WORKTREE/$FILE"
git -C "$WORKTREE" add "$FILE"
if git -C "$WORKTREE" diff --cached --quiet; then
  echo "No changes to $FILE."
else
  git -C "$WORKTREE" commit -qm "chore: update pipeline state [skip ci]"
  git -C "$WORKTREE" push -q origin "HEAD:refs/heads/$BRANCH"
  echo "Saved $FILE to branch $BRANCH"
fi
git worktree remove --force "$WORKTREE"
