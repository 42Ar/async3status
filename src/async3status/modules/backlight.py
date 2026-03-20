import os
from base import Module
from asyncinotify import Inotify, Mask


class Backlight(Module):
    """
    Backlight module that automatically updates when the brightness
    file in /sys/class/backlight changes.
    """

    async def run(self):
        cfg = self.config
        icon = cfg.get("icon", "💡")
        path = cfg.get("path", "/sys/class/backlight/intel_backlight")

        brightness_file = os.path.join(path, "brightness")
        max_file = os.path.join(path, "max_brightness")

        def read_int(p):
            try:
                with open(p, "r") as f:
                    return int(f.read().strip())
            except Exception:
                return None

        def get_text():
            cur = read_int(brightness_file)
            maxv = read_int(max_file)
            if cur is None or maxv is None or maxv == 0:
                return f"{icon} ?%"
            percent = int(cur / maxv * 100)
            return f"{icon} {percent}%"

        # Initial output
        self.update(get_text())

        # Watch brightness file
        inotify = Inotify()
        inotify.add_watch(brightness_file, Mask.MODIFY)
        async for event in inotify:
            if event.mask & Mask.MODIFY:
                self.update(get_text())

