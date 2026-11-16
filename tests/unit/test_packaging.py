"""Tests for package metadata consistency with CI and requires-python."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"


def test_python_version_classifiers_match_ci_matrix():
    """Classifiers list the exact Python versions exercised by CI."""
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'Programming Language :: Python :: 3.10' in text
    assert 'Programming Language :: Python :: 3.12' in text
    assert 'Programming Language :: Python :: 3.13' in text
    # 3.11 is not in the CI matrix
    assert 'Programming Language :: Python :: 3.11' not in text
