# -*- coding: utf-8 -*-
"""
    logbook.helpers
    ~~~~~~~~~~~~~~~

    Various helper functions

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import os
import re
import sys
import errno
import time
import random
from datetime import datetime, timedelta


# Python 2.4 compatibility

try:
    any = any
except NameError:
    def any(iterable):
        for item in iterable:
            if item:
                return True


# Python 2.5 compatibility

try:
    import json
except ImportError:
    import simplejson as json

if hasattr(str, 'format'):
    def F(format_string):
        return format_string
else:
    from logbook._stringfmt import FormattableString as F

# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules) use this
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)
_missing = object()
_py3 = sys.version_info >= (3, 0)
if _py3:
    import io
    def b(x): return x.encode('ascii')
    def _is_text_stream(stream): return isinstance(stream, io.TextIOBase)
else:
    def b(x): return x
    def _is_text_stream(x): return True


can_rename_open_file = False
if os.name == 'nt': # pragma: no cover
    _rename = lambda src, dst: False
    _rename_atomic = lambda src, dst: False

    try:
        import ctypes

        _MOVEFILE_REPLACE_EXISTING = 0x1
        _MOVEFILE_WRITE_THROUGH = 0x8
        _MoveFileEx = ctypes.windll.kernel32.MoveFileExW

        def _rename(src, dst):
            if not isinstance(src, unicode):
                src = unicode(src, sys.getfilesystemencoding())
            if not isinstance(dst, unicode):
                dst = unicode(dst, sys.getfilesystemencoding())
            if _rename_atomic(src, dst):
                return True
            retry = 0
            rv = False
            while not rv and retry < 100:
                rv = _MoveFileEx(src, dst, _MOVEFILE_REPLACE_EXISTING |
                                           _MOVEFILE_WRITE_THROUGH)
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
            ta = _CreateTransaction(None, 0, 0, 0, 0, 1000, 'Logbook rename')
            if ta == -1:
                return False
            try:
                retry = 0
                rv = False
                while not rv and retry < 100:
                    rv = _MoveFileTransacted(src, dst, None, None,
                                             _MOVEFILE_REPLACE_EXISTING |
                                             _MOVEFILE_WRITE_THROUGH, ta)
                    if rv:
                        rv = _CommitTransaction(ta)
                        break
                    else:
                        time.sleep(0.001)
                        retry += 1
                return rv
            finally:
                _CloseHandle(ta)
    except Exception:
        pass

    def rename(src, dst):
        # Try atomic or pseudo-atomic rename
        if _rename(src, dst):
            return
        # Fall back to "move away and replace"
        try:
            os.rename(src, dst)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
            old = "%s-%08x" % (dst, random.randint(0, sys.maxint))
            os.rename(dst, old)
            os.rename(src, dst)
            try:
                os.unlink(old)
            except Exception:
                pass
else:
    rename = os.rename
    can_rename_open_file = True


def to_safe_json(data):
    """Makes a data structure safe for JSON silently discarding invalid
    objects from nested structures.  This also converts dates.
    """
    def _convert(obj):
        if obj is None:
            return None
        elif not _py3 and isinstance(obj, str):
            return obj.decode('utf-8', 'replace')
        elif isinstance(obj, (bool, int, long, float, unicode)):
            return obj
        elif isinstance(obj, datetime):
            return format_iso8601(obj)
        elif isinstance(obj, list):
            return [_convert(x) for x in obj]
        elif isinstance(obj, tuple):
            return tuple(_convert(x) for x in obj)
        elif isinstance(obj, dict):
            rv = {}
            for key, value in obj.iteritems():
                if not _py3 and isinstance(key, str):
                    key = key.decode('utf-8', 'replace')
                else:
                    key = unicode(key)
                rv[key] = _convert(value)
            return rv
    return _convert(data)


def format_iso8601(d=None):
    """Returns a date in iso8601 format."""
    if d is None:
        d = datetime.utcnow()
    rv = d.strftime('%Y-%m-%dT%H:%M:%S')
    if d.microsecond:
        rv += '.' + str(d.microsecond)
    return rv + 'Z'


def parse_iso8601(value):
    """Parse an iso8601 date into a datetime object.  The timezone is
    normalized to UTC.
    """
    m = _iso8601_re.match(value)
    if m is None:
        raise ValueError('not a valid iso8601 date value')

    groups = m.groups()
    args = []
    for group in groups[:-2]:
        if group is not None:
            group = int(group)
        args.append(group)
    seconds = groups[-2]
    if seconds is not None:
        if '.' in seconds:
            sec, usec = seconds.split('.')
            args.append(int(sec))
            args.append(int(usec.ljust(6, '0')))
        else:
            args.append(int(seconds))

    rv = datetime(*args)
    tz = groups[-1]
    if tz and tz != 'Z':
        args = map(int, tz[1:].split(':'))
        delta = timedelta(hours=args[0], minutes=args[1])
        if tz[0] == '+':
            rv -= delta
        else:
            rv += delta

    return rv


def get_application_name():
    if not sys.argv or not sys.argv[0]:
        return 'Python'
    return os.path.basename(sys.argv[0]).title()


class cached_property(object):
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
