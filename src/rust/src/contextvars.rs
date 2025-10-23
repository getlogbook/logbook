use std::ffi::CString;
use std::ptr::{self, addr_of_mut};

use pyo3::ffi::{self, PyTypeObject};
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::DerefToPyAny;
use pyo3::{intern, IntoPyObjectExt, PyTypeInfo};

#[repr(transparent)]
pub struct PyContextVar(PyAny);

impl DerefToPyAny for PyContextVar {}

unsafe impl PyTypeInfo for PyContextVar {
    const NAME: &'static str = "ContextVar";
    const MODULE: Option<&'static str> = Some("_contextvars");

    #[inline]
    fn type_object_raw(_py: Python<'_>) -> *mut PyTypeObject {
        #[allow(unused_unsafe)] // https://github.com/rust-lang/rust/pull/125834
        unsafe {
            addr_of_mut!(ffi::PyContextVar_Type)
        }
    }

    #[inline]
    fn is_type_of(obj: &Bound<'_, PyAny>) -> bool {
        unsafe { ffi::PyContextVar_CheckExact(obj.as_ptr()) > 0 }
    }

    #[inline]
    fn is_exact_type_of(obj: &Bound<'_, PyAny>) -> bool {
        unsafe { ffi::PyContextVar_CheckExact(obj.as_ptr()) > 0 }
    }
}

impl PyContextVar {
    #[allow(dead_code)]
    pub fn new<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyContextVar>> {
        let name = CString::new(name)?;
        unsafe {
            let ptr = ffi::PyContextVar_New(name.as_ptr(), ptr::null_mut());
            Ok(Bound::from_owned_ptr_or_err(py, ptr)?.downcast_into_unchecked())
        }
    }

    pub fn new_with_default<'py, T>(
        py: Python<'py>,
        name: &str,
        default: T,
    ) -> PyResult<Bound<'py, PyContextVar>>
    where
        T: IntoPyObject<'py>,
    {
        let name = CString::new(name)?;
        let default = default.into_bound_py_any(py)?;
        unsafe {
            let ptr = ffi::PyContextVar_New(name.as_ptr(), default.as_ptr());
            Ok(Bound::from_owned_ptr_or_err(py, ptr)?.downcast_into_unchecked())
        }
    }
}

pub trait PyContextVarMethods<'py> {
    fn get(&self, default_value: Option<&Bound<'py, PyAny>>)
        -> PyResult<Option<Bound<'py, PyAny>>>;
    fn set<V>(&self, value: V) -> PyResult<Bound<'py, PyContextToken>>
    where
        V: IntoPyObject<'py>;
    #[allow(dead_code)]
    fn reset(&self, token: &Bound<'py, PyContextToken>) -> PyResult<()>;
}

impl<'py> PyContextVarMethods<'py> for Bound<'py, PyContextVar> {
    fn get(
        &self,
        default_value: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = self.py();
        let mut result = ptr::null_mut();
        let default_value = default_value.map(|v| v.as_ptr()).unwrap_or(ptr::null_mut());
        if unsafe { ffi::PyContextVar_Get(self.as_ptr(), default_value, &mut result) < 0 } {
            return Err(PyErr::fetch(py));
        }
        Ok(unsafe { Bound::from_owned_ptr_or_opt(py, result) })
    }

    fn set<V>(&self, value: V) -> PyResult<Bound<'py, PyContextToken>>
    where
        V: IntoPyObject<'py>,
    {
        let py = self.py();
        unsafe {
            let token = ffi::PyContextVar_Set(self.as_ptr(), value.into_bound_py_any(py)?.as_ptr());
            Ok(Bound::from_owned_ptr_or_err(py, token)?.downcast_into_unchecked())
        }
    }

    fn reset(&self, token: &Bound<'py, PyContextToken>) -> PyResult<()> {
        if unsafe { ffi::PyContextVar_Reset(self.as_ptr(), token.as_ptr()) == -1 } {
            return Err(PyErr::fetch(self.py()));
        }
        Ok(())
    }
}

#[repr(transparent)]
pub struct PyContextToken(PyAny);

impl DerefToPyAny for PyContextToken {}

unsafe impl PyTypeInfo for PyContextToken {
    const NAME: &'static str = "Token";
    const MODULE: Option<&'static str> = Some("_contextvars");

    #[inline]
    fn type_object_raw(_py: Python<'_>) -> *mut PyTypeObject {
        #[allow(unused_unsafe)] // https://github.com/rust-lang/rust/pull/125834
        unsafe {
            addr_of_mut!(ffi::PyContextToken_Type)
        }
    }

    #[inline]
    fn is_type_of(obj: &Bound<'_, PyAny>) -> bool {
        unsafe { ffi::PyContextToken_CheckExact(obj.as_ptr()) > 0 }
    }

    #[inline]
    fn is_exact_type_of(obj: &Bound<'_, PyAny>) -> bool {
        unsafe { ffi::PyContextToken_CheckExact(obj.as_ptr()) > 0 }
    }
}

impl PyContextToken {
    #[allow(dead_code)]
    fn missing(py: Python<'_>) -> PyResult<Borrowed<'static, '_, PyAny>> {
        static MISSING: PyOnceLock<Py<PyAny>> = PyOnceLock::new();
        MISSING
            .get_or_try_init(py, || {
                Ok(PyContextToken::type_object(py)
                    .getattr(intern!(py, "MISSING"))?
                    .unbind())
            })
            .map(|missing| missing.bind_borrowed(py))
    }
}

#[allow(dead_code)]
pub trait PyContextTokenMethods<'py> {
    fn var(&self) -> PyResult<Bound<'py, PyContextVar>>;
    fn old_value(&self) -> PyResult<Option<Bound<'py, PyAny>>>;
}

impl<'py> PyContextTokenMethods<'py> for Bound<'py, PyContextToken> {
    fn var(&self) -> PyResult<Bound<'py, PyContextVar>> {
        self.getattr(intern!(self.py(), "var"))?.extract()
    }

    fn old_value(&self) -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = self.py();
        let old_value = self.getattr(intern!(py, "old_value"))?;
        if old_value.is(PyContextToken::missing(py)?) {
            Ok(None)
        } else {
            Ok(Some(old_value))
        }
    }
}

#[cfg(test)]
mod tests {
    use pyo3::types::PyString;

    use super::*;

    #[test]
    fn contextvar_no_default() -> PyResult<()> {
        Python::initialize();
        Python::attach(|py| {
            let foo = PyString::new(py, "foo");
            let bar = PyString::new(py, "bar");
            let baz = PyString::new(py, "baz");
            let var = PyContextVar::new(py, "var")?;
            assert!(var.get(None)?.is_none());
            assert!(var.get(Some(&foo))?.unwrap().is(&foo));
            let token = var.set(&baz)?;
            assert!(var.get(None)?.unwrap().is(&baz));
            assert!(var.get(Some(&bar))?.unwrap().is(&baz));
            assert!(token.var()?.is(&var));
            assert!(token.old_value()?.is_none());
            var.reset(&token)?;
            assert!(var.get(None)?.is_none());
            assert!(var.get(Some(&bar))?.unwrap().is(&bar));

            Ok(())
        })
    }

    #[test]
    fn contextvar_with_default() -> PyResult<()> {
        Python::initialize();
        Python::attach(|py| {
            let foo = PyString::new(py, "foo");
            let bar = PyString::new(py, "bar");
            let baz = PyString::new(py, "baz");
            let var = PyContextVar::new_with_default(py, "var", &foo)?;
            assert!(var.get(None)?.unwrap().is(&foo));
            assert!(var.get(Some(&bar))?.unwrap().is(&bar));
            let token = var.set(&baz)?;
            assert!(var.get(None)?.unwrap().is(&baz));
            assert!(var.get(Some(&bar))?.unwrap().is(&baz));
            assert!(token.var()?.is(&var));
            assert!(token.old_value()?.is_none());
            var.reset(&token)?;
            assert!(var.get(None)?.unwrap().is(&foo));
            assert!(var.get(Some(&bar))?.unwrap().is(&bar));

            Ok(())
        })
    }
}
