from stdlib cimport pythread

cdef object _missing = object()


cdef class group_reflected_property:
    cdef char* name
    cdef char* _name
    cdef object default
    cdef object fallback

    def __init__(self, char* name, object default, object fallback=_missing):
        self.name = name
        _name = '_' + name
        self._name = _name
        self.default = default
        self.fallback = fallback

    def __get__(self, obj, type):
        if obj is None:
            return self
        rv = getattr3(obj, self._name, _missing)
        if rv is not _missing and rv != self.fallback:
            return rv
        if obj.group is None:
            return self.default
        return getattr(obj.group, self.name)

    def __set__(self, obj, value):
        setattr(obj, self._name, value)

    def __del__(self, obj):
        delattr(obj, self._name)
