# -*- coding: utf-8 -*-
"""
    logbook.base
    ~~~~~~~~~~~~

    Base implementation for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import os
import sys
import thread
import warnings
import threading
import traceback
from thread import get_ident as current_thread
from contextlib import contextmanager
from itertools import count
from weakref import ref as weakref
from datetime import datetime


CRITICAL = 6
ERROR = 5
WARNING = 4
NOTICE = 3
INFO = 2
DEBUG = 1
NOTSET = 0

_MAX_CONTEXT_OBJECT_CACHE = 256

_level_names = {
    CRITICAL:   'CRITICAL',
    ERROR:      'ERROR',
    WARNING:    'WARNING',
    NOTICE:     'NOTICE',
    INFO:       'INFO',
    DEBUG:      'DEBUG',
    NOTSET:     'NOTSET'
}
_reverse_level_names = dict((v, k) for (k, v) in _level_names.iteritems())
_missing = object()
_main_thread = thread.get_ident()


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


def _level_name_property():
    """Returns a property that reflects the level as name from
    the internal level attribute.
    """
    def _get_level_name(self):
        return get_level_name(self.level)
    def _set_level_name(self, level):
        self.level = lookup_level(level)
    return property(_get_level_name, _set_level_name, doc=
        'The level as unicode string')


def _group_reflected_property(name, default, fallback=_missing):
    """Returns a property for a given name that falls back to the
    value of the group if set.  If there is no such group, the
    provided default is used.
    """
    def _get(self):
        rv = getattr(self, '_' + name, _missing)
        if rv is not _missing and rv != fallback:
            return rv
        if self.group is None:
            return default
        return getattr(self.group, name)
    def _set(self, value):
        setattr(self, '_' + name, value)
    def _del(self):
        delattr(self, '_' + name)
    return property(_get, _set, _del)


def get_level_name(level):
    """Return the textual representation of logging level 'level'."""
    try:
        return _level_names[level]
    except KeyError:
        raise LookupError('unknown level')


def lookup_level(level):
    """Return the integer representation of a logging level."""
    if isinstance(level, (int, long)):
        return level
    try:
        return _reverse_level_names[level]
    except KeyError:
        raise LookupError('unknown level name %s' % level)


class ExtraDict(dict):
    """A dictionary which returns ``u''`` on missing keys."""

    def __missing__(self, key):
        return u''

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            dict.__repr__(self)
        )


class _ExceptionCatcher(object):
    """Helper for exception caught blocks."""

    def __init__(self, logger, args, kwargs):
        self.logger = logger
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            kwargs = self.kwargs.copy()
            kwargs['exc_info'] = (exc_type, exc_value, tb)
            self.logger.exception(*self.args, **kwargs)
        return True


class _ContextObjectType(type):
    """Helper metaclass for context objects that creates the class
    specific registry objects.
    """

    def __new__(cls, name, bases, d):
        rv = type.__new__(cls, name, bases, d)
        if rv._co_abstract or hasattr(rv, '_co_stackop'):
            return rv
        rv._co_global = []
        rv._co_context_lock = threading.Lock()
        rv._co_context = threading.local()
        rv._co_cache = {}
        rv._co_stackop = count().next
        return rv

    def iter_context_objects(cls):
        """Returns an iterator over all objects for the combined
        application and context cache.
        """
        objects = cls._co_cache.get(current_thread())
        if objects is None:
            if len(cls._co_cache) > _MAX_CONTEXT_OBJECT_CACHE:
                cls._co_cache.clear()
            objects = cls._co_global[:]
            objects.extend(getattr(cls._co_context, 'stack', ()))
            objects.sort(reverse=True)
            objects = [x[1] for x in objects]
            cls._co_cache[current_thread()] = objects
        return iter(objects)


class ContextObject(object):
    """An object that can be bound to a context."""
    __metaclass__ = _ContextObjectType
    _co_abstract = True

    def push_thread(self):
        """Pushes the context object to the thread stack."""
        with _context_handler_lock:
            self._co_cache.pop(current_thread(), None)
            item = (self._co_stackop(), self)
            stack = getattr(self._co_context, 'stack', None)
            if stack is None:
                self._context.stack = [item]
            else:
                stack.append(item)

    def pop_thread(self):
        """Pops the context object from the stack."""
        with self._co_context_lock:
            self._co_cache.pop(current_thread(), None)
            stack = getattr(self._co_context, 'stack', None)
            assert stack, 'no objects on stack'
            popped = stack.pop()[1]
            assert popped is self, 'popped unexpected object'

    def push_application(self):
        """Pushes the context object to the application stack."""
        self._co_global.append((self._co_stackop(), self))
        self._co_cache.clear()

    def pop_application(self):
        """Pops the context object from the stack."""
        assert self._co_global, 'no objects on application stack'
        popped = self._co_global.pop()[1]
        self._co_cache.clear()
        assert popped is self, 'popped unexpected object'

    @contextmanager
    def threadbound(self):
        self.push_thread()
        try:
            yield self
        finally:
            self.pop_thread()

    @contextmanager
    def applicationbound(self):
        self.push_application()
        try:
            yield self
        finally:
            self.pop_application()

    def __enter__(self):
        self.push_thread()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.pop_thread()


class Processor(ContextObject):
    """Can be pushed to a stack to inject additional information into
    a log record as necessary::

        def inject_ip(record):
            record.extra['ip'] = '127.0.0.1'

        with Processor(inject_ip):
            ...
    """

    _co_abstract = False

    def __init__(self, callback=None):
        self.callback = callback

    def process(self, record):
        if self.callback is not None:
            self.callback(record)

    def __call__(self, record):
        self.process(record)


class LogRecord(object):
    """A LogRecord instance represents an event being logged.

    LogRecord instances are created every time something is logged. They
    contain all the information pertinent to the event being logged. The
    main information passed in is in msg and args
    """
    _pullable_information = ('func_name', 'module', 'filename', 'lineno',
                             'process_name', 'thread', 'thread_name')

    def __init__(self, logger_name, level, msg, args=None, kwargs=None,
                 exc_info=None, extra=None, frame=None, channel=None):
        #: the time of the log record creation as :class:`datetime.datetime`
        #: object.
        self.time = datetime.utcnow()
        #: the name of the logger that created it.  This is a descriptive
        #: name and should not be used for logging.  A log record might have
        #: a :attr:`channel` defined which provides more information for
        #: filtering if this is absolutely necessary.
        self.logger_name = logger_name
        #: The message of the log record as new-style format string.
        self.msg = msg
        #: the positional arguments for the format string.
        self.args = args or ()
        #: the keyword arguments for the format string.
        self.kwargs = kwargs or {}
        #: the level of the log record as integer.
        self.level = level
        #: optional exception information.  If set, this is a tuple in the
        #: form ``(exc_type, exc_value, tb)`` as returned by
        #: :func:`sys.exc_info`.
        self.exc_info = exc_info
        #: optional extra information as dictionary.  This is the place
        #: where custom log processors can attach custom context sensitive
        #: data.
        self.extra = ExtraDict(extra or ())
        #: If available, optionally the interpreter frame that created the
        #: log record.  Might not be available for all calls and is removed
        #: when the log record is closed.
        self.frame = frame
        #: the PID of the current process
        self.process = os.getpid()
        if channel is not None:
            channel = weakref(channel)
        self._channel = channel
        self._information_pulled = False

    def pull_information(self):
        """A helper function that pulls all frame-related information into
        the object so that this information is available after the log
        record was closed.
        """
        if self._information_pulled:
            return
        # due to how cached_property is implemented, the attribute access
        # has the side effect of caching the attribute on the instance of
        # the class.
        for key in self._pullable_information:
            getattr(self, key)
        self._information_pulled = True

    def close(self):
        """Closes the log record.  This will set the frame and calling
        frame to `None` and frame-related information will no longer be
        available unless it was pulled in first (:meth:`pull_information`).
        This makes a log record safe for pickling and will clean up
        memory that might be still referenced by the frames.
        """
        self.frame = None
        self.calling_frame = None

    @cached_property
    def message(self):
        """The formatted message."""
        if not (self.args or self.kwargs):
            return self.msg
        try:
            return self.msg.format(*self.args, **self.kwargs)
        except Exception, e:
            # this obviously will not give a proper error message if the
            # information was not pulled and the log record no longer has
            # access to the frame.  But there is not much we can do about
            # that.
            raise TypeError('Could not format message with provided '
                            'arguments: {err}\n  msg=\'{msg}\'\n  args={args} '
                            '\n  kwargs={kwargs}.\n'
                            'Happened in file {file}, line {lineno}'.format(
                err=e, msg=self.msg.encode('utf-8'), args=self.args,
                kwargs=self.kwargs, file=self.filename.encode('utf-8'),
                lineno=self.lineno
            ))

    @cached_property
    def level_name(self):
        """The name of the record's level."""
        return get_level_name(self.level)

    @cached_property
    def calling_frame(self):
        """The frame in which the record has been created.  This only
        exists for as long the log record is not closed.
        """
        frm = self.frame
        globs = globals()
        while frm is not None and frm.f_globals is globs:
            frm = frm.f_back
        return frm

    @cached_property
    def func_name(self):
        """The name of the function that triggered the log call if
        available.  Requires a frame or that :meth:`pull_information`
        was called before.
        """
        cf = self.calling_frame
        if cf is not None:
            return cf.f_code.co_name

    @cached_property
    def module(self):
        """The name of the module that triggered the log call if
        available.  Requires a frame or that :meth:`pull_information`
        was called before.
        """
        cf = self.calling_frame
        if cf is not None:
            return cf.f_globals.get('__name__')

    @cached_property
    def filename(self):
        """The filename of the module in which the record has been created.
        Requires a frame or that :meth:`pull_information` was called before.
        """
        cf = self.calling_frame
        if cf is not None:
            return os.path.abspath(cf.f_code.co_filename) \
                .decode(sys.getfilesystemencoding() or 'utf-8', 'replace')

    @cached_property
    def lineno(self):
        """The line number of the file in which the record has been created.
        Requires a frame or that :meth:`pull_information` was called before.
        """
        cf = self.calling_frame
        if cf is not None:
            return cf.f_lineno

    @cached_property
    def thread(self):
        """The ident of the thread.  This is evaluated late and means that
        if the log record is passed to another thread, :meth:`pull_information`
        was called in the old thread.
        """
        return thread.get_ident()

    @cached_property
    def thread_name(self):
        """The name of the thread.  This is evaluated late and means that
        if the log record is passed to another thread, :meth:`pull_information`
        was called in the old thread.
        """
        return threading.currentThread().name

    @cached_property
    def process_name(self):
        """The name of the process in which the record has been created."""
        # Errors may occur if multiprocessing has not finished loading
        # yet - e.g. if a custom import hook causes third-party code
        # to run when multiprocessing calls import. See issue 8200
        # for an example
        mp = sys.modules.get('multiprocessing')
        if mp is not None:
            try:
                return mp.current_process().name
            except Exception:
                pass

    def format_exception(self):
        """Returns the formatted exception which caused this record to be
        created.
        """
        if self.exc_info is not None:
            lines = traceback.format_exception(*self.exc_info)
            rv = ''.join(lines).decode('utf-8', 'replace')
            return rv.rstrip()

    @property
    def channel(self):
        """The channel that created the log record.  Might not exist because
        a log record does not have to be created from a logger to be
        handled by logbook.  If this is set, it will point to an object
        that implements the :class:`~logbook.base.RecordDispatcher`
        interface.
        """
        if self._channel is not None:
            return self._channel()


class LoggerMixin(object):
    """This mixin class defines and implements the "usual" logger
    interface (i.e. the descriptive logging functions).

    Classes using this mixin have to implement a :meth:`handle` method which
    takes a :class:`LogRecord` and passes it along.
    """

    #: The name of the minimium logging level required for records to be
    #: created.
    level_name = _level_name_property()

    def debug(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.DEBUG`
        """
        if DEBUG >= self.level:
            self._log(DEBUG, args, kwargs)

    def info(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.INFO`
        """
        if INFO >= self.level:
            self._log(INFO, args, kwargs)

    def warn(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.WARNING`.  This function has an alias
        named :meth:`warning`.
        """
        if WARNING >= self.level:
            self._log(WARNING, args, kwargs)

    warning = warn

    def notice(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.NOTICE`
        """
        if NOTICE >= self.level:
            self._log(NOTICE, args, kwargs)

    def error(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.ERROR`
        """
        if ERROR >= self.level:
            self._log(ERROR, args, kwargs)

    def exception(self, *args, **kwargs):
        """Works exactly like :meth:`error` just that the message
        is optional and exception information is recorded.
        """
        if 'exc_info' not in kwargs:
            exc_info = sys.exc_info()
            assert exc_info[0] is not None, 'no exception occurred'
            kwargs.setdefault('exc_info', sys.exc_info())
        return self.error(*args, **kwargs)

    def catch_exceptions(self, *args, **kwargs):
        """A context manager that catches exceptions and calls
        :meth:`exception` for exceptions caught that way.  Example::

            with logger.catch_exceptions():
                execute_code_that_might_fail()
        """
        if not args:
            args = ('Uncaught exception occurred',)
        return _ExceptionCatcher(self, args, kwargs)

    def critical(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.CRITICAL`
        """
        if CRITICAL >= self.level:
            self._log(CRITICAL, args, kwargs)

    def log(self, level, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to the `level` parameter.  Because custom levels are not
        supported by logbook, this method is mainly used to avoid
        the use of reflection (e.g.: :func:`getattr`) for programmatic
        logging.
        """
        level = lookup_level(level)
        if level >= self.level:
            self._log(level, args, kwargs)

    def _log(self, level, args, kwargs):
        msg, args = args[0], args[1:]
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', None)
        record = LogRecord(self.name, level, msg, args, kwargs, exc_info,
                           extra, sys._getframe(), self)
        try:
            self.handle(record)
        finally:
            record.close()


class RecordDispatcher(object):
    """A record dispatcher is the internal base class that implements
    the logic used by the :class:`~logbook.Logger`.
    """

    def __init__(self, name=None, level=NOTSET):
        #: the name of the record dispatcher
        self.name = name
        #: list of handlers specific for this record dispatcher
        self.handlers = []
        #: optionally the name of the group this logger belongs to
        self.group = None
        #: the level of the record dispatcher as integer
        self.level = level

    disabled = _group_reflected_property('disabled', False)
    level = _group_reflected_property('level', NOTSET, fallback=NOTSET)

    def handle(self, record):
        """Call the handlers for the specified record.  This is
        invoked automatically when a record should be handled.
        The default implementation checks if the dispatcher is disabled
        and if the record level is greater than the level of the
        record dispatcher.  In that case it will process the record
        (:meth:`process_record`) and call the handlers
        (:meth:`call_handlers`).
        """
        if not self.disabled and record.level >= self.level:
            self.process_record(record)
            self.call_handlers(record)

    def process_record(self, record):
        """Processes the record with all context specific processors.  This
        can be overriden to also inject additional information as necessary
        that can be provided by this record dispatcher.
        """
        for processor in Processor.iter_context_objects():
            processor(record)

    def call_handlers(self, record):
        """Pass a record to all relevant handlers in the following
        order:

        -   per-dispatcher handlers are handled first
        -   afterwards all the current context handlers (first
            thread bound, then application bound) until one of the
            handlers is set up to not bubble up
        """
        # for performance reasons records are only processed if at
        # least one of the handlers has a higher level than the
        # record.
        record_processed = False

        # logger attached handlers are always handled and before the
        # context specific handlers are running.  There is no way to
        # disable those unless by removing the handlers.  They will
        # always bubble
        for handler in self.handlers:
            if record.level >= handler.level:
                handler.handle(record)

        # after that, context specific handlers run (this includes the
        # global handlers)
        for handler in Handler.iter_context_objects():
            if record.level >= handler.level:
                # we are about to handle the record.  If it was not yet
                # processed by context-specific record processors we
                # have to do that now and remeber that we processed
                # the record already.
                if not record_processed:
                    self.process_record(record)
                    record_processed = True

                # a filter can still veto the handling of the record.
                if handler.filter is not None \
                   and not handler.filter(record, handler):
                    continue

                # handle the record.  If the record was handled and
                # the record is not bubbling we can abort now.
                if handler.handle(record) and not handler.bubble:
                    break

    def process_record(self, record):
        """Called before handling the record.  This can be used to stuff
        additional information into a log record.
        """
        if self.group is not None:
            self.group.process_record(record)


class Logger(RecordDispatcher, LoggerMixin):
    """Instances of the Logger class represent a single logging channel.
    A "logging channel" indicates an area of an application. Exactly
    how an "area" is defined is up to the application developer.

    Names used by logbook should be descriptive and are intended for user
    display, not for filtering.  Filtering should happen based on the
    context information instead.

    A logger internally is a subclass of a
    :class:`~logbook.base.RecordDispatcher` that implements the actual
    logic.  If you want to implement a custom logger class, have a look
    at the interface of that class as well.
    """


class LoggerGroup(LoggerMixin):
    """A LoggerGroup represents a group of loggers while behaving like one."""

    def __init__(self, loggers=None, level=NOTSET):
        if loggers is None:
            loggers = []
        self.loggers = loggers
        self.level = lookup_level(level)
        self.disabled = False

    def add_logger(self, logger):
        """Adds a logger to this group."""
        logger.group = self
        self.loggers.append(logger)

    def handle(self, record):
        for logger in self.loggers:
            logger.handle(record)


class log_warnings_to(object):
    """A context manager that copies and restores the warnings filter upon
    exiting the context, and logs warnings using the logbook system.

    The 'record' argument specifies whether warnings should be captured by a
    custom implementation of warnings.showwarning() and be appended to a list
    returned by the context manager. Otherwise None is returned by the context
    manager. The objects appended to the list are arguments whose attributes
    mirror the arguments to showwarning().
    """

    def __init__(self, logger):
        self._logger = logger
        self._entered = False

    def __enter__(self):
        if self._entered:
            raise RuntimeError("Cannot enter %r twice" % self)
        self._entered = True
        if self._save_filters:
            self._filters = warnings.filters
            warnings.filters = self._filters[:]
        self._showwarning = warnings.showwarning
        def showwarning(message, category, filename, lineno,
                        file=None, line=None):
            formatted = warnings.formatwarning(message, category, filename,
                                               lineno, line)
            self._logger.warning(formatted)
        warnings.showwarning = showwarning

    def __exit__(self, *exc_info):
        if not self._entered:
            raise RuntimeError("Cannot exit %r without entering first" % self)
        if self._save_filters:
            warnings.filters = self._filters
        warnings.showwarning = self._showwarning


from logbook.handlers import Handler
