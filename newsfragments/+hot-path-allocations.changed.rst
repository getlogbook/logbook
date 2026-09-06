Logging calls no longer look up three keyword arguments in an empty dictionary
when none were passed, and :class:`~logbook.LogRecord` builds its empty
``extra`` mapping directly rather than passing an empty iterable through
:class:`collections.defaultdict`. Logging calls are 4-9% faster.
