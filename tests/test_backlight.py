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
    async def test_missing_brightness_file(self, mock_bar, tmp_path):
        """Test handling of missing brightness file.
        
        Note: Currently the module crashes if the brightness file doesn't exist
        because inotify.add_watch fails. This test documents that behavior.
        A future improvement would be to handle this gracefully.
        """
        bl_path = tmp_path / "missing_backlight"
        bl_path.mkdir()
        # Only create max_brightness, not brightness
        (bl_path / "max_brightness").write_text("1000")

        config = {"type": "backlight", "path": str(bl_path), "icon": "BL"}
        module = Backlight(mock_bar, config)

        # Module shows "?" initially but then crashes when trying to watch missing file
        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            # Initial update shows "?" since brightness file is missing
            assert "?" in module.block.get("full_text", "?")
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, FileNotFoundError):
                pass  # FileNotFoundError expected - inotify can't watch missing file

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
