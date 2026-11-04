#!/usr/bin/env bash
# Checks that run without Omarchy or Qt: manifest rules from the Omarchy plugin
# marketplace, then the Python unit tests. Used by CI and the release workflow.
# Usage: tests/ci.sh [expected-version]
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
python=${PYTHON:-python3}

echo "== manifest"
"$python" - "${1:-}" <<'PY'
import json, os, re, sys

expected = sys.argv[1]
manifest = json.load(open("manifest.json"))
required = ["schemaVersion", "id", "name", "version", "author", "description", "kinds", "entryPoints"]
missing = [key for key in required if key not in manifest]
errors = ["missing field: " + key for key in missing]
plugin_id = manifest.get("id", "")
if plugin_id.startswith("omarchy."):
    errors.append("id uses the reserved omarchy.* namespace")
version = str(manifest.get("version", ""))
if not re.fullmatch(r"\d+\.\d+\.\d+", version) or len(version) > 64:
    errors.append("version must be MAJOR.MINOR.PATCH: %r" % version)
if expected and version != expected:
    errors.append("manifest version %s does not match %s" % (version, expected))
for kind, path in manifest.get("entryPoints", {}).items():
    if not os.path.isfile(path):
        errors.append("entry point for %s missing: %s" % (kind, path))
for path in ("README.md", "LICENSE", "preview.png", "CHANGELOG.md"):
    if not os.path.isfile(path):
        errors.append("missing " + path)
if version and "\n## %s\n" % version not in open("CHANGELOG.md").read():
    errors.append("CHANGELOG.md has no '## %s' section" % version)
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("ok: %s %s" % (plugin_id, version))
PY

echo "== python unit tests"
"$python" -c 'import yaml' 2>/dev/null || { echo "PyYAML is required for the keymap tests" >&2; exit 1; }
"$python" -m unittest discover -s tests/python
