# -*- coding: utf-8 -*-
"""
    logbook.helpers
    ~~~~~~~~~~~~~~~

    Various helper functions

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
import errno
import time
import random


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
