The Rust extension now renders logbook's default format string directly,
writing the timestamp digit by digit instead of going through
:meth:`~datetime.datetime.isoformat`. Records that are written out are a
further 10% faster in the measured workloads. Anything the extension cannot reproduce exactly -- a
timezone-aware timestamp, a year before 1000, a
:class:`~datetime.datetime` subclass, or a level name, channel or message that
is not a plain string or contains surrogate characters -- falls back to the existing Python code, and the pure
Python build is unaffected.
