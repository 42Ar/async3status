import asyncio
import threading
import pulsectl
from base import Module

class Volume(Module):
    """
    PulseAudio volume module using pulsectl.

    Example config:

    modules:
      - type: volume
        icon: "🔊"
        icon_muted: "🔇"
        muted_color: "gray"
    """

    async def run(self):
        cfg = self.config
        icon = cfg.get("icon", "🔊")
        icon_muted = cfg.get("icon_muted", "🔇")
        muted_color = cfg.get("muted_color", "gray")

        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def pulse_worker():
            pulse = pulsectl.Pulse("async3status_volume")
            def callback(ev):
                loop.call_soon_threadsafe(event_queue.put_nowait, True)
            pulse.event_mask_set("sink", "server")
            pulse.event_callback_set(callback)
            try:
                pulse.event_listen()
            except Exception:
                pass

        threading.Thread(target=pulse_worker, daemon=True).start()

        # main loop
        pulse = pulsectl.Pulse("async3status_volume")
        first = True
        while True:
            if not first:
                await event_queue.get()  # wait for event
            first = False

            try:
                default_sink_name = pulse.server_info().default_sink_name
                sink = pulse.get_sink_by_name(default_sink_name)
                vol = int(round(sink.volume.value_flat * 100))
                text = f"{icon_muted} <span foreground='{muted_color}'>{vol}%</span>" if sink.mute else f"{icon} {vol}%"
            except Exception:
                text = "<span foreground='red'>error</span>"
            self.update(text)

