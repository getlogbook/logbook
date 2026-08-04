#![deny(rust_2018_idioms)]

use std::sync::Arc;

use arc_swap::{ArcSwap, ArcSwapOption};

use contextvars::{PyContextVar, PyContextVarMethods};
use pyo3::exceptions::{PyAssertionError, PyLookupError, PyNotImplementedError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyIterator, PyString, PyTuple, PyType};
use pyo3::{intern, IntoPyObjectExt};

mod contextvars;
mod stack_item;

use crate::stack_item::{StackItem, StackItemFactory};

#[derive(Default)]
struct StackSnapshot {
    items: Vec<StackItem>,
}

impl StackSnapshot {
    fn pushed(&self, py: Python<'_>, item: StackItem) -> Self {
        debug_assert!(
            self.items
                .last()
                .is_none_or(|current| current.seq() < item.seq()),
            "stack snapshots must remain sorted by sequence number"
        );
        let mut items: Vec<StackItem> = self.items.iter().map(|item| item.clone_ref(py)).collect();
        items.push(item);
        Self { items }
    }

    fn popped(&self, py: Python<'_>) -> Option<(StackItem, Self)> {
        let (popped, remaining) = self.items.split_last()?;
        let remaining = remaining.iter().map(|item| item.clone_ref(py)).collect();
        Some((popped.clone_ref(py), Self { items: remaining }))
    }
}

/// The context stack, stored as a linked list.
///
/// Each node holds one pushed object and points at the node below it
/// (`Entry::parent`). Pushing creates a new node; popping goes back to
/// the parent `Arc`. Because popping returns to the same node rather
/// than rebuilding the stack, a merge cached on that node can be reused
/// when the context pops back to it. Each manager has one root node
/// (`entry: None`) that represents the empty stack.
///
/// `Node`, `Merged`, and the `StackState` wrapper hold Python references
/// (`Py`) that Python's garbage collector cannot see, because
/// `StackState` has no `__traverse__`. Adding one would be wrong:
/// several `StackState` objects can share one chain of nodes, and Python
/// requires each object to report only the references it owns itself,
/// exactly once. The cost of leaving it out: a reference cycle that
/// passes through a manager (an object pushed onto a manager that also
/// refers back to that manager) can never be collected. Logbook's own
/// managers live for the whole process anyway, so this only affects
/// user-created managers that are meant to be temporary.
struct Node {
    entry: Option<Entry>,
    /// Cached result of merging this stack with the application stack.
    /// Nodes can be shared between threads (via `copy_context()`), so two
    /// threads may store a cache at the same time. That is harmless:
    /// both computed a correct value, and whichever store wins is either
    /// reused or recomputed on the next read.
    ///
    /// Every node on a live stack keeps its own cache, ready for when the
    /// context pops back to that depth. This is a deliberate trade: with
    /// n handlers pushed and a log call at every level on the way in, the
    /// caches together hold about n^2/2 references to live handlers.
    /// Caches built against an old application stack are cleared the next
    /// time a node above them recomputes (see `iter_context_objects`).
    merged: ArcSwapOption<Merged>,
}

/// The contents of every node except the root.
struct Entry {
    item: StackItem,
    parent: Arc<Node>,
    len: usize,
}

struct Merged {
    /// The application stack this cache was built from. The cache is only
    /// reused while this is still the current stack (compared by pointer).
    /// Holding the `Arc` keeps that allocation alive, so a newer stack can
    /// never sit at the same address and match by accident.
    global: Arc<StackSnapshot>,
    objects: Py<PyTuple>,
}

impl Node {
    fn root() -> Self {
        Self {
            entry: None,
            merged: ArcSwapOption::empty(),
        }
    }

    fn len(&self) -> usize {
        self.entry.as_ref().map_or(0, |entry| entry.len)
    }

    fn pushed(self: &Arc<Self>, item: StackItem) -> Self {
        debug_assert!(
            self.entry
                .as_ref()
                .is_none_or(|entry| entry.item.seq() < item.seq()),
            "stack nodes must remain sorted by sequence number"
        );
        Self {
            entry: Some(Entry {
                item,
                parent: Arc::clone(self),
                len: self.len() + 1,
            }),
            merged: ArcSwapOption::empty(),
        }
    }
}

impl Drop for Node {
    fn drop(&mut self) {
        // Without this, dropping a node would drop its parent, which drops
        // its parent, and so on, one call stack frame per node. Dropping
        // a deep stack all at once would overflow the call stack, so walk
        // the chain in a loop instead.
        let mut entry = self.entry.take();
        while let Some(Entry { parent, .. }) = entry {
            match Arc::try_unwrap(parent) {
                Ok(mut node) => entry = node.entry.take(),
                Err(_) => break,
            }
        }
    }
}

/// Merge the application stack and the context stack into one tuple,
/// most recently pushed first. The application stack is stored oldest
/// first; walking the context stack from the top gives newest first.
fn merged_objects(py: Python<'_>, global: &StackSnapshot, node: &Node) -> PyResult<Py<PyTuple>> {
    let mut merged: Vec<Py<PyAny>> = Vec::with_capacity(global.items.len() + node.len());
    let mut global_index = global.items.len();
    let mut entry = node.entry.as_ref();

    loop {
        let global_item = global.items[..global_index].last();
        match (global_item, entry) {
            (Some(global_item), Some(stack_entry)) => {
                if global_item.seq() > stack_entry.item.seq() {
                    merged.push(global_item.obj().clone_ref(py));
                    global_index -= 1;
                } else {
                    merged.push(stack_entry.item.obj().clone_ref(py));
                    entry = stack_entry.parent.entry.as_ref();
                }
            }
            (Some(global_item), None) => {
                merged.push(global_item.obj().clone_ref(py));
                global_index -= 1;
            }
            (None, Some(stack_entry)) => {
                merged.push(stack_entry.item.obj().clone_ref(py));
                entry = stack_entry.parent.entry.as_ref();
            }
            (None, None) => break,
        }
    }

    Ok(PyTuple::new(py, merged)?.unbind())
}

fn tuple_to_iter(py: Python<'_>, objects: &Py<PyTuple>) -> PyResult<Py<PyIterator>> {
    Ok(objects.bind(py).try_iter()?.unbind())
}

// This class holds Python references but has no `__traverse__` on
// purpose; see `Node` for why adding one would be wrong.
#[pyclass(module = "logbook._speedups", name = "_StackState", frozen)]
pub struct StackState {
    node: Arc<Node>,
}

#[pymethods]
impl StackState {
    fn __repr__(&self) -> String {
        format!("<_StackState len={}>", self.node.len())
    }
}

#[pyclass(module = "logbook._speedups", frozen)]
pub struct ContextStackManager {
    global: ArcSwap<StackSnapshot>,
    context_stack: Py<PyContextVar>,
    /// The empty-stack node that `context_stack` uses as its default.
    /// Also kept here because push/pop_application need to clear its
    /// cache and cannot reach it through any context.
    root: Arc<Node>,
    stack_items: StackItemFactory,
}

impl ContextStackManager {
    fn current_stack<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, StackState>> {
        let context_stack = self.context_stack.bind(py);
        match context_stack.get(None)? {
            Some(stack) => Ok(stack.cast_into::<StackState>()?),
            None => Err(PyLookupError::new_err(context_stack.clone().unbind())),
        }
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
        let root = Arc::new(Node::root());
        let stack = Bound::new(
            py,
            StackState {
                node: Arc::clone(&root),
            },
        )?;
        Ok(Self {
            global: ArcSwap::from(Arc::new(StackSnapshot::default())),
            context_stack: PyContextVar::new_with_default(py, "stack", stack)?.unbind(),
            root,
            stack_items: StackItemFactory::new(),
        })
    }

    #[getter(_global)]
    fn get_global(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        let global = self.global.load_full();
        Ok(PyTuple::new(
            py,
            global
                .items
                .iter()
                .map(|item| (item.seq(), item.obj().clone_ref(py))),
        )?
        .unbind())
    }

    #[getter(_context_stack)]
    fn get_context_stack(&self, py: Python<'_>) -> Py<PyContextVar> {
        self.context_stack.clone_ref(py)
    }

    fn iter_context_objects(&self, py: Python<'_>) -> PyResult<Py<PyIterator>> {
        let stack = self.current_stack(py)?;
        let node = &stack.get().node;
        // `load()` rather than `load_full()`: it skips bumping the shared
        // reference count, which many reader threads would otherwise fight
        // over. On a cache hit we only need to compare pointers.
        let current_global = self.global.load();

        let memo = node.merged.load();
        if let Some(merged) = &*memo {
            if Arc::ptr_eq(&merged.global, &current_global) {
                return tuple_to_iter(py, &merged.objects);
            }
        }

        let current_global = arc_swap::Guard::into_inner(current_global);
        let objects = merged_objects(py, current_global.as_ref(), node)?;
        node.merged.store(Some(Arc::new(Merged {
            global: current_global.clone(),
            objects: objects.clone_ref(py),
        })));

        // Each node below keeps its own cache, ready for when the context
        // pops back to that depth. But a cache built against an old
        // application stack will never be used again, and it keeps that
        // stack's handlers alive. Clear those out now rather than waiting
        // for the context to unwind. If another thread stores a fresh
        // cache at the same time, either outcome is fine; the worst case
        // is one extra recompute.
        let mut ancestor = node.entry.as_ref().map(|entry| &entry.parent);
        while let Some(parent) = ancestor {
            let memo = parent.merged.load();
            if let Some(merged) = &*memo {
                if !Arc::ptr_eq(&merged.global, &current_global) {
                    parent.merged.store(None);
                }
            }
            ancestor = parent.entry.as_ref().map(|entry| &entry.parent);
        }

        tuple_to_iter(py, &objects)
    }

    fn push_context<'py>(&self, py: Python<'py>, obj: Bound<'py, PyAny>) -> PyResult<()> {
        let item = self.stack_items.new_item(obj);
        let stack = self.current_stack(py)?;
        let node = Arc::new(stack.get().node.pushed(item));
        self.context_stack.bind(py).set(StackState { node })?;
        Ok(())
    }

    fn pop_context<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let stack = self.current_stack(py)?;
        let Some(entry) = stack.get().node.entry.as_ref() else {
            return Err(PyAssertionError::new_err("no objects on stack"));
        };
        let popped = entry.item.obj().bind(py).clone();
        self.context_stack.bind(py).set(StackState {
            node: Arc::clone(&entry.parent),
        })?;
        Ok(popped)
    }

    fn push_application(&self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        loop {
            let current = self.global.load_full();
            let item = self.stack_items.new_item(obj.clone());
            let next = Arc::new(current.pushed(py, item));
            let prev = self.global.compare_and_swap(&current, next);
            if Arc::ptr_eq(&current, &*prev) {
                // Not needed for correctness (the pointer check would
                // reject it), but the root node lives as long as the
                // manager, and its cache holds the old application stack
                // alive. Clear it now instead of waiting for an iteration
                // on an empty context stack, which may never happen.
                self.root.merged.store(None);
                return Ok(());
            }
        }
    }

    fn pop_application<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        loop {
            let current = self.global.load_full();
            let Some((popped, remaining)) = current.popped(py) else {
                return Err(PyAssertionError::new_err("no objects on application stack"));
            };
            let prev = self.global.compare_and_swap(&current, Arc::new(remaining));
            if Arc::ptr_eq(&current, &*prev) {
                // See push_application. Here it matters more: without
                // this, the root's cache would keep the popped handler
                // alive.
                self.root.merged.store(None);
                return Ok(popped.obj().bind(py).clone());
            }
        }
    }
}

#[pyclass(module = "logbook._speedups", frozen)]
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
        _exc_type: &Bound<'_, PyAny>,
        _exc_val: &Bound<'_, PyAny>,
        _exc_tb: &Bound<'_, PyAny>,
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
        _exc_type: &Bound<'_, PyAny>,
        _exc_val: &Bound<'_, PyAny>,
        _exc_tb: &Bound<'_, PyAny>,
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

impl<'a, 'py, T> FromPyObject<'a, 'py> for Maybe<T>
where
    T: FromPyObject<'a, 'py>,
{
    type Error = T::Error;

    fn extract(obj: Borrowed<'a, 'py, PyAny>) -> Result<Self, Self::Error> {
        obj.extract().map(Maybe::Some)
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
        self.attr_name = Some(intern!(py, "_").add(&name)?.cast_into()?.unbind());
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

#[pymodule(gil_used = false)]
fn _speedups(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<StackState>()?;
    m.add_class::<ContextStackManager>()?;
    m.add_class::<StackedObject>()?;
    m.add_class::<PyGroupReflectedProperty>()?;

    Ok(())
}
