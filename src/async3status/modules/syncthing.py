import asyncio
from datetime import datetime, timezone

import aiohttp

from async3status.base import Module


class Syncthing(Module):
    """
    Displays the overall Syncthing sync state and aggregate completion.

    Driven by Syncthing's long-poll Event API (``GET /rest/events``), which
    blocks until something actually changes, so the module waits efficiently
    for changes instead of busy-polling.

    The API key is kept out of the config file: ``apikey_command`` is run and
    its stdout is used as the ``X-API-Key`` header. A plain ``apikey`` is also
    accepted as a fallback.

    Configuration:

    - address (str): Base URL of the Syncthing GUI/API.
        Default: "http://127.0.0.1:8384"
    - apikey_command (str | None): Shell command whose stdout is the API key.
    - apikey (str | None): API key in plaintext (discouraged; use the command).
    - timeout (int): Long-poll timeout in seconds for the events request.
        Default: 60
    - format (str): Format string. Available fields: icon, state, pct, need.
        Default: "{icon} {pct}"
    - show_percentage (bool): Show the overall completion percentage.
        Default: True
    - idle_icon / syncing_icon / scanning_icon / error_icon /
      disconnected_icon (str): Icons for each state.
    - text_color (str | None): Pango color for the overall status text
        (idle/syncing/scanning). Default: None (theme default)
    - error_color / disconnected_color (str): Pango colors for those states.
    - per_device (bool): Append per-device status (name, connection icon and
        completion %) for every configured remote device. Default: False
    - devices (list[str] | None): Only show these devices (matched by name or
        device id). Default: None (all remote devices)
    - device_format (str): Per-device entry format. Fields: icon, name, pct,
        type, last_seen, state. Default: "{icon}{name} {pct}"
    - device_separator (str): String joining device entries. Default: " "
    - device_connected_icon / device_disconnected_icon /
      device_paused_icon (str): Per-device state icons.
    - connected_color (str): Pango color for connected devices.
    - show_device_percentage (bool | "incomplete"): Show per-device completion.
        True shows always; "incomplete" only shows when below 100%; False hides.
        Default: True
    - last_seen_format (str): strftime format for the {last_seen} field.
        Default: "%Y-%m-%dT%H:%M"
    - type_labels (dict): Map of connection type base (tcp/relay/quic) to a
        short label used by the {type} field.

    Example:

        modules:
          - type: syncthing
            apikey_command: "pass show syncthing/apikey"
            format: "{icon} {pct}"
            per_device: true

    Force a manual refresh via IPC:

        echo "module syncthing update" | socat - UNIX-CONNECT:/path/to/async3status.sock
    """

    def __post_init__(self):
        self.address = self.config.get("address", "http://127.0.0.1:8384").rstrip("/")
        self.apikey_command = self.config.get("apikey_command")
        self.apikey = self.config.get("apikey")
        self.timeout = self.config.get("timeout", 60)
        self.format = self.config.get("format", "{icon} {pct}")
        # Show the overall completion percentage in the status text.
        self.show_percentage = self.config.get("show_percentage", True)

        self.idle_icon = self.config.get("idle_icon", "\U0001F504")        # 🔄
        self.syncing_icon = self.config.get("syncing_icon", "\U0001F501")  # 🔁
        self.scanning_icon = self.config.get("scanning_icon", "\U0001F50D")  # 🔍
        self.error_icon = self.config.get("error_icon", "\u26A0")          # ⚠
        self.disconnected_icon = self.config.get("disconnected_icon", "\u274C")  # ❌
        # Base text color applied to the overall status (idle/syncing/scanning).
        self.text_color = self.config.get("text_color", None)
        self.error_color = self.config.get("error_color", "red")
        self.disconnected_color = self.config.get("disconnected_color", "#aaaaaa")

        self.per_device = self.config.get("per_device", False)
        self.device_format = self.config.get("device_format", "{icon}{name} {pct}")
        self.device_separator = self.config.get("device_separator", " ")
        self.device_connected_icon = self.config.get("device_connected_icon", "\u25CF")  # ●
        self.device_disconnected_icon = self.config.get("device_disconnected_icon", "\u25CB")  # ○
        self.device_paused_icon = self.config.get("device_paused_icon", "\u23F8")  # ⏸
        self.connected_color = self.config.get("connected_color", "#3cc63c")
        # Show per-device completion percentage. If "incomplete", only show it
        # when the device is below 100%.
        self.show_device_percentage = self.config.get("show_device_percentage", True)
        # Format for the last-seen timestamp ({last_seen} field in device_format).
        self.last_seen_format = self.config.get("last_seen_format", "%Y-%m-%dT%H:%M")
        # Short labels for connection types ({type} field in device_format).
        self.type_labels = self.config.get("type_labels", {
            "tcp": "tcp",
            "relay": "relay",
            "quic": "quic",
        })
        # Optional filter: only show these devices (by name or id). None = all.
        devices_filter = self.config.get("devices", None)
        self.devices_filter = set(devices_filter) if devices_filter else None

        self._api_key = None
        self._folder_states = {}  # folder id -> "idle"/"scanning"/"syncing"/"error"
        self._last_id = 0
        self._refresh_event = asyncio.Event()  # set by IPC/on_wake to force refresh
        self._device_names = {}  # remote device id -> friendly name
        self._local_id = None  # this device's own id, to exclude it

    async def _get_api_key(self, force=False):
        """Resolve the API key, running apikey_command if configured."""
        if self._api_key is not None and not force:
            return self._api_key
        if self.apikey_command:
            proc = await asyncio.create_subprocess_shell(
                self.apikey_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError("apikey_command failed")
            self._api_key = out.decode().strip()
        elif self.apikey:
            self._api_key = self.apikey
        else:
            raise RuntimeError("no apikey or apikey_command configured")
        return self._api_key

    async def _request(self, session, path, params=None):
        """GET a REST endpoint and return parsed JSON."""
        key = await self._get_api_key()
        headers = {"X-API-Key": key}
        url = f"{self.address}{path}"
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 401 or resp.status == 403:
                # Stale key: force re-fetch on next attempt.
                self._api_key = None
                raise RuntimeError(f"auth failed ({resp.status})")
            resp.raise_for_status()
            return await resp.json()

    def _overall_state(self, completion):
        """Derive overall state from folder states and completion snapshot."""
        states = set(self._folder_states.values())
        if "error" in states:
            return "error"
        if "syncing" in states:
            return "syncing"
        if "scanning" in states:
            return "scanning"
        if states:
            return "idle"
        # No state events yet: fall back to completion snapshot.
        if completion and completion.get("needBytes", 0) > 0:
            return "syncing"
        return "idle"

    def _render(self, state, completion):
        """Build the display text/block for the given state."""
        icons = {
            "idle": self.idle_icon,
            "syncing": self.syncing_icon,
            "scanning": self.scanning_icon,
            "error": self.error_icon,
            "disconnected": self.disconnected_icon,
        }
        icon = icons.get(state, self.disconnected_icon)

        pct = ""
        need = ""
        if completion is not None:
            if self.show_percentage:
                pct = f"{int(round(completion.get('completion', 100)))}%"
            need_items = completion.get("needItems", 0)
            if need_items:
                need = f"{need_items} items"

        text = self.format.format(icon=icon, state=state, pct=pct, need=need).strip()

        if state == "error":
            color = self.error_color
        elif state == "disconnected":
            color = self.disconnected_color
        else:
            color = self.text_color
        if color:
            return f"<span foreground='{color}'>{text}</span>"
        return text

    async def _fetch_devices(self, session, force=False):
        """Populate the local id and remote device-name map (cached)."""
        if self._local_id is None or force:
            status = await self._request(session, "/rest/system/status")
            self._local_id = status.get("myID")
        if not self._device_names or force:
            devices = await self._request(session, "/rest/config/devices")
            names = {}
            for dev in devices:
                dev_id = dev.get("deviceID")
                if not dev_id or dev_id == self._local_id:
                    continue
                name = dev.get("name") or dev_id.split("-")[0]
                # Apply the optional filter (match by name or device id).
                if self.devices_filter is not None and (
                    name not in self.devices_filter
                    and dev_id not in self.devices_filter
                ):
                    continue
                names[dev_id] = name
            self._device_names = names

    async def _device_completion(self, session, dev_id):
        """Per-device completion percentage, or None on failure."""
        try:
            data = await self._request(
                session, "/rest/db/completion", params={"device": dev_id}
            )
            return int(round(data.get("completion", 100)))
        except Exception:
            return None

    def _short_type(self, conn_type):
        """Shorten a connection type like 'tcp-client' to a configured label."""
        if not conn_type:
            return ""
        base = conn_type.split("-", 1)[0]  # tcp, relay, quic
        return self.type_labels.get(base, base)

    def _format_last_seen(self, last_seen):
        """Format an ISO last-seen timestamp, or '' if unavailable/zero."""
        if not last_seen:
            return ""
        # Syncthing uses RFC3339; "never seen" is the year-1 zero time.
        if last_seen.startswith("0001-01-01"):
            return ""
        dt = self._parse_rfc3339(last_seen)
        if dt is None:
            return ""
        return dt.astimezone().strftime(self.last_seen_format)

    @staticmethod
    def _parse_rfc3339(value):
        """Parse an RFC3339 timestamp robustly across Python versions.

        Handles a trailing 'Z' and sub-second precision beyond 6 digits, which
        datetime.fromisoformat rejects on Python < 3.11.
        """
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # Truncate fractional seconds to microseconds (6 digits).
        dot = s.find(".")
        if dot != -1:
            end = dot + 1
            while end < len(s) and s[end].isdigit():
                end += 1
            frac = s[dot + 1:end][:6]
            s = s[:dot + 1] + frac + s[end:]
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    async def _fetch_per_device(self, session):
        """Return a name-sorted list of per-device status dicts."""
        await self._fetch_devices(session)
        connections = await self._request(session, "/rest/system/connections")
        conn_map = connections.get("connections", {})
        try:
            stats = await self._request(session, "/rest/stats/device")
        except Exception:
            stats = {}

        devices = []
        connected_ids = []
        for dev_id, name in self._device_names.items():
            info = conn_map.get(dev_id, {})
            connected = bool(info.get("connected"))
            paused = bool(info.get("paused"))
            last_seen = (stats.get(dev_id) or {}).get("lastSeen")
            devices.append({
                "id": dev_id,
                "name": name,
                "connected": connected,
                "paused": paused,
                "conn_type": info.get("type", ""),
                "last_seen": last_seen,
                "pct": None,
            })
            if connected and not paused:
                connected_ids.append(dev_id)

        # Fetch completion only for connected devices, concurrently.
        if connected_ids:
            results = await asyncio.gather(
                *(self._device_completion(session, d) for d in connected_ids)
            )
            pct_by_id = dict(zip(connected_ids, results))
            for dev in devices:
                if dev["id"] in pct_by_id:
                    dev["pct"] = pct_by_id[dev["id"]]

        devices.sort(key=lambda d: d["name"].lower())
        return devices

    def _device_pct_text(self, dev):
        """Completion text for a connected device, honoring show options."""
        if dev["pct"] is None:
            return ""
        if not self.show_device_percentage:
            return ""
        if self.show_device_percentage == "incomplete" and dev["pct"] >= 100:
            return ""
        return f"{dev['pct']}%"

    def _render_devices(self, devices):
        """Render the per-device section as a single string."""
        entries = []
        for dev in devices:
            if dev["paused"]:
                icon = self.device_paused_icon
                color = self.disconnected_color
                pct = ""
                conn_type = ""
            elif dev["connected"]:
                icon = self.device_connected_icon
                color = self.connected_color
                pct = self._device_pct_text(dev)
                conn_type = self._short_type(dev.get("conn_type", ""))
            else:
                # Disconnected: icon + name only, no completion / type.
                icon = self.device_disconnected_icon
                color = self.disconnected_color
                pct = ""
                conn_type = ""

            text = self.device_format.format(
                icon=icon,
                name=dev["name"],
                pct=pct,
                type=conn_type,
                last_seen=self._format_last_seen(dev.get("last_seen")),
                state="paused" if dev["paused"]
                else "connected" if dev["connected"]
                else "disconnected",
            )
            # Collapse any double spaces left by empty fields, then trim.
            text = " ".join(text.split())
            entries.append(f"<span foreground='{color}'>{text}</span>")
        return self.device_separator.join(entries)

    async def _refresh_status(self, session):
        """Fetch a completion snapshot and update the display."""
        try:
            completion = await self._request(session, "/rest/db/completion")
        except Exception:
            completion = None
        state = self._overall_state(completion)
        text = self._render(state, completion)

        if self.per_device:
            try:
                devices = await self._fetch_per_device(session)
                device_text = self._render_devices(devices)
                if device_text:
                    text = f"{text} {device_text}"
            except Exception:
                pass  # Degrade gracefully to overall status only.

        self.update(text)

    def _apply_events(self, events):
        """Update internal state from a batch of events. Returns True if the
        display should be refreshed."""
        refresh = False
        for ev in events:
            ev_id = ev.get("id", 0)
            if ev_id > self._last_id:
                self._last_id = ev_id
            if ev.get("type") == "StateChanged":
                data = ev.get("data") or {}
                folder = data.get("folder")
                to = data.get("to")
                if folder and to:
                    self._folder_states[folder] = to
                    refresh = True
            elif ev.get("type") == "ConfigSaved":
                # Device names/list may have changed; force a re-fetch.
                self._device_names = {}
                refresh = True
            elif ev.get("type") in (
                "FolderSummary",
                "FolderCompletion",
                "DeviceConnected",
                "DeviceDisconnected",
                "DevicePaused",
                "DeviceResumed",
            ):
                refresh = True
        return refresh

    async def _prime_last_id(self, session):
        """Get the most recent event ID so we only stream new events."""
        events = await self._request(
            session, "/rest/events", params={"since": 0, "limit": 1}
        )
        if events:
            self._last_id = max(ev.get("id", 0) for ev in events)

    async def _consume_events(self, session):
        """Long-poll the event stream, refreshing the display on changes.

        Races the long-poll against a forced-refresh event (set by IPC or
        on_wake) so manual refreshes take effect promptly rather than waiting
        out the long-poll timeout.
        """
        while True:
            params = {"since": self._last_id, "timeout": self.timeout}
            events_task = asyncio.ensure_future(
                self._request(session, "/rest/events", params=params)
            )
            refresh_task = asyncio.ensure_future(self._refresh_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {events_task, refresh_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                events_task.cancel()
                refresh_task.cancel()
                raise

            if refresh_task in done:
                self._refresh_event.clear()
                await self._refresh_status(session)
            else:
                refresh_task.cancel()

            if events_task in done:
                try:
                    events = events_task.result()
                except asyncio.TimeoutError:
                    # Long-poll returned nothing new within the client timeout.
                    continue
                if self._apply_events(events):
                    await self._refresh_status(session)
            else:
                events_task.cancel()

    async def run(self):
        backoff = 1
        while True:
            # Client timeout must exceed the server long-poll timeout.
            client_timeout = aiohttp.ClientTimeout(total=self.timeout + 15)
            try:
                async with aiohttp.ClientSession(timeout=client_timeout) as session:
                    await self._get_api_key()
                    await self._prime_last_id(session)
                    await self._refresh_status(session)
                    backoff = 1  # connected successfully
                    await self._consume_events(session)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.update(self._render("disconnected", None))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def on_wake(self):
        """Force a refresh after waking from suspend."""
        self._refresh_event.set()

    async def handle_ipc(self, command: str):
        if command == "update":
            self._refresh_event.set()
