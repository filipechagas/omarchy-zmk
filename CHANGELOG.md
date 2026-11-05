# Changelog

Each release has a `## <version>` heading matching `manifest.json` and the
`v<version>` git tag. `scripts/release.sh` and the release workflow read the
section under that heading as the GitHub release notes.

## 0.2.0

- The bar widget is now a single split-keyboard icon, dimmed while the
  keyboard is disconnected. Battery and layer moved out of the bar and its
  tooltip, where they kept changing while you typed; they stay in the panel.
- The panel's layer tabs follow the keyboard: switching layers selects that
  layer's tab while the panel is open, not only when it opens.
- New preview screenshot; the README demo GIF is gone.

## 0.1.2

- Fix the bar widget rendering a few pixels tall on Omarchy 4.5, which
  scales a bar button's custom icon down to a single icon's size. The
  widget now draws its battery and layer text as the button's own content.

## 0.1.1

- `scripts/release.sh` checks `main` and the release tag with
  `git ls-remote` instead of fetching, so the Omarchy marketplace security
  baseline no longer flags it. No change to the plugin itself.

## 0.1.0

First release.

- Bar widget showing each half's battery and the active layer name, with
  low-battery colors and a greyed-out right half while it is disconnected.
- Click panel with per-half battery and trend, BLE profile, right-half link,
  firmware revision, caps word state when the firmware reports it, and one tab
  per keymap layer drawn from a keymap-drawer YAML file.
- Desktop notifications at 20%, 10% and 5% per half, and when the right half
  stays disconnected for over a minute.
- Reads the custom ZMK status GATT service when the firmware has it and falls
  back to the standard Battery Service otherwise.
- Resolves keymap-drawer `mdi:` legends, and common `material:` names, to
  Nerd Font icons.
