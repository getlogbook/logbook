import pytest
gevent = pytest.importorskip('gevent')

from logbook.concurrency import enable_gevent
enable_gevent()

import types
import test_handlers
locals = locals()
for name in dir(test_handlers):
    f = getattr(test_handlers, name)
    if name.startswith('test_') and isinstance(f, types.FunctionType):
        locals[name] = f
