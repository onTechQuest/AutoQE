"""Negative distribution cases ensure CI fails closed on packaging regressions."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.verify_wheel import verify_wheel


@pytest.fixture
def package(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    for folder in ("src/autoqe", "autoqe_integration"):
        source = tmp_path / folder
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("# source\n")
    members = {f"{name}/__init__.py": b"# source\n" for name in ("autoqe", "autoqe_integration")}
    members.update({f"autoqe-0.1.0.dist-info/{name}": b"" for name in ("METADATA", "WHEEL", "RECORD")})
    return tmp_path, members


def write_wheel(root, members):
    wheel = root / "test.whl"
    with ZipFile(wheel, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return wheel


def test_valid_distribution(package):
    root, members = package
    assert verify_wheel(write_wheel(root, members), root) == {
        "autoqe": 1, "autoqe_integration": 1, "autoqe-0.1.0.dist-info": 3}


@pytest.mark.parametrize("name", [
    "integration/__init__.py", "qualification/data.json", "tests/test.py",
    "reports/evidence.json", "examples/profile.json", "agentguard/__init__.py",
    "autoqe/__pycache__/x.pyc", "autoqe/x.pyc", "autoqe/agentguard/scoring.py",
    "../escape.py", "/autoqe/absolute.py", "autoqe\\bad.py",
])
def test_forbidden_distribution_member(package, name):
    root, members = package
    members[name] = b"unexpected"
    with pytest.raises(ValueError):
        verify_wheel(write_wheel(root, members), root)


@pytest.mark.parametrize("name", ["autoqe/__init__.py", "autoqe_integration/__init__.py", "autoqe-0.1.0.dist-info/METADATA"])
def test_missing_distribution_member(package, name):
    root, members = package
    del members[name]
    with pytest.raises(ValueError, match="Incomplete"):
        verify_wheel(write_wheel(root, members), root)


def test_stale_package_source(package):
    root, members = package
    members["autoqe/__init__.py"] = b"stale build"
    with pytest.raises(ValueError, match="mismatch"):
        verify_wheel(write_wheel(root, members), root)


def test_duplicate_member(package):
    root, members = package
    wheel = write_wheel(root, members)
    with ZipFile(wheel, "a") as archive, pytest.warns(UserWarning, match="Duplicate"):
        archive.writestr("autoqe/__init__.py", b"duplicate")
    with pytest.raises(ValueError, match="Duplicate"):
        verify_wheel(wheel, root)
