# Desktop Sticky Note

A lightweight, always-on-desktop sticky note for Windows. Built with Python and Tkinter, it sits on your desktop behind other windows — just like a real sticky note pinned to your desk.

## Features

- **Desktop-level window** — stays behind all other windows by default, or pin it to the top
- **Frameless, resizable** — no title bar; drag from the top grip handle, resize from any edge or corner
- **Auto-hiding drag handle** — a subtle dot-grip appears when you hover near the top edge, then slides away
- **System tray icon** — minimize to tray; left-click to toggle visibility, right-click for the context menu
- **Rich text editing** — configurable font family, size, color, tab width, and background color
- **Persistent** — text and all settings are saved automatically and restored on next launch
- **Start on boot** — optional Windows startup registration via the registry
- **Borderless mode** — toggle the text area border on or off
- **Single-file exe** — compiles to a standalone `.exe` with PyInstaller (no Python install needed to run)

## Screenshot

*(Place a screenshot here)*

## Requirements

- Python 3.10+ (for development)
- Windows 10/11
- No third-party Python packages required at runtime (only `tkinter` and `ctypes`, both included with Python)

### Build dependency

- [PyInstaller](https://pyinstaller.org/) (for compiling to `.exe`)

## Getting Started

### Run from source

```bash
python desktop_sticky_note.py
```

### Build a standalone exe

```bash
pip install pyinstaller
pyinstaller --onefile -w desktop_sticky_note.py
```

The compiled exe will be at `dist/desktop_sticky_note.exe`.

## Configuration

All settings are stored in a hidden folder next to the executable (or script):

```
.desktopStickNote_config/
    sticky_note_config.json   # all preferences
    sticky_note.txt           # your note content
    logo.png                  # (optional) window/tray icon
```

Right-click the note and choose **Settings...** to open the settings panel:

| Setting | Description |
|---|---|
| Background color | Pick any color for the note background |
| Font color | Pick any color for the text |
| Font family | Choose from all installed system fonts |
| Font size | 8 – 72 pt |
| Tab size | Tab stop width in spaces (1 – 16) |
| Launch at Windows startup | Register/unregister in the Windows Run registry key |
| Pin to top | Keep the note above all other windows |
| Show taskbar tray icon | Show/hide the system tray icon |
| Pin drag handle | Keep the drag grip always visible |
| Drag handle reveal distance | How close the cursor must be to the top edge to reveal the grip (5 – 80 px) |
| Show border | Toggle the text area border |

## Project Structure

```
desktop_sticky_note.py        # entire application (single file)
desktop_sticky_note.spec      # PyInstaller spec (auto-generated)
.desktopStickNote_config/     # runtime data (created on first launch)
dist/
    desktop_sticky_note.exe   # compiled executable
```

## License

This project is provided as-is for personal use.
