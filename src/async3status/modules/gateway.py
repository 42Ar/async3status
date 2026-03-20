import asyncio
from base import Module


class Gateway(Module):
    """
    Module that shows the default gateway (polling `ip r g 8.8.8.8` command).

    Example config:

    modules:
      - type: gateway
        refresh: 5
    """

    async def run(self):
        refresh = self.config.get("refresh", 5)

        async def get_gateway():
            try:
                # Use subprocess asynchronously
                proc = await asyncio.create_subprocess_exec(
                    "ip", "r", "g", "8.8.8.8",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                out, _ = await proc.communicate()
                # Example output: b'8.8.8.8 via 192.168.1.1 dev eth0 src 192.168.1.100 uid 1000\n'
                # We split by spaces and take the 5th the Element after dev
                splitted = out.split()
                devi = splitted.index(b"dev")
                gw = splitted[devi + 1].decode("utf-8")
                return f"G: {gw}"
            except Exception:
                return "G: ?"

        while True:
            self.update(await get_gateway())
            await asyncio.sleep(refresh)

