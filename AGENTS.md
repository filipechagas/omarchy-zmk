# AGENTS.md

Omarchy shell plugin (`io.github.filipechagas.zmk`): a Quickshell bar widget
fed by a Python bridge (`bridge/`) that reads a ZMK keyboard over BlueZ D-Bus.
The user-facing contract, settings and wire format live in `README.md`.

## Checks

- `tests/check.sh` — every check: manifest validator, Python tests, qmllint,
  QML model tests, host smoke test. Needs Omarchy, Qt 6 and a Wayland session;
  run it before every commit.
- `tests/ci.sh [version]` — the subset CI runs (marketplace manifest rules,
  changelog section, Python tests). Needs PyYAML.

## Live testing

When the plugin is installed as a symlink into `~/.config/omarchy/plugins/`,
omarchy-shell keeps serving the QML it first compiled (it logs `Module path …
is outside of the config folder`). After editing QML or the bridge, run
`omarchy restart shell` before judging the result.

## Wire contract

The status GATT payload is shared with the firmware module in
`filipechagas/zmk-config-corne` (`src/zmk_status_gatt.c`). Change it in both
repos together, bump the protocol version byte, and update the README's
"Wire contract" section, which is the reference.

## Releasing

1. Add a `## <version>` section to `CHANGELOG.md` (semver; its body becomes
   the GitHub release notes) and commit it to `main`.
2. Run `scripts/release.sh <version>`. It bumps `manifest.json`, runs both
   check scripts, tags `v<version>`, pushes `main` and the tag atomically, and
   prints the full commit SHA plus a prefilled marketplace link.
3. The `Release` workflow re-checks the tag and creates the GitHub release.
   Confirm it is green: `gh run list --workflow release.yml`.
4. Send the update to the marketplace (next section).

## Omarchy plugin marketplace

The listing at <https://plugins.omarchy.org> is pinned to one exact commit,
recorded through issues on `omacom/omarchy-plugin-marketplace`. Its rules:
<https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md>.

Updating the listing after a release:

1. Open the link `scripts/release.sh` printed. It prefills Plugin ID,
   Repository URL and Target commit (the full 40-character SHA of the
   released `main` HEAD).
2. Choose **Verify and publish a newer upstream commit** and tick the
   acknowledgment. URL parameters reach only text fields, so these stay manual.
3. Show the owner the completed form and submit only after they approve.
4. Watch the issue: the bot posts validation and an Automated Security
   Baseline result; a maintainer then applies `approved-and-verified`. On a
   failure, push a fix, release again, and edit the same issue with the new
   SHA.

Keep the repository listable:

- `manifest.json` `id` is permanent; renaming it means a new listing.
- Root `README.md` keeps its Install, Update and Remove sections; root
  `LICENSE` and `preview.png` (the marketplace card image) stay in place.
- The baseline outcome is `passed` today. Privilege, service-manager and
  package-manager commands in runtime code, docs or workflows, and files named
  `*install*` or `*setup*`, turn it into `review-required`; keep those out
  (`tests/` is excluded from the scan).
