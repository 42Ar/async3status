import asyncio
import os

from async3status.base import Module


class Disk(Module):
    """
    Storage module for async3status.

    Displays available disk space for a given path.

    Configuration (all optional):

    - path (str): Filesystem path to check.
        Default: "/"
    - unit (str): Unit for display.
        Options: B, KB, MB, GB, TB, KiB, MiB, GiB, TiB
        Default: "GB"
    - refresh (int): Refresh interval in seconds.
        Default: 10
    - format (str): Output format string.
        Available fields:
            {free}  -> free space
            {used}  -> used space
            {total} -> total space
            {percent} -> used percentage
        Default: "💾 {free}{unit}"

    Example:

        modules:
          - type: disk
            path: "/"
            unit: "GiB"
            format: "💾 {free:.1f}{unit} ({percent:.0f}%)"
            refresh: 60
    """

    UNITS = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }

    def __post_init__(self):
        self.path = self.config.get("path", "/")
        self.unit = self.config.get("unit", "GB")
        self.refresh = self.config.get("refresh", 60)
        self.format = self.config.get("format", "💾 {free:.0f}{unit}")
        self.factor = self.UNITS.get(self.unit)

    def get_stats(self):
        try:
            st = os.statvfs(self.path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            percent = (used / total) * 100 if total > 0 else 0
            return total, used, free, percent
        except Exception:
            return None

    def format_value(self, value):
        return value / self.factor

    def get_text(self):
        stats = self.get_stats()
        if stats is None:
            text = "💾 ?"
        else:
            total, used, free, percent = stats
            text = self.format.format(
                total=self.format_value(total),
                used=self.format_value(used),
                free=self.format_value(free),
                percent=percent,
                unit=self.unit,
            )
        return text

    async def run(self):
        while True:
            self.update(self.get_text())
            await asyncio.sleep(self.refresh)

