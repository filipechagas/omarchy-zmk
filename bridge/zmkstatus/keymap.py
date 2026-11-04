"""Turn a keymap-drawer YAML file into a render-ready layer model.

Layer names are the keys of the top-level `layers` mapping, in file order, so
firmware layer index N maps to the Nth name.

Physical geometry, in priority order:
  1. layout.qmk_info_json: a local QMK info.json (path relative to the YAML)
     with x/y/w/h/r/rx/ry per key, as keymap-drawer uses it.
  2. layout.ortho_layout: {split, rows, columns, thumbs} as in keymap-drawer.
  3. Heuristic from the key count: a split 3xN+T (or 4xN+T) grid when the
     count fits, else a plain 12- or 10-column grid.
Remote QMK/ZMK keyboard names (qmk_keyboard, zmk_keyboard) are not fetched;
they fall through to the heuristic.
"""

import json
import math
import os

from . import glyphs

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LAYERS = 32
MAX_KEYS = 256
SPLIT_GAP = 1.0
THUMB_DROP = 0.15


class KeymapError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(code if not detail else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _flatten(keys):
    rows = []
    for item in keys:
        if isinstance(item, list):
            rows.extend(item)
        else:
            rows.append(item)
    return rows


def normalize_key(raw, table):
    """Return {"t", "h", "s", "type", "glyph"} with glyph tokens resolved."""
    if isinstance(raw, dict):
        tap, hold, shifted = raw.get("t", raw.get("tap")), raw.get("h", raw.get("hold")), raw.get("s", raw.get("shifted"))
        kind = _text(raw.get("type"))
    else:
        tap, hold, shifted, kind = raw, None, None, ""
    tap_text, tap_glyph = glyphs.render_legend(_text(tap), table)
    hold_text, _ = glyphs.render_legend(_text(hold), table)
    shifted_text, _ = glyphs.render_legend(_text(shifted), table)
    return {
        "t": tap_text,
        "h": hold_text,
        "s": shifted_text,
        "type": kind,
        "glyph": tap_glyph,
    }


def _number(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _key(x, y, w=1.0, h=1.0, r=0.0, rx=None, ry=None):
    return {"x": round(x, 4), "y": round(y, 4), "w": w, "h": h, "r": r, "rx": rx, "ry": ry}


def split_grid(rows, columns, thumbs):
    """Row-major split grid: each row lists left keys then right keys,
    then the left thumbs and the right thumbs, as keymap-drawer and ZMK
    keymaps order a Corne-style board."""
    keys = []
    right = columns + SPLIT_GAP
    for row in range(rows):
        for col in range(columns):
            keys.append(_key(col, row))
        for col in range(columns):
            keys.append(_key(right + col, row))
    if thumbs:
        y = rows + THUMB_DROP
        for i in range(thumbs):
            keys.append(_key(max(0, columns - thumbs) + i, y))
        for i in range(thumbs):
            keys.append(_key(right + i, y))
    return keys


def plain_grid(count, columns):
    return [_key(i % columns, i // columns) for i in range(count)]


def heuristic_geometry(count):
    # Prefer layouts with a thumb cluster: 36 keys is 3x5+3, not 3x6+0.
    for rows in (3, 4):
        for thumbs in (3, 2, 4, 1, 5, 6, 0):
            for columns in (6, 5, 7, 4):
                if 2 * (rows * columns + thumbs) == count:
                    return split_grid(rows, columns, thumbs), "split-%dx%d+%d" % (rows, columns, thumbs)
    columns = 12 if count % 12 == 0 or count > 40 else 10
    return plain_grid(count, columns), "grid-%d" % columns


def ortho_geometry(spec):
    if not isinstance(spec, dict):
        raise KeymapError("bad_layout", "ortho_layout must be a mapping")
    rows = int(_number(spec.get("rows"), 0))
    columns = int(_number(spec.get("columns"), 0))
    thumbs = spec.get("thumbs", 0)
    if isinstance(thumbs, str) or rows <= 0 or columns <= 0:
        raise KeymapError("unsupported_layout", "ortho_layout")
    thumbs = int(_number(thumbs, 0))
    if spec.get("split"):
        return split_grid(rows, columns, thumbs), "ortho-split"
    return plain_grid(rows * columns, columns), "ortho"


def qmk_geometry(info_path, layout_name):
    try:
        if os.path.getsize(info_path) > MAX_FILE_BYTES:
            raise KeymapError("file_too_large", info_path)
        with open(info_path, "r", encoding="utf-8") as handle:
            info = json.load(handle)
    except (OSError, ValueError) as error:
        raise KeymapError("bad_qmk_info_json", str(error))
    layouts = info.get("layouts") if isinstance(info, dict) else None
    if not isinstance(layouts, dict) or not layouts:
        raise KeymapError("bad_qmk_info_json", "no layouts")
    name = layout_name if layout_name in layouts else sorted(layouts)[0]
    entry = layouts[name]
    raw_keys = entry.get("layout") if isinstance(entry, dict) else entry
    if not isinstance(raw_keys, list) or not raw_keys:
        raise KeymapError("bad_qmk_info_json", "empty layout")
    keys = []
    for raw in raw_keys[:MAX_KEYS]:
        if not isinstance(raw, dict):
            raise KeymapError("bad_qmk_info_json", "key is not an object")
        keys.append(
            _key(
                _number(raw.get("x"), 0.0),
                _number(raw.get("y"), 0.0),
                _number(raw.get("w"), 1.0),
                _number(raw.get("h"), 1.0),
                _number(raw.get("r"), 0.0),
                raw.get("rx") if raw.get("rx") is None else _number(raw.get("rx"), 0.0),
                raw.get("ry") if raw.get("ry") is None else _number(raw.get("ry"), 0.0),
            )
        )
    return keys, "qmk-info-json:%s" % name


def geometry_for(layout_spec, key_count, base_dir):
    spec = layout_spec if isinstance(layout_spec, dict) else {}
    info = spec.get("qmk_info_json")
    if isinstance(info, str) and info and "://" not in info:
        path = os.path.expanduser(info)
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        return qmk_geometry(path, spec.get("layout_name"))
    if "ortho_layout" in spec:
        return ortho_geometry(spec["ortho_layout"])
    return heuristic_geometry(key_count)


def _bounds(keys):
    width = max((k["x"] + k["w"] for k in keys), default=0)
    height = max((k["y"] + k["h"] for k in keys), default=0)
    left = min((k["x"] for k in keys), default=0)
    top = min((k["y"] for k in keys), default=0)
    return left, top, width, height


def build_model(document, base_dir, table):
    if not isinstance(document, dict):
        raise KeymapError("bad_document", "top level is not a mapping")
    layers = document.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise KeymapError("no_layers")
    names = list(layers.keys())[:MAX_LAYERS]
    model_layers = []
    for index, name in enumerate(names):
        keys = layers[name]
        if not isinstance(keys, list):
            raise KeymapError("bad_layer", _text(name))
        model_layers.append(
            {
                "index": index,
                "name": _text(name),
                "keys": [normalize_key(raw, table) for raw in _flatten(keys)[:MAX_KEYS]],
            }
        )
    key_count = max(len(layer["keys"]) for layer in model_layers)
    geometry, source = geometry_for(document.get("layout"), key_count, base_dir)
    left, top, right, bottom = _bounds(geometry)
    for key in geometry:
        key["x"] = round(key["x"] - left, 4)
        key["y"] = round(key["y"] - top, 4)
        if key["rx"] is not None:
            key["rx"] = round(key["rx"] - left, 4)
        if key["ry"] is not None:
            key["ry"] = round(key["ry"] - top, 4)
    mismatched = [layer["name"] for layer in model_layers if len(layer["keys"]) != len(geometry)]
    return {
        "layers": model_layers,
        "geometry": {
            "source": source,
            "width": round(right - left, 4),
            "height": round(bottom - top, 4),
            "keys": geometry,
        },
        "mismatchedLayers": mismatched,
    }


def load_keymap(path, table, yaml_module=None):
    """Load and convert a keymap-drawer YAML file. Raises KeymapError."""
    if yaml_module is None:
        try:
            import yaml as yaml_module
        except ImportError:
            raise KeymapError("missing_dependency", "PyYAML")
    path = os.path.expanduser(path)
    try:
        size = os.path.getsize(path)
    except OSError as error:
        raise KeymapError("not_found", str(error))
    if size > MAX_FILE_BYTES:
        raise KeymapError("file_too_large", path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = yaml_module.safe_load(handle)
    except OSError as error:
        raise KeymapError("unreadable", str(error))
    except Exception as error:  # yaml.YAMLError and friends
        raise KeymapError("bad_yaml", str(error).splitlines()[0] if str(error) else "")
    return build_model(document, os.path.dirname(os.path.abspath(path)), table)
