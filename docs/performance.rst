Performance Tuning
==================

The more logging calls you add to your application and libraries, the more
overhead will you introduce.  There are a couple things you can do to
remedy this behavior.

Debug-Only Logging
------------------

There are debug log calls, and there are debug log calls.  Some debug log
calls would sometimes be interesting in a production environment, others
really only if you are on your local machine fiddling around with the
code.  Logbook internally makes sure to process as little of your logging
call as necessary, but it will still have to walk the current stack to
figure out if there are any active handlers or not.  Depending on the
number of handlers on the stack, the kind of handler etc, there will be
more or less processed.

Generally speaking a not-handled logging call is cheap enough that you
don't have to care about it.  However there is not only your logging call,
there might also be some data you have to process for the record.  This
will always be processed, even if the log record ends up being discarded.

This is where the Python ``__debug__`` feature comes in handy.  This
variable is a special flag that is evaluated at the time where Python
processes your script.  It can elliminate code completely from your script
so that it does not even exist in the compiled bytecode (requires Python
to be run with the ``-O`` switch)::

    if __debug__:
        info = get_wallcalculate_debug_info()
        logger.debug("Call to response() failed.  Reason: {0}", info)

Keep the Fingers Crossed
------------------------

Do you really need the debug info?  In case you find yourself only looking
at the logfiles when errors occurred it would be an option to put in the
:class:`~logbook.more.FingersCrossedHandler`.  Logging into memory is
always cheaper than logging on a filesystem.

Keep the Stack Static
---------------------

Whenever you do a push or pop from one of the stacks you will invalidate
an internal cache that is used by logbook.  This is an implementation
detail, but this is how it works for the moment.  That means that the
first logging call after a push or pop will have a higher impact on the
performance than following calls.  That means you should not attempt to
push or pop from a stack for each logging call.  Make sure to do the
pushing and popping only as needed.  (start/end of application/request)
