import os
from pathlib import Path
import stat
import time

import pytest

from scripts import cleanup_reports as utility


@pytest.fixture
def tree(tmp_path):
    folder = tmp_path / "reports/run"
    folder.mkdir(parents=True)
    (folder / "record.json").write_bytes(b"{}")
    (tmp_path / "README.md").write_text("source")
    return tmp_path


def test_default_dry_run(tree, monkeypatch, capsys):
    monkeypatch.setattr(utility, "ROOT", tree)
    assert utility.main([]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert (tree / "reports/run/record.json").exists()


def test_confirm_all_keeps_reports_and_source(tree, monkeypatch, capsys):
    monkeypatch.setattr(utility, "ROOT", tree)
    assert utility.main(["--all", "--confirm"]) == 0
    assert "1 files, 1 directories, 2 bytes" in capsys.readouterr().out
    assert list((tree / "reports").iterdir()) == []
    assert (tree / "README.md").read_text() == "source"


def test_age_filter_retains_recent_files_and_parent(tree):
    old = tree / "reports/run/record.json"
    timestamp = time.time() - 10 * 86400
    os.utime(old, (timestamp, timestamp))
    recent = tree / "reports/run/recent.json"
    recent.write_text("recent")
    entries = utility.cleanup(tree, 7, confirm=True)
    assert [e.path for e in entries] == [old]
    assert recent.exists() and recent.parent.exists()


def test_age_threshold_is_inclusive(tree):
    old = tree / "reports/run/record.json"
    os.utime(old, (100000, 100000))
    assert old in [e.path for e in utility.plan_cleanup(tree, 1, now=186400)]


def test_missing_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(utility, "ROOT", tmp_path)
    assert utility.main(["--all", "--confirm"]) == 0
    assert "0 files" in capsys.readouterr().out
    assert not (tmp_path / "reports").exists()


@pytest.mark.parametrize("args", [["--confirm"], ["--older-than-days", "-1"], ["--all", "--older-than-days", "1"], ["../src"]])
def test_bad_cli_selection(args):
    with pytest.raises(SystemExit) as error:
        utility.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize("name", sorted(utility.PROTECTED))
def test_protected_tree_fails_before_deletion(tree, name):
    protected = tree / "reports/run" / name
    protected.mkdir()
    with pytest.raises(ValueError):
        utility.cleanup(tree, confirm=True)
    assert (tree / "reports/run/record.json").exists()


def test_traversal_rejected(tree):
    with pytest.raises(ValueError):
        utility._checked(tree / "reports/../README.md", tree / "reports")


@pytest.mark.parametrize("root_link", [True, False])
def test_reparse_point_refused_without_following(tree, monkeypatch, root_link):
    # Portable Windows-junction simulation; also exercises the root path guard.
    target = tree / ("reports" if root_link else "reports/run")
    original = Path.lstat
    def lstat(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == target:
            from types import SimpleNamespace
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return info
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(ValueError, match="reparse"):
        utility.cleanup(tree, confirm=True)
    assert (tree / "reports/run/record.json").exists()


def test_changed_plan_refused(tree, monkeypatch):
    original = utility.plan_cleanup
    def plan(*args):
        result = original(*args)
        (tree / "reports/run/record.json").write_text("changed")
        return result
    monkeypatch.setattr(utility, "plan_cleanup", plan)
    with pytest.raises(ValueError, match="changed"):
        utility.cleanup(tree, confirm=True)
    assert (tree / "reports/run/record.json").exists()
