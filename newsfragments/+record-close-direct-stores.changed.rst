Closing a log record, which happens for every record logged, no longer goes
through :func:`setattr` in a loop to clear its frame references. Logging calls
are 2-10% faster depending on the handler stack. A subclass that overrides
``_noned_on_close`` still gets the loop.
