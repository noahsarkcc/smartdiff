"""
updater 模块 + /api/update/* 端点测试
=====================================

不需要真实网络，通过 unittest.mock 替换 updater 的 HTTP 调用。

直接运行：python tests/test_updater.py
"""
import os
import sys
import json
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import updater
import server


RESET = "\033[0m"; RED = "\033[91m"; GREEN = "\033[92m"; CYAN = "\033[96m"

_passed = 0
_failed = 0
_failures = []


def t(name):
    def deco(fn):
        def wrapper(*a, **kw):
            global _passed, _failed
            try:
                fn(*a, **kw)
                _passed += 1
                print(f"  {GREEN}PASS{RESET} {name}")
            except AssertionError as e:
                _failed += 1
                _failures.append((name, str(e)))
                print(f"  {RED}FAIL{RESET} {name}")
                print(f"       {e}")
            except Exception as e:
                _failed += 1
                _failures.append((name, f"EXCEPTION: {type(e).__name__}: {e}"))
                print(f"  {RED}ERROR{RESET} {name}")
                print(f"       {type(e).__name__}: {e}")
        return wrapper
    return deco


def section(title):
    print(f"\n{CYAN}── {title} ──{RESET}")


class FakeResp:
    """模拟 urllib response（支持 with 语句、read、headers）。"""
    def __init__(self, data=b"", headers=None, chunks=None):
        self._data = data
        self._chunks = list(chunks) if chunks else None
        self.headers = headers or {}

    def read(self, size=-1):
        if self._chunks is not None:
            return self._chunks.pop(0) if self._chunks else b""
        d, self._data = self._data, b""
        return d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _reset_updater():
    updater._use_proxy = False
    with updater._dl_lock:
        updater._dl_state.update(status="idle", percent=0, downloaded=0,
                                 total=0, error=None, path=None)


def _reset_server_cache():
    with server._update_cache_lock:
        server._update_cache["result"] = None
        server._update_cache["ts"] = 0.0


def _release_json(tag="v9.9.9", with_asset=True, notes="notes here"):
    info = {
        "tag_name": tag,
        "body": notes,
        "html_url": f"https://github.com/{updater.GITHUB_REPO}/releases/tag/{tag}",
        "assets": [],
    }
    if with_asset:
        info["assets"].append({
            "name": "SmartDiff.exe",
            "size": 12345,
            "browser_download_url":
                f"https://github.com/{updater.GITHUB_REPO}/releases/download/{tag}/SmartDiff.exe",
        })
    info["assets"].append({"name": "other.zip", "size": 1,
                           "browser_download_url": "https://example.com/other.zip"})
    return json.dumps(info).encode("utf-8")


# ── 1. 版本号比较 ────────────────────────────────────────


@t("parse_version：v 前缀 / 纯数字 / 空值")
def test_parse_version():
    assert updater.parse_version("v1.3.7") == (1, 3, 7)
    assert updater.parse_version("1.4.0") == (1, 4, 0)
    assert updater.parse_version("V2.0") == (2, 0)
    assert updater.parse_version("") == (0,)
    assert updater.parse_version(None) == (0,)


@t("parse_version：非数字后缀按前导数字解析")
def test_parse_version_suffix():
    assert updater.parse_version("v1.4.0-beta") == (1, 4, 0)
    assert updater.parse_version("v1.x.2") == (1, 0, 2)


@t("is_newer：大于 / 等于 / 小于 / 位数不齐补零")
def test_is_newer():
    assert updater.is_newer("v1.4.0", "1.3.7") is True
    assert updater.is_newer("v1.3.7", "1.3.7") is False
    assert updater.is_newer("v1.3.6", "1.3.7") is False
    assert updater.is_newer("v1.4", "1.4.0") is False
    assert updater.is_newer("v2.0", "1.9.9") is True
    assert updater.is_newer("v1.4.0.1", "1.4.0") is True


# ── 2. 代理 URL 与 _fetch 回退 ───────────────────────────


@t("proxied：代理前缀拼接")
def test_proxied():
    url = "https://api.github.com/repos/x/releases/latest"
    assert updater.proxied(url) == updater.PROXY_PREFIX + url


@t("_fetch：直连成功不走代理")
def test_fetch_direct():
    _reset_updater()
    calls = []

    def fake_open(url, timeout):
        calls.append(url)
        return FakeResp(b"direct")

    with patch.object(updater, "_open", side_effect=fake_open):
        data = updater._fetch("https://api.github.com/x")
    assert data == b"direct", data
    assert calls == ["https://api.github.com/x"], calls
    assert updater._use_proxy is False


@t("_fetch：直连失败自动用代理重试并记住通道")
def test_fetch_proxy_fallback():
    _reset_updater()
    calls = []

    def fake_open(url, timeout):
        calls.append(url)
        if not url.startswith(updater.PROXY_PREFIX):
            raise OSError("connection refused")
        return FakeResp(b"via proxy")

    with patch.object(updater, "_open", side_effect=fake_open):
        data = updater._fetch("https://api.github.com/x")
        assert data == b"via proxy", data
        assert updater._use_proxy is True
        # 第二次请求应直接走代理，不再尝试直连
        calls.clear()
        updater._fetch("https://api.github.com/y")
    assert calls == [updater.proxied("https://api.github.com/y")], calls
    _reset_updater()


# ── 3. check_update 解析 ─────────────────────────────────


@t("check_update：发现新版本并解析 exe 资产")
def test_check_update_has_update():
    _reset_updater()
    with patch.object(updater, "_fetch", return_value=_release_json("v9.9.9")):
        r = updater.check_update("1.3.7")
    assert r["has_update"] is True
    assert r["latest"] == "9.9.9"
    assert r["current"] == "1.3.7"
    assert r["asset_url"].endswith("/SmartDiff.exe"), r["asset_url"]
    assert r["asset_size"] == 12345
    assert r["notes"] == "notes here"
    assert r["proxy_page_url"].startswith(updater.PROXY_PREFIX)
    assert r["is_frozen"] is False


@t("check_update：已是最新版本")
def test_check_update_up_to_date():
    _reset_updater()
    with patch.object(updater, "_fetch", return_value=_release_json("v1.3.7")):
        r = updater.check_update("1.3.7")
    assert r["has_update"] is False


@t("check_update：release 无 exe 资产时 asset_url=None")
def test_check_update_no_asset():
    _reset_updater()
    with patch.object(updater, "_fetch",
                      return_value=_release_json("v9.9.9", with_asset=False)):
        r = updater.check_update("1.3.7")
    assert r["has_update"] is True
    assert r["asset_url"] is None
    assert r["asset_size"] == 0


# ── 4. 下载状态机 ────────────────────────────────────────


@t("start_download：源码模式直接返回错误状态")
def test_start_download_source_mode():
    _reset_updater()
    r = updater.start_download("https://example.com/SmartDiff.exe")
    assert r["status"] == "error"
    assert "git pull" in r["error"]


@t("_download_worker：流式写入 .part 后改名 .new，进度 100%")
def test_download_worker():
    _reset_updater()
    workdir = tempfile.mkdtemp(prefix="xmldev_upd_")
    dest = os.path.join(workdir, "SmartDiff.exe.new")
    chunks = [b"a" * 100, b"b" * 100, b""]

    def fake_open(url, timeout):
        return FakeResp(headers={"Content-Length": "200"}, chunks=list(chunks))

    with patch.object(updater, "_open", side_effect=fake_open):
        with updater._dl_lock:
            updater._dl_state.update(status="downloading", percent=0,
                                     downloaded=0, total=0, error=None, path=None)
        updater._download_worker("https://example.com/SmartDiff.exe", dest)

    state = updater.get_progress()
    assert state["status"] == "ready", state
    assert state["percent"] == 100
    assert state["downloaded"] == 200
    assert state["path"] == dest
    assert os.path.isfile(dest)
    assert not os.path.isfile(dest + ".part")
    os.remove(dest)
    os.rmdir(workdir)
    _reset_updater()


@t("_download_worker：失败时清理 .part 并记录错误")
def test_download_worker_error():
    _reset_updater()
    workdir = tempfile.mkdtemp(prefix="xmldev_upd_")
    dest = os.path.join(workdir, "SmartDiff.exe.new")

    def fake_open(url, timeout):
        raise OSError("network down")

    # _use_proxy=True 时不再二次回退，直接报错
    updater._use_proxy = True
    with patch.object(updater, "_open", side_effect=fake_open):
        updater._download_worker("https://example.com/SmartDiff.exe", dest)

    state = updater.get_progress()
    assert state["status"] == "error", state
    assert "network down" in state["error"]
    assert not os.path.isfile(dest + ".part")
    os.rmdir(workdir)
    _reset_updater()


@t("apply_update：源码模式返回 ok=False")
def test_apply_update_source_mode():
    _reset_updater()
    r = updater.apply_update()
    assert r["ok"] is False
    assert "git pull" in r["error"]


# ── 5. /api/update/* 端点 ────────────────────────────────


_FAKE_RESULT = {
    "has_update": True, "current": "1.3.7", "latest": "9.9.9",
    "notes": "n", "html_url": "https://github.com/x",
    "proxy_page_url": updater.PROXY_PREFIX + "https://github.com/x",
    "asset_url": "https://github.com/x/SmartDiff.exe", "asset_size": 1,
    "is_frozen": False, "proxy_used": False,
}


@t("/api/update/check：返回检查结果且写入缓存")
def test_api_check():
    _reset_server_cache()
    client = server.app.test_client()
    with patch.object(updater, "check_update", return_value=dict(_FAKE_RESULT)) as m:
        r = client.get("/api/update/check")
        assert r.status_code == 200, r.status_code
        data = r.get_json()
        assert data["has_update"] is True
        assert data["latest"] == "9.9.9"
        assert data["cached"] is False
        # 第二次命中缓存，不再调用 check_update
        r2 = client.get("/api/update/check")
        assert r2.get_json()["cached"] is True
        assert m.call_count == 1, m.call_count
    _reset_server_cache()


@t("/api/update/check：force=1 跳过缓存")
def test_api_check_force():
    _reset_server_cache()
    client = server.app.test_client()
    with patch.object(updater, "check_update", return_value=dict(_FAKE_RESULT)) as m:
        client.get("/api/update/check")
        r = client.get("/api/update/check?force=1")
        assert r.get_json()["cached"] is False
        assert m.call_count == 2, m.call_count
    _reset_server_cache()


@t("/api/update/check：网络失败返回 502")
def test_api_check_failure():
    _reset_server_cache()
    client = server.app.test_client()
    with patch.object(updater, "check_update", side_effect=OSError("timed out")):
        r = client.get("/api/update/check")
    assert r.status_code == 502, r.status_code
    assert "timed out" in r.get_json()["error"]
    _reset_server_cache()


@t("/api/update/download：源码模式返回 400")
def test_api_download_source_mode():
    _reset_server_cache()
    client = server.app.test_client()
    r = client.post("/api/update/download", json={"asset_url": "https://x/SmartDiff.exe"})
    assert r.status_code == 400, r.status_code
    assert "git pull" in r.get_json()["error"]


@t("/api/update/download：frozen 但无资产时返回 400")
def test_api_download_no_asset():
    _reset_server_cache()
    client = server.app.test_client()
    with patch.object(updater, "is_frozen", return_value=True):
        r = client.post("/api/update/download", json={})
    assert r.status_code == 400, r.status_code


@t("/api/update/progress：初始为 idle")
def test_api_progress():
    _reset_updater()
    client = server.app.test_client()
    r = client.get("/api/update/progress")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "idle", data
    assert set(data) >= {"status", "percent", "downloaded", "total", "error"}


@t("/api/update/apply：源码模式返回 400")
def test_api_apply_source_mode():
    client = server.app.test_client()
    r = client.post("/api/update/apply")
    assert r.status_code == 400, r.status_code
    assert "git pull" in r.get_json()["error"]


def main():
    print(f"{CYAN}updater 模块 + /api/update/* 端点测试{RESET}")

    section("1. 版本号比较")
    test_parse_version()
    test_parse_version_suffix()
    test_is_newer()

    section("2. 代理 URL 与 _fetch 回退")
    test_proxied()
    test_fetch_direct()
    test_fetch_proxy_fallback()

    section("3. check_update 解析")
    test_check_update_has_update()
    test_check_update_up_to_date()
    test_check_update_no_asset()

    section("4. 下载状态机")
    test_start_download_source_mode()
    test_download_worker()
    test_download_worker_error()
    test_apply_update_source_mode()

    section("5. /api/update/* 端点")
    test_api_check()
    test_api_check_force()
    test_api_check_failure()
    test_api_download_source_mode()
    test_api_download_no_asset()
    test_api_progress()
    test_api_apply_source_mode()

    print()
    total = _passed + _failed
    if _failed == 0:
        print(f"{GREEN}== 全部通过：{_passed}/{total} =={RESET}")
        return 0
    print(f"{RED}== 失败 {_failed} / 通过 {_passed} / 共 {total} =={RESET}")
    for name, msg in _failures:
        print(f"  {RED}- {name}{RESET}")
        print(f"      {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
