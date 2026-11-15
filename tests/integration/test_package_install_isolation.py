"""Exercise the package smoke test's isolation guard in real interpreters."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import venv

import pytest


def load_smoke():
    path = Path(__file__).resolve().parents[2] / "scripts" / "package_smoke.py"
    spec = importlib.util.spec_from_file_location("package_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated_python(tmp_path):
    root = tmp_path / "venv"
    venv.EnvBuilder(with_pip=False).create(root)
    python = root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    site = Path(subprocess.check_output(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True,
    ).strip())
    return python, site


def make_package(parent):
    package = parent / "promptmigrate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text("", encoding="utf-8")


def test_smoke_accepts_modules_installed_inside_venv(tmp_path, isolated_python):
    python, site = isolated_python
    make_package(site)
    load_smoke().verify_install(python, tmp_path)


def test_smoke_rejects_source_import_via_pth(tmp_path, isolated_python, capfd):
    python, site = isolated_python
    source = tmp_path / "source"
    make_package(source)
    (site / "source.pth").write_text(str(source) + "\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        load_smoke().verify_install(python, tmp_path)
    assert "imported from outside the venv" in capfd.readouterr().err
