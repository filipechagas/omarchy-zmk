import os
import tempfile
import unittest

from bridge.zmkstatus import keymap

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TABLE = {"keyboard-tab": 0xF0312, "arrow-left": 0xF004D}


def load(name, table=TABLE):
    return keymap.load_keymap(os.path.join(FIXTURES, name), table)


class SplitKeymapTest(unittest.TestCase):
    def setUp(self):
        self.model = load("split_3x6_3.yaml")

    def test_layer_names_in_file_order(self):
        self.assertEqual([layer["name"] for layer in self.model["layers"]], ["default", "nav"])
        self.assertEqual([layer["index"] for layer in self.model["layers"]], [0, 1])

    def test_heuristic_split_geometry(self):
        geometry = self.model["geometry"]
        self.assertEqual(geometry["source"], "split-3x6+3")
        self.assertEqual(len(geometry["keys"]), 42)
        self.assertEqual(geometry["width"], 13.0)
        self.assertEqual(geometry["height"], 4.15)
        keys = geometry["keys"]
        self.assertEqual((keys[0]["x"], keys[0]["y"]), (0, 0))
        self.assertEqual((keys[6]["x"], keys[6]["y"]), (7.0, 0))  # first right-half key
        self.assertEqual((keys[36]["x"], keys[36]["y"]), (3, 3.15))  # first left thumb
        self.assertEqual((keys[39]["x"], keys[39]["y"]), (7.0, 3.15))  # first right thumb
        self.assertEqual(self.model["mismatchedLayers"], [])

    def test_key_legends(self):
        keys = self.model["layers"][0]["keys"]
        self.assertEqual(keys[0], {"t": "\U000F0312", "h": "", "s": "`", "type": "", "glyph": True})
        self.assertEqual(keys[1]["t"], "Q")
        self.assertEqual(keys[12]["t"], "Esc")  # no keyboard-esc in TABLE → label
        self.assertEqual(keys[12]["h"], "Ctrl")
        self.assertEqual(keys[41]["t"], "Thing")
        nav = self.model["layers"][1]["keys"]
        self.assertEqual(nav[0]["type"], "trans")
        self.assertEqual(nav[18], {"t": "", "h": "", "s": "", "type": "held", "glyph": False})


class OtherLayoutsTest(unittest.TestCase):
    def test_ortho_layout_and_nested_rows(self):
        model = load("ortho.yaml")
        self.assertEqual(model["geometry"]["source"], "ortho")
        self.assertEqual(model["geometry"]["width"], 3)
        self.assertEqual(model["geometry"]["height"], 2)
        self.assertEqual([k["t"] for k in model["layers"][0]["keys"]], list("ABCDEF"))
        self.assertEqual(model["layers"][1]["keys"][5]["t"], "true")

    def test_qmk_info_json(self):
        model = load("qmk.yaml")
        geometry = model["geometry"]
        self.assertEqual(geometry["source"], "qmk-info-json:LAYOUT_tiny")
        self.assertEqual(geometry["keys"][1]["w"], 1.5)
        self.assertEqual(geometry["keys"][2]["r"], 15)
        self.assertEqual((geometry["keys"][2]["rx"], geometry["keys"][2]["ry"]), (3, 1))
        self.assertEqual(geometry["height"], 2.25)

    def test_heuristics(self):
        self.assertEqual(keymap.heuristic_geometry(36)[1], "split-3x5+3")
        self.assertEqual(keymap.heuristic_geometry(34)[1], "split-3x5+2")
        geometry, source = keymap.heuristic_geometry(61)
        self.assertEqual(source, "grid-12")
        self.assertEqual(len(geometry), 61)

    def test_mismatched_layer_is_reported(self):
        model = keymap.build_model({"layers": {"a": ["x"] * 36, "b": ["y"] * 30}}, FIXTURES, {})
        self.assertEqual(model["mismatchedLayers"], ["b"])
        self.assertEqual(model["geometry"]["source"], "split-3x5+3")


class ErrorsTest(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def assertCode(self, path, code):
        with self.assertRaises(keymap.KeymapError) as caught:
            keymap.load_keymap(path, {})
        self.assertEqual(caught.exception.code, code)

    def test_missing_file(self):
        self.assertCode(os.path.join(FIXTURES, "nope.yaml"), "not_found")

    def test_bad_yaml(self):
        self.assertCode(self.write("layers: [unclosed\n"), "bad_yaml")

    def test_no_layers(self):
        self.assertCode(self.write("layout: {}\n"), "no_layers")
        self.assertCode(self.write("- just a list\n"), "bad_document")

    def test_bad_layer(self):
        self.assertCode(self.write("layers:\n  a: 3\n"), "bad_layer")

    def test_unsupported_ortho(self):
        self.assertCode(self.write("layout: {ortho_layout: {rows: 3, columns: 5, thumbs: MIT}}\nlayers: {a: [x]}\n"), "unsupported_layout")

    def test_bad_qmk_json(self):
        self.assertCode(self.write("layout: {qmk_info_json: missing.json}\nlayers: {a: [x]}\n"), "bad_qmk_info_json")


if __name__ == "__main__":
    unittest.main()
