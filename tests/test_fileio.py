"""落檔的讀寫（arm/fileio.py；docs/code_ponytail_audit.md 第 3 條）：寫到一半被砍掉時原本的檔還在；
七本前瞻紀錄讀到壞檔時停下報錯、不從頭記（頁面顯示照樣當成沒有）。"""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from arm import fileio

ROOT = Path(__file__).resolve().parent.parent
BAD = '{"v":1,"days":{\n"2026-10-30":{"st'          # 寫到一半被砍掉的樣子


class Killed(Exception):
    pass


def _bad(p: Path) -> bytes:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BAD, encoding="utf-8")
    return p.read_bytes()


def test_write_replaces_whole_file(tmp_path):
    p = tmp_path / "a" / "x.json"
    fileio.write_text(p, "舊的")
    fileio.write_text(p, "新的內容")
    assert p.read_text(encoding="utf-8") == "新的內容"
    fileio.write_bytes(tmp_path / "b.gz", b"\x00\x01")
    assert (tmp_path / "b.gz").read_bytes() == b"\x00\x01"
    assert not list(tmp_path.rglob("*.tmp"))


def test_killed_before_rename_keeps_old_file(tmp_path, monkeypatch):
    p = tmp_path / "x.json"
    p.write_text('{"ok": 1}', encoding="utf-8")

    def killed(*a, **k):
        raise Killed

    monkeypatch.setattr(fileio.os, "replace", killed)
    with pytest.raises(Killed):
        fileio.write_text(p, '{"ok": 2, "half')
    assert json.loads(p.read_text(encoding="utf-8")) == {"ok": 1}


def test_tmp_files_are_gitignored():
    if not shutil.which("git"):
        pytest.skip("沒有 git")
    r = subprocess.run(["git", "check-ignore", "-q", "data/lab/.val_log.json.123.tmp"], cwd=ROOT)
    if r.returncode not in (0, 1):
        pytest.skip("不是 git 工作目錄")
    assert r.returncode == 0


def test_read_json_missing_bad_and_strict(tmp_path, monkeypatch, capsys):
    p = tmp_path / "x.json"
    assert fileio.read_json(p, {"d": 1}) == {"d": 1}
    _bad(p)
    assert fileio.read_json(p, {}) == {}
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(RuntimeError, match="讀不起來"):
        fileio.read_json(p, {}, strict=True)
    assert "::error::" in capsys.readouterr().out


def test_fund_nav_history_not_restarted(tmp_path, monkeypatch):
    from arm import fundnav
    p = tmp_path / "fund_nav_history.json"
    before = _bad(p)
    monkeypatch.setattr(fundnav, "PATH", p)
    with pytest.raises(RuntimeError):
        fundnav.record([{"fund_id": "47", "nav": 10.0, "nav_date": "2026/10/30"}])
    with pytest.raises(RuntimeError):
        fundnav.backfill_official([{"fund_id": "47"}], lambda fid: {})
    assert p.read_bytes() == before
    assert fundnav.load() == {}


def test_core_live_not_restarted(tmp_path, monkeypatch):
    from arm.lab import core
    p = tmp_path / "core_live.json"
    before = _bad(p)
    monkeypatch.setattr(core, "LIVE", p)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(RuntimeError):
        core.record({}, None)
    assert p.read_bytes() == before
    assert core.load_live()["days"] == {}


def test_val_log_not_restarted(tmp_path, monkeypatch):
    from arm.lab import store, valog
    monkeypatch.setattr(store, "LAB", tmp_path)
    p = tmp_path / valog.FP
    before = _bad(p)
    with pytest.raises(RuntimeError):
        valog.update({"adv": {"last": "2026-10-30"}}, write_file=True)
    assert p.read_bytes() == before
    assert valog.read()["days"] == {}


def test_ytd_live_not_restarted(tmp_path, monkeypatch):
    from arm.lab import store, ytd
    monkeypatch.setattr(store, "LAB", tmp_path)
    p = tmp_path / ytd.LIVE_FILE
    before = _bad(p)
    with pytest.raises(RuntimeError):
        ytd.record_tw("2099-01-02", {"2330": [{"w": 0.1, "h": 1}]}, 0.2, force=True)
    assert p.read_bytes() == before
    assert ytd.load_live()["tw"] == {}


def test_us_qm_live_not_restarted(tmp_path, monkeypatch):
    from arm.lab import ussxqm as QM
    p = tmp_path / "ussx_qm_live.json"
    before = _bad(p)
    monkeypatch.setattr(QM, "LIVE", p)
    with pytest.raises(RuntimeError):
        QM.live_update({"cal": [], "T": 0, "cols": {"wk": []}}, {"a": 0}, {})
    assert p.read_bytes() == before
    assert QM.load_live()["weeks"] == {}


def test_cands_live_not_restarted(tmp_path):
    from arm.lab import candrun as R
    p = tmp_path / "cands_live.json"
    before = _bad(p)
    spec = tmp_path / "spec.json"
    spec.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(RuntimeError):
        R.forward(object(), live_path=p, spec_path=spec, board={})
    assert p.read_bytes() == before
    assert R.load_live(p)["items"] == {}


def test_sxlive_log_not_restarted(tmp_path, monkeypatch):
    from arm.lab import store, sxlive
    monkeypatch.setattr(store, "LAB", tmp_path)
    p = tmp_path / sxlive.S.LOG_FILE
    before = _bad(p)
    with pytest.raises(RuntimeError):
        sxlive.update(None, {"P": SimpleNamespace(cal=[])}, write_file=True)
    assert p.read_bytes() == before
    assert sxlive.read()["weeks"] == {}
