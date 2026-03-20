import importlib


def load_module(name):
    pymodule = f"modules.{name}"
    spec = importlib.util.find_spec(pymodule)
    if spec is None:
        return None
    mod = importlib.import_module(pymodule)
    return getattr(mod, name.capitalize())

