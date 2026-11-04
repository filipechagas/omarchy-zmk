"""Resolve keymap-drawer `$$mdi:name$$` glyphs to Nerd Font codepoints.

keymap-drawer embeds Material Design Icons as SVG. QML renders text, so the
bridge maps each icon name to the codepoint a patched Nerd Font uses for it.
The table is read from the font itself: Nerd Fonts name those glyphs
"md-<name with underscores>" in the TrueType `post` table, and the `cmap`
format-12 subtable maps their codepoints. Only the standard library is used.
"""

import re
import struct

GLYPH_TOKEN = re.compile(r"\$\$([A-Za-z0-9_]+):([A-Za-z0-9_.-]+)\$\$")

# Short text used when no Nerd Font table is available or a name is unknown.
FALLBACK_LABELS = {
    "keyboard-tab": "Tab",
    "keyboard-tab-reverse": "S-Tab",
    "keyboard-esc": "Esc",
    "keyboard-return": "Ret",
    "keyboard-space": "Spc",
    "keyboard-caps": "Caps",
    "backspace": "Bksp",
    "backspace-outline": "Bksp",
    "backspace-reverse-outline": "Del",
    "apple-keyboard-shift": "Shft",
    "apple-keyboard-command": "Cmd",
    "apple-keyboard-option": "Alt",
    "apple-keyboard-control": "Ctrl",
    "apple-keyboard-caps": "Caps",
    "arrow-left": "Left",
    "arrow-right": "Right",
    "arrow-up": "Up",
    "arrow-down": "Down",
    "arrow-all": "Nav",
    "numeric": "Num",
    "symbol": "Sym",
    "cog": "Cfg",
    "volume-high": "Vol+",
    "volume-low": "Vol-",
    "volume-off": "Mute",
    "bluetooth": "BT",
    "microsoft-windows": "Win",
    "linux": "Super",
}

_SKIP_PREFIXES = ("apple-keyboard-", "keyboard-", "arrow-")

# Material Symbols names (keymap-drawer's `material:` source) that have no
# same-named MDI glyph, mapped to the closest MDI icon. Names are compared
# after "_" -> "-" normalization.
MATERIAL_ALIASES = {
    "keyboard-double-arrow-left": "chevron-double-left",
    "keyboard-double-arrow-right": "chevron-double-right",
    "keyboard-double-arrow-up": "chevron-double-up",
    "keyboard-double-arrow-down": "chevron-double-down",
    "keyboard-arrow-left": "chevron-left",
    "keyboard-arrow-right": "chevron-right",
    "keyboard-arrow-up": "chevron-up",
    "keyboard-arrow-down": "chevron-down",
    "arrow-back": "arrow-left",
    "arrow-forward": "arrow-right",
    "arrow-upward": "arrow-up",
    "arrow-downward": "arrow-down",
    "keyboard-backspace": "backspace-outline",
    "keyboard-capslock": "apple-keyboard-caps",
    "keyboard-command-key": "apple-keyboard-command",
    "keyboard-option-key": "apple-keyboard-option",
    "keyboard-control-key": "apple-keyboard-control",
    "volume-mute": "volume-off",
}


class FontTableError(ValueError):
    pass


def _tables(data):
    if len(data) < 12:
        raise FontTableError("truncated header")
    offset = 0
    if data[:4] == b"ttcf":
        if len(data) < 16:
            raise FontTableError("truncated collection header")
        offset = struct.unpack_from(">I", data, 12)[0]
    num_tables = struct.unpack_from(">H", data, offset + 4)[0]
    tables = {}
    for index in range(num_tables):
        record = offset + 12 + index * 16
        if record + 16 > len(data):
            raise FontTableError("truncated table directory")
        tag, _checksum, table_offset, length = struct.unpack_from(">4sIII", data, record)
        if table_offset + length > len(data):
            raise FontTableError("table out of range")
        tables[tag.decode("latin-1")] = (table_offset, length)
    return tables


def _post_names(data, table):
    offset, length = table
    if length < 34:
        return {}
    version = struct.unpack_from(">I", data, offset)[0]
    if version != 0x00020000:
        return {}
    num_glyphs = struct.unpack_from(">H", data, offset + 32)[0]
    index_start = offset + 34
    strings_start = index_start + 2 * num_glyphs
    end = offset + length
    if strings_start > end:
        raise FontTableError("truncated post table")
    indices = struct.unpack_from(">%dH" % num_glyphs, data, index_start)
    custom = []
    cursor = strings_start
    while cursor < end:
        size = data[cursor]
        cursor += 1
        custom.append(data[cursor:cursor + size].decode("latin-1"))
        cursor += size
    names = {}
    for glyph, name_index in enumerate(indices):
        if name_index >= 258 and name_index - 258 < len(custom):
            names[glyph] = custom[name_index - 258]
    return names


def _cmap_format12(data, table):
    offset, _length = table
    _version, count = struct.unpack_from(">HH", data, offset)
    candidates = []
    for index in range(count):
        platform, encoding, sub_offset = struct.unpack_from(">HHI", data, offset + 4 + index * 8)
        start = offset + sub_offset
        if struct.unpack_from(">H", data, start)[0] == 12:
            preference = 0 if (platform, encoding) == (3, 10) else 1
            candidates.append((preference, start))
    if not candidates:
        return {}
    start = sorted(candidates)[0][1]
    groups = struct.unpack_from(">I", data, start + 12)[0]
    glyph_to_codepoint = {}
    for index in range(groups):
        first, last, glyph = struct.unpack_from(">III", data, start + 16 + index * 12)
        if last - first > 0x10FFFF:
            raise FontTableError("bad cmap group")
        for codepoint in range(first, last + 1):
            glyph_to_codepoint.setdefault(glyph + codepoint - first, codepoint)
    return glyph_to_codepoint


def mdi_table_from_font(data):
    """Return {"keyboard-tab": 0xF0312, ...} from a Nerd Font's bytes."""
    tables = _tables(data)
    if "post" not in tables or "cmap" not in tables:
        return {}
    names = _post_names(data, tables["post"])
    codepoints = _cmap_format12(data, tables["cmap"])
    table = {}
    for glyph, name in names.items():
        if not name.startswith("md-"):
            continue
        codepoint = codepoints.get(glyph)
        if codepoint is not None:
            table[name[3:].replace("_", "-")] = codepoint
    return table


def fallback_label(name):
    if name in FALLBACK_LABELS:
        return FALLBACK_LABELS[name]
    short = name
    for prefix in _SKIP_PREFIXES:
        if short.startswith(prefix) and len(short) > len(prefix):
            short = short[len(prefix):]
            break
    short = short.replace("-outline", "").replace("-", " ").strip()
    return short[:5].title() if short else "?"


def render_legend(text, table):
    """Replace every $$source:name$$ token with a glyph or short label.

    Returns (rendered_text, used_glyph).
    """
    if not text:
        return "", False
    used = [False]

    def replace(match):
        source, name = match.group(1).lower(), match.group(2).lower().replace("_", "-")
        if source == "material" and name not in (table or {}):
            name = MATERIAL_ALIASES.get(name, name)
        if source in ("mdi", "mdil", "material") and table and name in table:
            used[0] = True
            return chr(table[name])
        return fallback_label(name)

    return GLYPH_TOKEN.sub(replace, str(text)), used[0]
