#!/usr/bin/env python3
"""
async3status - Async event-driven i3/sway status bar framework.
"""

import asyncio
from pathlib import Path

from async3status.bar import Bar


async def _async_main():
    config_path = Path("~/.config/async3status/config.yaml").expanduser()
    bar = Bar(config_path)
    await bar.run()


def main():
    """Entry point for the async3status command."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
