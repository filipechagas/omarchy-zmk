#!/usr/bin/env bash
# Cut a release: bump manifest.json, run every check, tag v<version> on main,
# and push. The release workflow then creates the GitHub release from the
# CHANGELOG.md section. Prints the marketplace update link at the end.
# Usage: scripts/release.sh <MAJOR.MINOR.PATCH>
set -euo pipefail

version=${1:-}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: scripts/release.sh MAJOR.MINOR.PATCH" >&2; exit 2; }
tag="v$version"
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

fail() { echo "release: $*" >&2; exit 1; }

[[ $(git branch --show-current) == main ]] || fail "run from main"
[[ -z $(git status --porcelain) ]] || fail "working tree is not clean"
# Compare against the remote refs directly; nothing is downloaded.
remote_main=$(git ls-remote origin refs/heads/main | cut -f1)
[[ $(git rev-parse HEAD) == "$remote_main" ]] || fail "main is not in sync with origin's main"
git rev-parse --quiet --verify "refs/tags/$tag" >/dev/null && fail "tag $tag already exists locally"
[[ -z $(git ls-remote --tags origin "refs/tags/$tag") ]] || fail "tag $tag already exists on origin"
grep -qx "## $version" CHANGELOG.md || fail "add a '## $version' section to CHANGELOG.md first"

current=$(/usr/bin/python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
if [[ $current != "$version" ]]; then
  /usr/bin/python3 - "$version" <<'PY'
import json, sys
manifest = json.load(open("manifest.json"))
manifest["version"] = sys.argv[1]
with open("manifest.json", "w") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
PY
fi

tests/check.sh
PYTHON=/usr/bin/python3 tests/ci.sh "$version"

if [[ -n $(git status --porcelain) ]]; then
  git commit --quiet -am "chore(release): $tag"
fi
git tag -a "$tag" -m "$tag"
git push --atomic origin main "refs/tags/$tag"

sha=$(git rev-parse HEAD)
id=$(/usr/bin/python3 -c 'import json; print(json.load(open("manifest.json"))["id"])')
repo=$(gh repo view --json url -q .url)
cat <<EOF

Released $tag at $sha.
The release workflow creates the GitHub release: gh run list --workflow release.yml

Publish this commit to the Omarchy plugin marketplace (see AGENTS.md):
https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=verify-plugin.yml&plugin-id=$id&repository=$repo&target-commit=$sha
EOF
