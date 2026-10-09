# Fresh installation: release downloads and Wine shortcuts

This records the fixes and remaining limit from community reports #15–#17.
They were reproduced with isolated downloader and shortcut fixtures; no
production Wine prefix or running desktop was reinstalled to test them.

## Choose an accepted release, not whatever the CDN returns

A fresh install defaults to the maintainer-accepted `4.42.1.2835` manifest.
A plain reinstall keeps the installed manifest. `--release-manifest PATH` and
`UURB_RELEASE_MANIFEST` remain explicit overrides. This is a pinned baseline,
not automatic approval of any newer version found on the download server.

NetEase's official `latest` endpoint moves. Downloads now use one fresh curl
request, with no parallel ranges, resumed bytes, or automatic retry that could
splice different releases. A verified cached installer is reused. A mismatch
fails with expected/received hashes and leaves existing cached files intact.
Required downloads are checked before stopping an existing bridge.

If the endpoint serves a different release, use an installer obtained from
NetEase that matches the approved manifest. For example:

```bash
sha256sum /path/to/uu-4.42.1.2835.exe
# Expected: d3a7776f6fb00b196e2fcbf8acba06fd52b19437b0da80fec0ae838ee362f06f
./install.sh --uu-installer /path/to/uu-4.42.1.2835.exe \
  --release-manifest patches/uu-remote-4.42.1.2835.json
```

Do not change the approved hash just to accept another download. Binary
patches belong to exact releases, and a passing download hash does not by
itself establish support for a new release.

## FreeRDP nightly expired: still an open dependency issue

The pinned Jenkins build **2064** returns HTTP 404. Simply replacing it with
another short-lived build repeats the problem and changes the reviewed
FreeRDP/WinPR pair. A durable reviewed artifact or reproducible replacement
still needs to be supplied and validated. This change does **not** restore a
fully working default RDP fresh install when no approved client is available.

For an existing **X11/XRDP desktop**, the VNC relay does not need this Windows
FreeRDP binary:

```bash
./install.sh --desktop-relay vnc
```

This fallback is not a Wayland capture solution. It is also not a reason to
switch a working relay automatically. For RDP, an already-owned copy of the
exact reviewed client can be provided explicitly:

```bash
export UURB_FREERDP_CLIENT=/path/to/reviewed/sdl-freerdp.exe
# Required SHA256:
# b384347b6d0dd1e0c9912d18f5993b4e30643470e2a627e112debb34e8710762
./scripts/build-winpr.sh --download-client-only
./install.sh
```

The override is checked against the existing pin. It cannot approve a new
nightly. The download-only check needs no Wine/service restart. Do not post
vendor binaries, account state or private logs in an issue. Any future
FreeRDP distribution must preserve its provenance and applicable notices.

## One working launcher

Wine may create a second visible `UU远程` launcher that starts the vendor GUI
outside the bridge. Installation now archives visible UU `.desktop` entries
only when their `Exec` explicitly names the selected `WINEPREFIX`, Wine, and a
known UU shortcut/target. A matching Desktop `.lnk` is archived with its owned
launcher. Hidden `uuremote://` handlers, unrelated applications, symlinks and
other Wine prefixes are preserved. The helper respects the XDG Desktop and
data/state locations and does not disable Wine's menu builder globally.

For an existing installation, preview before applying:

```bash
python3 scripts/archive-wine-launchers.py \
  --wine-prefix "$HOME/.local/share/wineprefixes/uu-remote"
python3 scripts/archive-wine-launchers.py \
  --wine-prefix "$HOME/.local/share/wineprefixes/uu-remote" --apply
update-desktop-database "$HOME/.local/share/applications"
```

With a custom `XDG_DATA_HOME`, use its `applications` directory for the last
command. Each run with matching entries creates a private backup under
`${XDG_STATE_HOME:-$HOME/.local/state}/uu-remote-bridge/launcher-backups/`.
`restore-map.json` maps originals to backups. To undo, copy a listed backup
to its original path only if that original path is still absent. A repeated
cleanup is a no-op until Wine creates a new owned shortcut. There is no
runtime watcher and no account/login or protocol-registration change.
