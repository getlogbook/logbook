``cached_property`` is now backed by the Rust extension, falling back to the
pure Python implementation when the extension is unavailable. It runs once per
object per attribute, and :class:`~logbook.LogRecord` has thirteen of them, so
reading ``record.message`` is about 23% cheaper and
:meth:`~logbook.LogRecord.pull_information` -- which
:meth:`~logbook.LogRecord.to_dict`, pickling and the queue handlers all go
through -- about 21% cheaper.
