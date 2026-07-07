"""Plugin discovery and registration."""
import importlib, pkgutil, inspect, os, sys
from pathlib import Path
from typing import Callable, Any

from instareport.plugins.base import PlatformPlugin


_plugins: dict[str, PlatformPlugin] = {}
_flow_map: dict[str, Callable[..., Any]] = {}


def _extract_plugins(mod) -> None:
    """Extract both instance and class-type PlatformPlugin members from a module."""
    for _name, obj in inspect.getmembers(mod):
        if isinstance(obj, PlatformPlugin):
            _plugins[obj.platform_key] = obj
            if not hasattr(_plugins[obj.platform_key], '_source'):
                _plugins[obj.platform_key]._source = "builtin"
        elif inspect.isclass(obj) and issubclass(obj, PlatformPlugin) and obj is not PlatformPlugin:
            try:
                instance = obj()
                _plugins[instance.platform_key] = instance
                if not hasattr(instance, '_source'):
                    instance._source = "builtin"
            except Exception:
                continue


def discover_plugins(package: str = "instareport.plugins.builtin",
                     external_dir: str | Path | None = None) -> None:
    _plugins.clear()
    _flow_map.clear()
    # Discover builtin plugins
    try:
        pkg = importlib.import_module(package)
        for _finder, name, _ispkg in pkgutil.iter_modules(pkg.__path__, prefix=f"{package}."):
            try:
                mod = importlib.import_module(name)
                _extract_plugins(mod)
            except Exception:
                continue
    except Exception:
        pass
    # Discover external plugins from directory (DB setting overrides parameter)
    from instareport.core.database import get_plugin_dir
    db_dir = get_plugin_dir()
    ext_path_str = db_dir or (str(external_dir) if external_dir else "")
    if ext_path_str:
        ext_path = Path(ext_path_str)
        if ext_path.is_dir():
            sys.path.insert(0, str(ext_path.parent))
            for f in sorted(ext_path.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                mod_name = f"external_plugins.{f.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, f)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        for _name, obj in inspect.getmembers(mod):
                            if isinstance(obj, PlatformPlugin):
                                _plugins[obj.platform_key] = obj
                                _plugins[obj.platform_key]._source = str(f)
                            elif inspect.isclass(obj) and issubclass(obj, PlatformPlugin) and obj is not PlatformPlugin:
                                try:
                                    instance = obj()
                                    _plugins[instance.platform_key] = instance
                                    _plugins[instance.platform_key]._source = str(f)
                                except Exception:
                                    continue
                except Exception:
                    continue
            sys.path.pop(0)
    _build_flow_map()


def register_plugin(plugin: PlatformPlugin) -> None:
    _plugins[plugin.platform_key] = plugin
    _build_flow_map()


def _build_flow_map() -> None:
    _flow_map.clear()
    for key, plugin in _plugins.items():
        if plugin.enabled:
            _flow_map[key] = plugin.report


def get_flow_map() -> dict[str, Callable[..., Any]]:
    if not _plugins:
        discover_plugins()
    return _flow_map


def get_plugin(key: str) -> PlatformPlugin | None:
    if not _plugins:
        discover_plugins()
    return _plugins.get(key)


def get_all_plugins() -> list[PlatformPlugin]:
    if not _plugins:
        discover_plugins()
    return list(_plugins.values())


def set_plugin_enabled(key: str, enabled: bool) -> None:
    plugin = get_plugin(key)
    if plugin:
        plugin.enabled = enabled
        _build_flow_map()


def import_plugin_file(path: str | Path) -> PlatformPlugin | None:
    path = Path(path)
    if not path.exists():
        return None
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"_imported_{path.stem}", path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for _name, obj in inspect.getmembers(mod):
            if isinstance(obj, PlatformPlugin):
                obj._source = str(path)
                register_plugin(obj)
                return obj
            elif inspect.isclass(obj) and issubclass(obj, PlatformPlugin) and obj is not PlatformPlugin:
                try:
                    instance = obj()
                    instance._source = str(path)
                    register_plugin(instance)
                    return instance
                except Exception:
                    continue
    except Exception:
        pass
    finally:
        sys.path.pop(0)
    return None
