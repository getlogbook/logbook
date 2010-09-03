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


# this regexp also matches incompatible dates like 20070101 because
# some libraries (like the python xmlrpclib modules) use this
_iso8601_re = re.compile(
    # date
    r'(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?'
    # time
    r'(?:T(\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?(Z|[+-]\d{2}:\d{2})?)?$'
)


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
    _invalid = object()
    def _convert(obj):
        if obj is None:
            return None
        elif isinstance(obj, str):
            return obj.decode('utf-8', 'replace')
        elif isinstance(obj, (bool, int, long, float, unicode)):
            return obj
        elif isinstance(obj, datetime):
            return format_iso8601(obj)
        elif isinstance(obj, list):
            return [x for x in map(_convert, obj) if x is not _invalid]
        elif isinstance(obj, tuple):
            return tuple(x for x in map(_convert, obj) if x is not _invalid)
        elif isinstance(obj, dict):
            rv = {}
            for key, value in obj.iteritems():
                value = _convert(value)
                if value is not _invalid:
                    if isinstance(key, str):
                        key = key.decode('utf-8', 'replace')
                    else:
                        key = unicode(key)
                    rv[key] = value
            return rv
        return _invalid
    rv = _convert(data)
    if rv is not _invalid:
        return rv


def format_iso8601(d=None):
    """Returns a date in iso8601 format."""
    if d is None:
        d = datetime.utcnow()
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')


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
