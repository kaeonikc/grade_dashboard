#!/usr/bin/env bash
# web/scripts/deploy.sh: put the committed web/apps_script on the phone's URL.
# `clasp push` alone only updates @HEAD (the /dev URL); the /exec URL stays on its version until a new version is
# made and every deployment is moved to it (README "Push and deploy"). This does all of it and checks the result.
set -euo pipefail
cd "$(dirname "$0")/.."

user=$(clasp show-authorized-user 2>&1 || true)
if ! grep -q '@g\.cmru\.ac\.th' <<<"$user"; then
  echo "❌ clasp isn't logged in with the CMRU account: $user"
  echo "   clasp logout && clasp login"
  exit 1
fi
if [ -n "$(git status --porcelain -- apps_script)" ]; then
  echo "❌ web/apps_script has uncommitted changes. Commit them first, so the version names a commit:"
  git status --short -- apps_script
  exit 1
fi

note="$(git log -1 --format='%h %s' -- apps_script | cut -c1-90)"
echo "== clasp push"
clasp push --force
echo "== clasp create-version \"$note\""
out=$(clasp create-version "$note" 2>&1) || { echo "$out"; exit 1; }
echo "$out"
version=$(grep -oE '[0-9]+' <<<"$out" | tail -1)
[ -n "$version" ] || { echo "❌ Couldn't read the version number."; exit 1; }

# Every deployment but @HEAD: "- <id> @<n> - <description>"
deployments=$(clasp list-deployments 2>&1 | grep -E '^- \S+ @[0-9]+' || true)
[ -n "$deployments" ] || { echo "❌ No deployment to update. Create one: clasp create-deployment -V $version --description grade_web"; exit 1; }
while read -r _ id at rest; do
  desc="${rest#- }"
  echo "== $id ${at} → @$version ($desc)"
  clasp update-deployment "$id" -V "$version" --description "${desc:-grade_web}"
done <<<"$deployments"

# list-deployments can lag a few seconds behind an update
for try in 1 2 3 4 5; do
  sleep 3
  now=$(clasp list-deployments 2>&1 | grep -E '^- \S+ @[0-9]+' || true)
  if ! grep -vqE "@$version( |$)" <<<"$now"; then
    echo "$now"
    echo "✅ Every deployment is on @$version. Close the grade_web tab on the phone and open it again."
    exit 0
  fi
done
echo "$now"
echo "❌ Not every deployment shows @$version yet. Run clasp list-deployments again in a minute."
exit 1
