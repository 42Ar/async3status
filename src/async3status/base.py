"""
base.py

Defines the base class for all modules in the async3status framework.
Each module should inherit from Module and implement the async run() method.
"""

from dataclasses import dataclass, field
from bar import Bar


@dataclass
class Module:
    """
    Base class for all status bar modules in async3status.

    Attributes:
        bar (Bar): Reference to the parent Bar object.
        config (dict): Configuration dictionary for the module.
        block (dict): The current JSON block that represents the module output.
    """

    bar: Bar
    config: dict
    block: dict = field(default_factory=dict)

    @property
    def name(self):
        return self.config.get("name", self.config["type"])
 
    def __post_init__(self):
        pass

    def update(self, text, markup="pango"):
        block = {"name": self.name, "full_text": text, "markup": markup}
        if block != self.block:
            self.block = block
            self.bar.notify_update()

    async def handle_ipc(self, command: str):
        """
        Handle an ipc command send via async3status control socket to this module.
        """
        pass

    async def run(self):
        """
        Run the module's main loop.

        This method should contain an asynchronous loop that calls
        self.update(new_text) whenever the output changes.

        Example pattern:

            async def run(self):
                while True:
                    self.update("new text")
                    await asyncio.sleep(interval)
        """

