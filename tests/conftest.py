"""
Shared fixtures for async3status tests.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest


@dataclass
class MockBar:
    """Mock Bar object for testing modules."""
    updates: list = field(default_factory=list)
    update_event: asyncio.Event = field(default_factory=asyncio.Event)
    modules: list = field(default_factory=list)

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


@asynccontextmanager
async def _run_module(module):
    """
    Context manager to run a module and clean up properly.

    Usage:
        async with run_module(my_module):
            # module is running
            await mock_bar.update_event.wait()
    """
    task = asyncio.create_task(module.run())
    try:
        yield task
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.fixture
def run_module():
    """Fixture that provides the run_module context manager."""
    return _run_module
