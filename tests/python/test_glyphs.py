import os
import struct
import subprocess
import unittest

from bridge.zmkstatus import glyphs


def build_font(names_to_codepoints):
    """Build a minimal sfnt with only `post` (format 2) and `cmap` (format 12)."""
    names = list(names_to_codepoints)
    num_glyphs = len(names) + 1  # glyph 0 is .notdef (standard name index 0)
    post = struct.pack(">IiHhIIIII", 0x00020000, 0, 0, 0, 0, 0, 0, 0, 0)
    post += struct.pack(">H", num_glyphs)
    post += struct.pack(">%dH" % num_glyphs, 0, *[258 + i for i in range(len(names))])
    for name in names:
        post += bytes([len(name)]) + name.encode("latin-1")

    groups = b"".join(
        struct.pack(">III", cp, cp, glyph + 1) for glyph, cp in enumerate(names_to_codepoints.values())
    )
    sub = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(names)) + groups
    cmap = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 10, 12) + sub

    tables = [(b"cmap", cmap), (b"post", post)]
    offset = 12 + 16 * len(tables)
    header = struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0)
    directory = b""
    body = b""
    for tag, data in tables:
        directory += struct.pack(">4sIII", tag, 0, offset + len(body), len(data))
        body += data
    return header + directory + body


class FontTableTest(unittest.TestCase):
    def test_reads_md_names_from_post_and_cmap(self):
        font = build_font({"md-keyboard_tab": 0xF0312, "md-arrow_all": 0xF0041, "cod-other": 0xEA00})
        table = glyphs.mdi_table_from_font(font)
        self.assertEqual(table, {"keyboard-tab": 0xF0312, "arrow-all": 0xF0041})

    def test_truncated_font_raises_value_error(self):
        with self.assertRaises(ValueError):
            glyphs.mdi_table_from_font(b"\x00\x01")

    def test_font_without_tables_is_empty(self):
        header = struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0)
        self.assertEqual(glyphs.mdi_table_from_font(header), {})

    @unittest.skipUnless(os.path.exists("/usr/bin/fc-list"), "fontconfig not installed")
    def test_installed_nerd_font_if_present(self):
        listing = subprocess.run(
            ["fc-list", "--format", "%{file}\n", ":charset=f030c"], capture_output=True, text=True, check=False
        ).stdout.split()
        fonts = [path for path in listing if path.lower().endswith(".ttf")]
        if not fonts:
            self.skipTest("no Nerd Font installed")
        with open(sorted(fonts)[0], "rb") as handle:
            table = glyphs.mdi_table_from_font(handle.read())
        self.assertEqual(table.get("keyboard"), 0xF030C)


class RenderLegendTest(unittest.TestCase):
    def test_replaces_known_mdi_glyph(self):
        text, used = glyphs.render_legend("$$mdi:keyboard-tab$$", {"keyboard-tab": 0xF0312})
        self.assertEqual(text, "\U000F0312")
        self.assertTrue(used)

    def test_falls_back_to_short_label(self):
        self.assertEqual(glyphs.render_legend("$$mdi:keyboard-tab$$", {}), ("Tab", False))
        self.assertEqual(glyphs.render_legend("$$phosphor:keyboard-esc$$", {"keyboard-esc": 1}), ("Esc", False))
        self.assertEqual(glyphs.render_legend("$$mdi:music-note-outline$$", {}), ("Music", False))

    def test_material_names_normalize_and_alias_to_mdi(self):
        table = {"chevron-double-left": 0xF0D2, "keyboard-tab": 0xF0312}
        self.assertEqual(glyphs.render_legend("$$material:keyboard_double_arrow_left$$", table), ("\uf0d2", True))
        self.assertEqual(glyphs.render_legend("$$material:keyboard_tab$$", table), ("\U000F0312", True))
        # Aliases only apply to the material source.
        self.assertFalse(glyphs.render_legend("$$mdi:keyboard-double-arrow-left$$", table)[1])

    def test_plain_and_mixed_text(self):
        self.assertEqual(glyphs.render_legend("Q", {}), ("Q", False))
        self.assertEqual(glyphs.render_legend("", {}), ("", False))
        self.assertEqual(glyphs.render_legend("x $$mdi:cog$$", {}), ("x Cfg", False))


if __name__ == "__main__":
    unittest.main()
