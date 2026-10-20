"""Serialize temporary repository imports without retaining repository modules."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

_MODULE_LOCK = RLock()


def _is_repository_module(name: str) -> bool:
    return name == "core" or name.startswith("core.")


@contextmanager
def repository_module_transaction() -> Iterator[None]:
    """Isolate core imports, including transitive imports, for cooperating loaders.

    The API also has a core package. Preserve its exact module identities and
    remove temporary repository modules even when initialization raises.
    """
    with _MODULE_LOCK:
        preserved = {
            name: module
            for name, module in sys.modules.copy().items()
            if _is_repository_module(name)
        }
        try:
            for name in preserved:
                del sys.modules[name]
            yield
        finally:
            for name in list(sys.modules):
                if _is_repository_module(name):
                    del sys.modules[name]
            sys.modules.update(preserved)
