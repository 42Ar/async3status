# async3status

**async3status** is an **asyncio-based, event-driven i3/sway status bar framework**.  
It allows you to write **extensible Python modules** that can update the bar in response to:
- timers (periodic updates)  
- sockets / file descriptors  
- IPC events

It is a lightweight replacement for `py3status` with **full async support**.

## Features

- **Event-driven**: Modules update in response to file changes, sockets, D-Bus signals, and timers - no wasteful polling
- **Wake detection**: Automatic refresh after system suspend via D-Bus
- **Modular**: Easy to add, remove, or customize modules
- **IPC support**: Control modules at runtime via Unix socket
- **Pango markup**: Full support for colors and formatting

## Requirements

- Python 3.8+
- i3 or sway

## Installation

```bash
git clone https://github.com/yourusername/async3status.git
cd async3status
pip install -e .
```

### Optional Dependencies

- **dbus-fast**: Required for wake detection after suspend
  ```bash
  pip install dbus-fast
  ```

## Configuration

Create `~/.config/async3status/config.yaml`:

```yaml
modules:
  - type: clock
    format: "%Y-%m-%d %H:%M:%S"

  - type: battery
    battery_path: "/sys/class/power_supply/BAT0"

  - type: volume

  - type: backlight
    path: "/sys/class/backlight/intel_backlight"

  - type: disk
    path: "/"
    format: "💾 {free:.0f}{unit}"

  - type: watch
    path: "/tmp/status.txt"
    relative_time: true
```

## i3/sway Integration

Add to your i3 or sway config:

```
bar {
    status_command /path/to/async3status/src/async3status/main.py
}
```

Reload with `i3-msg reload` or `swaymsg reload`.

## Modules

### clock

Displays current time with automatic interval detection based on format string.

| Option   | Default        | Description                    |
|----------|----------------|--------------------------------|
| `format` | `"%H:%M:%S"`   | strftime format string         |

The refresh interval is automatically determined from the format (e.g., `%S` = every second, `%M` = every minute).

### battery

Battery monitoring with ACPI event support, notifications, and power management.

| Option              | Default                              | Description                         |
|---------------------|--------------------------------------|-------------------------------------|
| `battery_path`      | `/sys/class/power_supply/BAT0`       | Path to battery sysfs directory     |
| `refresh`           | `60`                                 | Fallback refresh interval (seconds) |
| `background_red_on` | `10`                                 | Show red background below this %    |
| `throttle_on`       | `10`                                 | Enable power throttling below this %|
| `display_current`   | `false`                              | Show current draw in amps           |
| `send_notify_on`    | `10`                                 | Send notification below this %      |
| `icon_plug`         | `🔌`                                 | Icon when charging                  |
| `icon_battery`      | `🔋`                                 | Icon when discharging               |
| `text_colors`       | (gradient)                           | Colors by battery percentage        |

### volume

PulseAudio/PipeWire volume display with real-time event updates.

| Option        | Default  | Description               |
|---------------|----------|---------------------------|
| `icon`        | `🔊`     | Icon when unmuted         |
| `icon_muted`  | `🔇`     | Icon when muted           |
| `muted_color` | `gray`   | Text color when muted     |

### backlight

Screen brightness with inotify-based updates.

| Option           | Default                             | Description                    |
|------------------|-------------------------------------|--------------------------------|
| `path`           | `/sys/class/backlight/intel_backlight` | Backlight sysfs directory   |
| `icon`           | `💡`                                | Display icon                   |
| `retry_interval` | `5`                                 | Retry interval if file missing |

### disk

Filesystem usage display.

| Option    | Default              | Description                              |
|-----------|----------------------|------------------------------------------|
| `path`    | `/`                  | Filesystem path to monitor               |
| `unit`    | `GB`                 | Unit: B, KB, MB, GB, TB, KiB, MiB, GiB, TiB |
| `refresh` | `60`                 | Refresh interval (seconds)               |
| `format`  | `💾 {free:.0f}{unit}` | Format string with `{free}`, `{used}`, `{total}`, `{percent}` |

### watch

Displays file contents with optional relative timestamps.

| Option          | Default | Description                              |
|-----------------|---------|------------------------------------------|
| `path`          | (required) | File to watch                         |
| `format`        | `{}`    | Format string (`{}` = file contents)     |
| `strip`         | `true`  | Strip whitespace from contents           |
| `refresh`       | `null`  | Optional polling interval (seconds)      |
| `relative_time` | `false` | Replace ISO timestamps with relative (T-3h) |

Relative time format: `T-0m` (< 1 min), `T-5m` (minutes), `T-3h` (hours), `T-2d` (days), `T-1w` (weeks).

### gateway

Shows the default network gateway interface.

| Option             | Default | Description                                      |
|--------------------|---------|--------------------------------------------------|
| `refresh`          | `5`     | Refresh interval (seconds)                       |
| `known_gateways`   | `[]`    | List of known interface names (e.g. `["wlp0s20f3"]`) |
| `unknown_color`    | `red`   | Pango color when interface is not in known_gateways |

### dunst

Notification pause state indicator.

| Option        | Default | Description             |
|---------------|---------|-------------------------|
| `paused_icon` | `🔕`    | Icon when paused        |
| `active_icon` | `🔔`    | Icon when active        |

Update via IPC: `async3cmd module dunst update`

### syncthing

Overall Syncthing sync state and aggregate completion, driven by the
Syncthing long-poll Event API (waits for changes, no busy polling).

| Option              | Default                 | Description                                   |
|---------------------|-------------------------|-----------------------------------------------|
| `address`           | `http://127.0.0.1:8384` | Syncthing GUI/API base URL                    |
| `apikey_command`    | (none)                  | Command whose stdout is the API key           |
| `apikey`            | (none)                  | API key in plaintext (use `apikey_command`)   |
| `timeout`           | `60`                    | Event long-poll timeout (seconds)             |
| `format`            | `{icon} {pct}`          | Format with `{icon}`, `{state}`, `{pct}`, `{need}` |
| `show_percentage`   | `true`                  | Show the overall completion percentage        |
| `idle_icon`         | `🔄`                    | Icon when idle                                |
| `syncing_icon`      | `🔁`                    | Icon when syncing                             |
| `scanning_icon`     | `🔍`                    | Icon when scanning                            |
| `error_icon`        | `⚠`                     | Icon on error                                 |
| `disconnected_icon` | `❌`                    | Icon when Syncthing is unreachable            |
| `text_color`        | (theme default)         | Pango color for the overall status text       |
| `error_color`       | `red`                   | Pango color on error                          |
| `disconnected_color`| `#aaaaaa`               | Pango color when disconnected                 |
| `per_device`        | `false`                 | Append per-device status after overall status |
| `devices`           | (all)                   | List of device names/ids to show (filter)     |
| `device_format`     | `{icon}{name} {pct}`    | Per-device format (`{icon}`, `{name}`, `{pct}`, `{type}`, `{last_seen}`, `{state}`) |
| `device_separator`  | ` `                     | String joining device entries                 |
| `device_connected_icon`    | `●`              | Icon for a connected device                   |
| `device_disconnected_icon` | `○`              | Icon for a disconnected device                |
| `device_paused_icon`       | `⏸`              | Icon for a paused device                      |
| `connected_color`   | `#3cc63c`               | Pango color for connected devices             |
| `show_device_percentage` | `true`             | `true`/`false`, or `incomplete` (hide at 100%) |
| `last_seen_format`  | `%Y-%m-%dT%H:%M`        | strftime format for `{last_seen}`             |
| `type_labels`       | tcp/relay/quic          | Map connection-type base to a short label     |

The API key is kept out of the config: `apikey_command` is run and its stdout
is used as the `X-API-Key` header, e.g. `apikey_command: "pass show syncthing/apikey"`.

With `per_device: true` the module appends every configured remote device with
a connection icon, connection type (`{type}`), completion percentage, and the
last-seen time (`{last_seen}`). Disconnected devices show only the icon and name.

Force a refresh via IPC: `async3cmd module syncthing update`

### static

Displays static text.

| Option  | Default | Description |
|---------|---------|-------------|
| `text`  | `ERROR` | Text to display |
| `color` | `red`   | Text color      |

## IPC Commands

Send commands to modules via the Unix socket:

```bash
# Using the helper script
async3cmd module <module_name> <command>

# Or directly with socat
echo "module dunst update" | socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/async3status.sock
```

The socket path defaults to `$XDG_RUNTIME_DIR/async3status.sock`.

## Writing Custom Modules

Create a new file in `src/async3status/modules/`. The class name must be the capitalized filename:

```python
# modules/mymodule.py
import asyncio
from base import Module

class Mymodule(Module):
    """Custom module example."""

    def __post_init__(self):
        # Initialize instance variables from config
        self.refresh = self.config.get("refresh", 10)

    async def on_wake(self):
        # Called when system wakes from suspend
        self.update("Woke up!")

    async def handle_ipc(self, command: str):
        # Handle IPC commands
        if command == "refresh":
            self.update("Refreshed!")

    async def run(self):
        while True:
            self.update("Hello!")
            await asyncio.sleep(self.refresh)
```

Then add to config:

```yaml
modules:
  - type: mymodule
    refresh: 30
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run from source
cd src/async3status && python main.py
```

## requirements.txt

For pip-based installations without pyproject.toml:

```
PyYAML>=6.0
pulsectl>=23.11.1
asyncinotify
```

Optional:
```
dbus-fast  # for wake detection
```

## pyproject.toml

```toml
[project]
name = "async3status"
version = "0.1.0"
description = "Async event-driven i3/sway status bar framework"
readme = "README.md"
requires-python = ">=3.8"
dependencies = [
    "PyYAML>=6.0",
    "pulsectl>=23.11.1",
    "asyncinotify"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
wake = [
    "dbus-fast",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

## License

See [LICENSE](LICENSE) for details.
