"""
Tests for the syncthing module.

These tests avoid hitting a real Syncthing instance: pure logic (state
derivation, rendering, event application) is tested directly, and the network
paths are exercised with a small stub session.
"""

import asyncio
import pytest

from async3status.modules.syncthing import Syncthing


@pytest.fixture
def module(mock_bar):
    config = {
        "type": "syncthing",
        "apikey": "test-key",
        "format": "{icon} {pct}",
    }
    return Syncthing(mock_bar, config)


class TestStateDerivation:
    def test_idle_when_no_states_and_no_need(self, module):
        assert module._overall_state({"needBytes": 0}) == "idle"

    def test_syncing_from_completion_fallback(self, module):
        assert module._overall_state({"needBytes": 1234}) == "syncing"

    def test_error_takes_priority(self, module):
        module._folder_states = {"a": "idle", "b": "error", "c": "syncing"}
        assert module._overall_state({"needBytes": 0}) == "error"

    def test_syncing_over_scanning(self, module):
        module._folder_states = {"a": "scanning", "b": "syncing"}
        assert module._overall_state({"needBytes": 0}) == "syncing"

    def test_scanning(self, module):
        module._folder_states = {"a": "scanning"}
        assert module._overall_state({"needBytes": 0}) == "scanning"

    def test_idle_when_all_idle(self, module):
        module._folder_states = {"a": "idle", "b": "idle"}
        assert module._overall_state({"needBytes": 0}) == "idle"


class TestRender:
    def test_idle_render(self, module):
        text = module._render("idle", {"completion": 100})
        assert module.idle_icon in text
        assert "100%" in text

    def test_syncing_render_pct(self, module):
        text = module._render("syncing", {"completion": 87.4})
        assert module.syncing_icon in text
        assert "87%" in text

    def test_error_render_colored(self, module):
        text = module._render("error", None)
        assert "foreground='red'" in text
        assert module.error_icon in text

    def test_disconnected_render_colored(self, module):
        text = module._render("disconnected", None)
        assert "foreground='#aaaaaa'" in text
        assert module.disconnected_icon in text

    def test_idle_no_color_by_default(self, module):
        text = module._render("idle", {"completion": 100})
        assert "foreground" not in text

    def test_text_color_applied_to_idle(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "text_color": "#cccccc",
        })
        text = m._render("idle", {"completion": 100})
        assert "foreground='#cccccc'" in text

    def test_custom_format_fields(self, mock_bar):
        config = {
            "type": "syncthing",
            "apikey": "k",
            "format": "{state} {pct} {need}",
        }
        m = Syncthing(mock_bar, config)
        text = m._render("syncing", {"completion": 50, "needItems": 3})
        assert "syncing" in text
        assert "50%" in text
        assert "3 items" in text


class TestApplyEvents:
    def test_state_changed_updates_folder(self, module):
        events = [
            {"id": 5, "type": "StateChanged",
             "data": {"folder": "default", "from": "idle", "to": "syncing"}},
        ]
        refresh = module._apply_events(events)
        assert refresh is True
        assert module._folder_states["default"] == "syncing"
        assert module._last_id == 5

    def test_last_id_advances_to_max(self, module):
        events = [
            {"id": 2, "type": "Ping", "data": None},
            {"id": 7, "type": "Ping", "data": None},
        ]
        refresh = module._apply_events(events)
        assert refresh is False
        assert module._last_id == 7

    def test_device_events_trigger_refresh(self, module):
        events = [{"id": 9, "type": "DeviceConnected", "data": {}}]
        assert module._apply_events(events) is True
        assert module._last_id == 9


# --- Stub-session integration ---

class _StubResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class _StubSession:
    """Maps a request path to a canned payload.

    A route value is normally a ``(status, payload)`` tuple. To vary the
    response by the ``device`` query parameter (used by per-device completion),
    a route value may instead be a callable ``params -> (status, payload)``.
    """
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        for path, value in self.routes.items():
            if url.endswith(path):
                if callable(value):
                    status, payload = value(params or {})
                else:
                    status, payload = value
                return _StubResponse(status, payload)
        return _StubResponse(404, None)


class TestRequestIntegration:
    async def test_refresh_status_updates_block(self, module, mock_bar):
        session = _StubSession({
            "/rest/db/completion": (200, {"completion": 42.0, "needItems": 5}),
        })
        await module._refresh_status(session)
        assert "42%" in module.block["full_text"]
        # API key header was sent.
        assert session.calls[-1][2]["X-API-Key"] == "test-key"

    async def test_refresh_status_disconnected_on_error(self, module):
        session = _StubSession({})  # 404 for everything
        await module._refresh_status(session)
        # completion fetch failed -> falls back to idle (no need data)
        assert module.block["full_text"]  # something was rendered

    async def test_auth_failure_clears_key(self, module):
        module._api_key = "cached"
        session = _StubSession({"/rest/db/completion": (401, None)})
        with pytest.raises(Exception):
            await module._request(session, "/rest/db/completion")
        assert module._api_key is None

    async def test_prime_last_id(self, module):
        session = _StubSession({
            "/rest/events": (200, [{"id": 100, "type": "Ping"}]),
        })
        await module._prime_last_id(session)
        assert module._last_id == 100


class TestApiKey:
    async def test_apikey_from_command(self, mock_bar):
        config = {
            "type": "syncthing",
            "apikey_command": "printf 'secret-from-cmd'",
        }
        m = Syncthing(mock_bar, config)
        key = await m._get_api_key()
        assert key == "secret-from-cmd"

    async def test_apikey_plain(self, module):
        key = await module._get_api_key()
        assert key == "test-key"

    async def test_missing_apikey_raises(self, mock_bar):
        m = Syncthing(mock_bar, {"type": "syncthing"})
        with pytest.raises(RuntimeError):
            await m._get_api_key()


class TestIPC:
    async def test_ipc_update_sets_refresh_event(self, module):
        assert not module._refresh_event.is_set()
        await module.handle_ipc("update")
        assert module._refresh_event.is_set()

    async def test_on_wake_sets_refresh_event(self, module):
        await module.on_wake()
        assert module._refresh_event.is_set()


# --- Per-device tests ---

@pytest.fixture
def pd_module(mock_bar):
    config = {
        "type": "syncthing",
        "apikey": "test-key",
        "per_device": True,
        "format": "{icon} {pct}",
    }
    return Syncthing(mock_bar, config)


class TestFetchDevices:
    async def test_excludes_local_device(self, pd_module):
        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "LOCAL", "name": "this-machine"},
                {"deviceID": "NAS-AAA", "name": "nas"},
                {"deviceID": "PHONE-BBB", "name": "phone"},
            ]),
        })
        await pd_module._fetch_devices(session)
        assert pd_module._local_id == "LOCAL"
        assert pd_module._device_names == {"NAS-AAA": "nas", "PHONE-BBB": "phone"}

    async def test_empty_name_falls_back_to_short_id(self, pd_module):
        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "ABCDEFG-1234", "name": ""},
            ]),
        })
        await pd_module._fetch_devices(session)
        assert pd_module._device_names == {"ABCDEFG-1234": "ABCDEFG"}

    async def test_devices_filter_by_name(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "devices": ["graphit", "pinkbox"],
        })
        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "G-1", "name": "graphit"},
                {"deviceID": "P-1", "name": "pinkbox"},
                {"deviceID": "X-1", "name": "other"},
            ]),
        })
        await m._fetch_devices(session)
        assert m._device_names == {"G-1": "graphit", "P-1": "pinkbox"}

    async def test_devices_filter_by_id(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "devices": ["G-1"],
        })
        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "G-1", "name": "graphit"},
                {"deviceID": "P-1", "name": "pinkbox"},
            ]),
        })
        await m._fetch_devices(session)
        assert m._device_names == {"G-1": "graphit"}


class TestRenderDevices:
    def test_connected_shows_pct_including_100(self, pd_module):
        devices = [
            {"id": "A", "name": "nas", "connected": True, "paused": False, "pct": 100},
        ]
        text = pd_module._render_devices(devices)
        assert "nas" in text
        assert "100%" in text
        assert "foreground='#3cc63c'" in text
        assert pd_module.device_connected_icon in text

    def test_disconnected_no_pct(self, pd_module):
        devices = [
            {"id": "A", "name": "phone", "connected": False, "paused": False, "pct": None},
        ]
        text = pd_module._render_devices(devices)
        assert "phone" in text
        assert "%" not in text
        assert "foreground='#aaaaaa'" in text
        assert pd_module.device_disconnected_icon in text

    def test_paused_uses_paused_icon_no_pct(self, pd_module):
        devices = [
            {"id": "A", "name": "laptop", "connected": False, "paused": True, "pct": None},
        ]
        text = pd_module._render_devices(devices)
        assert "laptop" in text
        assert "%" not in text
        assert pd_module.device_paused_icon in text

    def test_multiple_joined_by_separator(self, pd_module):
        pd_module.device_separator = " | "
        devices = [
            {"id": "A", "name": "aaa", "connected": True, "paused": False, "pct": 50},
            {"id": "B", "name": "bbb", "connected": False, "paused": False, "pct": None},
        ]
        text = pd_module._render_devices(devices)
        assert " | " in text


class TestFetchPerDevice:
    async def test_only_connected_devices_get_completion(self, pd_module):
        completion_calls = []

        def completion_route(params):
            completion_calls.append(params.get("device"))
            pct = {"NAS-AAA": 73, "PHONE-BBB": 100}.get(params.get("device"), 0)
            return (200, {"completion": pct})

        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "NAS-AAA", "name": "nas"},
                {"deviceID": "PHONE-BBB", "name": "phone"},
            ]),
            "/rest/system/connections": (200, {"connections": {
                "NAS-AAA": {"connected": True, "paused": False},
                "PHONE-BBB": {"connected": False, "paused": False},
            }}),
            "/rest/db/completion": completion_route,
        })

        devices = await pd_module._fetch_per_device(session)
        # Sorted by name: nas, phone
        assert [d["name"] for d in devices] == ["nas", "phone"]
        nas = next(d for d in devices if d["name"] == "nas")
        phone = next(d for d in devices if d["name"] == "phone")
        assert nas["connected"] and nas["pct"] == 73
        assert not phone["connected"] and phone["pct"] is None
        # Completion fetched only for the connected device.
        assert completion_calls == ["NAS-AAA"]

    async def test_refresh_status_appends_device_section(self, pd_module):
        session = _StubSession({
            "/rest/db/completion": lambda params: (
                (200, {"completion": 90}) if params.get("device")
                else (200, {"completion": 100, "needItems": 0})
            ),
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "NAS-AAA", "name": "nas"},
            ]),
            "/rest/system/connections": (200, {"connections": {
                "NAS-AAA": {"connected": True, "paused": False},
            }}),
        })
        await pd_module._refresh_status(session)
        text = pd_module.block["full_text"]
        assert "nas" in text
        assert "90%" in text

    async def test_per_device_failure_degrades_gracefully(self, pd_module):
        # Overall completion works; device endpoints 404.
        session = _StubSession({
            "/rest/db/completion": lambda params: (
                (404, None) if params.get("device")
                else (200, {"completion": 100})
            ),
            "/rest/system/status": (404, None),
        })
        await pd_module._refresh_status(session)
        # Still renders the overall status without raising.
        assert pd_module.block["full_text"]


class TestConfigSavedEvent:
    def test_config_saved_clears_device_names(self, pd_module):
        pd_module._device_names = {"OLD": "old"}
        refresh = pd_module._apply_events([
            {"id": 1, "type": "ConfigSaved", "data": None},
        ])
        assert refresh is True
        assert pd_module._device_names == {}

    def test_device_paused_triggers_refresh(self, pd_module):
        assert pd_module._apply_events([
            {"id": 2, "type": "DevicePaused", "data": {"device": "X"}},
        ]) is True


class TestShowPercentage:
    def test_overall_pct_hidden(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k",
            "show_percentage": False, "format": "{icon} {pct}",
        })
        text = m._render("syncing", {"completion": 50})
        assert "%" not in text

    def test_overall_pct_shown_by_default(self, module):
        text = module._render("syncing", {"completion": 50})
        assert "50%" in text


class TestShowDevicePercentage:
    def _dev(self, pct):
        return {"id": "A", "name": "nas", "connected": True, "paused": False,
                "pct": pct, "conn_type": "tcp-client", "last_seen": None}

    def test_hidden_when_false(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "show_device_percentage": False,
        })
        text = m._render_devices([self._dev(42)])
        assert "%" not in text

    def test_incomplete_hides_at_100(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "show_device_percentage": "incomplete",
        })
        assert "%" not in m._render_devices([self._dev(100)])
        assert "73%" in m._render_devices([self._dev(73)])


class TestConnectionType:
    def test_short_type(self, pd_module):
        assert pd_module._short_type("tcp-client") == "tcp"
        assert pd_module._short_type("relay-server") == "relay"
        assert pd_module._short_type("quic-client") == "quic"
        assert pd_module._short_type("") == ""

    def test_type_shown_in_device_format(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "device_format": "{icon}{name} {type} {pct}",
        })
        dev = {"id": "A", "name": "nas", "connected": True, "paused": False,
               "pct": 100, "conn_type": "relay-client", "last_seen": None}
        text = m._render_devices([dev])
        assert "relay" in text

    def test_custom_type_labels(self, mock_bar):
        m = Syncthing(mock_bar, {
            "type": "syncthing", "apikey": "k", "per_device": True,
            "device_format": "{name} {type}",
            "type_labels": {"tcp": "direct", "relay": "via relay"},
        })
        dev = {"id": "A", "name": "nas", "connected": True, "paused": False,
               "pct": 100, "conn_type": "tcp-client", "last_seen": None}
        assert "direct" in m._render_devices([dev])


class TestLastSeen:
    def test_format_last_seen(self, pd_module):
        out = pd_module._format_last_seen("2026-06-19T12:30:00+00:00")
        # Rendered with default "%Y-%m-%dT%H:%M" in local time.
        assert out.startswith("2026-06-19T") or out.startswith("2026-06-")

    def test_never_seen_zero_time(self, pd_module):
        assert pd_module._format_last_seen("0001-01-01T00:00:00Z") == ""

    def test_missing_last_seen(self, pd_module):
        assert pd_module._format_last_seen(None) == ""
        assert pd_module._format_last_seen("") == ""

    def test_invalid_last_seen(self, pd_module):
        assert pd_module._format_last_seen("not-a-date") == ""

    async def test_last_seen_from_stats_endpoint(self, pd_module):
        session = _StubSession({
            "/rest/system/status": (200, {"myID": "LOCAL"}),
            "/rest/config/devices": (200, [
                {"deviceID": "NAS-AAA", "name": "nas"},
            ]),
            "/rest/system/connections": (200, {"connections": {
                "NAS-AAA": {"connected": True, "paused": False, "type": "tcp-client"},
            }}),
            "/rest/stats/device": (200, {
                "NAS-AAA": {"lastSeen": "2026-06-19T12:00:00+00:00"},
            }),
            "/rest/db/completion": lambda params: (200, {"completion": 100}),
        })
        devices = await pd_module._fetch_per_device(session)
        assert devices[0]["last_seen"] == "2026-06-19T12:00:00+00:00"
        assert devices[0]["conn_type"] == "tcp-client"
