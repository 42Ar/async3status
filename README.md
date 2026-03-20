# async3status
**async3status** is an **asyncio-based, event-driven i3/sway status bar framework**.  
It allows you to write **extensible Python modules** that can update the bar in response to:
- timers (periodic updates)  
- sockets / file descriptors  
- IPC events  
It is a lightweight replacement for `py3status` with **full async support**.

## Features
- Fully **async event-driven**  
- Modular: add/remove modules easily  
- Configurable via `~/.config/async3status/config.yaml`  
- Supports timers, sockets and other async sources  
- No global state; modules interact via the `Bar` object  
- Easy to extend with new Python modules

## Installation
Clone the repository and install in editable mode:
```bash
git clone https://github.com/yourusername/async3status.git
cd async3status
pip install -e .
```

## Configuration
Create the config file at:
```bash
~/.config/async3status/config.yaml
```
Example `config.yaml`:
```yaml
modules:
  - type: clock
    format: "%Y-%m-%d %H:%M:%S"
```
- Each module has a `type` and optionally a `name`
- The `type` matches a Python module in `modules/` and the capitalized version matches the class name in that module
- Modules can accept any **custom config keys**

## i3 Integration
To use **async3status** with i3 or sway:
1. Ensure the config file exists at:
```bash
~/.config/async3status/config.yaml
```
2. Edit your i3 config (`~/.config/i3/config`) and set the bar command:
```ini
bar {
    status_command /path/to/repo/src/async3status/main.py
}
```
3. Reload i3:
```bash
i3-msg reload
```

## Modules
Modules are Python classes that inherit from `Module` (`base.py`).  
Each module must implement:
```python
async def run(self):
    # update self.block
    self.update()
```
Example modules:
- `modules/clock.py` – displays a clock  

## IPC Command
To send an command to a module, you can use the helper script `src/async3status/async3cmd`. The command must be of the form `async3cmd module <module_name> [args]`, where args depends on the module type.


