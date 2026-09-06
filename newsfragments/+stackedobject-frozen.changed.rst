The ``StackedObject`` base class in the Rust extension is now declared
``frozen``, shrinking it to ``sizeof(PyObject)``. On CPython 3.13 and older, a
Python class inheriting a larger extension type cannot use inline values, which
disables the interpreter's specialised attribute access for every handler
class. Logging calls are now 2-5% faster on those versions; CPython 3.14
removed the size restriction, so no change there.
