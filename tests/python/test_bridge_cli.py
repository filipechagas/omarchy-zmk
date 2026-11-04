import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRIDGE = os.path.join(ROOT, "bridge", "zmk_bridge.py")
FIXTURES = os.path.join(ROOT, "tests", "python", "fixtures")


def run(*args):
    completed = subprocess.run(
        [sys.executable, BRIDGE, "--keymap-only", *args],
        capture_output=True, text=True, timeout=30, check=False,
    )
    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    return completed.returncode, lines


class BridgeCliTest(unittest.TestCase):
    def test_hello_then_keymap(self):
        code, lines = run("--keymap", os.path.join(FIXTURES, "split_3x6_3.yaml"))
        self.assertEqual(code, 0)
        self.assertEqual([m["type"] for m in lines], ["hello", "keymap"])
        self.assertTrue(all(m["v"] == 1 for m in lines))
        keymap = lines[1]
        self.assertTrue(keymap["configured"])
        self.assertTrue(keymap["ok"])
        self.assertEqual([layer["name"] for layer in keymap["layers"]], ["default", "nav"])

    def test_unconfigured_keymap(self):
        code, lines = run()
        self.assertEqual(code, 0)
        self.assertEqual(lines[1], {"v": 1, "type": "keymap", "configured": False, "ok": False})

    def test_keymap_error_is_a_message_not_a_crash(self):
        code, lines = run("--keymap", os.path.join(FIXTURES, "missing.yaml"))
        self.assertEqual(code, 0)
        self.assertFalse(lines[1]["ok"])
        self.assertEqual(lines[1]["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
