Formatting a record with the default format string no longer goes through
:meth:`~datetime.datetime.strftime`, which accounted for two thirds of the cost
of formatting. Records that are actually written out are about a third faster.
A custom format string, a timezone-aware timestamp, a year before 1000 or a
:class:`~datetime.datetime` subclass all keep the previous code path, so their
output is unchanged.
