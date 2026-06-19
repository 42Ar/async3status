import asyncio

from async3status.base import Module


class Dunst(Module):
    """
    Displays a simple icon depending on whether dunst notifications are paused.
    If dunst notifications are changed, it is required to update this module via an IPC command.

    Example config:

    modules:
      - type: dunst
        name: mydunst  # optional (defaults to "notifications")
        paused_icon: "🔕"
        active_icon: "🔔"

    Updating via IPC:

        echo "module mydunst pause" | socat - UNIX-CONNECT:/path/to/async3status.sock
    """

    async def refresh(self):
        proc = await asyncio.create_subprocess_exec(
            "dunstctl", "is-paused",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await proc.communicate()
        out = out.decode().strip()
        if out == "true":
            self.update(self.config.get("paused_icon", "🔕"))
        elif out == "false":
            self.update(self.config.get("active_icon", "🔔"))
        else:
            self.update("DUNST ERROR")

    async def run(self):
        await self.refresh()

    async def handle_ipc(self, command: str):
        if command == "update":
            await self.refresh()

