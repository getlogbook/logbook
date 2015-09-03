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
import traceback
from itertools import chain
from weakref import ref as weakref
from datetime import datetime
from logbook import helpers
from logbook.concurrency import thread_get_name, thread_get_ident, greenlet_get_ident

from logbook.helpers import to_safe_json, parse_iso8601, cached_property, \
     PY2, u, string_types, iteritems, integer_types
try:
    from logbook._speedups import group_reflected_property, \
         ContextStackManager, StackedObject
except ImportError:
    from logbook._fallback import group_reflected_property, \
         ContextStackManager, StackedObject

_datetime_factory = datetime.utcnow
def set_datetime_format(datetime_format):
    """
    Set the format for the datetime objects created, which are then
    made available as the :py:attr:`LogRecord.time` attribute of
    :py:class:`LogRecord` instances.

    :param datetime_format: Indicates how to generate datetime objects.  Possible values are:

         "utc"
             :py:attr:`LogRecord.time` will be a datetime in UTC time zone (but not time zone aware)
         "local"
             :py:attr:`LogRecord.time` will be a datetime in local time zone (but not time zone aware)

    This function defaults to creating datetime objects in UTC time,
    using `datetime.utcnow()
    <http://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow>`_,
    so that logbook logs all times in UTC time by default.  This is
    recommended in case you have multiple software modules or
    instances running in different servers in different time zones, as
    it makes it simple and less error prone to correlate logging
    across the different servers.

    On the other hand if all your software modules are running in the
    same time zone and you have to correlate logging with third party
    modules already logging in local time, it can be more convenient
    to have logbook logging to local time instead of UTC.  Local time
    logging can be enabled like this::

       import logbook
       from datetime import datetime
       logbook.set_datetime_format("local")

    """
    global _datetime_factory
    if datetime_format == "utc":
        _datetime_factory = datetime.utcnow
    elif datetime_format == "local":
        _datetime_factory = datetime.now
    else:
        raise ValueError("Invalid value %r.  Valid values are 'utc' and 'local'." % (datetime_format,))

# make sure to sync these up with _speedups.pyx
CRITICAL = 15
ERROR = 14
WARNING = 13
NOTICE = 12
INFO = 11
DEBUG = 10
TRACE = 9
NOTSET = 0

_level_names = {
    CRITICAL:   'CRITICAL',
    ERROR:      'ERROR',
    WARNING:    'WARNING',
    NOTICE:     'NOTICE',
    INFO:       'INFO',
    DEBUG:      'DEBUG',
    TRACE:      'TRACE',
    NOTSET:     'NOTSET'
}
_reverse_level_names = dict((v, k) for (k, v) in iteritems(_level_names))
_missing = object()


# on python 3 we can savely assume that frame filenames will be in
# unicode, on Python 2 we have to apply a trick.
if PY2:
    def _convert_frame_filename(fn):
        if isinstance(fn, unicode):
            fn = fn.decode(sys.getfilesystemencoding() or 'utf-8',
                           'replace')
        return fn
else:
    def _convert_frame_filename(fn):
        return fn


def level_name_property():
    """Returns a property that reflects the level as name from
    the internal level attribute.
    """

    def _get_level_name(self):
        return get_level_name(self.level)

    def _set_level_name(self, level):
        self.level = lookup_level(level)
    return property(_get_level_name, _set_level_name,
                    doc='The level as unicode string')


def lookup_level(level):
    """Return the integer representation of a logging level."""
    if isinstance(level, integer_types):
        return level
    try:
        return _reverse_level_names[level]
    except KeyError:
        raise LookupError('unknown level name %s' % level)


def get_level_name(level):
    """Return the textual representation of logging level 'level'."""
    try:
        return _level_names[level]
    except KeyError:
        raise LookupError('unknown level')


class ExtraDict(dict):
    """A dictionary which returns ``u''`` on missing keys."""

    if sys.version_info[:2] < (2, 5):
        def __getitem__(self, key):
            try:
                return dict.__getitem__(self, key)
            except KeyError:
                return u('')
    else:
        def __missing__(self, key):
            return u('')

    def copy(self):
        return self.__class__(self)

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


class ContextObject(StackedObject):
    """An object that can be bound to a context.  It is managed by the
    :class:`ContextStackManager`"""

    #: subclasses have to instanciate a :class:`ContextStackManager`
    #: object on this attribute which is then shared for all the
    #: subclasses of it.
    stack_manager = None

    def push_greenlet(self):
        """Pushes the context object to the greenlet stack."""
        self.stack_manager.push_greenlet(self)

    def pop_greenlet(self):
        """Pops the context object from the stack."""
        popped = self.stack_manager.pop_greenlet()
        assert popped is self, 'popped unexpected object'

    def push_thread(self):
        """Pushes the context object to the thread stack."""
        self.stack_manager.push_thread(self)

    def pop_thread(self):
        """Pops the context object from the stack."""
        popped = self.stack_manager.pop_thread()
        assert popped is self, 'popped unexpected object'

    def push_application(self):
        """Pushes the context object to the application stack."""
        self.stack_manager.push_application(self)

    def pop_application(self):
        """Pops the context object from the stack."""
        popped = self.stack_manager.pop_application()
        assert popped is self, 'popped unexpected object'


class NestedSetup(StackedObject):
    """A nested setup can be used to configure multiple handlers
    and processors at once.
    """

    def __init__(self, objects=None):
        self.objects = list(objects or ())

    def push_application(self):
        for obj in self.objects:
            obj.push_application()

    def pop_application(self):
        for obj in reversed(self.objects):
            obj.pop_application()

    def push_thread(self):
        for obj in self.objects:
            obj.push_thread()

    def pop_thread(self):
        for obj in reversed(self.objects):
            obj.pop_thread()

    def push_greenlet(self):
        for obj in self.objects:
            obj.push_greenlet()

    def pop_greenlet(self):
        for obj in reversed(self.objects):
            obj.pop_greenlet()


class Processor(ContextObject):
    """Can be pushed to a stack to inject additional information into
    a log record as necessary::

        def inject_ip(record):
            record.extra['ip'] = '127.0.0.1'

        with Processor(inject_ip):
            ...
    """

    stack_manager = ContextStackManager()

    def __init__(self, callback=None):
        #: the callback that was passed to the constructor
        self.callback = callback

    def process(self, record):
        """Called with the log record that should be overridden.  The default
        implementation calls :attr:`callback` if it is not `None`.
        """
        if self.callback is not None:
            self.callback(record)


class _InheritedType(object):
    __slots__ = ()

    def __repr__(self):
        return 'Inherit'

    def __reduce__(self):
        return 'Inherit'
Inherit = _InheritedType()


class Flags(ContextObject):
    """Allows flags to be pushed on a flag stack.  Currently two flags
    are available:

    `errors`
        Can be set to override the current error behaviour.  This value is
        used when logging calls fail.  The default behaviour is spitting
        out the stacktrace to stderr but this can be overridden:

        =================== ==========================================
        ``'silent'``        fail silently
        ``'raise'``         raise a catchable exception
        ``'print'``         print the stacktrace to stderr (default)
        =================== ==========================================

    `introspection`
        Can be used to disable frame introspection.  This can give a
        speedup on production systems if you are using a JIT compiled
        Python interpreter such as pypy.  The default is `True`.

        Note that the default setup of some of the handler (mail for
        instance) includes frame dependent information which will
        not be available when introspection is disabled.

    Example usage::

        with Flags(errors='silent'):
            ...
    """
    stack_manager = ContextStackManager()

    def __init__(self, **flags):
        self.__dict__.update(flags)

    @staticmethod
    def get_flag(flag, default=None):
        """Looks up the current value of a specific flag."""
        for flags in Flags.stack_manager.iter_context_objects():
            val = getattr(flags, flag, Inherit)
            if val is not Inherit:
                return val
        return default


def _create_log_record(cls, dict):
    """Extra function for reduce because on Python 3 unbound methods
    can no longer be pickled.
    """
    return cls.from_dict(dict)


class LogRecord(object):
    """A LogRecord instance represents an event being logged.

    LogRecord instances are created every time something is logged. They
    contain all the information pertinent to the event being logged. The
    main information passed in is in msg and args
    """
    _pullable_information = frozenset((
        'func_name', 'module', 'filename', 'lineno', 'process_name', 'thread',
        'thread_name', 'greenlet', 'formatted_exception', 'message', 'exception_name',
        'exception_message'
    ))
    _noned_on_close = frozenset(('exc_info', 'frame', 'calling_frame'))

    #: can be overriden by a handler to not close the record.  This could
    #: lead to memory leaks so it should be used carefully.
    keep_open = False

    #: the time of the log record creation as :class:`datetime.datetime`
    #: object.  This information is unavailable until the record was
    #: heavy initialized.
    time = None

    #: a flag that is `True` if the log record is heavy initialized which
    #: is not the case by default.
    heavy_initialized = False

    #: a flag that is `True` when heavy initialization is no longer possible
    late = False

    #: a flag that is `True` when all the information was pulled from the
    #: information that becomes unavailable on close.
    information_pulled = False

    def __init__(self, channel, level, msg, args=None, kwargs=None,
                 exc_info=None, extra=None, frame=None, dispatcher=None, frame_correction=0):
        #: the name of the logger that created it or any other textual
        #: channel description.  This is a descriptive name and can be
        #: used for filtering.
        self.channel = channel
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
        #: This parameter can also be ``True``, which would cause the exception info tuple
        #: to be fetched for you.
        if not exc_info:
            # this is a special case where exc_info=False can be passed in theory,
            # and it should be the same as exc_info=None
            exc_info = None
        self.exc_info = exc_info
        #: optional extra information as dictionary.  This is the place
        #: where custom log processors can attach custom context sensitive
        #: data.
        self.extra = ExtraDict(extra or ())
        #: If available, optionally the interpreter frame that pulled the
        #: heavy init.  This usually points to somewhere in the dispatcher.
        #: Might not be available for all calls and is removed when the log
        #: record is closed.
        self.frame = frame
        #: A positive integer telling the number of frames to go back from
        #: the frame which triggered the log entry. This is mainly useful
        #: for decorators that want to show that the log was emitted from
        #: form the function they decorate
        self.frame_correction = frame_correction
        #: the PID of the current process
        self.process = None
        if dispatcher is not None:
            dispatcher = weakref(dispatcher)
        self._dispatcher = dispatcher

    def heavy_init(self):
        """Does the heavy initialization that could be expensive.  This must
        not be called from a higher stack level than when the log record was
        created and the later the initialization happens, the more off the
        date information will be for example.

        This is internally used by the record dispatching system and usually
        something not to worry about.
        """
        if self.heavy_initialized:
            return
        assert not self.late, 'heavy init is no longer possible'
        self.heavy_initialized = True
        self.process = os.getpid()
        self.time = _datetime_factory()
        if self.frame is None and Flags.get_flag('introspection', True):
            self.frame = sys._getframe(1)
        if self.exc_info is True:
            self.exc_info = sys.exc_info()

    def pull_information(self):
        """A helper function that pulls all frame-related information into
        the object so that this information is available after the log
        record was closed.
        """
        if self.information_pulled:
            return
        # due to how cached_property is implemented, the attribute access
        # has the side effect of caching the attribute on the instance of
        # the class.
        for key in self._pullable_information:
            getattr(self, key)
        self.information_pulled = True

    def close(self):
        """Closes the log record.  This will set the frame and calling
        frame to `None` and frame-related information will no longer be
        available unless it was pulled in first (:meth:`pull_information`).
        This makes a log record safe for pickling and will clean up
        memory that might be still referenced by the frames.
        """
        for key in self._noned_on_close:
            setattr(self, key, None)
        self.late = True

    def __reduce_ex__(self, protocol):
        return _create_log_record, (type(self), self.to_dict())

    def to_dict(self, json_safe=False):
        """Exports the log record into a dictionary without the information
        that cannot be safely serialized like interpreter frames and
        tracebacks.
        """
        self.pull_information()
        rv = {}
        for key, value in iteritems(self.__dict__):
            if key[:1] != '_' and key not in self._noned_on_close:
                rv[key] = value
        # the extra dict is exported as regular dict
        rv['extra'] = dict(rv['extra'])
        if json_safe:
            return to_safe_json(rv)
        return rv

    @classmethod
    def from_dict(cls, d):
        """Creates a log record from an exported dictionary.  This also
        supports JSON exported dictionaries.
        """
        rv = object.__new__(cls)
        rv.update_from_dict(d)
        return rv

    def update_from_dict(self, d):
        """Like the :meth:`from_dict` classmethod, but will update the
        instance in place.  Helpful for constructors.
        """
        self.__dict__.update(d)
        for key in self._noned_on_close:
            setattr(self, key, None)
        self._information_pulled = True
        self._channel = None
        if isinstance(self.time, string_types):
            self.time = parse_iso8601(self.time)
        self.extra = ExtraDict(self.extra)
        return self

    def _format_message(self, msg, *args, **kwargs):
        """Called if the record's message needs to be formatted.
        Subclasses can implement their own formatting.
        """
        return msg.format(*args, **kwargs)

    @cached_property
    def message(self):
        """The formatted message."""
        if not (self.args or self.kwargs):
            return self.msg
        try:
            try:
                return self._format_message(self.msg, *self.args, **self.kwargs)
            except UnicodeDecodeError:
                # Assume an unicode message but mixed-up args
                msg = self.msg.encode('utf-8', 'replace')
                return self._format_message(msg, *self.args, **self.kwargs)
            except (UnicodeEncodeError, AttributeError):
                # we catch AttributeError since if msg is bytes, it won't have the 'format' method
                if sys.exc_info()[0] is AttributeError and (PY2 or not isinstance(self.msg, bytes)):
                    # this is not the case we thought it is...
                    raise
                # Assume encoded message with unicode args.
                # The assumption of utf8 as input encoding is just a guess,
                # but this codepath is unlikely (if the message is a constant
                # string in the caller's source file)
                msg = self.msg.decode('utf-8', 'replace')
                return self._format_message(msg, *self.args, **self.kwargs)

        except Exception:
            # this obviously will not give a proper error message if the
            # information was not pulled and the log record no longer has
            # access to the frame.  But there is not much we can do about
            # that.
            e = sys.exc_info()[1]
            errormsg = ('Could not format message with provided '
                       'arguments: {err}\n  msg={msg!r}\n  '
                       'args={args!r} \n  kwargs={kwargs!r}.\n'
                       'Happened in file {file}, line {lineno}').format(
                err=e, msg=self.msg, args=self.args,
                kwargs=self.kwargs, file=self.filename,
                lineno=self.lineno
            )
            if PY2:
                errormsg = errormsg.encode('utf-8')
            raise TypeError(errormsg)

    level_name = level_name_property()

    @cached_property
    def calling_frame(self):
        """The frame in which the record has been created.  This only
        exists for as long the log record is not closed.
        """
        frm = self.frame
        globs = globals()
        while frm is not None and frm.f_globals is globs:
            frm = frm.f_back

        for _ in helpers.xrange(self.frame_correction):
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
            fn = cf.f_code.co_filename
            if fn[:1] == '<' and fn[-1:] == '>':
                return fn
            return _convert_frame_filename(os.path.abspath(fn))

    @cached_property
    def lineno(self):
        """The line number of the file in which the record has been created.
        Requires a frame or that :meth:`pull_information` was called before.
        """
        cf = self.calling_frame
        if cf is not None:
            return cf.f_lineno

    @cached_property
    def greenlet(self):
        """The ident of the greenlet.  This is evaluated late and means that
        if the log record is passed to another greenlet, :meth:`pull_information`
        was called in the old greenlet.
        """
        return greenlet_get_ident()

    @cached_property
    def thread(self):
        """The ident of the thread.  This is evaluated late and means that
        if the log record is passed to another thread, :meth:`pull_information`
        was called in the old thread.
        """
        return thread_get_ident()

    @cached_property
    def thread_name(self):
        """The name of the thread.  This is evaluated late and means that
        if the log record is passed to another thread, :meth:`pull_information`
        was called in the old thread.
        """
        return thread_get_name()

    @cached_property
    def process_name(self):
        """The name of the process in which the record has been created."""
        # Errors may occur if multiprocessing has not finished loading
        # yet - e.g. if a custom import hook causes third-party code
        # to run when multiprocessing calls import. See issue 8200
        # for an example
        mp = sys.modules.get('multiprocessing')
        if mp is not None:  # pragma: no cover
            try:
                return mp.current_process().name
            except Exception:
                pass

    @cached_property
    def formatted_exception(self):
        """The formatted exception which caused this record to be created
        in case there was any.
        """
        if self.exc_info is not None and self.exc_info != (None, None, None):
            rv = ''.join(traceback.format_exception(*self.exc_info))
            if PY2:
                rv = rv.decode('utf-8', 'replace')
            return rv.rstrip()

    @cached_property
    def exception_name(self):
        """The name of the exception."""
        if self.exc_info is not None:
            cls = self.exc_info[0]
            return u(cls.__module__ + '.' + cls.__name__)

    @property
    def exception_shortname(self):
        """An abbreviated exception name (no import path)"""
        return self.exception_name.rsplit('.')[-1]

    @cached_property
    def exception_message(self):
        """The message of the exception."""
        if self.exc_info is not None:
            val = self.exc_info[1]
            try:
                if PY2:
                    return unicode(val)
                else:
                    return str(val)
            except UnicodeError:
                return str(val).decode('utf-8', 'replace')

    @property
    def dispatcher(self):
        """The dispatcher that created the log record.  Might not exist because
        a log record does not have to be created from a logger or other
        dispatcher to be handled by logbook.  If this is set, it will point to
        an object that implements the :class:`~logbook.base.RecordDispatcher`
        interface.
        """
        if self._dispatcher is not None:
            return self._dispatcher()


class LoggerMixin(object):
    """This mixin class defines and implements the "usual" logger
    interface (i.e. the descriptive logging functions).

    Classes using this mixin have to implement a :meth:`!handle` method which
    takes a :class:`~logbook.LogRecord` and passes it along.
    """

    #: The name of the minimium logging level required for records to be
    #: created.
    level_name = level_name_property()

    def trace(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.TRACE`.
        """
        if not self.disabled and TRACE >= self.level:
            self._log(TRACE, args, kwargs)


    def debug(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.DEBUG`.
        """
        if not self.disabled and DEBUG >= self.level:
            self._log(DEBUG, args, kwargs)

    def info(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.INFO`.
        """
        if not self.disabled and INFO >= self.level:
            self._log(INFO, args, kwargs)

    def warn(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.WARNING`.  This function has an alias
        named :meth:`warning`.
        """
        if not self.disabled and WARNING >= self.level:
            self._log(WARNING, args, kwargs)

    def warning(self, *args, **kwargs):
        """Alias for :meth:`warn`."""
        return self.warn(*args, **kwargs)

    def notice(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.NOTICE`.
        """
        if not self.disabled and NOTICE >= self.level:
            self._log(NOTICE, args, kwargs)

    def error(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.ERROR`.
        """
        if not self.disabled and ERROR >= self.level:
            self._log(ERROR, args, kwargs)

    def exception(self, *args, **kwargs):
        """Works exactly like :meth:`error` just that the message
        is optional and exception information is recorded.
        """
        if self.disabled or ERROR < self.level:
            return
        if not args:
            args = ('Uncaught exception occurred',)
        if 'exc_info' not in kwargs:
            exc_info = sys.exc_info()
            assert exc_info[0] is not None, 'no exception occurred'
            kwargs.setdefault('exc_info', sys.exc_info())
        return self.error(*args, **kwargs)

    def critical(self, *args, **kwargs):
        """Logs a :class:`~logbook.LogRecord` with the level set
        to :data:`~logbook.CRITICAL`.
        """
        if not self.disabled and CRITICAL >= self.level:
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

    def catch_exceptions(self, *args, **kwargs):
        """A context manager that catches exceptions and calls
        :meth:`exception` for exceptions caught that way.  Example:

        .. code-block:: python

            with logger.catch_exceptions():
                execute_code_that_might_fail()
        """
        if not args:
            args = ('Uncaught exception occurred',)
        return _ExceptionCatcher(self, args, kwargs)

    def _log(self, level, args, kwargs):
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', None)
        frame_correction = kwargs.pop('frame_correction', 0)
        self.make_record_and_handle(level, args[0], args[1:], kwargs,
                                    exc_info, extra, frame_correction)


class RecordDispatcher(object):
    """A record dispatcher is the internal base class that implements
    the logic used by the :class:`~logbook.Logger`.
    """

    #: If this is set to `True` the dispatcher information will be suppressed
    #: for log records emitted from this logger.
    suppress_dispatcher = False

    def __init__(self, name=None, level=NOTSET):
        #: the name of the record dispatcher
        self.name = name
        #: list of handlers specific for this record dispatcher
        self.handlers = []
        #: optionally the name of the group this logger belongs to
        self.group = None
        #: the level of the record dispatcher as integer
        self.level = level

    disabled = group_reflected_property('disabled', False)
    level = group_reflected_property('level', NOTSET, fallback=NOTSET)

    def handle(self, record):
        """Call the handlers for the specified record.  This is
        invoked automatically when a record should be handled.
        The default implementation checks if the dispatcher is disabled
        and if the record level is greater than the level of the
        record dispatcher.  In that case it will call the handlers
        (:meth:`call_handlers`).
        """
        if not self.disabled and record.level >= self.level:
            self.call_handlers(record)

    def make_record_and_handle(self, level, msg, args, kwargs, exc_info,
                               extra, frame_correction):
        """Creates a record from some given arguments and heads it
        over to the handling system.
        """
        # The channel information can be useful for some use cases which is
        # why we keep it on there.  The log record however internally will
        # only store a weak reference to the channel, so it might disappear
        # from one instruction to the other.  It will also disappear when
        # a log record is transmitted to another process etc.
        channel = None
        if not self.suppress_dispatcher:
            channel = self

        record = LogRecord(self.name, level, msg, args, kwargs, exc_info,
                           extra, None, channel, frame_correction)

        # after handling the log record is closed which will remove some
        # referenes that would require a GC run on cpython.  This includes
        # the current stack frame, exception information.  However there are
        # some use cases in keeping the records open for a little longer.
        # For example the test handler keeps log records open until the
        # test handler is closed to allow assertions based on stack frames
        # and exception information.
        try:
            self.handle(record)
        finally:
            record.late = True
            if not record.keep_open:
                record.close()

    def call_handlers(self, record):
        """Pass a record to all relevant handlers in the following
        order:

        -   per-dispatcher handlers are handled first
        -   afterwards all the current context handlers in the
            order they were pushed

        Before the first handler is invoked, the record is processed
        (:meth:`process_record`).
        """
        # for performance reasons records are only heavy initialized
        # and processed if at least one of the handlers has a higher
        # level than the record and that handler is not a black hole.
        record_initialized = False

        # Both logger attached handlers as well as context specific
        # handlers are handled one after another.  The latter also
        # include global handlers.
        for handler in chain(self.handlers,
                             Handler.stack_manager.iter_context_objects()):
            # skip records that this handler is not interested in based
            # on the record and handler level or in case this method was
            # overridden on some custom logic.
            if not handler.should_handle(record):
                continue

            # first case of blackhole (without filter).
            # this should discard all further processing and we don't have to heavy_init to know that...
            if handler.filter is None and handler.blackhole:
                break

            # we are about to handle the record.  If it was not yet
            # processed by context-specific record processors we
            # have to do that now and remeber that we processed
            # the record already.
            if not record_initialized:
                record.heavy_init()
                self.process_record(record)
                record_initialized = True


            # a filter can still veto the handling of the record.  This
            # however is already operating on an initialized and processed
            # record.  The impact is that filters are slower than the
            # handler's should_handle function in case there is no default
            # handler that would handle the record (delayed init).
            if handler.filter is not None \
               and not handler.filter(record, handler):
                continue

            # We might have a filter, so now that we know we *should* handle
            # this record, we should consider the case of us being a black hole...
            if handler.blackhole:
                break


            # handle the record.  If the record was handled and
            # the record is not bubbling we can abort now.
            if handler.handle(record) and not handler.bubble:
                break

    def process_record(self, record):
        """Processes the record with all context specific processors.  This
        can be overriden to also inject additional information as necessary
        that can be provided by this record dispatcher.
        """
        if self.group is not None:
            self.group.process_record(record)
        for processor in Processor.stack_manager.iter_context_objects():
            processor.process(record)


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


class LoggerGroup(object):
    """A LoggerGroup represents a group of loggers.  It cannot emit log
    messages on its own but it can be used to set the disabled flag and
    log level of all loggers in the group.

    Furthermore the :meth:`process_record` method of the group is called
    by any logger in the group which by default calls into the
    :attr:`processor` callback function.
    """

    def __init__(self, loggers=None, level=NOTSET, processor=None):
        #: a list of all loggers on the logger group.  Use the
        #: :meth:`add_logger` and :meth:`remove_logger` methods to add
        #: or remove loggers from this list.
        self.loggers = []
        if loggers is not None:
            for logger in loggers:
                self.add_logger(logger)

        #: the level of the group.  This is reflected to the loggers
        #: in the group unless they overrode the setting.
        self.level = lookup_level(level)
        #: the disabled flag for all loggers in the group, unless
        #: the loggers overrode the setting.
        self.disabled = False
        #: an optional callback function that is executed to process
        #: the log records of all loggers in the group.
        self.processor = processor

    def add_logger(self, logger):
        """Adds a logger to this group."""
        assert logger.group is None, 'Logger already belongs to a group'
        logger.group = self
        self.loggers.append(logger)

    def remove_logger(self, logger):
        """Removes a logger from the group."""
        self.loggers.remove(logger)
        logger.group = None

    def process_record(self, record):
        """Like :meth:`Logger.process_record` but for all loggers in
        the group.  By default this calls into the :attr:`processor`
        function is it's not `None`.
        """
        if self.processor is not None:
            self.processor(record)


_default_dispatcher = RecordDispatcher()


def dispatch_record(record):
    """Passes a record on to the handlers on the stack.  This is useful when
    log records are created programmatically and already have all the
    information attached and should be dispatched independent of a logger.
    """
    _default_dispatcher.call_handlers(record)


# at that point we are save to import handler
from logbook.handlers import Handler
