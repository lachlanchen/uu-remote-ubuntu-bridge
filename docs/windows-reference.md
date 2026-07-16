# Windows reference comparison

The compatibility work was compared with the same UU release on a Windows 11
Pro machine. The reference system was accessed only through its existing RDP
and SSH configuration; no Windows credential or account database was changed.

## Installed layout

The reference installation used:

```text
C:\zml\GameViewer
C:\zml\GameViewer\bin\GameViewerService.exe --service
C:\zml\GameViewer\bin\drivers\gvInput\gvinput.sys
C:\zml\GameViewer\bin\drivers\gvInput\gvinputmf.sys
```

The `GameViewerService` Windows service was running. Device Manager and UU's
logs showed `ROOT\HIDCLASS` and `HID\GVINPUT` devices, including a HID keyboard
collection. This established that control on Windows depends on a kernel HID
path that Wine cannot reproduce.

## Safe inspection commands

The following read-only commands were useful from OpenSSH for Windows:

```powershell
Get-Service GameViewerService
Get-CimInstance Win32_Service -Filter "Name='GameViewerService'" |
  Select-Object Name, State, PathName
Get-ChildItem 'C:\zml\GameViewer\bin\drivers\gvInput'
Get-PnpDevice | Where-Object InstanceId -Match 'GVINPUT'
```

UU logs were located under the installation's `log\server`, `log\service`, and
`log\client` directories. Only selected non-secret status lines were compared;
raw logs were not copied into Git because they include account and device
metadata.

## End-to-end controller test

The Windows machine's ordinary UU GUI was used as a controller for the Ubuntu
device. The sequence was:

1. Confirm the Ubuntu alias was online in the Windows UU device list.
2. Open the Ubuntu device and verify that the live GNOME desktop rendered.
3. Click the Ubuntu terminal icon.
4. Open a fresh terminal with `Ctrl+Alt+T`.
5. Type a command that created `/tmp/uu-broker-ok`.
6. Verify the file locally on Ubuntu.
7. Keep the same GameViewerServer PID alive beyond four minutes.

Before the input broker, step 3 caused an immediate forced disconnect. After
the broker, both mouse and keyboard events returned success and the file was
created. The temporary Windows RDP test session was then disconnected so it
would not compete with a mobile controller.

## What was not copied

The Windows `gvinput` driver, driver certificates, NetEase binaries, registry
state, account tokens, and device identifiers are not needed by this bridge
and are not stored in this repository.
