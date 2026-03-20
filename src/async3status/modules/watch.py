import asyncio
import asyncinotify
from base import Module
from pathlib import Path


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

    Example:

        modules:
          - type: file
            path: "/tmp/status.txt"
            refresh: 5
            format: "{}"
    """

    def __post_init__(self):
        self.path = Path(self.config["path"]).absolute()
        self.refresh = self.config.get("refresh", None)
        self.format = self.config.get("format", "{}")
        self.strip = self.config.get("strip", True)

    def do_update(self):
        try:
            with open(self.path, "r") as f:
                content = f.read()
        except Exception:
            self.update(f"Failed to read '{self.path}'")
            return
        if self.strip:
            content = content.strip()
        self.update(self.format.format(content))

    async def watch_file(self):
        watcher = asyncinotify.Inotify()
        if self.path.is_file():
            watcher.add_watch(self.path, asyncinotify.Mask.MODIFY)
        watcher.add_watch(
            self.path.parent,
            asyncinotify.Mask.CREATE | asyncinotify.Mask.MOVED_TO
        )
        async for event in watcher:
            if event.watch.mask == asyncinotify.Mask.MODIFY:
                self.do_update()  # file modified
            elif event.name.name == self.path.name and self.path.is_file():
                # file created or moved
                self.do_update()
                try:
                    watcher.add_watch(self.path, asyncinotify.Mask.MODIFY)
                except Exception:
                    pass

    async def poll_file(self):
        while self.refresh is not None:
            await asyncio.sleep(self.refresh)
            self.do_update()

    async def run(self):
        self.do_update()
        tasks = [asyncio.create_task(self.watch_file())]
        if self.refresh is not None:
            tasks.append(asyncio.create_task(self.poll_file()))
        await asyncio.gather(*tasks)

