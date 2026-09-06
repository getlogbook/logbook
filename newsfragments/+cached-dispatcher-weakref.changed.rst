A dispatcher now keeps one weak reference to itself and hands it to every record
it creates, rather than asking the weakref machinery for the same object on
every logging call. Logging calls are about 4.5% faster. Dispatchers remain
picklable and copyable: the cached reference is left out of the pickled state
and rebuilt on demand. Slots defined by dispatcher subclasses are preserved.
