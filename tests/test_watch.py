"""
Tests for the watch inotify-based module.
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from async3status.modules.watch import Watch


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

    async def test_initial_content_display(self, watch_module, mock_bar, run_module):
        """Test that initial file content is displayed."""
        async with run_module(watch_module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert watch_module.block["full_text"] == "initial content"

    async def test_file_modification_triggers_update(self, watch_module, mock_bar, tmp_file, run_module):
        """Test that modifying the file triggers an update."""
        async with run_module(watch_module):
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

    async def test_file_creation_triggers_update(self, mock_bar, tmp_path, run_module):
        """Test that creating a watched file triggers an update."""
        watch_file = tmp_path / "new_file.txt"
        config = {
            "type": "watch",
            "path": str(watch_file),
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
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

    async def test_file_replacement_triggers_update(self, mock_bar, tmp_path, run_module):
        """Test that replacing a file (move/rename) triggers an update."""
        watch_file = tmp_path / "watched.txt"
        watch_file.write_text("original")

        temp_file = tmp_path / "temp.txt"

        config = {
            "type": "watch",
            "path": str(watch_file),
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
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

    async def test_custom_format(self, mock_bar, tmp_file, run_module):
        """Test that custom format string is applied."""
        tmp_file.write_text("value")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "format": "Status: {}",
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert module.block["full_text"] == "Status: value"

    async def test_strip_whitespace(self, mock_bar, tmp_file, run_module):
        """Test that whitespace is stripped by default."""
        tmp_file.write_text("  content with spaces  \n")
        config = {
            "type": "watch",
            "path": str(tmp_file),
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert module.block["full_text"] == "content with spaces"

    async def test_no_strip_whitespace(self, mock_bar, tmp_file, run_module):
        """Test that whitespace is preserved when strip=False."""
        tmp_file.write_text("  spaces  ")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "strip": False,
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert module.block["full_text"] == "  spaces  "

    async def test_polling_fallback(self, mock_bar, tmp_file, run_module):
        """Test that polling mode works as fallback."""
        tmp_file.write_text("poll content")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "refresh": 0.1,  # Fast polling for test
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            # Wait for initial update
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            mock_bar.update_event.clear()

            # Modify file content
            tmp_file.write_text("polled update")

            # Wait for polling update (should happen within refresh interval)
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=0.5)

            assert module.block["full_text"] == "polled update"

    async def test_missing_file_shows_error(self, mock_bar, tmp_path, run_module):
        """Test that missing file shows an error message."""
        missing_file = tmp_path / "nonexistent.txt"
        config = {
            "type": "watch",
            "path": str(missing_file),
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert "Failed to read" in module.block["full_text"]
        assert "nonexistent.txt" in module.block["full_text"]


class TestWatchRelativeTime:
    """Tests for Watch module relative_time functionality."""

    @pytest.fixture
    def watch_module(self, mock_bar, tmp_path):
        """Create a Watch module with relative_time enabled."""
        tmp_file = tmp_path / "test.txt"
        tmp_file.write_text("Test 2026-06-19T12:00:00")
        config = {
            "type": "watch",
            "path": str(tmp_file),
            "relative_time": True,
        }
        return Watch(mock_bar, config)

    # Timestamp parsing tests

    def test_parse_timestamp_full_iso(self, watch_module):
        """Test parsing full ISO timestamp with seconds."""
        dt = watch_module.parse_timestamp("2026-06-19T12:30:45")
        assert dt == datetime(2026, 6, 19, 12, 30, 45)

    def test_parse_timestamp_no_seconds(self, watch_module):
        """Test parsing ISO timestamp without seconds."""
        dt = watch_module.parse_timestamp("2026-06-19T12:30")
        assert dt == datetime(2026, 6, 19, 12, 30, 0)

    def test_parse_timestamp_date_only(self, watch_module):
        """Test parsing date-only timestamp."""
        dt = watch_module.parse_timestamp("2026-06-19")
        assert dt == datetime(2026, 6, 19, 0, 0, 0)

    def test_parse_timestamp_invalid(self, watch_module):
        """Test that invalid timestamp returns None."""
        assert watch_module.parse_timestamp("not-a-date") is None
        assert watch_module.parse_timestamp("2026/06/19") is None

    # Relative time formatting tests

    def test_format_relative_seconds(self, watch_module):
        """Test formatting for < 1 minute ago."""
        now = datetime.now()
        dt = now - timedelta(seconds=30)
        result = watch_module.format_relative(dt)
        assert result == "T-0m"

    def test_format_relative_minutes(self, watch_module):
        """Test formatting for minutes ago."""
        now = datetime.now()
        dt = now - timedelta(minutes=45)
        result = watch_module.format_relative(dt)
        assert result == "T-45m"

    def test_format_relative_hours(self, watch_module):
        """Test formatting for hours ago."""
        now = datetime.now()
        dt = now - timedelta(hours=11)
        result = watch_module.format_relative(dt)
        assert result == "T-11h"

    def test_format_relative_days(self, watch_module):
        """Test formatting for days ago."""
        now = datetime.now()
        dt = now - timedelta(days=3)
        result = watch_module.format_relative(dt)
        assert result == "T-3d"

    def test_format_relative_weeks(self, watch_module):
        """Test formatting for weeks ago."""
        now = datetime.now()
        dt = now - timedelta(weeks=2)
        result = watch_module.format_relative(dt)
        assert result == "T-2w"

    def test_format_relative_future_minutes(self, watch_module):
        """Test formatting for future timestamps."""
        now = datetime.now()
        dt = now + timedelta(minutes=30, seconds=30)  # Add buffer for timing
        result = watch_module.format_relative(dt)
        assert result == "T+30m"

    def test_format_relative_future_hours(self, watch_module):
        """Test formatting for future timestamps in hours."""
        now = datetime.now()
        dt = now + timedelta(hours=5, minutes=30)  # Add buffer for timing
        result = watch_module.format_relative(dt)
        assert result == "T+5h"

    # Timestamp replacement tests

    def test_replace_single_timestamp(self, watch_module):
        """Test replacing a single timestamp in content."""
        now = datetime.now()
        past = now - timedelta(hours=3)
        iso_str = past.strftime("%Y-%m-%dT%H:%M:%S")
        content = f"Backup completed {iso_str}"

        result = watch_module.replace_timestamps(content)
        assert "T-3h" in result
        assert iso_str not in result

    def test_replace_multiple_timestamps(self, watch_module):
        """Test replacing multiple timestamps in content."""
        now = datetime.now()
        past1 = now - timedelta(hours=2)
        past2 = now - timedelta(days=5)
        iso1 = past1.strftime("%Y-%m-%dT%H:%M")
        iso2 = past2.strftime("%Y-%m-%d")

        content = f"Last: {iso1}, Previous: {iso2}"
        result = watch_module.replace_timestamps(content)

        assert "T-2h" in result
        assert "T-5d" in result
        assert iso1 not in result
        assert iso2 not in result

    def test_replace_mixed_past_future(self, watch_module):
        """Test replacing mixed past and future timestamps."""
        now = datetime.now()
        past = now - timedelta(hours=6, minutes=30)  # Add buffer for timing
        future = now + timedelta(hours=12, minutes=30)  # Add buffer for timing
        iso_past = past.strftime("%Y-%m-%dT%H:%M")
        iso_future = future.strftime("%Y-%m-%dT%H:%M")

        content = f"Last: {iso_past}, Next: {iso_future}"
        result = watch_module.replace_timestamps(content)

        assert "T-6h" in result
        assert "T+12h" in result

    def test_replace_preserves_non_timestamps(self, watch_module):
        """Test that non-timestamp text is preserved."""
        content = "Status: OK, Count: 42"
        result = watch_module.replace_timestamps(content)
        assert result == content

    # Bucket change calculation tests

    def test_next_bucket_change_minutes(self, watch_module):
        """Test bucket change calculation for minutes."""
        now = datetime.now()
        # 45 minutes and 30 seconds ago -> next change at 46 minutes (30 seconds away)
        past = now - timedelta(minutes=45, seconds=30)
        iso_str = past.strftime("%Y-%m-%dT%H:%M:%S")
        watch_module.last_content = f"Test {iso_str}"

        seconds = watch_module.next_bucket_change()
        # Should be about 30 seconds until it becomes T-46m
        assert seconds is not None
        assert 0 <= seconds <= 60  # Within a minute

    def test_next_bucket_change_hours(self, watch_module):
        """Test bucket change calculation for hours."""
        now = datetime.now()
        # 2.5 hours ago -> should change to T-3h in 30 minutes
        past = now - timedelta(hours=2, minutes=30)
        iso_str = past.strftime("%Y-%m-%dT%H:%M:%S")
        watch_module.last_content = f"Test {iso_str}"

        seconds = watch_module.next_bucket_change()
        assert seconds is not None
        # Should be about 30 minutes until next hour boundary
        assert 29 * 60 <= seconds <= 31 * 60

    def test_next_bucket_change_no_timestamps(self, watch_module):
        """Test bucket change returns None when no timestamps."""
        watch_module.last_content = "No timestamps here"
        assert watch_module.next_bucket_change() is None

    def test_next_bucket_change_multiple_timestamps(self, watch_module):
        """Test bucket change returns soonest transition."""
        now = datetime.now()
        # One timestamp 58 minutes ago (changes in 2 min)
        past1 = now - timedelta(minutes=58)
        # One timestamp 2 hours ago (changes in ~1 hour)
        past2 = now - timedelta(hours=2, minutes=1)

        iso1 = past1.strftime("%Y-%m-%dT%H:%M:%S")
        iso2 = past2.strftime("%Y-%m-%dT%H:%M:%S")
        watch_module.last_content = f"A: {iso1}, B: {iso2}"

        seconds = watch_module.next_bucket_change()
        assert seconds is not None
        # Should be about 2 minutes (the sooner transition)
        assert seconds <= 3 * 60

    # Integration tests

    async def test_on_wake_refreshes_display(self, watch_module, mock_bar):
        """Test that on_wake() refreshes the display."""
        # Initial state
        watch_module.do_update()

        # Simulate wake
        await watch_module.on_wake()

        # Block should be updated (notify_update called)
        assert mock_bar.update_event.is_set()

    async def test_relative_time_display(self, mock_bar, tmp_path, run_module):
        """Test full relative time display in watch module."""
        now = datetime.now()
        past = now - timedelta(hours=5)
        iso_str = past.strftime("%Y-%m-%dT%H:%M")

        tmp_file = tmp_path / "status.txt"
        tmp_file.write_text(f"Backup {iso_str}")

        config = {
            "type": "watch",
            "path": str(tmp_file),
            "relative_time": True,
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.sleep(0.1)

        assert "T-5h" in module.block["full_text"]
        assert "Backup" in module.block["full_text"]

    async def test_new_timestamp_reschedules_bucket_timer(self, mock_bar, tmp_path, run_module):
        """Regression: a new timestamp from a file event must reschedule the
        bucket timer.

        Previously the bucket-change updater ran as a separate task and slept
        on a duration computed from the old content. A newly arrived timestamp
        did not recompute that sleep, so the relative display stayed stale.
        With the single unified loop, the next timeout is recomputed every
        iteration, so a fresh file event must reschedule it.
        """
        now = datetime.now()
        # Start with a timestamp ~58 minutes old: bucket changes in ~2 minutes,
        # so the old design would sleep ~2 minutes before any timer update.
        old = now - timedelta(minutes=58)
        old_iso = old.strftime("%Y-%m-%dT%H:%M:%S")

        tmp_file = tmp_path / "status.txt"
        tmp_file.write_text(f"Backup {old_iso}")

        config = {
            "type": "watch",
            "path": str(tmp_file),
            "relative_time": True,
        }
        module = Watch(mock_bar, config)

        async with run_module(module):
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)
            assert "T-58m" in module.block["full_text"]
            mock_bar.update_event.clear()

            # Let the watcher arm, then deliver a brand-new timestamp.
            await asyncio.sleep(0.05)
            fresh = datetime.now()
            fresh_iso = fresh.strftime("%Y-%m-%dT%H:%M:%S")
            tmp_file.write_text(f"Backup {fresh_iso}")

            # The file event must promptly update the display to the new value.
            await asyncio.wait_for(mock_bar.update_event.wait(), timeout=1.0)

        assert "T-0m" in module.block["full_text"]
        # The new bucket timeout is now ~60s; recomputed from fresh content.
        assert module._next_timeout() <= 61
