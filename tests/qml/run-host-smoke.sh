#!/usr/bin/env bash
# Load Service.qml and Panel.qml in a throwaway Quickshell instance with a fake
# bridge and a fake notify-send, then check what the fakes observed.
# Needs a Wayland session (Ui.KeyboardPanel requires the layer-shell backend).
# The popup is never opened, so no surface is mapped, and the running
# omarchy-shell is not touched.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
plugin_root=$(cd -- "$script_dir/../.." && pwd)
omarchy_path=${OMARCHY_PATH:-/usr/share/omarchy}

if ! command -v quickshell >/dev/null; then
  printf '%s\n' "HOST-SMOKE: SKIP (quickshell is not installed)"
  exit 77
fi

if [[ -z ${WAYLAND_DISPLAY:-} ]]; then
  printf '%s\n' "HOST-SMOKE: SKIP (WAYLAND_DISPLAY is not set)"
  exit 77
fi

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
config="$tmp/config"
mkdir -p "$config" "$tmp/home/.config" "$tmp/cache" "$tmp/state"
ln -s "$omarchy_path/shell/Ui" "$config/Ui"
ln -s "$omarchy_path/shell/Commons" "$config/Commons"
ln -s "$script_dir/host-smoke/shell.qml" "$config/shell.qml"

export ZMK_TEST_LOG="$tmp/bridge.jsonl"
export ZMK_TEST_NOTIFY_LOG="$tmp/notify.log"
: >"$ZMK_TEST_NOTIFY_LOG"

set +e
output=$(env \
  HOME="$tmp/home" \
  XDG_CONFIG_HOME="$tmp/home/.config" \
  XDG_CACHE_HOME="$tmp/cache" \
  XDG_STATE_HOME="$tmp/state" \
  PATH="$script_dir/fixtures/bin:$PATH" \
  OMARCHY_PATH="$omarchy_path" \
  ZMK_PLUGIN_ROOT="$plugin_root" \
  ZMK_BRIDGE_ROOT="$script_dir/fixtures/fake-plugin" \
  QT_QPA_PLATFORM=wayland \
  QS_DISABLE_FILE_WATCHER=1 \
  QS_NO_RELOAD_POPUP=1 \
  /usr/bin/timeout --kill-after=1s 20s quickshell -p "$config" --no-color 2>&1)
status=$?
set -e
printf '%s\n' "$output"
if ((status != 0)); then
  printf '%s\n' "HOST-SMOKE: quickshell exited with $status" >&2
  exit "$status"
fi
if grep -E "(WARN|ERROR).*(Panel|Service|Model)\.(qml|js)" <<<"$output"; then
  printf '%s\n' "HOST-SMOKE: plugin QML warning detected" >&2
  exit 1
fi
sleep 0.5
if pgrep -f -- "$script_dir/fixtures/fake-plugin/bridge/zmk_bridge.py" >/dev/null; then
  printf '%s\n' "HOST-SMOKE: fake bridge survived service destruction" >&2
  exit 1
fi

python3 - "$ZMK_TEST_LOG" "$ZMK_TEST_NOTIFY_LOG" <<'PY'
import json
import sys

bridge = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
argv = [entry["argv"] for entry in bridge if "argv" in entry]
stdin = [json.loads(entry["stdin"]) for entry in bridge if entry.get("stdin")]
ended = [entry for entry in bridge if entry.get("eof") or "signal" in entry]
notes = open(sys.argv[2], encoding="utf-8").read().splitlines()

failures = []
if argv != [
    ["--stdio", "--device-name", "Corne", "--keymap", "/tmp/k.yaml"],
    ["--stdio", "--device-name", "Other"],
]:
    failures.append("unexpected bridge argv: %r" % argv)
if {"v": 1, "type": "refresh"} not in stdin:
    failures.append("refresh command not received: %r" % stdin)
# The instance replaced on a settings change must be stopped before its
# successor starts. The last instance dies with the Service object (Quickshell
# kills it on destruction, uncatchably); the pgrep check above covers it.
first_ended = next((i for i, entry in enumerate(bridge) if entry.get("eof") or "signal" in entry), None)
second_started = [i for i, entry in enumerate(bridge) if "argv" in entry][1:2]
if first_ended is None or not second_started or first_ended > second_started[0]:
    failures.append("replaced bridge was not stopped before its successor started: %r" % bridge)
expected = ("--app-name=ZMK Keyboard --icon=input-keyboard --urgency=normal "
            "Corne: Right half at 19% Right half battery is at or below 20%.")
if notes != [expected, expected]:  # the fixture raises one alert per bridge start
    failures.append("unexpected notifications: %r" % notes)
for failure in failures:
    print("HOST-SMOKE: FAIL", failure)
if failures:
    sys.exit(1)
print("HOST-SMOKE: logs PASS (argv, restart on settings change, refresh, child stopped, notify-send): %r" % ended)
PY
