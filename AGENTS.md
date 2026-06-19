# AGENTS.md

## Project Overview

Asyncio-based i3/sway status bar framework. Lightweight py3status replacement.

## Installation

```bash
pip install -e .
```

## Running

Must run from `src/async3status/` due to relative imports:

```bash
cd src/async3status && python main.py
```

Config: `~/.config/async3status/config.yaml`

## Module Convention

Modules in `src/async3status/modules/`. Class name must be capitalized filename:
- `clock.py` → class `Clock`
- `volume.py` → class `Volume`

All modules inherit from `Module` (in `base.py`) and implement `async def run(self)`.

## IPC

Unix socket at `$XDG_RUNTIME_DIR/async3status.sock` (default `/run/user/1000/async3status.sock`).

Command format: `module <module_name> <args>`

## Testing

```bash
pip install -e ".[dev]"
pytest
```

Tests use real inotify (no mocking). Add `await asyncio.sleep(0.05)` after initial setup before modifying files to ensure watchers are ready.

## Linting

No linter or CI configured.
