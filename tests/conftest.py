"""
Shared fixtures for async3status tests.
"""

import asyncio
import pytest
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MockBar:
    """Mock Bar object for testing modules."""
    updates: list = field(default_factory=list)
    update_event: asyncio.Event = field(default_factory=asyncio.Event)

    def notify_update(self):
        self.update_event.set()


@pytest.fixture
def mock_bar():
    """Provide a fresh MockBar instance."""
    return MockBar()


@pytest.fixture
def tmp_file(tmp_path):
    """Provide a temporary file path (does not create the file)."""
    return tmp_path / "test_file.txt"
