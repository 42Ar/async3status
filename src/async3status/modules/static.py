from async3status.base import Module


class Static(Module):
    """
    Displays a static text with specified color.

    Example config:

    modules:
      - type: static
        text: "Hello World!"
        color: "red"
    """

    async def run(self):
        cfg = self.config
        text = cfg.get("text", "ERROR")
        color = cfg.get("color", "red")
        self.update(f"<span foreground='{color}'>{text}</span>")

