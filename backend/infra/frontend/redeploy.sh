#!/bin/sh
# Pull the integration branch and rebuild the frontend. Run by hook.py on a push,
# and by `deploy_staging.py frontend` by hand. One at a time: hook.py serialises.
#
# Read access to the private repo, whichever the organisation allows:
#   - DEPLOY_TOKEN: a fine-grained token, read-only Contents on this one repo. Sent
#     as a header on each fetch, never written into .git/config or a URL.
#   - else the deploy key in /keys/deploy_key (the org disables deploy keys today).
set -eu

# One build at a time whoever starts it: the webhook's queue serialises its own
# runs, and this lock makes a manual `deploy_staging.py frontend` wait its turn
# rather than reset the same checkout mid-build (astra P2).
exec 9>/srv/redeploy.lock
flock 9

BRANCH="${DEPLOY_BRANCH:-integration}"
SRC=/srv/frontend-src

if [ -n "${DEPLOY_TOKEN:-}" ]; then
    REPO="https://github.com/polysil-company/Polysil-CRM.git"
    AUTH="$(printf 'x-access-token:%s' "$DEPLOY_TOKEN" | base64 | tr -d '\n')"
    git_() { git -c "http.extraHeader=Authorization: Basic $AUTH" "$@"; }
else
    REPO="git@github.com:polysil-company/Polysil-CRM.git"
    export GIT_SSH_COMMAND="ssh -i /keys/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/srv/known_hosts"
    git_() { git "$@"; }
fi

echo "== $(date -u +%FT%TZ) redeploy of $BRANCH"
if [ ! -d "$SRC/.git" ]; then
    git_ clone --depth 1 --branch "$BRANCH" "$REPO" "$SRC"
else
    git -C "$SRC" remote set-url origin "$REPO"
    git_ -C "$SRC" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC" reset --hard FETCH_HEAD
    git -C "$SRC" clean -fdx -e node_modules
fi
RELEASE="$(git -C "$SRC" rev-parse --short HEAD)"
export RELEASE
echo "== building $RELEASE"
cp /opt/hook/Dockerfile "$SRC/Frontend/Dockerfile.polysil"
# nice: the box has one CPU, and the API keeps answering while this builds
nice -n 10 docker compose -f /opt/hook/docker-compose.frontend.yml build frontend
docker compose -f /opt/hook/docker-compose.frontend.yml up -d frontend
docker image prune -f >/dev/null
echo "== live: $RELEASE"
