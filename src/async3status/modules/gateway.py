import asyncio

from async3status.base import Module


class Gateway(Module):
    """
    Module that shows the default gateway (polling `ip r g 8.8.8.8` command).

    Example config:

    modules:
      - type: gateway
        refresh: 5
        known_gateways:
          - "wlp0s20f3"
          - "eth0"
        unknown_color: "red"
    """

    async def run(self):
        cfg = self.config
        refresh = cfg.get("refresh", 5)
        known_gateways = cfg.get("known_gateways", [])
        unknown_color = cfg.get("unknown_color", "red")

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
                splitted = out.split()
                devi = splitted.index(b"dev")
                iface = splitted[devi + 1].decode("utf-8")
                gw = splitted[2].decode("utf-8")
                if known_gateways and iface not in known_gateways:
                    return f"G: <span foreground='{unknown_color}'>{iface}</span>"
                return f"G: {iface}"
            except Exception:
                return "G: ?"

        while True:
            self.update(await get_gateway())
            await asyncio.sleep(refresh)

