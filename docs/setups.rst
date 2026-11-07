Common Logbook Setups
=====================

This part of the documentation shows how you can configure Logbook for
different kinds of setups.


Desktop Application Setup
-------------------------

If you develop a desktop application (command line or GUI), you probably have a line
like this in your code:

.. code-block:: python

    if __name__ == "__main__":
        main()

This is what you should wrap with a ``with`` statement that sets up your log
handler:

.. code-block:: python

    from logbook import FileHandler

    log_handler = FileHandler("application.log")

    if __name__ == "__main__":
        with log_handler.applicationbound():
            main()

Alternatively you can also just push a handler in there:

.. code-block:: python

    from logbook import FileHandler

    log_handler = FileHandler("application.log")
    log_handler.push_application()

    if __name__ == "__main__":
        main()

Please keep in mind that you will have to pop the handlers in reverse order if
you want to remove them from the stack, so it is recommended to use the context
manager API if you plan on reverting the handlers.

Web Application Setup
---------------------

Typical modern web applications written in Python have two separate contexts
where code might be executed: when the code is imported, as well as when a
request is handled.  The first case is easy to handle, just push a global file
handler that writes everything into a file.

But Logbook also gives you the ability to improve upon the logging.  For
example, you can easily create yourself a log handler that is used for
request-bound logging that also injects additional information.

For this you can either subclass the logger or you can bind to the handler with
a function that is invoked before logging.  The latter has the advantage that it
will also be triggered for other logger instances which might be used by a
different library.

Here is a simple WSGI example application that showcases sending error mails for
errors happened during a WSGI application:

.. code-block:: python

    from logbook import MailHandler, Processor

    format_string = """\
    Subject: Application Error at {record.extra[url]}

    Message type:       {record.level_name}
    Location:           {record.filename}:{record.lineno}
    Module:             {record.module}
    Function:           {record.func_name}
    Time:               {record.time:%Y-%m-%d %H:%M:%S}
    Remote IP:          {record.extra[ip]}
    Request:            {record.extra[url]} [{record.extra[method]}]

    Message:

    {record.message}
    """

    mail_handler = MailHandler(
        "errors@example.com",
        ["admin@example.com"],
        format_string=format_string,
        bubble=True,
    )


    def application(environ, start_response):
        request = Request(environ)

        def inject_info(record, handler):
            record.extra.update(
                ip=request.remote_addr, method=request.method, url=request.url
            )

        with mail_handler, Processor(inject_info):
            # standard WSGI processing happens here.  If an error
            # is logged, a mail will be sent to the admin on
            # example.com
            ...

Deeply Nested Setups
--------------------

If you want deeply nested logger setups, you can use the
:class:`~logbook.NestedSetup` class which simplifies that.  This is best
explained using an example:

.. code-block:: python

    import os
    from logbook import NestedSetup, NullHandler, FileHandler, MailHandler, Processor


    def inject_information(record):
        record.extra["cwd"] = os.getcwd()


    # a nested handler setup can be used to configure more complex setups
    setup = NestedSetup(
        [
            # make sure we never bubble up to the stderr handler
            # if we run out of setup handling
            NullHandler(),
            # then write messages that are at least warnings to a logfile
            FileHandler("application.log", level="WARNING"),
            # errors should then be delivered by mail and also be kept
            # in the application log, so we let them bubble up.
            MailHandler(
                "servererrors@example.com",
                ["admin@example.com"],
                level="ERROR",
                bubble=True,
            ),
            # while we're at it we can push a processor on its own stack to
            # record additional information.  Because processors and handlers
            # go to different stacks it does not matter if the processor is
            # added here at the bottom or at the very beginning.  Same would
            # be true for flags.
            Processor(inject_information),
        ]
    )

Once such a complex setup is defined, the nested handler setup can be used as if
it was a single handler:

.. code-block:: python

    with setup:
        # everything here is handled as specified by the rules above.
        ...


.. _configuration-from-dictionaries:

Configuration from Dictionaries and Files
-----------------------------------------

:meth:`NestedSetup.from_dict <logbook.NestedSetup.from_dict>` creates a setup
from a mapping. The ``objects`` list follows the same order as the objects
passed to :class:`~logbook.NestedSetup`: handlers later in the list see a
record first. Each entry contains a fully qualified ``class`` name and
keyword arguments for that class::

    from logbook import NestedSetup

    config = {
        "objects": [
            {"class": "logbook.NullHandler"},
            {"class": "logbook.StderrHandler", "level": "WARNING"},
        ]
    }
    setup = NestedSetup.from_dict(config)
    with setup.applicationbound():
        main()

This setup writes warnings and errors to standard error and discards lower
levels. Construction does not activate the setup. Use ``with setup`` for the
current context, or ``setup.applicationbound()`` for the whole application.
As with a manually constructed nested setup, popping it does not close its
handlers; close handlers that own resources when you are finished using them.

The mapping may be loaded from a file using a parser of your choice. For
example, a JSON file named ``logging.json`` can contain:

.. code-block:: json

    {
        "objects": [
            {"class": "logbook.NullHandler"},
            {"class": "logbook.StderrHandler", "level": "WARNING"}
        ]
    }

Load it with the standard library::

    import json
    from logbook import NestedSetup

    with open("logging.json", encoding="utf-8") as stream:
        setup = NestedSetup.from_dict(json.load(stream))

The equivalent YAML file is:

.. code-block:: yaml

    objects:
      - class: logbook.NullHandler
      - class: logbook.StderrHandler
        level: WARNING

If your application uses PyYAML, load it with ``yaml.safe_load``::

    import yaml
    from logbook import NestedSetup

    with open("logging.yaml", encoding="utf-8") as stream:
        setup = NestedSetup.from_dict(yaml.safe_load(stream))

Logbook does not require a YAML parser. In both examples, activate ``setup``
as shown above. Only use trusted configuration files: class names cause
Python modules to be imported and the classes to be instantiated.

Classes must derive from :class:`~logbook.base.ContextObject`, which includes
handlers, processors, and flags. Python dictionaries can also supply class
objects and values such as callbacks directly::

    from logbook import NestedSetup, Processor, StderrHandler


    def inject_environment(record):
        record.extra["environment"] = "production"


    setup = NestedSetup.from_dict(
        {
            "objects": [
                {
                    "class": StderrHandler,
                    "format_string": "{record.extra[environment]}: {record.message}",
                },
                {"class": Processor, "callback": inject_environment},
            ]
        }
    )

Keyword argument values are passed unchanged. Strings in those values are
not imported, and nested mappings are not interpreted as object definitions.
For callbacks or wrapped handlers, supply the Python objects after loading
the file, or use a custom handler class with suitable constructor arguments.
The input mapping is not modified. Invalid configuration raises an exception;
if construction fails, already created handlers are closed before the
exception is propagated.


Distributed Logging
-------------------

For applications that are spread over multiple processes or even machines
logging into a central system can be a pain.  Logbook supports ZeroMQ to
deal with that.  You can set up a :class:`~logbook.queues.ZeroMQHandler`
that acts as ZeroMQ publisher and will send log records encoded as JSON
over the wire:

.. code-block:: python

    from logbook.queues import ZeroMQHandler

    handler = ZeroMQHandler("tcp://127.0.0.1:5000")

Then you just need a separate process that can receive the log records and
hand it over to another log handler using the
:class:`~logbook.queues.ZeroMQSubscriber`.  The usual setup is this:

.. code-block:: python

    from logbook.queues import ZeroMQSubscriber

    subscriber = ZeroMQSubscriber("tcp://127.0.0.1:5000")
    with my_handler:
        subscriber.dispatch_forever()

You can also run that loop in a background thread with
:meth:`~logbook.queues.ZeroMQSubscriber.dispatch_in_background`:

.. code-block:: python

    from logbook.queues import ZeroMQSubscriber

    subscriber = ZeroMQSubscriber("tcp://127.0.0.1:5000")
    subscriber.dispatch_in_background(my_handler)

If you just want to use this in a :mod:`multiprocessing` environment you
can use the :class:`~logbook.queues.MultiProcessingHandler` and
:class:`~logbook.queues.MultiProcessingSubscriber` instead.  They work the
same way as the ZeroMQ equivalents but are connected through a
:class:`multiprocessing.Queue`:

.. code-block:: python

    from multiprocessing import Queue
    from logbook.queues import MultiProcessingHandler, MultiProcessingSubscriber

    queue = Queue(-1)
    handler = MultiProcessingHandler(queue)
    subscriber = MultiProcessingSubscriber(queue)

There is also the possibility to log into a Redis instance using the
:class:`~logbook.queues.RedisHandler`. To do so, you just need to create an
instance of this handler as follows:

.. code-block:: python

    import logbook
    from logbook.queues import RedisHandler

    handler = RedisHandler()
    l = logbook.Logger()
    with handler:
        l.info("Your log message")

With the default parameters, this will send a message to redis under the key redis.


Redirecting Single Loggers
--------------------------

If you want to have a single logger go to another logfile you have two
options.  First of all you can attach a handler to a specific record
dispatcher.  So just import the logger and attach something:

.. code-block:: python

    from yourapplication.yourmodule import logger

    logger.handlers.append(MyHandler(...))

Handlers attached directly to a record dispatcher will always take
precedence over the stack based handlers.  The bubble flag works as
expected, so if you have a non-bubbling handler on your logger and it
always handles, it will never be passed to other handlers.

Secondly you can write a handler that looks at the logging channel and
only accepts loggers of a specific kind.  You can also do that with a
filter function:

.. code-block:: python

    handler = MyHandler(filter=lambda r, h: r.channel == "app.database")

Keep in mind that the channel is intended to be a human readable string
and is not necessarily unique.  If you really need to keep loggers apart
on a central point you might want to introduce some more meta information
into the extra dictionary.

You can also compare the dispatcher on the log record:

.. code-block:: python

    from yourapplication.yourmodule import logger

    handler = MyHandler(filter=lambda r, h: r.dispatcher is logger)

This however has the disadvantage that the dispatcher entry on the log
record is a weak reference and might go away unexpectedly and will not be
there if log records are sent to a different process.

Last but not least you can check if you can modify the stack around the
execution of the code that triggers that logger  For instance if the
logger you are interested in is used by a specific subsystem, you can
modify the stacks before calling into the system.
