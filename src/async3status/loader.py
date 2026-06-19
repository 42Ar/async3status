import importlib
import importlib.util


def load_module(name):
    """Load a module class by name from async3status.modules."""
    pymodule = f"async3status.modules.{name}"
    spec = importlib.util.find_spec(pymodule)
    if spec is None:
        return None
    mod = importlib.import_module(pymodule)
    return getattr(mod, name.capitalize())
