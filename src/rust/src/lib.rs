#![deny(rust_2018_idioms)]

use std::cmp::Reverse;
use std::sync::atomic::{self, AtomicUsize};

use contextvars::{PyContextVar, PyContextVarMethods};
use pyo3::exceptions::{
    PyAssertionError, PyException, PyKeyError, PyLookupError, PyNotImplementedError, PyTypeError,
};
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyIterator, PyList, PyMapping, PyString, PyTraceback, PyTuple, PyType};
use pyo3::{intern, IntoPyObjectExt};

mod contextvars;

pub struct LazyPyImport {
    module: &'static str,
    name: &'static str,
    value: PyOnceLock<Py<PyAny>>,
}

impl LazyPyImport {
    pub const fn new(module: &'static str, name: &'static str) -> LazyPyImport {
        LazyPyImport {
            module,
            name,
            value: PyOnceLock::new(),
        }
    }

    pub fn get<'py>(&'py self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        Ok(self.value.import(py, self.module, self.name)?.clone())
    }
}

pub static WEAKREF_WEAK_KEY_DICTIONARY: LazyPyImport =
    LazyPyImport::new("weakref", "WeakKeyDictionary");
pub static BUILTINS_REVERSED: LazyPyImport = LazyPyImport::new("builtins", "reversed");

#[pyclass(module = "logbook._speedups", sequence, weakref)]
pub struct FrozenSequence {
    pub(self) items: Py<PyTuple>,
    hash_cache: PyOnceLock<isize>,
}

impl FrozenSequence {
    fn new(items: Bound<'_, PyTuple>) -> Self {
        Self {
            items: items.unbind(),
            hash_cache: PyOnceLock::new(),
        }
    }

    fn empty(py: Python<'_>) -> Self {
        Self::new(PyTuple::empty(py))
    }
}

#[pymethods]
impl FrozenSequence {
    #[new]
    #[pyo3(signature = (iterable = None))]
    fn __new__(py: Python<'_>, iterable: Option<Bound<'_, PyAny>>) -> PyResult<Self> {
        let tuple = match iterable {
            None => PyTuple::empty(py),
            Some(it) => {
                let it: Vec<Bound<'_, PyAny>> = it.try_iter()?.collect::<PyResult<_>>()?;
                PyTuple::new(py, it)?
            }
        };
        Ok(Self::new(tuple))
    }

    fn __len__(&self, py: Python<'_>) -> usize {
        self.items.bind(py).len()
    }

    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<PyIterator>> {
        Ok(self.items.bind(py).try_iter()?.unbind())
    }

    fn __reversed__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(BUILTINS_REVERSED
            .get(py)?
            .call1((self.items.bind(py),))?
            .unbind())
    }

    fn __contains__(&self, py: Python<'_>, item: &Bound<'_, PyAny>) -> PyResult<bool> {
        self.items.bind(py).contains(item)
    }

    fn __getitem__(&self, py: Python<'_>, index: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let result = self.items.bind(py).as_any().get_item(index)?;
        match result.downcast_into::<PyTuple>() {
            Ok(t) => {
                let sliced = FrozenSequence::new(t);
                Ok(Py::new(py, sliced)?.into_any())
            }
            Err(err) => Ok(err.into_inner().unbind()),
        }
    }

    fn __eq__(&self, py: Python<'_>, other: &Self) -> PyResult<bool> {
        self.items.bind(py).eq(other.items.bind(py))
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        self.hash_cache
            .get_or_try_init(py, || self.items.bind(py).hash())
            .copied()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let items = self.items.bind(py);
        let s = if items.is_empty() {
            "".to_string()
        } else {
            self.items.bind(py).repr()?.to_string()
        };
        Ok(format!("FrozenSequence({})", s))
    }
}

const MAX_CONTEXT_OBJECT_CACHE: usize = 256;

#[pyclass(module = "logbook._speedups")]
pub struct ContextStackManager {
    global: Py<PyList>,
    context_stack: Py<PyContextVar>,
    cache: Py<PyMapping>,
    stack_count: AtomicUsize,
}

impl ContextStackManager {
    fn stackop(&self) -> usize {
        self.stack_count.fetch_add(1, atomic::Ordering::Relaxed)
    }
}

#[pymethods]
impl ContextStackManager {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn __new__(
        py: Python<'_>,
        _args: &Bound<'_, PyAny>,
        _kwargs: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let stack = Bound::new(py, FrozenSequence::empty(py))?;
        Ok(Self {
            global: PyList::empty(py).unbind(),
            context_stack: PyContextVar::new_with_default(py, "stack", stack)?.unbind(),
            cache: WEAKREF_WEAK_KEY_DICTIONARY
                .get(py)?
                .call0()?
                .downcast_into()?
                .unbind(),
            stack_count: AtomicUsize::new(0),
        })
    }

    #[getter(_global)]
    fn get_global(&self, py: Python<'_>) -> Py<PyList> {
        self.global.clone_ref(py)
    }

    #[getter(_context_stack)]
    fn get_context_stack(&self, py: Python<'_>) -> Py<PyContextVar> {
        self.context_stack.clone_ref(py)
    }

    #[getter(_cache)]
    fn get_cache(&self, py: Python<'_>) -> Py<PyMapping> {
        self.cache.clone_ref(py)
    }

    fn iter_context_objects(&self, py: Python<'_>) -> PyResult<Py<PyIterator>> {
        let context_stack = self.context_stack.bind(py);
        let Some(stack) = context_stack.get(None)? else {
            return Err(PyLookupError::new_err(context_stack.clone().unbind()));
        };
        let stack = stack.downcast_into::<FrozenSequence>()?;
        let cache = self.cache.bind(py);
        match cache.get_item(&stack) {
            Ok(objects) => Ok(objects.try_iter()?.unbind()),
            Err(err) if err.is_instance(py, &py.get_type::<PyKeyError>()) => {
                if cache.len()? >= MAX_CONTEXT_OBJECT_CACHE {
                    cache.call_method0(intern!(py, "clear"))?;
                }

                let global = self.global.bind(py);
                let mut stack_objects: Vec<(usize, Bound<'_, PyAny>)> = global
                    .try_iter()?
                    .chain(stack.try_iter()?)
                    .map(|item| item.and_then(|item| item.extract()))
                    .collect::<PyResult<_>>()?;
                stack_objects.sort_by_key(|item| Reverse(item.0));
                let objects = PyTuple::new(py, stack_objects.into_iter().map(|item| item.1))?;

                cache.set_item(stack, objects.clone())?;

                Ok(objects.try_iter()?.unbind())
            }
            Err(err) => Err(err),
        }
    }

    fn push_context<'py>(&self, py: Python<'py>, obj: Bound<'py, PyAny>) -> PyResult<()> {
        let context_stack = self.context_stack.bind(py);
        let new_item = (self.stackop(), obj).into_pyobject(py)?;
        let Some(stack) = context_stack.get(None)? else {
            return Err(PyLookupError::new_err(context_stack.clone().unbind()));
        };
        let stack: PyRef<'_, FrozenSequence> = stack.extract()?;
        let items = stack.items.bind(py);

        let stack = items
            .as_sequence()
            .concat(&((new_item,).into_pyobject(py)?.into_sequence()))?
            .to_tuple()?;

        let stack = FrozenSequence::new(stack);
        context_stack.set(stack)?;
        Ok(())
    }

    fn pop_context<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let context_stack = self.context_stack.bind(py);
        let Some(stack) = context_stack.get(None)? else {
            return Err(PyLookupError::new_err(context_stack.clone().unbind()));
        };
        let stack: PyRef<'_, FrozenSequence> = stack.extract()?;
        let items = stack.items.bind(py);
        let Some((popped, remaining)) = items.as_slice().split_last() else {
            return Err(PyAssertionError::new_err("no objects on stack"));
        };
        let stack = FrozenSequence::new(PyTuple::new(py, remaining)?);
        context_stack.set(stack)?;
        popped.get_item(1)
    }

    fn push_application(&self, py: Python<'_>, obj: Bound<'_, PyAny>) -> PyResult<()> {
        let new_item = (self.stackop(), obj).into_pyobject(py)?;
        self.global.bind(py).append(new_item)?;
        self.cache.bind(py).call_method0(intern!(py, "clear"))?;
        Ok(())
    }

    fn pop_application<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let global = self.global.bind(py);
        if global.is_empty() {
            return Err(PyAssertionError::new_err("no objects on application stack"));
        }
        let popped = global.call_method0(intern!(py, "pop"))?;
        self.cache.bind(py).call_method0(intern!(py, "clear"))?;
        popped.get_item(1)
    }
}

#[pyclass(module = "logbook._speedups")]
pub struct ApplicationBound {
    obj: Py<PyAny>,
}

impl ApplicationBound {
    fn new(obj: Py<PyAny>) -> Self {
        Self { obj }
    }
}

#[pymethods]
impl ApplicationBound {
    fn __enter__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let obj = self.obj.bind(py);
        obj.call_method0(intern!(py, "push_application"))?;
        Ok(obj.clone().unbind())
    }

    fn __exit__(
        &self,
        py: Python<'_>,
        _exc_type: Option<&Bound<'_, PyType>>,
        _exc_val: Option<&Bound<'_, PyException>>,
        _exc_tb: Option<&Bound<'_, PyTraceback>>,
    ) -> PyResult<()> {
        self.obj
            .bind(py)
            .call_method0(intern!(py, "pop_application"))?;
        Ok(())
    }
}

#[pyclass(module = "logbook._speedups", subclass)]
pub struct StackedObject;

#[pymethods]
impl StackedObject {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn __new__(_args: &Bound<'_, PyAny>, _kwargs: Option<&Bound<'_, PyAny>>) -> Self {
        Self
    }

    fn push_context(&self) -> PyResult<()> {
        Err(PyNotImplementedError::new_err(()))
    }

    fn pop_context(&self) -> PyResult<()> {
        Err(PyNotImplementedError::new_err(()))
    }

    fn push_application(&self) -> PyResult<()> {
        Err(PyNotImplementedError::new_err(()))
    }

    fn pop_application(&self) -> PyResult<()> {
        Err(PyNotImplementedError::new_err(()))
    }

    fn __enter__(self_: Py<Self>, py: Python<'_>) -> PyResult<Py<Self>> {
        self_.bind(py).call_method0(intern!(py, "push_context"))?;
        Ok(self_)
    }

    fn __exit__(
        self_: Py<Self>,
        py: Python<'_>,
        _exc_type: Option<&Bound<'_, PyType>>,
        _exc_val: Option<&Bound<'_, PyException>>,
        _exc_tb: Option<&Bound<'_, PyTraceback>>,
    ) -> PyResult<()> {
        self_.bind(py).call_method0(intern!(py, "pop_context"))?;
        Ok(())
    }

    fn applicationbound(self_: Py<Self>) -> ApplicationBound {
        ApplicationBound::new(self_.into_any())
    }
}

/// Similar to Option but the pyo3 conversion traits are not implemented for it,
/// so we can use it as a default argument and know that it wasn't passed.
#[derive(Clone, Debug)]
pub enum Maybe<T> {
    Some(T),
    Missing,
}

impl<'py> FromPyObject<'py> for Maybe<Py<PyAny>> {
    fn extract_bound(ob: &Bound<'py, PyAny>) -> PyResult<Self> {
        Ok(Maybe::Some(ob.clone().unbind()))
    }
}

#[pyclass(name = "group_reflected_property", module = "logbook._speedups")]
pub struct PyGroupReflectedProperty {
    prop_name: Option<Py<PyString>>,
    attr_name: Option<Py<PyString>>,
    default: Py<PyAny>,
    fallback: Option<Py<PyAny>>,
}

#[pymethods]
impl PyGroupReflectedProperty {
    #[new]
    #[pyo3(signature = (default, *, fallback = Maybe::Missing))]
    fn __new__(default: Py<PyAny>, fallback: Maybe<Py<PyAny>>) -> PyResult<Self> {
        let fallback = match fallback {
            Maybe::Some(fallback) => Some(fallback),
            Maybe::Missing => None,
        };
        Ok(Self {
            prop_name: None,
            attr_name: None,
            default,
            fallback,
        })
    }

    fn __set_name__(
        &mut self,
        py: Python<'_>,
        _owner: Option<&Bound<'_, PyType>>,
        name: Bound<'_, PyString>,
    ) -> PyResult<()> {
        self.attr_name = Some(intern!(py, "_").add(&name)?.downcast_into()?.unbind());
        self.prop_name = Some(name.unbind());
        Ok(())
    }

    fn __get__(
        self_: PyRef<'_, Self>,
        py: Python<'_>,
        instance: Option<&Bound<'_, PyAny>>,
        _owner: Option<&Bound<'_, PyType>>,
    ) -> PyResult<Py<PyAny>> {
        let Some(instance) = instance else {
            return self_.into_py_any(py);
        };
        let Some(attr_name) = &self_.attr_name else {
            return Err(PyTypeError::new_err("property is not bound to a class"));
        };
        let attr_name = attr_name.bind(py);

        let rv = instance.getattr_opt(attr_name)?;
        match (&self_.fallback, rv) {
            (Some(fallback), Some(rv)) if rv.ne(fallback)? => return Ok(rv.unbind()),
            (None, Some(rv)) => return Ok(rv.unbind()),
            _ => {}
        }

        let group = instance.getattr(intern!(py, "group"))?;
        if group.is_none() {
            return Ok(self_.default.clone_ref(py));
        }

        let Some(prop_name) = &self_.prop_name else {
            return Err(PyTypeError::new_err("property is not bound to a class"));
        };
        Ok(group.getattr(prop_name)?.unbind())
    }

    fn __set__(
        &self,
        py: Python<'_>,
        instance: Bound<'_, PyAny>,
        value: Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let Some(attr_name) = &self.attr_name else {
            return Err(PyTypeError::new_err("property is not bound to a class"));
        };
        let attr_name = attr_name.bind(py);
        instance.setattr(attr_name, value)?;
        Ok(())
    }

    fn __delete__(&self, py: Python<'_>, instance: Bound<'_, PyAny>) -> PyResult<()> {
        let Some(attr_name) = &self.attr_name else {
            return Err(PyTypeError::new_err("property is not bound to a class"));
        };
        let attr_name = attr_name.bind(py);
        instance.delattr(attr_name)?;
        Ok(())
    }
}

#[pymodule]
fn _speedups(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<FrozenSequence>()?;
    m.add_class::<ContextStackManager>()?;
    m.add_class::<StackedObject>()?;
    m.add_class::<PyGroupReflectedProperty>()?;
    m.setattr("_MAX_CONTEXT_OBJECT_CACHE", MAX_CONTEXT_OBJECT_CACHE)?;

    Ok(())
}
