"""PySide6 must not leak references to True when a signal is emitted.

PySide6 6.12.0 drops one reference to True on every ``Signal.emit()``. From
Python 3.12 on True is immortal and nothing happens; on 3.11 the count reaches
zero after a few thousand signals and the interpreter aborts with
``bool_dealloc`` -- in CI it did, at the end of an otherwise green run, the day
the redaction preview made the worker emit a few hundred renders more.
Reported upstream as PYSIDE-3474. pyproject.toml keeps 3.11 below 6.12; this
test is what tells, with a readable failure instead of a core dump, that an
allowed release does it again.
"""

import gc
import sys

import pytest
from PySide6.QtCore import QObject, Signal


class _Emitter(QObject):
    fired = Signal(object)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def test_emitting_a_signal_keeps_true_alive(qapp):
    emitter = _Emitter()
    emitter.fired.connect(lambda value: None)
    emitter.fired.emit(0)
    gc.collect()
    before = sys.getrefcount(True)
    for value in range(50):
        emitter.fired.emit(value)
    gc.collect()
    lost = before - sys.getrefcount(True)
    assert lost <= 0, (
        f"{lost} riferimenti a True persi in 50 emit(): su Python < 3.12 l'interprete "
        "abortira` (bool_dealloc, PYSIDE-3474). Escludere questa versione di PySide6 "
        "in pyproject.toml."
    )
