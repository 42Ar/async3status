"""
Tests for the watch inotify-based module.
"""

import asyncio
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "async3status"))

from modules.watch import Watch


class TestWatch:
    """Tests for Watch module."""

    @pytest.fixture
    def watch_module(self, mock_bar, tmp_file):
        """Create a Watch module with test config."""
        tmp_file.write_text("initial content")
        config = {
            "type": "watch",
            "path": str(tmp_file),
        }
        return Watch(mock_bar, config)

    @pytest.mark.asyncio
    async def test_initial_content_display(self, watch_module, mock_bar):
        """Test that initial file content is displayed."""
        task = asyncio.create_task(watch_module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert watch_module.block["full_text"] == "initial content"

    @pytest.mark.asyncio
    async def test_file_modification_triggers_update(self, watch_module, mock_bar, tmp_file):
        """Test that modifying the file triggers an update."""
        task = asyncio.create_task(watch_module.run())
        try:
            # Wait for initial update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            mock_bar.update_event.clear()

            # Give watcher time to be fully set up
            await asyncio.sleep(0.05)

            # Modify file (use open with 'w' to trigger MODIFY event)
            with open(tmp_file, "w") as f:
                f.write("modified content")

            # Wait for inotify update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

            assert watch_module.block["full_text"] == "modified content"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_file_creation_triggers_update(self, mock_bar, tmp_path):
        """Test that creating a watched file triggers an update."""
        watch_file = tmp_path / "new_file.txt"
        config = {
            "type": "watch",
            "path": str(watch_file),
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            # Initial update should show error (file doesn't exist)
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            assert "Failed to read" in module.block["full_text"]
            mock_bar.update_event.clear()

            # Give watcher time to be fully set up
            await asyncio.sleep(0.05)

            # Create the file
            watch_file.write_text("new file content")

            # Wait for inotify update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

            assert module.block["full_text"] == "new file content"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_file_replacement_triggers_update(self, mock_bar, tmp_path):
        """Test that replacing a file (move/rename) triggers an update."""
        watch_file = tmp_path / "watched.txt"
        watch_file.write_text("original")

        temp_file = tmp_path / "temp.txt"

        config = {
            "type": "watch",
            "path": str(watch_file),
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            # Wait for initial update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            assert module.block["full_text"] == "original"
            mock_bar.update_event.clear()

            # Give watcher time to be fully set up
            await asyncio.sleep(0.05)

            # Replace file by writing to temp and moving
            temp_file.write_text("replaced content")
            temp_file.rename(watch_file)

            # Wait for inotify update (MOVED_TO event)
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

            assert module.block["full_text"] == "replaced content"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_custom_format(self, mock_bar, tmp_file):
        """Test that custom format string is applied."""
        tmp_file.write_text("value")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "format": "Status: {}",
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert module.block["full_text"] == "Status: value"

    @pytest.mark.asyncio
    async def test_strip_whitespace(self, mock_bar, tmp_file):
        """Test that whitespace is stripped by default."""
        tmp_file.write_text("  content with spaces  \n")
        config = {
            "type": "watch",
            "path": str(tmp_file),
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert module.block["full_text"] == "content with spaces"

    @pytest.mark.asyncio
    async def test_no_strip_whitespace(self, mock_bar, tmp_file):
        """Test that whitespace is preserved when strip=False."""
        tmp_file.write_text("  spaces  ")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "strip": False,
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert module.block["full_text"] == "  spaces  "

    @pytest.mark.asyncio
    async def test_polling_fallback(self, mock_bar, tmp_file):
        """Test that polling mode works as fallback."""
        tmp_file.write_text("poll content")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "refresh": 0.1,  # Fast polling for test
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            # Wait for initial update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            mock_bar.update_event.clear()

            # Modify file content
            tmp_file.write_text("polled update")

            # Wait for polling update (should happen within refresh interval)
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=0.5)

            assert module.block["full_text"] == "polled update"
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_missing_file_shows_error(self, mock_bar, tmp_path):
        """Test that missing file shows an error message."""
        missing_file = tmp_path / "nonexistent.txt"
        config = {
            "type": "watch",
            "path": str(missing_file),
        }
        module = Watch(mock_bar, config)

        task = asyncio.create_task(module.run())
        try:
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert "Failed to read" in module.block["full_text"]
        assert "nonexistent.txt" in module.block["full_text"]
