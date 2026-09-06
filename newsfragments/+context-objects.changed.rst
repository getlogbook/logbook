:class:`ContextStackManager` gained a ``context_objects()`` method returning the
cached tuple of context objects, alongside the existing
``iter_context_objects()``. Logbook now uses it internally for handler dispatch,
record processing and flag lookup, which avoids allocating an iterator on every
logging call and lets CPython use its specialised tuple loop. Handler dispatch
also skips building a :func:`itertools.chain` when the logger has no handlers of
its own. Logging calls are 1-9% faster depending on the handler stack.
