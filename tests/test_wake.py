"""
Tests for the wake event system.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from modules.clock import Clock
from bar import Bar


class TestClockOnWake:
    """Tests for Clock module on_wake functionality."""

    @pytest.fixture
    def clock_module(self, mock_bar):
        config = {"type": "clock", "format": "%H:%M:%S"}
        return Clock(mock_bar, config)

    def test_clock_post_init_sets_format(self, clock_module):
        """Test that __post_init__ sets fmt and interval."""
        assert clock_module.fmt == "%H:%M:%S"
        assert clock_module.interval == 1  # Seconds format -> 1 second interval

    def test_clock_post_init_minute_format(self, mock_bar):
        """Test that minute format sets correct interval."""
        config = {"type": "clock", "format": "%H:%M"}
        clock = Clock(mock_bar, config)
        assert clock.interval == 60  # Minute format -> 60 second interval

    async def test_clock_on_wake_updates_time(self, clock_module, mock_bar):
        """Test that on_wake() updates the clock display."""
        await clock_module.on_wake()

        assert clock_module.block["full_text"] is not None
        assert ":" in clock_module.block["full_text"]  # Time format contains colons
        mock_bar.update_event.is_set()


class TestWakeListenerImportError:
    """Tests for wake listener when dbus-fast is not installed."""

    async def test_wake_listener_no_dbus_fast(self, mock_bar):
        """Test that missing dbus-fast shows warning in status bar."""
        # Create a minimal bar instance
        with patch.object(Bar, '__init__', lambda self, path: None):
            bar = Bar.__new__(Bar)
            bar.modules = []
            bar.update_event = asyncio.Event()

        # Mock the import to fail
        with patch.dict('sys.modules', {'dbus_fast': None, 'dbus_fast.aio': None}):
            # Force ImportError by patching the import mechanism
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def mock_import(name, *args, **kwargs):
                if name.startswith('dbus_fast'):
                    raise ImportError("No module named 'dbus_fast'")
                return original_import(name, *args, **kwargs)

            with patch('builtins.__import__', mock_import):
                # Run wake_listener briefly
                task = asyncio.create_task(bar.wake_listener())
                await asyncio.sleep(0.1)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Check that a warning module was added
        assert len(bar.modules) == 1
        assert "no dbus-fast" in bar.modules[0].block.get("full_text", "")


class TestWakeListenerDBusError:
    """Tests for wake listener when D-Bus connection fails."""

    async def test_wake_listener_dbus_connection_error(self):
        """Test that D-Bus connection error shows error in status bar."""
        # Create a minimal bar instance
        with patch.object(Bar, '__init__', lambda self, path: None):
            bar = Bar.__new__(Bar)
            bar.modules = []
            bar.update_event = asyncio.Event()

        # Mock dbus_fast to raise an error on connect
        mock_bus = AsyncMock()
        mock_bus.connect = AsyncMock(side_effect=ConnectionRefusedError("Connection refused"))

        with patch('dbus_fast.aio.MessageBus', return_value=mock_bus):
            task = asyncio.create_task(bar.wake_listener())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Check that an error module was added
        assert len(bar.modules) == 1
        assert "ConnectionRefusedError" in bar.modules[0].block.get("full_text", "")
