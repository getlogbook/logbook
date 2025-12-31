use std::sync::atomic::{AtomicU64, Ordering};

use pyo3::prelude::*;

mod item {
    use pyo3::prelude::*;

    pub struct StackItem {
        seq: u64,
        obj: Py<PyAny>,
    }

    impl StackItem {
        pub(super) fn new(seq: u64, obj: Bound<'_, PyAny>) -> Self {
            Self {
                seq,
                obj: obj.unbind(),
            }
        }

        pub fn seq(&self) -> u64 {
            self.seq
        }

        pub fn clone_ref(&self, py: Python<'_>) -> Self {
            Self {
                seq: self.seq,
                obj: self.obj.clone_ref(py),
            }
        }

        pub fn obj(&self) -> &Py<PyAny> {
            &self.obj
        }
    }
}

pub use item::StackItem;

pub struct StackItemFactory {
    next_seq: AtomicU64,
}

impl StackItemFactory {
    pub fn new() -> Self {
        Self {
            next_seq: AtomicU64::new(0),
        }
    }

    pub fn new_item(&self, obj: Bound<'_, PyAny>) -> StackItem {
        let seq = self.next_seq.fetch_add(1, Ordering::Relaxed);
        StackItem::new(seq, obj)
    }
}
