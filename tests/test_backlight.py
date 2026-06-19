"""
Tests for the backlight inotify-based module.
"""

import asyncio
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "async3status"))

from modules.backlight import Backlight


class TestBacklight:
    """Tests for Backlight module."""

    @pytest.fixture
    def backlight_dir(self, tmp_path):
        """Create a fake backlight sysfs directory."""
        bl_path = tmp_path / "backlight"
        bl_path.mkdir()
        (bl_path / "brightness").write_text("500")
        (bl_path / "max_brightness").write_text("1000")
        return bl_path

    @pytest.fixture
    def backlight_module(self, mock_bar, backlight_dir):
        """Create a Backlight module with test config."""
        config = {
            "type": "backlight",
            "path": str(backlight_dir),
            "icon": "BL",
        }
        return Backlight(mock_bar, config)

    @pytest.mark.asyncio
    async def test_initial_brightness_display(self, backlight_module, mock_bar):
        """Test that initial brightness is read and displayed correctly."""
        # Run module briefly to get initial update
        task = asyncio.create_task(backlight_module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert backlight_module.block["full_text"] == "BL 50%"

    @pytest.mark.asyncio
    async def test_brightness_change_triggers_update(self, backlight_module, mock_bar, backlight_dir):
        """Test that modifying brightness file triggers an update."""
        task = asyncio.create_task(backlight_module.run())
        try:
            # Wait for initial update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            mock_bar.update_event.clear()

            # Change brightness
            (backlight_dir / "brightness").write_text("750")

            # Wait for inotify update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

            assert backlight_module.block["full_text"] == "BL 75%"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_missing_brightness_file_shows_error(self, mock_bar, tmp_path):
        """Test that missing brightness file shows error text in status bar."""
        bl_path = tmp_path / "missing_backlight"
        bl_path.mkdir()
        # Only create max_brightness, not brightness
        (bl_path / "max_brightness").write_text("1000")

        config = {"type": "backlight", "path": str(bl_path), "icon": "BL"}
        module = Backlight(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            # Wait for error message to appear
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            # Should show "no backlight" error
            assert "no backlight" in module.block["full_text"]
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_missing_backlight_directory_shows_error(self, mock_bar, tmp_path):
        """Test that completely missing backlight path shows error text."""
        bl_path = tmp_path / "nonexistent_backlight"
        # Don't create the directory at all

        config = {"type": "backlight", "path": str(bl_path), "icon": "BL"}
        module = Backlight(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            # Should show "no backlight" error
            assert "no backlight" in module.block["full_text"]
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_brightness_file_appears_later(self, mock_bar, tmp_path):
        """Test that module recovers when brightness file appears after startup."""
        bl_path = tmp_path / "delayed_backlight"
        bl_path.mkdir()
        (bl_path / "max_brightness").write_text("1000")
        # brightness file doesn't exist yet

        config = {"type": "backlight", "path": str(bl_path), "icon": "BL", "retry_interval": 0.1}
        module = Backlight(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            # Wait for initial error message
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            assert "no backlight" in module.block["full_text"]
            mock_bar.update_event.clear()

            # Now create the brightness file
            (bl_path / "brightness").write_text("500")

            # Module should recover and show brightness after retry
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            assert "50%" in module.block["full_text"]
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_zero_max_brightness(self, mock_bar, tmp_path):
        """Test handling of zero max_brightness (avoid division by zero)."""
        bl_path = tmp_path / "zero_backlight"
        bl_path.mkdir()
        (bl_path / "brightness").write_text("500")
        (bl_path / "max_brightness").write_text("0")

        config = {"type": "backlight", "path": str(bl_path), "icon": "BL"}
        module = Backlight(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Should show "?" when max is 0
        assert "?" in module.block["full_text"]

    @pytest.mark.asyncio
    async def test_custom_icon(self, mock_bar, backlight_dir):
        """Test that custom icon is used."""
        config = {
            "type": "backlight",
            "path": str(backlight_dir),
            "icon": "LIGHT",
        }
        module = Backlight(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert module.block["full_text"].startswith("LIGHT")
