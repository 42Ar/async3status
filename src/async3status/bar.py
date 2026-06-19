import asyncio
import os
import json
import yaml
from loader import load_module


class Bar:

    def __init__(self, config_path):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self.update_event = asyncio.Event()
        self.modules = []
        self.socket_path = cfg.get(
            "socket",
            os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "async3status.sock")
        )
        for mconf in cfg["modules"]:
            module_class = load_module(mconf["type"])
            if module_class is None:
                from modules.static import Static
                module = Static(self, {"text": f"Unable to find module '{mconf['type']}'"})
            else:
                module = module_class(self, mconf)
            self.modules.append(module)

    def notify_update(self):
        self.update_event.set()

    def render(self):
        return [m.block for m in self.modules]

    async def printer(self):
        while True:
            await self.update_event.wait()
            self.update_event.clear()
            print(json.dumps(self.render()) + ",", flush=True)

    async def ipc_server(self):
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        server = await asyncio.start_unix_server(
            self.handle_client,
            path=self.socket_path
        )
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader, writer):
        try:
            line = await reader.readline()
            if not line:
                return
            parts = line.decode().strip().split(None, 2)
            if len(parts) != 3 or parts[0] != "module":
                writer.write(b"error: 'module <module_name> [args]'\n")
                await writer.drain()
                return
            for mod in self.modules:
                if mod.name == parts[1]:
                    await mod.handle_ipc(parts[2])
        finally:
            writer.close()
            await writer.wait_closed()

    async def run(self):
        print(json.dumps({"version": 1}), flush=True)
        print("[", flush=True)
        print("[],", flush=True)
        tasks = [asyncio.create_task(m.run()) for m in self.modules]
        tasks.append(asyncio.create_task(self.printer()))
        tasks.append(asyncio.create_task(self.ipc_server()))
        await asyncio.gather(*tasks)
