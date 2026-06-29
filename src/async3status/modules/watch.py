import asyncio
import re
from datetime import datetime
from pathlib import Path

import asyncinotify

from async3status.base import Module


class Watch(Module):
    """
    Displays the contents of a file and updates when it changes or is replaced.

    Configuration:

    - path (str): File to read.
    - refresh (int | None): Optional polling interval in seconds.
        If set, file is re-read periodically even without events.
        Default: None (event-driven only)
    - format (str): Format string
        Default: "{}"
    - strip (bool): Strip whitespace from file contents.
        Default: True
    - relative_time (bool): Replace ISO timestamps with relative times.
        E.g., "2026-06-19T03:09" becomes "T-12h"
        Default: False

    Example:

        modules:
          - type: watch
            path: "/tmp/status.txt"
            relative_time: true
            format: "{}"
    """

    # Regex to match ISO timestamps: YYYY-MM-DD, YYYY-MM-DDTHH:MM, YYYY-MM-DDTHH:MM:SS
    TIMESTAMP_PATTERN = re.compile(
        r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?'
    )

    def __post_init__(self):
        self.path = Path(self.config["path"]).absolute()
        self.refresh = self.config.get("refresh", None)
        self.format = self.config.get("format", "{}")
        self.strip = self.config.get("strip", True)
        self.relative_time = self.config.get("relative_time", False)
        self.last_content = ""  # Store raw content for bucket calculations

    def parse_timestamp(self, iso_str):
        """Parse ISO timestamp string to datetime, or None if invalid."""
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(iso_str, fmt)
            except ValueError:
                continue
        return None

    def format_relative(self, dt):
        """Format datetime as relative time (T-3h, T+2d, etc.)."""
        now = datetime.now()
        diff = now - dt
        total_seconds = diff.total_seconds()

        # Determine sign
        if total_seconds >= 0:
            sign = "-"
        else:
            sign = "+"
            total_seconds = abs(total_seconds)

        # Convert to appropriate unit
        minutes = total_seconds / 60
        hours = total_seconds / 3600
        days = total_seconds / 86400
        weeks = total_seconds / (86400 * 7)

        if total_seconds < 60:
            return f"T{sign}0m"
        elif minutes < 60:
            return f"T{sign}{int(minutes)}m"
        elif hours < 24:
            return f"T{sign}{int(hours)}h"
        elif days < 7:
            return f"T{sign}{int(days)}d"
        else:
            return f"T{sign}{int(weeks)}w"

    def replace_timestamps(self, content):
        """Replace all ISO timestamps in content with relative times."""
        def replacer(match):
            iso_str = match.group(0)
            dt = self.parse_timestamp(iso_str)
            if dt is None:
                return iso_str  # Leave unchanged if parse fails
            return self.format_relative(dt)

        return self.TIMESTAMP_PATTERN.sub(replacer, content)

    def seconds_until_bucket_change(self, dt):
        """Calculate seconds until the relative time display will change."""
        now = datetime.now()
        diff = now - dt
        total_seconds = abs(diff.total_seconds())

        if total_seconds < 60:
            # In "0m" bucket, will change at 60 seconds
            return 60 - total_seconds
        elif total_seconds < 3600:
            # In minutes bucket, will change at next minute boundary
            current_minutes = int(total_seconds / 60)
            next_boundary = (current_minutes + 1) * 60
            return next_boundary - total_seconds
        elif total_seconds < 86400:
            # In hours bucket, will change at next hour boundary
            current_hours = int(total_seconds / 3600)
            next_boundary = (current_hours + 1) * 3600
            return next_boundary - total_seconds
        elif total_seconds < 86400 * 7:
            # In days bucket, will change at next day boundary
            current_days = int(total_seconds / 86400)
            next_boundary = (current_days + 1) * 86400
            return next_boundary - total_seconds
        else:
            # In weeks bucket, will change at next week boundary
            current_weeks = int(total_seconds / (86400 * 7))
            next_boundary = (current_weeks + 1) * 86400 * 7
            return next_boundary - total_seconds

    def next_bucket_change(self):
        """Calculate seconds until next display bucket change, or None if no timestamps."""
        if not self.last_content:
            return None

        matches = self.TIMESTAMP_PATTERN.findall(self.last_content)
        if not matches:
            return None

        min_seconds = None
        for iso_str in matches:
            dt = self.parse_timestamp(iso_str)
            if dt is None:
                continue
            seconds = self.seconds_until_bucket_change(dt)
            if min_seconds is None or seconds < min_seconds:
                min_seconds = seconds

        return min_seconds

    def do_update(self):
        try:
            with open(self.path, "r") as f:
                content = f.read()
        except Exception:
            self.update(f"Failed to read '{self.path}'")
            return
        if self.strip:
            content = content.strip()

        # Store raw content for bucket calculations
        self.last_content = content

        # Replace timestamps if enabled
        if self.relative_time:
            content = self.replace_timestamps(content)

        self.update(self.format.format(content))

    def _next_timeout(self):
        """Seconds until the next timer-driven update, or None for none.

        Merges the relative-time bucket boundary with the optional refresh
        poll interval. Recomputed every loop iteration so newly arrived
        timestamps immediately reschedule the bucket timer.
        """
        timeout = None
        if self.relative_time:
            bucket = self.next_bucket_change()
            if bucket is not None:
                # +1s buffer to land past the boundary, capped at 1 hour
                timeout = min(bucket + 1, 3600)
        if self.refresh is not None:
            timeout = self.refresh if timeout is None else min(timeout, self.refresh)
        return timeout

    async def on_wake(self):
        """Refresh display after waking from suspend."""
        self.do_update()

    async def run(self):
        self.do_update()

        watcher = asyncinotify.Inotify()
        if self.path.is_file():
            watcher.add_watch(self.path, asyncinotify.Mask.MODIFY)
        if self.path.parent.is_dir():
            watcher.add_watch(
                self.path.parent,
                asyncinotify.Mask.CREATE | asyncinotify.Mask.MOVED_TO,
            )

        while True:
            timeout = self._next_timeout()
            try:
                if timeout is None:
                    event = await watcher.get()
                else:
                    event = await asyncio.wait_for(watcher.get(), timeout)
            except asyncio.TimeoutError:
                # Bucket boundary or refresh interval reached.
                self.do_update()
                continue

            if event.mask & asyncinotify.Mask.MODIFY:
                self.do_update()  # file modified
            elif event.name and str(event.name) == self.path.name and self.path.is_file():
                # file created or moved
                self.do_update()
                try:
                    watcher.add_watch(self.path, asyncinotify.Mask.MODIFY)
                except Exception:
                    pass
