import asyncio
import re
import time

from async3status.base import Module


class Clock(Module):
    """
    Clock module that syncs the clock ticks precisely.
    """

    # Mapping of strftime codes to minimum interval in seconds
    INTERVALS = {
        "f": 1e-6,       # microsecond
        "S": 1,          # second
        "s": 1,          # epoch second
        "M": 60,         # minute
        "H": 3600,       # hour
        "I": 3600,       # hour (12h)
        "p": 3600,       # AM/PM
        "d": 86400,      # day of month
        "j": 86400,      # day of year
        "m": 86400,      # month
        "y": 86400,      # 2-digit year
        "Y": 86400,      # 4-digit year
        "w": 86400,      # weekday number
        "U": 86400,      # week number Sunday first
        "W": 86400,      # week number Monday first
        "a": 86400,      # weekday abbreviated
        "A": 86400,      # weekday full
        "b": 86400,      # month abbreviated
        "B": 86400,      # month full
    }

    def __post_init__(self):
        self.fmt = self.config.get("format", "%H:%M:%S")
        # Extract all % codes from the format string using regex
        codes = re.findall(r"%([a-zA-Z])", self.fmt)
        if codes:
            self.interval = min(self.INTERVALS.get(code, 86400) for code in codes)
        else:
            self.interval = 86400  # default daily if no recognizable code

    async def on_wake(self):
        """Refresh clock immediately after waking from suspend."""
        self.update(time.strftime(self.fmt))

    async def run(self):
        while True:
            self.update(time.strftime(self.fmt))

            # Compute exact next tick
            now = time.time()
            next_tick = ((now // self.interval) + 1) * self.interval
            wait_time = max(0, next_tick - now)
            await asyncio.sleep(wait_time)

