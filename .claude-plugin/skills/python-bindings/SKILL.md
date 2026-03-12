# Python Bindings Skill — PyO3 and Maturin Expert Context

<!--
skill:
  name: python-bindings
  description: Expert context for all Python binding work: PyO3 0.26 patterns, maturin build commands, type stub generation, error conversion, GIL safety, and the Python public API layer structure.
  auto-invoke:
    - "python/**/*.py"
    - "python/**/*.pyi"
    - "src/python_bindings/**/*.rs"
  triggers:
    - "python bindings"
    - "pyo3"
    - "maturin"
    - "pyclass"
    - "python layer"
    - "type stubs"
    - ".pyi"
-->

## Architecture Overview

The Python layer has two components:

```
claude_trace/                       ← User-facing package (pure Python)
├── __init__.py                     ← Public API: instrument(), session(), etc.
├── py.typed                        ← PEP 561 marker (enables mypy type checking)
├── _claude_trace.pyi               ← Type stubs for the Rust extension
└── _claude_trace.so (built)        ← Rust extension module (maturin output)

src/python_bindings/               ← Rust source for the extension
├── mod.rs                         ← #[pymodule] entry point
├── session.rs                     ← PySessionSpan class
├── turn.rs                        ← PyTurnSpan class
├── cost.rs                        ← PyCostBreakdown class + py_calculate_cost fn
└── errors.rs                      ← From<ClaudeTraceError> for PyErr
```

**Key principle**: The `python/claude_trace/__init__.py` is the **only** public API surface. It re-exports types from `_claude_trace` with Python ergonomics added. Users should never import from `_claude_trace` directly.

---

## PyO3 0.26 Patterns

### Module Entry Point

```rust
// src/python_bindings/mod.rs
use pyo3::prelude::*;

mod cost;
mod errors;
mod session;
mod turn;

/// Python module entry point.
///
/// Called when Python does `import claude_trace._claude_trace`.
/// The module name MUST match `tool.maturin.module-name` in pyproject.toml.
#[pymodule(gil_used = false)]  // REQUIRED: gil_used=false for all new code
pub fn _claude_trace(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<session::PySessionSpan>()?;
    m.add_class::<turn::PyTurnSpan>()?;
    m.add_class::<cost::PyCostBreakdown>()?;
    m.add_function(wrap_pyfunction!(cost::py_calculate_cost, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
```

**`gil_used = false` is mandatory.** It declares that this module does not rely on the GIL for thread safety, enabling Python 3.13+ free-threaded mode compatibility. Omitting it will generate a deprecation warning in PyO3 0.26 and break Python 3.13 free-threading.

### Defining Python Classes

```rust
// src/python_bindings/session.rs
use pyo3::prelude::*;
use std::sync::Arc;
use crate::spans::session::SessionSpan;

/// Represents a single agent session span.
///
/// This is the Python-facing wrapper around the Rust `SessionSpan`.
/// Use `claude_trace.session()` context manager instead of constructing directly.
#[pyclass(name = "SessionSpan", frozen, module = "claude_trace._claude_trace")]
// `frozen` = Python cannot set arbitrary attributes; good for correctness
// `module` = affects repr and pickle
pub struct PySessionSpan {
    // Arc<> for shared ownership — Python may hold references past Rust's control
    pub(crate) inner: Arc<SessionSpan>,
}

#[pymethods]
impl PySessionSpan {
    /// Create a new session span.
    ///
    /// In normal usage, prefer `claude_trace.session()` which handles context.
    ///
    /// Args:
    ///     session_id: Unique identifier. Use `claude_trace.generate_session_id()` for auto-gen.
    ///     model: Claude model identifier (e.g., "claude-sonnet-4-6").
    #[new]
    #[pyo3(text_signature = "(session_id, model)")]
    pub fn new(session_id: String, model: String) -> PyResult<Self> {
        let inner = SessionSpan::new(session_id, model)
            .map_err(crate::python_bindings::errors::to_py_err)?;
        Ok(Self { inner: Arc::new(inner) })
    }

    /// Human-readable repr for interactive use (shown in Python REPL).
    pub fn __repr__(&self) -> String {
        format!(
            "SessionSpan(id={:?}, model={:?}, status={:?})",
            self.inner.session_id,
            self.inner.model,
            self.inner.status(),
        )
    }

    pub fn __str__(&self) -> String {
        self.__repr__()
    }

    // Properties: use #[getter] instead of exposing fields directly
    /// Unique session identifier.
    #[getter]
    pub fn session_id(&self) -> &str {
        &self.inner.session_id
    }

    /// Model configured for this session.
    #[getter]
    pub fn model(&self) -> &str {
        &self.inner.model
    }

    /// Current session status.
    #[getter]
    pub fn status(&self) -> String {
        self.inner.status().to_string()
    }

    /// Export spans to the configured OTel backend.
    ///
    /// Releases the GIL during the blocking export call.
    pub fn flush(&self, py: Python<'_>) -> PyResult<()> {
        py.allow_threads(|| {
            self.inner.flush()
                .map_err(crate::python_bindings::errors::to_py_err)
        })
    }
}
```

### `Bound<'_, T>` — The GIL-Aware Reference

In PyO3 0.26, all Python object references use `Bound<'_, T>`:

```rust
// CORRECT: use Bound<'_, PyAny> for generic Python objects
pub fn process_dict(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<String> {
    let dict = obj.downcast::<PyDict>()?;
    // ...
}

// OLD (do not use in new code): PyRef, &PyAny, etc.
// These are pre-0.21 patterns and will be removed in PyO3 1.0
pub fn process_dict(obj: &PyAny) -> PyResult<String> { // WRONG
    // ...
}
```

### Python Context Manager Protocol

To make a Rust type usable as `with claude_trace.session(...) as sess:`:

```rust
#[pymethods]
impl PySessionSpan {
    /// Enter the context manager — returns self.
    pub fn __enter__(slf: Py<Self>) -> Py<Self> {
        slf
    }

    /// Exit the context manager — ends the session span.
    pub fn __exit__(
        &self,
        py: Python<'_>,
        _exc_type: &Bound<'_, PyAny>,
        _exc_val: &Bound<'_, PyAny>,
        _exc_tb: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        py.allow_threads(|| {
            self.inner.end()
                .map_err(crate::python_bindings::errors::to_py_err)
        })?;
        Ok(false) // Don't suppress exceptions
    }
}
```

---

## Error Conversion

All errors from Rust must be converted to appropriate Python exception types:

```rust
// src/python_bindings/errors.rs
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::PyErr;
use crate::ClaudeTraceError;

/// Convert a `ClaudeTraceError` into the most appropriate Python exception type.
pub fn to_py_err(err: ClaudeTraceError) -> PyErr {
    match err {
        ClaudeTraceError::UnknownModel(model) => PyValueError::new_err(format!(
            "Unknown model '{}'. Supported models: {}. \
             Set CLAUDE_TRACE_STRICT_PRICING=false to use fallback pricing.",
            model,
            crate::cost::supported_model_ids().join(", ")
        )),
        ClaudeTraceError::OtelError(msg) => PyRuntimeError::new_err(format!(
            "OpenTelemetry error: {}. Check your OTLP_ENDPOINT and exporter configuration.",
            msg
        )),
        ClaudeTraceError::AttributeTooLong { attribute, max, actual } => {
            PyValueError::new_err(format!(
                "Attribute '{}' too long: {} chars > {} max. \
                 Increase max_attribute_length in Config or shorten the value.",
                attribute, actual, max
            ))
        }
        ClaudeTraceError::InvalidConfig(msg) => PyValueError::new_err(msg),
    }
}
```

**Never** raise `PyException` (the base class) — always use the most specific subclass:
- `PyValueError` for invalid user input (bad model name, too-long string)
- `PyRuntimeError` for operational failures (OTel export failed)
- `PyTypeError` for wrong types passed to functions
- `PyIOError` for I/O failures

---

## GIL Rules: Exhaustive

### Release the GIL for Everything That Blocks

```rust
// ANY of these must release the GIL:
// - Network I/O (OTLP export)
// - File I/O
// - Sleeping
// - Acquiring a Mutex that another thread might hold

pub fn export_to_otlp(&self, py: Python<'_>) -> PyResult<()> {
    py.allow_threads(|| {
        // This sends spans over a gRPC connection — definitely blocks
        self.exporter.export_blocking()
            .map_err(to_py_err)
    })
}
```

### Acquire Python Objects Before Releasing GIL

```rust
// CORRECT: extract the string BEFORE releasing GIL
pub fn set_tag(&self, py: Python<'_>, key: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
    let value_str: String = value.extract()?;  // Extract while holding GIL
    py.allow_threads(|| {
        self.inner.set_tag(key, &value_str)  // Use owned String after releasing
            .map_err(to_py_err)
    })
}

// WRONG: trying to use a Bound<> reference after allow_threads
pub fn set_tag(&self, py: Python<'_>, key: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
    py.allow_threads(|| {
        let s = value.extract::<String>(); // COMPILE ERROR: Bound cannot cross threads
        // ...
    })
}
```

### Thread Safety for #[pyclass] Types

All `#[pyclass]` types must be `Send + Sync`. If your type contains non-Send data, wrap it:

```rust
// Option 1: Use Arc<Mutex<T>> for interior mutability
#[pyclass]
pub struct PyMutableState {
    inner: Arc<Mutex<InnerState>>,
}

// Option 2: Use atomic types
#[pyclass]
pub struct PyCounter {
    count: Arc<std::sync::atomic::AtomicU64>,
}

// Option 3: Make the type truly immutable (use `frozen`)
#[pyclass(frozen)]
pub struct PyImmutableConfig {
    pub capture_content: bool,
    pub max_attribute_length: usize,
}
```

---

## Maturin Commands

### Development (local iteration)

```bash
# Build and install the extension in-place (fastest)
maturin develop

# Build with release optimizations (for benchmarking)
maturin develop --release

# Build with extra cargo features
maturin develop --features python,some-feature

# Verify it works
python -c "import claude_trace; print(claude_trace.__version__)"
```

### Building Wheels

```bash
# Build a wheel for the current platform (dev/testing)
maturin build

# Build optimized release wheel
maturin build --release

# Build abi3 wheel (Python 3.11+ compatible)
maturin build --release --interpreter python3.11

# Build for all supported Python versions (CI)
maturin build --release --interpreter python3.11 python3.12 python3.13
```

### Publishing

```bash
# Publish to PyPI (requires MATURIN_PYPI_TOKEN or twine credentials)
maturin publish

# Test publish to TestPyPI
maturin publish --repository testpypi
```

---

## Type Stub Generation (`.pyi` files)

After running `maturin develop`, generate stubs for the Rust extension:

```bash
# Method 1: Using pyo3-stubgen (preferred)
pip install pyo3-stubgen
python -m pyo3_stubgen claude_trace._claude_trace

# Method 2: Using inspect (fallback)
python -c "
import inspect
import claude_trace._claude_trace as m
help(m)
"
```

The generated stubs should be placed in `python/claude_trace/_claude_trace.pyi` and committed to the repository. Update them whenever the Rust API changes.

Example of a correct `.pyi` stub:

```python
# python/claude_trace/_claude_trace.pyi
from __future__ import annotations
from typing import Any

__version__: str

class SessionSpan:
    """Represents a single agent session span."""

    def __new__(cls, session_id: str, model: str) -> SessionSpan: ...
    def __repr__(self) -> str: ...
    def __str__(self) -> str: ...
    def __enter__(self) -> SessionSpan: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool: ...

    @property
    def session_id(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def status(self) -> str: ...
    def flush(self) -> None: ...
```

---

## Python Public API Layer (`python/claude_trace/__init__.py`)

The `__init__.py` wraps the Rust extension with Python ergonomics:

```python
# python/claude_trace/__init__.py
"""
claude-trace: Zero-configuration OpenTelemetry observability for Claude Agent SDK.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterator

from claude_trace._claude_trace import (
    SessionSpan as _SessionSpan,
    __version__,
)

__all__ = ["instrument", "session", "__version__"]


def instrument() -> None:
    """Patch the Anthropic SDK to emit OTel spans automatically.

    Call this once at application startup, before creating any Anthropic clients.

    Example::

        import claude_trace
        claude_trace.instrument()

        client = anthropic.Anthropic()  # Now auto-instrumented
    """
    from claude_trace._instrumentation import install_patches
    install_patches()


@contextmanager
def session(
    *,
    customer_id: str | None = None,
    tags: list[str] | None = None,
    model: str = "claude-sonnet-4-6",
) -> Iterator[_SessionSpan]:
    """Context manager for a single agent session.

    Creates a root OTel session span and manages its lifecycle.

    Args:
        customer_id: Optional customer identifier for cost attribution.
        tags: Optional list of tags for filtering in your observability backend.
        model: Claude model identifier. Defaults to claude-sonnet-4-6.

    Yields:
        A `SessionSpan` with cost and token tracking.

    Example::

        with claude_trace.session(customer_id="acme") as sess:
            response = client.messages.create(...)
        print(f"Cost: ${sess.cost.total_usd:.4f}")
    """
    import uuid
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    span = _SessionSpan(session_id=session_id, model=model)
    if customer_id:
        span.set_customer_id(customer_id)
    if tags:
        span.set_tags(tags)
    with span:
        yield span
```

---

## Python Testing Patterns

```python
# python/tests/test_session_span.py
import pytest
from claude_trace._claude_trace import SessionSpan


class TestSessionSpan:
    def test_new_sets_session_id(self) -> None:
        span = SessionSpan("sess_abc123", "claude-sonnet-4-6")
        assert span.session_id == "sess_abc123"

    def test_new_sets_model(self) -> None:
        span = SessionSpan("sess_abc123", "claude-sonnet-4-6")
        assert span.model == "claude-sonnet-4-6"

    def test_repr_contains_session_id(self) -> None:
        span = SessionSpan("sess_abc123", "claude-sonnet-4-6")
        assert "sess_abc123" in repr(span)

    def test_new_rejects_empty_session_id(self) -> None:
        with pytest.raises(ValueError, match="session_id"):
            SessionSpan("", "claude-sonnet-4-6")

    def test_context_manager_protocol(self) -> None:
        with SessionSpan("sess_test", "claude-sonnet-4-6") as span:
            assert span.status == "running"
        # After __exit__, status should be completed
        assert span.status == "completed"
```
