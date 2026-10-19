import asyncio
import os
import time

from async3status.base import Module


class Battery(Module):
    """
    Battery monitoring module.

    Config example:

    modules:
      - type: battery
        battery_path: "/sys/class/power_supply/BAT0"
        refresh: 60
        background_red_on: 10
        display_current: false
        text_colors:
          color_10: "#FF0000"
          color_20: "#FF3300"
          color_30: "#FF6600"
          color_40: "#FF9900"
          color_50: "#FFCC00"
          color_60: "#FFFF00"
          color_70: "#FFFF33"
          color_80: "#FFFF66"
          color_90: "#FFFFFF"
          color_100: "#FFFFFF"
    """

    def __post_init__(self):
        cfg = self.config
        self.battery_path = cfg.get("battery_path", "/sys/class/power_supply/BAT0")
        self.refresh = cfg.get("refresh", 60)
        self.background_red_on = cfg.get("background_red_on", 10)
        self.icon_plug = cfg.get("icon_plug", "🔌")
        self.icon_battery = cfg.get("icon_battery", "🔋")
        self.icon_unknown = cfg.get("icon_unknown", "?")
        self.display_current = cfg.get("display_current", False)
        self.colors = cfg.get("text_colors", {
            "color_10": "#FF0000",
            "color_20": "#FF3300",
            "color_30": "#FF6600",
            "color_40": "#FF9900",
            "color_50": "#FFCC00",
            "color_60": "#FFFF00",
            "color_70": "#FFFF33",
            "color_80": "#FFFF66",
            "color_90": "#FFFFFF",
            "color_100": "#FFFFFF"
        })

    def read(self, node):
        try:
            with open(os.path.join(self.battery_path, node), "r") as f:
                return f.read().strip()
        except Exception:
            return ""

    def get_text_color(self, percent, discharging):
        if percent <= self.background_red_on or not discharging:
            return "#FFFFFF"
        for threshold in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
            if percent <= threshold:
                return self.colors.get(f"color_{threshold}", "#FFFFFF")
        return self.colors.get("color_100", "#FFFFFF")

    async def do_check(self):
        state = self.read("status")
        discharging = state == "Discharging"
        icon = self.icon_unknown
        if discharging:
            icon = self.icon_battery
        elif state in ["Charging", "Full", "Not charging"]:
            icon = self.icon_plug
        try:
            percentleft = int(self.read("capacity"))
        except Exception:
            percentleft = 0

        text = f"{icon} <span foreground='{self.get_text_color(percentleft, discharging)}'>{percentleft}%</span>"
        if percentleft <= self.background_red_on and discharging:
            text = f"<span background='red'>{text}</span>"

        if self.display_current:
            try:
                current = int(self.read("current_now"))
                if current > 0.1e6:
                    text += f", {current/1e6:.2f}A"
            except Exception:
                pass
        return text

    async def run_command(self, *args):
        proc = await asyncio.create_subprocess_exec(*args)
        await proc.wait()

    async def on_wake(self):
        """Refresh battery state immediately after waking from suspend."""
        self.update(await self.do_check())

    async def run(self):
        # Start acpid
        await self.run_command("sudo", "systemctl", "start", "acpid")

        # Connect to acpid socket asynchronously
        success = False
        for _ in range(100):
            try:
                reader, writer = await asyncio.open_unix_connection("/var/run/acpid.socket")
                success = True
                break
            except Exception:
                await asyncio.sleep(0.1)

        if not success:
            self.update("FAILED TO CONNECT TO ACPID")
            return

        async def wait_for_battery_event(timeout):
            try:
                while timeout > 0:
                    start = time.time()
                    data = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                    timeout -= time.time() - start
                    if b"battery" in data:
                        return True
                return False
            except asyncio.TimeoutError:
                return False

        # Main loop: event-driven with fallback periodic refresh
        first = True
        while True:
            if not first:
                timeout = self.refresh
                while await wait_for_battery_event(timeout):
                    timeout = 1  # debounce if multiple events come in close succession
            first = False

            # Update text
            self.update(await self.do_check())
