import asyncio
import os
from base import Module
import time


class Battery(Module):
    """
    Battery monitoring module.

    Config example:

    modules:
      - type: battery
        battery_path: "/sys/class/power_supply/BAT0"
        refresh: 60
        background_red_on: 10
        throttle_on: 10
        throttle_state: "power"
        charge_state: "normal"
        normal_state: "normal"
        display_current: false
        send_notify_on: 10
        notification_icon: "/usr/share/icons/gnome/24x24/status/battery-low.png"
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

    async def run(self):
        cfg = self.config
        battery = cfg.get("battery_path", "/sys/class/power_supply/BAT0")
        refresh = cfg.get("refresh", 60)
        background_red_on = cfg.get("background_red_on", 10)
        throttle_on = cfg.get("throttle_on", 10)
        throttle_state = cfg.get("throttle_state", "power")
        charge_state = cfg.get("charge_state", "normal")
        normal_state = cfg.get("normal_state", "normal")
        icon_plug = cfg.get("icon_plug", "🔌")
        icon_battery = cfg.get("icon_battery", "🔋")
        icon_unknown = cfg.get("icon_unknown", "?")
        display_current = cfg.get("display_current", False)
        send_notify_on = cfg.get("send_notify_on", 10)
        notification_icon = cfg.get("notification_icon", "/usr/share/icons/gnome/24x24/status/battery-low.png")
        colors = cfg.get("text_colors", {
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

        def read(node):
            try:
                with open(os.path.join(battery, node), "r") as f:
                    return f.read().strip()
            except:
                return ""

        def get_text_color(percent, discharging):
            if percent <= background_red_on or not discharging:
                return "#FFFFFF"
            for threshold in [10,20,30,40,50,60,70,80,90]:
                if percent <= threshold:
                    return colors.get(f"color_{threshold}", "#FFFFFF")
            return colors.get("color_100", "#FFFFFF")

        async def do_check():
            state = read("status")
            discharging = state == "Discharging"
            icon = icon_unknown
            if discharging:
                icon = icon_battery
            elif state in ["Charging", "Full", "Not charging"]:
                icon = icon_plug
            try:
                percentleft = int(read("capacity"))
            except:
                percentleft = 0

            text = f"{icon} <span foreground='{get_text_color(percentleft, discharging)}'>{percentleft}%</span>"
            if percentleft <= background_red_on and discharging:
                text = f"<span background='red'>{text}</span>"

            if display_current:
                try:
                    current = int(read("current_now"))
                    if current > 0.1e6:
                        text += f", {current/1e6:.2f}A"
                except:
                    pass
            return percentleft, discharging, state, text

        async def run_command(*args):
            proc = await asyncio.create_subprocess_exec(*args)
            await proc.wait()

        # Start acpid
        await run_command("sudo", "systemctl", "start", "acpid")

        # Connect to acpid socket asynchronously
        success = False
        for _ in range(100):
            try:
                reader, writer = await asyncio.open_unix_connection("/var/run/acpid.socket")
                success = True
                break
            except:
                await asyncio.sleep(0.1)

        if not success:
            self.update("FAILED TO CONNECT TO ACPID")
            return

        # Main loop: event-driven with fallback periodic refresh
        first = True
        cur_state = ""
        has_send_notify = False
        while True:
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
            if not first:
                timeout = refresh
                while await wait_for_battery_event(timeout):
                    timeout = 1  # debounce if multiple events come in close succession
            first = False

            # Update text
            percentleft, discharging, state, text = await do_check()
            self.update(text)

            # Handle performance throttling
            if discharging:
                if percentleft <= throttle_on and cur_state != throttle_state:
                    await run_command("sudo", "x86_energy_perf_policy", "-all", throttle_state)
                    cur_state = throttle_state
                elif cur_state != normal_state:
                    await run_command("sudo", "x86_energy_perf_policy", "-all", normal_state)
                    cur_state = normal_state
            elif cur_state != charge_state:
                await run_command("sudo", "x86_energy_perf_policy", "-all", charge_state)
                cur_state = charge_state

            # Notifications
            if percentleft > send_notify_on or not discharging:
                has_send_notify = False
            elif percentleft <= send_notify_on and discharging and not has_send_notify:
                await run_command(
                    "notify-send",
                    "-i", notification_icon,
                    "-a", "SYS",
                    "-u", "critical",
                    f"BAT < {send_notify_on}%"
                )
                has_send_notify = True

