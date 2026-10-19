"""
Tests for the battery module's read-only status rendering.
"""

import pytest

from async3status.modules.battery import Battery


class TestBattery:
    """Tests for Battery module."""

    @pytest.fixture
    def battery_dir(self, tmp_path):
        """Create a fake battery sysfs directory."""
        bat_path = tmp_path / "BAT0"
        bat_path.mkdir()
        (bat_path / "status").write_text("Discharging")
        (bat_path / "capacity").write_text("50")
        return bat_path

    @pytest.fixture
    def battery_module(self, mock_bar, battery_dir):
        """Create a Battery module with test config."""
        config = {
            "type": "battery",
            "battery_path": str(battery_dir),
            "background_blink_interval": 1,
        }
        return Battery(mock_bar, config)

    async def test_no_red_background_above_threshold(self, battery_module, battery_dir):
        (battery_dir / "capacity").write_text("50")
        text = await battery_module.do_check()
        assert "background='red'" not in text
        assert "50%" in text

    async def test_red_background_at_or_below_threshold(self, battery_module, battery_dir):
        (battery_dir / "capacity").write_text("10")
        text = await battery_module.do_check()
        assert "background='red'" in text
        assert battery_module._blink_active is True

    async def test_no_red_background_when_charging(self, battery_module, battery_dir):
        (battery_dir / "status").write_text("Charging")
        (battery_dir / "capacity").write_text("5")
        text = await battery_module.do_check()
        assert "background='red'" not in text
        assert battery_module._blink_active is False

    async def test_blink_toggles_red_background(self, battery_module, battery_dir):
        (battery_dir / "capacity").write_text("5")

        # Entering the red state starts with the background visible
        text = await battery_module.do_check()
        assert "background='red'" in text
        assert battery_module._blink_visible is True

        # Simulate the main loop toggling after each update
        battery_module._blink_visible = not battery_module._blink_visible
        text = await battery_module.do_check()
        assert "background='red'" not in text
        assert battery_module._blink_active is True

        # Toggle back: red returns
        battery_module._blink_visible = not battery_module._blink_visible
        text = await battery_module.do_check()
        assert "background='red'" in text

    async def test_blink_disabled_with_zero_interval(self, mock_bar, battery_dir):
        config = {
            "type": "battery",
            "battery_path": str(battery_dir),
            "background_blink_interval": 0,
        }
        module = Battery(mock_bar, config)
        (battery_dir / "capacity").write_text("5")

        text = await module.do_check()
        assert "background='red'" in text
        assert module._blink_active is False

        # Blink state is reset to visible; background stays solid
        module._blink_visible = not module._blink_visible
        text = await module.do_check()
        assert "background='red'" in text
        assert module._blink_visible is True
