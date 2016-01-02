Stacks in Logbook
=================

Logbook keeps three stacks internally currently:

-   one for the :class:`~logbook.Handler`\s: each handler is handled from
    stack top to bottom.  When a record was handled it depends on the
    :attr:`~logbook.Handler.bubble` flag of the handler if it should still
    be processed by the next handler on the stack.
-   one for the :class:`~logbook.Processor`\s: each processor in the stack
    is applied on a record before the log record is handled by the
    handler.
-   one for the :class:`~logbook.Flags`: this stack manages simple flags
    such as how errors during logging should be processed or if stackframe
    introspection should be used etc.

General Stack Management
------------------------

Generally all objects that are management by stacks have a common
interface (:class:`~logbook.base.StackedObject`) and can be used in
combination with the :class:`~logbook.NestedSetup` class.

Commonly stacked objects are used with a context manager (`with`
statement)::

    with context_object.threadbound():
        # this is managed for this thread only
        ...

    with context_object.applicationbound():
        # this is managed for all applications
        ...

Alternatively you can also use `try`/`finally`::

    context_object.push_thread()
    try:
        # this is managed for this thread only
        ...
    finally:
        context_object.pop_thread()

    context_object.push_application()
    try:
        # this is managed for all applications
        ...
    finally:
        context_object.pop_application()

It's very important that you will always pop from the stack again unless
you really want the change to last until the application closes down,
which probably is not the case.

If you want to push and pop multiple stacked objects at the same time, you
can use the :class:`~logbook.NestedSetup`::

    setup = NestedSetup([stacked_object1, stacked_object2])
    with setup.threadbound():
        # both objects are now bound to the thread's stack
        ...

Sometimes a stacked object can be passed to one of the functions or
methods in Logbook.  If any stacked object can be passed, this is usually
called the `setup`.  This is for example the case when you specify a
handler or processor for things like the
:class:`~logbook.queues.ZeroMQSubscriber`.

Handlers
--------

Handlers use the features of the stack the most because not only do they
stack, but they also specify how stack handling is supposed to work.  Each
handler can decide if it wants to process the record, and then it has a
flag (the :attr:`~logbook.Handler.bubble` flag) which specifies if the
next handler in the chain is supposed to get this record passed to.

If a handler is bubbling it will give the record to the next handler,
even if it was properly handled.  If it's not, it will stop promoting
handlers further down the chain.  Additionally there are so-called
"blackhole" handlers (:class:`~logbook.NullHandler`) which stop processing
at any case when they are reached.  If you push a blackhole handler on top
of an existing infrastructure you can build up a separate one without
performance impact.

Processor
---------

A processor can inject additional information into a log record when the
record is handled.  Processors are called once at least one log handler is
interested in handling the record.  Before that happens, no processing
takes place.

Here an example processor that injects the current working directory into
the extra attribute of the record::

    import os

    def inject_cwd(record):
        record.extra['cwd'] = os.getcwd()

    with Processor(inject_cwd):
        # all logging calls inside this block in this thread will now
        # have the current working directory information attached.
        ...

Flags
-----

The last pillar of logbook is the flags stack.  This stack can be used to
override settings of the logging system.  Currently this can be used to
change the behavior of logbook in case an exception during log handling
happens (for instance if a log record is supposed to be delivered to the
filesystem but it ran out of available space).  Additionally there is a
flag that disables frame introspection which can result in a speedup on
JIT compiled Python interpreters.

Here an example of a silenced error reporting::

    with Flags(errors='silent'):
        # errors are now silent for this block
        ...
