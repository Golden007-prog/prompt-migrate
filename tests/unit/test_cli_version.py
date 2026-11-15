"""Tests for the --version CLI flag (Issue #16)."""
import importlib.metadata
import pytest
from promptmigrate import __version__, cli


def test_version_flag_prints_version_and_exits_0(capsys, monkeypatch):
    monkeypatch.setattr(importlib.metadata, "version", lambda pkg: "1.2.3" if pkg == "promptmigrate" else "unknown")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    out, err = capsys.readouterr()
    assert out.strip() == "promptmigrate 1.2.3"
    assert err == ""


def test_version_fallback_when_package_not_found(monkeypatch):
    def raise_not_found(pkg):
        raise importlib.metadata.PackageNotFoundError(pkg)

    monkeypatch.setattr(importlib.metadata, "version", raise_not_found)
    assert cli._get_version() == __version__


def test_build_parser_has_version_option():
    parser = cli.build_parser()
    options = [opt for action in parser._actions for opt in action.option_strings]
    assert "--version" in options
