Design Principles
=================

.. currentmodule:: logbook

Logbook is a logging library that breaks many expectations people have in
logging libraries to support paradigms we think are more suitable for
modern applications than the traditional Java inspired logging system that
can also be found in the Python standard library and many more programming
languages.

This section of the documentation should help you understand the design of
Logbook and why it was implemented like this.

No Logger Registry
------------------

Logbook is unique in that it has the concept of logging channels but that
it does not keep a global registry of them.  In the standard library's
logging module a logger is attached to a tree of loggers that are stored
in the logging module itself as global state.

In logbook a logger is just an opaque object that might or might not have
a name and attached information such as log level or customizations, but
the lifetime and availability of that object is controlled by the person
creating that logger.

The registry is necessary for the logging library to give the user the
ability to configure these loggers.

Logbook has a completely different concept of dispatching from loggers to
the actual handlers which removes the requirement and usefulness of such a
registry.  The advantage of the logbook system is that it's a cheap
operation to create a logger and that a logger can easily be garbage
collected to remove all traces of it.

Instead Logbook moves the burden of delivering a log record from the log
channel's attached log to an independent entity that looks at the context
of the execution to figure out where to deliver it.

Context Sensitive Handler Stack
-------------------------------

Python has two builtin ways to express implicit context: processes and
threads.  What this means is that if you have a function that is passed no
arguments at all, you can figure out what thread called the function and
what process you are sitting in.  Logbook supports this context
information and lets you bind a handler (or more!) for such a context.

This is how this works: there are two stacks available at all times in
Logbook.  The first stack is the process wide stack.  It is manipulated
with :class:`Handler.push_application` and
:class:`Handler.pop_application` (and of course the context manager
:class:`Handler.applicationbound`).  Then there is a second stack which is
per thread.  The manipulation of that stack happens with
:class:`Handler.push_thread`, :class:`Handler.pop_thread` and the
:class:`Handler.threadbound` contextmanager.

Let's take a WSGI web application as first example.  When a request comes
in your WSGI server will most likely do one of the following two things:
either spawn a new Python process (or reuse a process in a pool), or
create a thread (or again, reuse something that already exists).  Either
way, we can now say that the context of process id and thread id is our
playground.  For this context we can define a log handler that is active
in this context only for a certain time.  In pseudocode this would look
like this::

    def my_application(environ, start_response):
        my_handler = FileHandler(...)
        my_handler.push_thread()
        try:
            # whatever happens here in terms of logging is handled
            # by the `my_handler` handler.
            ...
        finally:
            my_handler.pop_thread()

Because this is a lot to type, you can also use the `with` statement to do
the very same::

    def my_application(environ, start_response):
        with FileHandler(...).threadbound() as my_handler:
            # whatever happens here in terms of logging is handled
            # by the `my_handler` handler.
            ...

Additionally there is another place where you can put handlers: directly
onto a logging channel (for example on a :class:`Logger`).

This stack system might seem like overkill for a traditional system, but
it allows complete decoupling from the log handling system and other
systems that might log messages.

Let's take a GUI application rather than a web application.  You have an
application that starts up, shuts down and at any point in between might
fail or log messages.  The typical default behaviour here would be to log
into a logfile.  Fair enough, that's how these applications work.

But what's the point in logging if not even a single warning happened?
The traditional solution with the logging library from Python is to set
the level high (like `ERROR` or `WARNING`) and log into a file.  When
things break, you have a look at the file and hope it contains enough
information.

When you are in full control of the context of execution with a stack based
system like Logbook has, there is a lot more you can do.

For example you could immediately after your application boots up
instanciate a :class:`~logbook.FingersCrossedHandler`.  This handler
buffers *all* log records in memory and does not emit them at all.  What's
the point?  That handler activates when a certain threshold is reached.
For example, when the first warning occurs you can write the buffered
messages as well as the warning that just happened into a logfile and
continue logging from that point.  Because there is no point in logging
when you will never look at that file anyways.

But that alone is not the killer feature of a stack.  In a GUI application
there is the point where we are still initializing the windowing system.
So a file is the best place to log messages.  But once we have the GUI
initialized, it would be very helpful to show error messages to a user in
a console window or a dialog.  So what we can do is to initialize at that
point a new handler that logs into a dialog.

When then a long running tasks in the GUI starts we can move that into a
separate thread and intercept all the log calls for that thread into a
separate window until the task succeeded.

Here such a setup in pseudocode::

    from logbook import FileHandler, WARNING
    from logbook import FingersCrossedHandler

    def main():
        # first we set up a handler that logs everything (including debug
        # messages, but only starts doing that when a warning happens
        default_handler = FingersCrossedHandler(FileHandler(filename,
                                                            delay=True),
                                                WARNING)
        # this handler is now activated as the default handler for the
        # whole process.  We do not bubble up to the default handler
        # that logs to stderr.
        with default_handler.applicationbound(bubble=False):
            # now we initialize the GUI of the application
            initialize_gui()
            # at that point we can hook our own logger in that intercepts
            # errors and displays them in a log window
            with gui.log_handler.applicationbound():
                # run the gui mainloop
                gui.mainloop()

This stack can also be used to inject additional information automatically
into log records.  This is also used to replace the need for custom log
levels.

No Custom Log Levels
--------------------

This change over logging was controversial, even under the two original
core developers.  There clearly are use cases for custom log levels, but
there is an inherent problem with then: they require a registry.  If you
want custom log levels, you will have to register them somewhere or parts
of the system will not know about them.  Now we just spent a lot of time
ripping out the registry with a stack based approach to solve delivery
problems, why introduce a global state again just for log levels?

Instead we looked at the cases where custom log levels are useful and
figured that in most situations custom log levels are used to put
additional information into a log entry.  For example it's not uncommon to
have separate log levels to filter user input out of a logfile.

We instead provide powerful tools to inject arbitrary additional data into
log records with the concept of log processors.

So for example if you want to log user input and tag it appropriately you
can override the :meth:`Logger.process_record` method::

    class InputLogger(Logger):
        def process_record(self, record):
            record.extra['kind'] = 'input'

A handler can then use this information to filter out input::

    def no_input(record, handler):
        return record.extra.get('kind') != 'input'

    with MyHandler().threadbound(filter=no_input):
        ...

Injecting Context-Sensitive Information
---------------------------------------

For many situations it's not only necessary to inject information on a
per-channel basis but also for all logging calls from a given context.
This is best explained for web applications again.  If you have some
libraries doing logging in code that is triggered from a request you might
want to record the URL of that request for each log record so that you get
an idea where a specific error happened.

This can easily be accomplished by registering a custom processor when
binding a handler to a thread::

    def my_application(environ, start_reponse):
        def inject_request_info(record, handler):
            record.extra['path'] = environ['PATH_INFO']
        with Processor(inject_request_info).threadbound():
            with my_handler.threadbound():
                # rest of the request code here
                ...

Logging Compatibility
---------------------

The last pillar of logbook's design is the compatibility with the standard
libraries logging system.  There are many libraries that exist currently
that log information with the standard libraries logging module.  Having
two separate logging systems in the same process is countrproductive and
will cause separate logfiles to appear in the best case or complete chaos
in the worst.

Because of that, logbook provides ways to transparently redirect all
logging records into the logbook stack based record delivery system.  That
way you can even continue to use the standard libraries logging system to
emit log messages and can take the full advantage of logbook's powerful
stack system.

If you are curious, have a look at :ref:`logging-compat`.

Gevent Compatability
--------------------

Logbook will first try to import gevent; if successful:
* Logbook will use greenlets instead of threads
* The sockets being used in the handlers will be gevent sockets

Multiprocessing-related logging affecting by gevent.