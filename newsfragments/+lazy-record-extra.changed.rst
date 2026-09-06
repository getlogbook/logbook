:attr:`LogRecord.extra <logbook.LogRecord.extra>` is now created on first
access rather than for every record. Records created with ``extra=...`` are
unaffected. Logging calls are about 6.5% faster; code that reads
``record.extra``, including :meth:`~logbook.LogRecord.to_dict` and anything
that serialises records, pays about 114ns once per record. The mapping is still
a :class:`~collections.defaultdict` with a :class:`str` factory, so
``record.extra["missing"]`` still returns ``""``. It is no longer present in
``record.__dict__`` until something asks for it.
