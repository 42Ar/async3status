"""
Tests for the wake event system.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from async3status.bar import Bar
from async3status.modules.clock import Clock


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


class TestIPC:
    """Tests for IPC command handling."""

    @pytest.fixture
    def bar_with_socket(self, tmp_path):
        """Create a minimal Bar instance with a test socket path."""
        from async3status.modules.static import Static

        with patch.object(Bar, '__init__', lambda self, path: None):
            bar = Bar.__new__(Bar)
            bar.modules = []
            bar.update_event = asyncio.Event()
            bar.socket_path = str(tmp_path / "test.sock")

        # Add a test module
        module = Static(bar, {"type": "static", "name": "testmod", "text": "test"})
        bar.modules.append(module)

        return bar

    async def test_ipc_valid_command(self, bar_with_socket):
        """Test that valid IPC command returns 'ok' response."""
        bar = bar_with_socket

        # Start the IPC server
        server_task = asyncio.create_task(bar.ipc_server())
        await asyncio.sleep(0.05)  # Let server start

        try:
            # Connect and send valid command
            reader, writer = await asyncio.open_unix_connection(bar.socket_path)
            writer.write(b"module testmod update\n")
            await writer.drain()
            writer.write_eof()

            # Read response
            response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            assert response == b"ok\n"

            writer.close()
            await writer.wait_closed()
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    async def test_ipc_invalid_format(self, bar_with_socket):
        """Test that malformed command returns error."""
        bar = bar_with_socket

        # Start the IPC server
        server_task = asyncio.create_task(bar.ipc_server())
        await asyncio.sleep(0.05)

        try:
            reader, writer = await asyncio.open_unix_connection(bar.socket_path)
            writer.write(b"invalid command\n")
            await writer.drain()
            writer.write_eof()

            response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            assert response.startswith(b"error:")
            assert b"usage:" in response

            writer.close()
            await writer.wait_closed()
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    async def test_ipc_module_not_found(self, bar_with_socket):
        """Test that command to nonexistent module returns error."""
        bar = bar_with_socket

        # Start the IPC server
        server_task = asyncio.create_task(bar.ipc_server())
        await asyncio.sleep(0.05)

        try:
            reader, writer = await asyncio.open_unix_connection(bar.socket_path)
            writer.write(b"module nonexistent update\n")
            await writer.drain()
            writer.write_eof()

            response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            assert response.startswith(b"error:")
            assert b"nonexistent" in response
            assert b"not found" in response

            writer.close()
            await writer.wait_closed()
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    async def test_ipc_empty_line(self, bar_with_socket):
        """Test that empty line is handled gracefully."""
        bar = bar_with_socket

        # Start the IPC server
        server_task = asyncio.create_task(bar.ipc_server())
        await asyncio.sleep(0.05)

        try:
            reader, writer = await asyncio.open_unix_connection(bar.socket_path)
            writer.write(b"\n")
            await writer.drain()
            writer.write_eof()

            # Should get error response for empty/malformed command
            response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            assert response.startswith(b"error:")

            writer.close()
            await writer.wait_closed()
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
