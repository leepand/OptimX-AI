"""该模块提供了一组辅助函数，用于在optimx包的同组件中使用。
"""

"""Utility to lazy load modules."""
import importlib
import sys
import types
import importlib
from typing import Any


def load_obj(obj_path: str, default_obj_path: str = "") -> Any:
    """从一个给定的路径中提取一个对象。
    Args:
        obj_path: 要提取的对象的路径，包括对象名称。
        default_obj_path: 默认的对象路径。
    Returns:
        被提取的对象。
    Raises:
        AttributeError: 当该对象没有给定的命名属性时。
    """
    obj_path_list = obj_path.rsplit(".", 1)
    obj_path = obj_path_list.pop(0) if len(obj_path_list) > 1 else default_obj_path
    obj_name = obj_path_list[0]
    module_obj = importlib.import_module(obj_path)
    if not hasattr(module_obj, obj_name):
        raise AttributeError(f"Object '{obj_name}' cannot be loaded from '{obj_path}'.")
    return getattr(module_obj, obj_name)


class LazyLoader(types.ModuleType):
    """Class for module lazy loading.

    This class helps lazily load modules at package level, which avoids pulling in large
    dependencies like `tensorflow` or `torch`. This class is mirrored from wandb's LazyLoader:
    https://github.com/wandb/wandb/blob/79b2d4b73e3a9e4488e503c3131ff74d151df689/wandb/sdk/lib/lazyloader.py#L9
    """

    def __init__(self, local_name, parent_module_globals, name):
        self._local_name = local_name
        self._parent_module_globals = parent_module_globals

        self._module = None
        super().__init__(str(name))

    def _load(self):
        """Load the module and insert it into the parent's globals."""
        if self._module:
            # If already loaded, return the loaded module.
            return self._module

        # Import the target module and insert it into the parent's namespace
        module = importlib.import_module(self.__name__)
        self._parent_module_globals[self._local_name] = module
        sys.modules[self._local_name] = module

        # Update this object's dict so that if someone keeps a reference to the `LazyLoader`,
        # lookups are efficient (`__getattr__` is only called on lookups that fail).
        self.__dict__.update(module.__dict__)

        return module

    def __getattr__(self, item):
        module = self._load()
        return getattr(module, item)

    def __dir__(self):
        module = self._load()
        return dir(module)

    def __repr__(self):
        if not self._module:
            return f"<module '{self.__name__} (Not loaded yet)'>"
        return repr(self._module)
