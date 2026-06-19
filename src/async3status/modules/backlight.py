import asyncio
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
        retry_interval = cfg.get("retry_interval", 5)

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

        # Watch brightness file - retry if it doesn't exist
        while True:
            try:
                inotify = Inotify()
                inotify.add_watch(brightness_file, Mask.MODIFY)
                self.update(get_text())
                async for event in inotify:
                    if event.mask & Mask.MODIFY:
                        self.update(get_text())
            except FileNotFoundError:
                self.update(f"{icon} no backlight")
                await asyncio.sleep(retry_interval)

