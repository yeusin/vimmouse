# VimMouse

A macOS utility that brings Vim-style keyboard navigation to your mouse. Navigate and click UI elements across any application using keyboard shortcuts inspired by [Vimium](https://vimium.github.io/).

VimMouse overlays hint labels on clickable elements (buttons, links, text fields, menus) and lets you activate them by typing their hint characters — no mouse needed.

## Key Features

- **Hint-based clicking** — Type 1-2 character hints to click any UI element
- **Vim-style cursor movement** — HJKL keys with smooth acceleration
- **App launcher** — Alfred-like fuzzy search to launch apps and System Preferences panes
- **Window management** — Tile, split, center, and maximize windows with Ctrl+W prefix
- **Window switching** — Single-letter hints to jump between visible windows
- **Insert mode** — Passthrough mode for typing in the target app
- **Fully customizable keybindings** — Remap every action via Settings UI
- **Cmd+key passthrough** — Standard macOS shortcuts (Cmd+W, Cmd+Tab, etc.) work as expected
- **Launch at Login** — Start automatically via macOS ServiceManagement
- **Status bar indicator** — Shows current mode (VM:N / VM:I)

## Installation

Requires Python 3.13+, macOS, and [uv](https://docs.astral.sh/uv/).

```bash
uv run python -m vimmouse.main
```

### Build macOS App Bundle

```bash
uv run --group dev python setup.py py2app
```

The app bundle will be created in `dist/VimMouse.app`.

### Accessibility Permission

VimMouse requires Accessibility access to detect UI elements and intercept the global hotkey. On first launch, macOS will prompt you to grant permission in **System Settings > Privacy & Security > Accessibility**.

## Usage

### Activation

VimMouse enters Normal mode immediately on launch. Press **Cmd+Shift+Space** (default) to return to Normal mode from Insert mode.

### Modes

**Normal mode** — The overlay is active. Use HJKL to move the cursor, type hints to click elements, or use any bound action.

**Insert mode** — All keys pass through to the target app. A brief "INSERT" watermark flashes on screen. Press the hotkey to return to Normal mode.

### Default Keybindings

| Key | Action |
|-----|--------|
| `h` / `j` / `k` / `l` | Move cursor left / down / up / right |
| `Space` | Click at cursor position |
| `Shift+Space` | Right-click at cursor position |
| `f` | Toggle hint labels |
| `/` | Open app launcher |
| `i` | Enter Insert mode |
| `w` | Mouse forward button |
| `b` | Mouse back button |
| `Ctrl+W` | Window command prefix (see below) |
| `Ctrl+B` | Scroll up |
| `Ctrl+F` | Scroll down |
| `Cmd+key` | Passed through to the target app |

### Window Management

Press `Ctrl+W` to enter window command mode, then press a second key:

| Key | Action |
|-----|--------|
| `Ctrl+W` | Cycle through windows |
| `h` / `j` / `k` / `l` | Tile window to left / bottom / top / right half |
| `1` / `2` / `3` / `4` | Tile window to quarter |
| `q` / `w` / `e` | Tile window to top-left / top-center / top-right sixth |
| `a` / `s` / `d` | Tile window to bottom-left / bottom-center / bottom-right sixth |
| `c` | Center window |
| `Enter` | Maximize window |

### Hints

When hints are visible, type the hint characters to click the corresponding element:

- **UI elements** get two-character hints (e.g., `AB`, `CD`)
- **Windows** get single-character hints for quick switching
- Typing filters hints in real-time; backspace removes the last character

### Mouse Movement

Holding HJKL keys accelerates the cursor from 10px to 100px per step using an ease-in-out curve. Changing direction resets acceleration.

## Configuration

Settings are stored in `~/.config/vimmouse/config.json`.

Open Settings from the **VM** status bar menu to:

- Record a new activation hotkey (must include a modifier key)
- Customize keybindings for all actions (up to 4 keys per action)
- Reset to defaults

Example config:

```json
{
  "keycode": 49,
  "flags": 393216,
  "keybindings": {
    "move_left": {"keycode": 4},
    "toggle_hints": [
      {"keycode": 44},
      {"keycode": 3}
    ],
    "scroll_up": {"keycode": 11, "ctrl": true}
  }
}
```

## Project Structure

```
├── pyproject.toml          # Project metadata and dependencies
├── setup.py                # py2app build config
└── vimmouse/
    ├── main.py             # Entry point, status bar, app lifecycle
    ├── hint_overlay.py     # Overlay window, hints, keyboard handling
    ├── accessibility.py    # AX tree traversal, element detection
    ├── mouse.py            # Cursor movement, clicking, scrolling
    ├── config.py           # Config loading/saving, default keybindings
    ├── settings.py         # Settings UI, hotkey/key recorder
    ├── launcher.py         # Alfred-like app launcher with fuzzy search
    ├── window_manager.py   # Window tiling, splitting, centering, maximizing
    └── hotkey.py           # Global hotkey via CGEventTap
```

## License

MIT
