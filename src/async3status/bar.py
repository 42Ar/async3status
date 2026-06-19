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

    async def wake_listener(self):
        """Listen for system wake events via D-Bus and notify modules."""
        try:
            from dbus_fast.aio import MessageBus
            from dbus_fast import BusType
        except ImportError:
            from modules.static import Static
            module = Static(self, {"type": "static", "text": "wake: no dbus-fast", "color": "yellow"})
            self.modules.append(module)
            await module.run()
            return

        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            introspection = await bus.introspect(
                "org.freedesktop.login1", "/org/freedesktop/login1"
            )
            proxy = bus.get_proxy_object(
                "org.freedesktop.login1", "/org/freedesktop/login1", introspection
            )
            manager = proxy.get_interface("org.freedesktop.login1.Manager")

            def on_prepare_for_sleep(start):
                if not start:  # Waking up
                    for mod in self.modules:
                        asyncio.create_task(mod.on_wake())

            manager.on_prepare_for_sleep(on_prepare_for_sleep)
            await asyncio.Future()  # Run forever
        except Exception as e:
            from modules.static import Static
            module = Static(self, {"type": "static", "text": f"wake: {type(e).__name__}", "color": "red"})
            self.modules.append(module)
            await module.run()

    async def run(self):
        print(json.dumps({"version": 1}), flush=True)
        print("[", flush=True)
        print("[],", flush=True)
        tasks = [asyncio.create_task(m.run()) for m in self.modules]
        tasks.append(asyncio.create_task(self.printer()))
        tasks.append(asyncio.create_task(self.ipc_server()))
        tasks.append(asyncio.create_task(self.wake_listener()))
        await asyncio.gather(*tasks)
