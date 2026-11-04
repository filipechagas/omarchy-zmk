#!/usr/bin/env bash
# Run every local check: Python unit tests, qmllint, QML model tests, and the
# Quickshell host smoke test (skipped without a Wayland session).
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
omarchy_path=${OMARCHY_PATH:-/usr/share/omarchy}
qt_bin=${QT_BIN:-/usr/lib/qt6/bin}
cd "$root"

import_root=$(mktemp -d)
trap 'rm -rf -- "$import_root"' EXIT
ln -s "$omarchy_path/shell" "$import_root/qs"

echo "== manifest"
if [[ -x $omarchy_path/bin/omarchy-plugin-validate ]]; then
  "$omarchy_path/bin/omarchy-plugin-validate" .
  echo "valid"
else
  echo "SKIP (omarchy-plugin-validate not found)"
fi

echo "== python unit tests"
/usr/bin/python3 -m unittest discover -s tests/python

echo "== qmllint"
# qmllint exits 0 even with warnings, so count them from its JSON report.
"$qt_bin/qmllint" -I "$import_root" --json - Panel.qml Service.qml tests/qml/tst_Model.qml tests/qml/host-smoke/shell.qml |
  /usr/bin/python3 -c '
import json, sys
total = 0
for f in json.load(sys.stdin)["files"]:
    total += len(f["warnings"])
    for w in f["warnings"]:
        print("%s:%s: %s" % (f["filename"], w.get("line"), w["message"]))
print("qmllint warnings: %d" % total)
sys.exit(1 if total else 0)
'

echo "== QML model tests"
QT_QPA_PLATFORM=offscreen "$qt_bin/qmltestrunner" -input tests/qml/tst_Model.qml -import "$import_root"

echo "== host smoke test"
set +e
tests/qml/run-host-smoke.sh | tail -2
status=${PIPESTATUS[0]}
set -e
if ((status == 77)); then
  echo "host smoke test skipped"
elif ((status != 0)); then
  exit "$status"
fi
echo "== all checks passed"
