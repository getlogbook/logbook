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

PY2 = sys.version_info[0] == 2

if PY2:
    import __builtin__ as _builtins
else:
    import builtins as _builtins

try:
    import json
except ImportError:
    import simplejson as json

if PY2:
    from cStringIO import StringIO
    iteritems = dict.iteritems
    from itertools import izip as zip
    xrange = _builtins.xrange
else:
    from io import StringIO
    zip = _builtins.zip
    xrange = range
    iteritems = dict.items

_IDENTITY = lambda obj: obj

if PY2:
    def u(s):
        return unicode(s, "unicode_escape")
else:
    u = _IDENTITY

if PY2:
    integer_types = (int, long)
    string_types = (basestring,)
else:
    integer_types = (int,)
    string_types = (str,)

if PY2:
    import httplib as http_client
else:
    from http import client as http_client

if PY2:
    #Yucky, but apparently that's the only way to do this
    exec("""
def reraise(tp, value, tb=None):
    raise tp, value, tb
""", locals(), globals())
else:
    def reraise(tp, value, tb=None):
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value


# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules) use this
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)
_missing = object()
if PY2:
    def b(x): return x
    def _is_text_stream(x): return True
else:
    import io
    def b(x): return x.encode('ascii')
    def _is_text_stream(stream): return isinstance(stream, io.TextIOBase)


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
            if PY2:
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
        except OSError:
            e = sys.exc_info()[1]
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

_JSON_SIMPLE_TYPES = (bool, float) + integer_types + string_types

def to_safe_json(data):
    """Makes a data structure safe for JSON silently discarding invalid
    objects from nested structures.  This also converts dates.
    """
    def _convert(obj):
        if obj is None:
            return None
        elif PY2 and isinstance(obj, str):
            return obj.decode('utf-8', 'replace')
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
            for key, value in iteritems(obj):
                if not isinstance(key, string_types):
                    key = str(key)
                if not is_unicode(key):
                    key = u(key)
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
        args = [int(x) for x in tz[1:].split(':')]
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

def get_iterator_next_method(it):
    return lambda: next(it)

# python 2 support functions and aliases
def is_unicode(x):
    if PY2:
        return isinstance(x, unicode)
    return isinstance(x, str)

if PY2:
    exec("""def with_metaclass(meta):
    class _WithMetaclassBase(object):
        __metaclass__ = meta
    return _WithMetaclassBase
""")
else:
    exec("""def with_metaclass(meta):
    class _WithMetaclassBase(object, metaclass=meta):
        pass
    return _WithMetaclassBase
""")
