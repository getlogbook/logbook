``group_reflected_property`` is now a frozen pyclass, removing PyO3's runtime
borrow check from every read. :meth:`~logbook.Logger.info` and
``RecordDispatcher.handle`` read :attr:`~logbook.Logger.disabled` and
:attr:`~logbook.Logger.level` between them four times per logging call, so
logging is 2-3% faster. A single property object assigned to two names now
binds to the first rather than the last; only one of the two could ever work.
