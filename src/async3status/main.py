#!/usr/bin/env python3

import asyncio
from bar import Bar
from pathlib import Path


async def main():
    bar = Bar(Path("~/.config/async3status/config.yaml").expanduser())
    await bar.run()


if __name__ == "__main__":
    asyncio.run(main())

