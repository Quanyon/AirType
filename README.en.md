[English](README.en.md) | [简体中文](README.md)

# AirType — Cross-Screen Input

Type on your phone / dictate with voice → text appears right at the cursor on your PC; snap a photo on your phone → it's pasted automatically into the input field your PC is focused on.
Pure LAN communication: **zero install on the phone side** (works in any browser), **zero third-party dependencies on the PC side**.

## Why

Your PC has no microphone (or it's too far away) and you want to use your phone's voice input; or you're in a meeting and want to photograph a whiteboard or a paper document and drop it straight into the document / chat box on your PC.

AirType turns your phone into a "wireless keyboard + camera" for your PC: join the same Wi-Fi, scan the QR code to pair, and your phone becomes an extension of your PC's cursor.

## Quick Start

### Windows

1. Double-click `build/AirType.exe` (requires the built-in .NET Framework 4.x; Win10/11 both satisfy this);
2. A "scan to connect" window pops up, and a tray icon stays resident in the bottom-right corner;
3. On your phone (same Wi-Fi as the PC), scan the QR code with WeChat, or enter the address shown in the window in the phone's browser;
4. When the phone page shows a green dot "Connected", start typing. The window simultaneously shows "Phone connected".

Tray right-click menu: the first line always shows the current address / port / connection status; plus QR code link / regenerate pairing code / pause injection / select network adapter (scan address) / enable or disable startup on boot / view log / open received-files folder / recent files / quit.

### Kylin (Kylin V10 and other Linux desktops)

```bash
bash kylin/install.sh          # one-click install: installs dependencies, creates a desktop icon, enables autostart — zero input required
# or run directly:
python3 kylin/airtype.py    # after startup, open http://localhost:8765/pair in a browser
```

After installation, double-click the desktop icon. On first use you can run `python3 kylin/airtype.py --selfcheck` to check whether the injection channel is ready; on multi-NIC machines where the phone cannot connect, the startup log lists all candidate addresses — restart with `python3 kylin/airtype.py --ip <another NIC's address>` to switch which NIC the QR code points to.

### Two input modes on the phone page

| Mode | Behavior | Best for |
|---|---|---|
| Manual send | Finish typing/speaking, tap **Send**, text appears at the PC cursor | Short messages, send and go |
| Live sync | Text appears as you speak: a whole sentence is sent immediately on completion; continuous input syncs at least every 0.4 s | Long dictation, watch the text appear word by word |

Auxiliary actions: **Enter**, **Backspace**, **Undo** (deletes the last sent content); **Clear** resets the input box; you can also enable **Auto-clear** (clears automatically after a 2.5 s pause, off by default).

### Photos → PC (both versions)

Tap **Photo → PC** on the phone to select multiple photos or take a photo on the spot:

1. **Smart compression**: photos larger than 2 MB or with a long edge over 2048 px are automatically compressed to JPEG before transfer; toggle the **Original** switch to send uncompressed (the switch state is remembered);
2. **Transfer progress**: the phone shows "sending i/N · filename (percentage)"; tapping the button again mid-upload cancels the whole batch — a half-received file on the PC is discarded; a failed image is automatically retried once;
3. Photos travel over the LAN to the PC and are saved to `Downloads/AirType接收` (`~/Downloads`, or `~/下载` on Chinese-locale Kylin desktops; duplicate names get an auto-incrementing suffix; 200 MB per-file limit);
4. The Windows version then automatically pastes the photo into the app the cursor is currently in (WeChat, Word, Notepad, etc.): the clipboard carries **both a file reference and a bitmap**, and each app takes what it needs; clipboard operations use the **native system API** (CF_HDROP + CF_DIB in one shot, no OLE/COM — via OLE, clipboard-watching apps like WeChat/Word issue reverse data requests, and large images can freeze the foreground window for ~10 s); images with a long edge over 3000 px are **downscaled before going to the clipboard** (the disk file is still saved at the original size) to avoid dragging down the foreground app with a huge bitmap; the Ctrl+V keystroke is **injected step by step and waits for the foreground process to become idle**, so keys are not lost even while Word/WPS is busy handling clipboard notifications; after pasting, your original clipboard is restored only if it still holds what we put there — if you copied something new in the meantime, it is not overwritten; pasting is asynchronous — the phone first shows "Saved ✓ Pasting…", and the real result (success/failure/reason) is sent afterwards, never a premature "pasted";
5. If pasting fails, the target is not an image, or "pause injection" is on, it automatically degrades to save-only — the file is not lost, and the phone shows the reason;
6. **On the PC**: the tray menu has "Open received folder" and "Recent files" (open the most recent received file directly); the scan page also has an "Open received folder" button.

> The Kylin version's auto-paste depends on xclip / wl-copy and the target app's support for image clipboard formats — it is best-effort; saving to disk always works, and the paste result is accurately reported on the spot.

## Feature Overview

- **Text input**: Chinese / emoji go from your phone's IME straight to the PC cursor, with both manual-send and live-sync modes;
- **Photo transfer**: multi-select from gallery or camera, send immediately; smart compression + original toggle + progress/cancel/auto-retry, then auto-paste at the cursor (see above);
- **Pairing**: 4-digit pairing code, randomized at every startup; pair by scanning the QR code or entering the code manually;
- **PC-side control**: the scan page has "Disconnect current phone" and "Re-pair" buttons (operable only on the PC itself): disconnect stops the phone and requires re-entering the code; re-pair issues a new code and revokes the old session at the same time — a stale device cannot reconnect without obtaining a new code; the tray menu's "Regenerate pairing code" also revokes the old session;
- **Status feedback**: green "Connected" dot on the phone; the PC scan page shows "Phone connected, you can start typing" plus the current address:port in real time; the Windows tray's first line and hover tooltip also always show address/port/connection status; after a pairing-code change both ends guide you to re-pair (stale pages stop blind reconnecting — just enter the new code to recover);
- **Multi-NIC troubleshooting**: the QR code points to the "current scan address" rather than picking one on the fly; the Windows tray's "Select NIC (scan address)" can switch at any time (no restart needed — the QR code redraws immediately after switching); Kylin uses `--ip`; the startup log lists all candidate addresses;
- **Single session**: only one phone at a time; a new connection replaces the old one and explains why on the old page;
- **Pause injection**: one click in the tray; the phone receives a clear message when sending;
- **Autostart on boot**: supported on both versions (Windows tray menu; Kylin XDG autostart);
- **Logs**: Windows `%LocalAppData%\AirType\log.txt` (reachable from the tray), Kylin `~/.config/airtype/log.txt`.

## How It Works

```
Phone browser (mobile.html)                 PC
  │   text/keys → JSON text frames          ├─ Windows: AirType.exe (SendInput injection)
  ├──────────── WebSocket :8765 ────────────┤
  │   images → binary chunks (file protocol)└─ Kylin: airtype.py (xdotool/dotool/clipboard injection)
```

- **Zero dependencies**: the Windows version is a single C# 5 source file compiled with the system `csc.exe`; web resources are embedded into the exe as Win32 resources; the Kylin version uses only the Python 3 standard library; the WebSocket is a hand-written RFC6455 implementation (with fragmented-frame reassembly, compatible with the splitting behavior of WeChat's in-app browser engine).
- **Protocol** (phone → PC): `hello{code}` pairing → `text` / `enter` / `backspace` / `sync{back,text}` input → `file{name,size,paste}` + binary chunks + `file_end` for file transfer (cancellable mid-way with `file_cancel`) → `ping`; PC → phone: `ready` / `ack{ok,chars,fg}` / `file_begin` / `file_got` / `file_done{saved,pasted,pasting?,why?}` / `note{msg}` (async results and operation receipts) / `error{msg}` / `pong`. The scan page also serves HTTP endpoints: `GET /status?c=<page's own code>` which only answers the two booleans `{connected, match}` (never returns the pairing code), and `GET /ctrl?act=disconnect|recode|opendir&c=<code>` for the control buttons on the scan page; the scan page and QR resources are restricted to the PC itself (other LAN devices get 403), preventing other devices from seeing pairing info.
- **Injection**: Windows uses `SendInput` character-by-character without touching the clipboard; Kylin auto-selects the channel per session type (X11: clipboard > xdotool > dotool; Wayland: dotool > clipboard > xdotool). Injection failures are reported back to the phone — never "phone says success but the PC did nothing".
- **Undo guardrail**: the PC keeps a ledger of "how many characters were actually injected into the current foreground window in this session" (Windows resets it automatically when the foreground window switches); batch backspace (undo) is truncated or rejected when it exceeds the quota, while single backspace is unrestricted — this prevents deleting text in unrelated apps after switching windows.
- **Security**: data never leaves the LAN and never passes through any server; the 4-digit pairing code prevents accidental connections on the same Wi-Fi; filenames are sanitized and writes are restricted to the receive directory; frame sizes and file sizes are capped against abuse.

## Building from Source & Development

### Windows

```bat
build\build_stage1.bat
```

Compiles with the system `csc.exe` (.NET Framework 4.x); output is `build\AirType.exe`. Three hard constraints:

1. **C# 5 syntax only** (the system csc does not support newer syntax — not even string interpolation);
2. **The source file must stay UTF-8 with BOM**, otherwise Chinese strings become garbled;
3. **The pages under `src/web/` are embedded resources — you must recompile after changing them**; quit the running instance before compiling (file lock).

### Kylin

No compilation needed — run `python3 kylin/airtype.py` directly; pages live under `kylin/web/`, so just refresh the browser after editing.

### Automated Regression Tests

| Script (spike/) | What it tests | Prerequisite |
|---|---|---|
| `test_ws_pairing.py` | WS pairing / wrong-code rejection / ping-pong | Windows exe running (8765) |
| `test_sync.py` | sync protocol + phone-page elements | Same as above |
| `test_kylin.py` | Kylin service-layer full protocol (fake injector, no real input) | None; self-loads the module |
| `test_kylin_e2e.py` | Kylin graceful startup with no injection channel; duplicate-startup detection | None; starts the service itself |

Recommended baseline workflow for development (Windows, PowerShell):

```powershell
Stop-Process -Name AirType -Force -ErrorAction SilentlyContinue   # 1. kill old instance
& "build\build_stage1.bat"                                            # 2. rebuild
Start-Process "build\AirType.exe"                                  # 3. start new instance
python spike\test_ws_pairing.py; python spike\test_sync.py            # 4. regression; exit code 0 = pass
```

## Directory Layout

```
src/            Windows version: AirType.cs (single file) + web/ (phone/scan-page resources)
kylin/          Kylin version: airtype.py + web/ + install.sh / run.sh + assets/
build/          Build scripts and output (AirType.exe)
spike/          Automated tests and historical verification scripts (_-prefixed files are temporary, not committed)
```

## FAQ

**Phone keeps spinning / can't connect after scanning (timeout)?**
Check in order:
1. Is the phone on the **same Wi-Fi** as the PC (mobile data will never work)?
2. On multi-NIC PCs (VPN/hotspot/virtual adapters are common), the QR may point to a NIC the phone can't reach: check the current address on the scan page and try another — the Windows tray's "Select NIC (scan address)" switches directly; Kylin uses `--ip` followed by a restart;
3. Did Windows Firewall block inbound traffic? As admin PowerShell, allow it:
   ```powershell
   New-NetFirewallRule -Name AirType8765 -DisplayName "AirType LAN input (TCP 8765)" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Any
   ```
   Note: firewall **Block rules take precedence over Allow rules** — if you clicked "Cancel" on a Windows allow popup before, the system auto-creates a block rule; you must delete it for the allow rule to take effect (`Get-NetFirewallApplicationFilter` can help find it);
4. Still stuck: change the PC's network profile from "Public" to "Private".

**Pairing code changed and the phone can't connect?**
A new code is issued at every startup, so old QR codes/pages are immediately invalid. The phone page shows a code-entry box — just type the new 4-digit code displayed on the PC screen; no need to re-scan.

**Photo transferred but not pasted into the app?**
Pasting only happens into the window that is foreground at the exact moment the transfer completes — don't switch windows right after sending. The phone reports in two steps: first "Saved", then the real paste result; if pasting didn't happen it states the reason. If the target app doesn't recognize file references in the clipboard, it degrades to save-only — grab the file from `Downloads/AirType接收` (tray "Recent files" or the scan page's "Open received folder" get you there). With "pause injection" on, it also saves only.

**Phone shows "Injection failed"?**
The PC-side injection channel has a problem (common on Kylin: permissions, session switching). Check the PC log; run `--selfcheck` on Kylin to re-check the channel, or `--test-inject` for a live test.

**Can multiple phones be used at once?**
No — only one session at a time; a new device scanning in replaces the old one, and the old page receives a "replaced by a new connection" notice.

## Known Limitations

- Only solves "input into the PC"; no reverse direction (PC → phone) and no clipboard sync;
- Live sync relies on a longest-common-prefix incremental algorithm; after large out-of-order edits on the phone, the phone's content wins;
- In terminal-type windows clipboard paste is Ctrl+Shift+V, to which the Kylin clipboard channel is insensitive (the typing channel has no such issue);
- The Windows scan popup uses the system WebBrowser control (IE11 engine), so page code must stay ES5.

## License

[MIT](LICENSE)
