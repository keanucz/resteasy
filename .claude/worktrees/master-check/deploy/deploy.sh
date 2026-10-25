#!/usr/bin/env bash
# Deploy one master commit on the VPS: check it out, rebuild, restart, health-check; on failure,
# go back to the commit that was running. GitHub Actions runs it over SSH with a key whose
# authorized_keys entry forces this script, passing the commit as the SSH command
# (SSH_ORIGINAL_COMMAND). By hand: deploy.sh <sha>, or deploy.sh with no argument for origin/master.
set -euo pipefail

REPO=/opt/pillow/repo
HEALTH_URL=http://127.0.0.1:8000/api/health
HEALTH_WAIT_S=60

target="${SSH_ORIGINAL_COMMAND:-${1:-}}"
if [[ -n "$target" && ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
  echo "deploy: expected a full commit sha, got '$target'" >&2
  exit 2
fi

exec 9>/opt/pillow/deploy.lock
flock 9  # one deploy at a time

cd "$REPO"
git fetch --quiet origin master
target="${target:-$(git rev-parse origin/master)}"
if ! git merge-base --is-ancestor "$target" origin/master; then
  echo "deploy: $target is not on master" >&2
  exit 2
fi
previous=$(git rev-parse HEAD)

healthy() {
  local deadline=$((SECONDS + HEALTH_WAIT_S))
  while ((SECONDS < deadline)); do
    curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

run() {
  # git replaces files rather than rewriting them, so this running script is not disturbed
  git checkout --quiet --detach "$1"
  docker compose -f deploy/compose.yml up -d --build --remove-orphans
}

echo "deploy: $previous -> $target"
run "$target"
if healthy; then
  echo "deploy: $target is live"
  docker image prune -f >/dev/null
  exit 0
fi

echo "deploy: $target failed its health check; rolling back to $previous" >&2
docker compose -f deploy/compose.yml logs --tail 40 backend >&2 || true
run "$previous"
healthy && echo "deploy: rolled back to $previous" >&2
exit 1
