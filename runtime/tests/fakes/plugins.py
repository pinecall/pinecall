"""A fake vendor installed as a plugin is: its module where livekit's are, read by the runtime as any is."""

import sys
import types

from runtime.providers.service import plugins


# The runtime finds its vendors once, by walking livekit's plugins: a fake one is put among them for the
# whole run, under a name of its own, and read the way the runtime reads every plugin.
def install_plugin(name: str, **exported: object) -> str:
    """Put `livekit.plugins.<name>` exporting these, where the runtime looks for vendors; the vendor's name."""
    module = types.ModuleType(f"{plugins.PLUGINS}.{name}")
    vars(module).update(exported)
    sys.modules[module.__name__] = module
    plugins.list_vendors()[name] = plugins.read_vendor(name, module.__name__)
    return name
