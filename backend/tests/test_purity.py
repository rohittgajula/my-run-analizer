"""The `analysis` package must never import Django.

This is the guard behind the claim that segmentation and the metrics engine are
testable without a database. Stated as a convention it lasts about a month; stated as
a test it holds. Each import runs in a subprocess with no DJANGO_SETTINGS_MODULE, so
a Django import fails loudly instead of quietly picking up ambient configuration.
"""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

PURE_MODULES = [
    "analysis",
    "analysis.segmentation",
    "analysis.running_truth",
    "analysis.heart_rate",
    "analysis.load",
    "planning",
    "planning.calendar",
    "planning.prediction",
    "planning.generator",
    "planning.readiness",
]


@pytest.mark.parametrize("module", PURE_MODULES)
def test_imports_without_django(module):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": str(BACKEND)},
    )
    assert result.returncode == 0, (
        f"{module} cannot be imported without Django configured:\n{result.stderr}"
    )
