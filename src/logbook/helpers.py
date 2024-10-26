"""
    logbook.helpers
    ~~~~~~~~~~~~~~~

    Various helper functions

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import errno
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules) use this
_iso8601_re = re.compile(
    # date
    r"(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?"
    # time
    r"(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$"
)
_missing = object()


can_rename_open_file = False
if os.name == "nt":
    try:
        import ctypes

        _MOVEFILE_REPLACE_EXISTING = 0x1
        _MOVEFILE_WRITE_THROUGH = 0x8
        _MoveFileEx = ctypes.windll.kernel32.MoveFileExW

        def _rename(src, dst):
            if _rename_atomic(src, dst):
                return True
            retry = 0
            rv = False
            while not rv and retry < 100:
                rv = _MoveFileEx(
                    src, dst, _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH
                )
                if not rv:
                    time.sleep(0.001)
                    retry += 1
            return rv

        # new in Vista and Windows Server 2008
        _CreateTransaction = ctypes.windll.ktmw32.CreateTransaction
        _CommitTransaction = ctypes.windll.ktmw32.CommitTransaction
        _MoveFileTransacted = ctypes.windll.kernel32.MoveFileTransactedW
        _CloseHandle = ctypes.windll.kernel32.CloseHandle
        can_rename_open_file = True

        def _rename_atomic(src, dst):
            ta = _CreateTransaction(None, 0, 0, 0, 0, 1000, "Logbook rename")
            if ta == -1:
                return False
            try:
                retry = 0
                rv = False
                while not rv and retry < 100:
                    if rv := _MoveFileTransacted(
                        src,
                        dst,
                        None,
                        None,
                        _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH,
                        ta,
                    ):
                        rv = _CommitTransaction(ta)
                        break
                    else:
                        time.sleep(0.001)
                        retry += 1
                return rv
            finally:
                _CloseHandle(ta)

    except Exception:

        def _rename(src, dst):
            return False

        def _rename_atomic(src, dst):
            return False

    def rename(src, dst):
        # Try atomic or pseudo-atomic rename
        if _rename(src, dst):
            return
        # Fall back to "move away and replace"
        try:
            os.rename(src, dst)
        except OSError:
            e = sys.exc_info()[1]
            if e.errno not in (errno.EEXIST, errno.EACCES):
                raise
            old = f"{dst}-{random.randint(0, 2**31 - 1):08x}"
            os.rename(dst, old)
            os.rename(src, dst)
            try:
                os.unlink(old)
            except Exception:
                pass

else:
    rename = os.rename
    can_rename_open_file = True

_JSON_SIMPLE_TYPES = (bool, float, int, str)


def to_safe_json(data):
    """Makes a data structure safe for JSON silently discarding invalid
    objects from nested structures.  This also converts dates.
    """

    def _convert(obj):
        if obj is None:
            return None
        elif isinstance(obj, _JSON_SIMPLE_TYPES):
            return obj
        elif isinstance(obj, datetime):
            return format_iso8601(obj)
        elif isinstance(obj, list):
            return [_convert(x) for x in obj]
        elif isinstance(obj, tuple):
            return tuple(_convert(x) for x in obj)
        elif isinstance(obj, dict):
            rv = {}
            for key, value in obj.items():
                if not isinstance(key, str):
                    key = str(key)
                rv[key] = _convert(value)
            return rv

    return _convert(data)


if sys.version_info >= (3, 12):

    def datetime_utcnow():
        """datetime.utcnow() but doesn't emit a deprecation warning.

        Will be fixed by https://github.com/getlogbook/logbook/issues/353
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def datetime_utcfromtimestamp(timestamp):
        """datetime.utcfromtimesetamp() but doesn't emit a deprecation warning.

        Will be fixed by https://github.com/getlogbook/logbook/issues/353
        """
        return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)

else:
    datetime_utcnow = datetime.utcnow
    datetime_utcfromtimestamp = datetime.utcfromtimestamp


def format_iso8601(d=None):
    """Returns a date in iso8601 format."""
    if d is None:
        d = datetime_utcnow()
    rv = d.strftime("%Y-%m-%dT%H:%M:%S")
    if d.microsecond:
        rv += "." + str(d.microsecond)
    return rv + "Z"


def parse_iso8601(value):
    """Parse an iso8601 date into a datetime object.  The timezone is
    normalized to UTC.
    """
    m = _iso8601_re.match(value)
    if m is None:
        raise ValueError("not a valid iso8601 date value")

    groups = m.groups()
    args = []
    for group in groups[:-2]:
        if group is not None:
            group = int(group)
        args.append(group)
    seconds = groups[-2]
    if seconds is not None:
        if "." in seconds:
            sec, usec = seconds.split(".")
            args.append(int(sec))
            args.append(int(usec.ljust(6, "0")))
        else:
            args.append(int(seconds))

    rv = datetime(*args)
    tz = groups[-1]
    if tz and tz != "Z":
        args = [int(x) for x in tz[1:].split(":")]
        delta = timedelta(hours=args[0], minutes=args[1])
        if tz[0] == "+":
            rv -= delta
        else:
            rv += delta

    return rv


def get_application_name():
    if not sys.argv or not sys.argv[0]:
        return "Python"
    return os.path.basename(sys.argv[0]).title()


class cached_property:
    """A property that is lazily calculated and then cached."""

    def __init__(self, func, name=None, doc=None):
        self.__name__ = name or func.__name__
        self.__module__ = func.__module__
        self.__doc__ = doc or func.__doc__
        self.func = func

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        value = obj.__dict__.get(self.__name__, _missing)
        if value is _missing:
            value = self.func(obj)
            obj.__dict__[self.__name__] = value
        return value


def get_iterator_next_method(it):
    return lambda: next(it)
