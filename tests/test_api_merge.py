"""
/api/merge/* 端到端测试（Flask test client + mock SVN）
=====================================================

不需要真实 SVN 仓库，通过 unittest.mock 替换 svn_helper 的网络/磁盘调用。

直接运行：python tests/test_api_merge.py
"""
import os
import sys
import json
import shutil
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server
import svn_helper
import xml_parser


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BASE_PATH = os.path.join(DATA_DIR, "base.xml")
MINE_PATH = os.path.join(DATA_DIR, "mine.xml")
THEIRS_PATH = os.path.join(DATA_DIR, "theirs.xml")


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


def with_workspace(fn):
    """装饰器：每个测试创建临时工作区 + 复制 mine.xml，并 mock SVN。"""
    def wrapper():
        workdir = tempfile.mkdtemp(prefix="xmldev_test_")
        try:
            fpath = os.path.join(workdir, "items.xml")
            shutil.copy(MINE_PATH, fpath)
            with open(BASE_PATH, "r", encoding="utf-8") as f:
                base_text = f.read()
            with open(THEIRS_PATH, "r", encoding="utf-8") as f:
                theirs_text = f.read()

            client = server.app.test_client()
            with patch.object(server, "_get_work_dir", return_value=workdir), \
                 patch.object(svn_helper, "is_available", return_value=True), \
                 patch.object(svn_helper, "get_base_content_raw",
                              return_value=base_text.encode("utf-8")), \
                 patch.object(svn_helper, "get_svn_info",
                              return_value={"url": "https://svn.example/items"}), \
                 patch.object(svn_helper, "get_remote_head_revision", return_value=42), \
                 patch.object(svn_helper, "get_file_at_revision_raw",
                              return_value=theirs_text.encode("utf-8")):
                fn(client, workdir, fpath)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return wrapper


# ── 1. /api/merge/preview ────────────────────────────────


@t("preview：返回结构包含 sheets / summary / labels")
@with_workspace
def test_preview_structure(client, workdir, fpath):
    r = client.post("/api/merge/preview", json={"file": "items.xml"})
    assert r.status_code == 200, f"status={r.status_code} body={r.get_data(as_text=True)}"
    data = r.get_json()
    assert "sheets" in data
    assert "summary" in data
    assert data["theirs_label"] == "r42"
    assert data["theirs_revision"] == 42
    assert data["base_label"] == "SVN BASE"
    assert "Items" in data["sheets"]


@t("preview：summary 反映出冲突数量")
@with_workspace
def test_preview_summary(client, workdir, fpath):
    r = client.post("/api/merge/preview", json={"file": "items.xml"})
    s = r.get_json()["summary"]
    assert s["row_conflicts"] == 3, f"实际 {s['row_conflicts']}（期望 3）"
    assert s["cell_conflicts"] == 1, f"实际 {s['cell_conflicts']}（期望 1）"
    assert s["conflicts"] == 4


@t("preview：拒绝 .xlsx 文件，返回 400")
@with_workspace
def test_preview_rejects_xlsx(client, workdir, fpath):
    r = client.post("/api/merge/preview", json={"file": "items.xlsx"})
    assert r.status_code == 400
    assert "xml" in r.get_json()["error"].lower() or "XML" in r.get_json()["error"]


@t("preview：缺失 file 参数 → 400")
@with_workspace
def test_preview_missing_file(client, workdir, fpath):
    r = client.post("/api/merge/preview", json={})
    assert r.status_code == 400


@t("preview：file 不存在 → 404")
@with_workspace
def test_preview_missing_actual_file(client, workdir, fpath):
    r = client.post("/api/merge/preview", json={"file": "nonexistent.xml"})
    assert r.status_code == 404


# ── 2. /api/merge/apply ──────────────────────────────────


@t("apply：未决议时返回 400 + unresolved 列表")
@with_workspace
def test_apply_unresolved(client, workdir, fpath):
    r = client.post("/api/merge/apply", json={
        "file": "items.xml",
        "resolutions": [],
    })
    assert r.status_code == 400
    body = r.get_json()
    assert "unresolved" in body
    assert len(body["unresolved"]) == 4


@t("apply：全部决议后写回成功，文件内容符合预期")
@with_workspace
def test_apply_full(client, workdir, fpath):
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "theirs"},
        {"sheet": "Items", "row_key": "1010", "choice": "accept_theirs"},
        {"sheet": "Items", "row_key": "1011", "choice": "accept_theirs_delete"},
        {"sheet": "Items", "row_key": "2004", "choice": "merge"},
        {"sheet": "Items", "row_key": "2004", "col": "B", "choice": "custom", "value": "调和版本"},
        {"sheet": "Items", "row_key": "2004", "col": "D", "choice": "mine"},
    ]
    r = client.post("/api/merge/apply", json={
        "file": "items.xml",
        "resolutions": resolutions,
    })
    assert r.status_code == 200, f"body={r.get_data(as_text=True)}"
    body = r.get_json()
    assert body["ok"] is True
    assert body["applied"] == 6
    assert body["svn_resolved"] is False  # 默认不标记

    parsed = xml_parser.parse_file(fpath)
    rows = parsed["sheets"]["Items"]["rows"]
    by_id = {r["cells"]["A"]: r["cells"] for r in rows[1:] if r["cells"].get("A")}

    # 单元格冲突 1006.B 用了 theirs
    assert by_id["1006"]["B"] == "远程改后"
    # 自动决议项也都生效
    assert by_id["1003"]["C"] == "33"
    assert by_id["1005"]["B"] == "本地改名称"
    assert by_id["1005"]["C"] == "55"
    # 1010 行被恢复
    assert "1010" in by_id and by_id["1010"]["D"] == "远程修改"
    # 1011 被删除
    assert "1011" not in by_id
    # 2004 走 merge：B=custom(调和版本)，D=mine(本地说)
    assert by_id["2004"]["B"] == "调和版本"
    assert by_id["2004"]["D"] == "本地说"


@t("apply：mark_resolved=true 时尝试 svn resolve（mocked）")
@with_workspace
def test_apply_mark_resolved(client, workdir, fpath):
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "mine"},
        {"sheet": "Items", "row_key": "1010", "choice": "keep_mine_delete"},
        {"sheet": "Items", "row_key": "1011", "choice": "keep_mine"},
        {"sheet": "Items", "row_key": "2004", "choice": "keep_mine"},
    ]
    with patch.object(svn_helper, "_run", return_value=(0, "Resolved", "")):
        r = client.post("/api/merge/apply", json={
            "file": "items.xml",
            "resolutions": resolutions,
            "mark_resolved": True,
        })
    assert r.status_code == 200
    assert r.get_json()["svn_resolved"] is True


@t("apply：拒绝 .xlsx 文件")
@with_workspace
def test_apply_rejects_xlsx(client, workdir, fpath):
    r = client.post("/api/merge/apply", json={
        "file": "items.xlsx",
        "resolutions": [],
    })
    assert r.status_code == 400


# ── 3. /api/merge/svn-mark-resolved ──────────────────────


@t("svn-mark-resolved：成功路径")
@with_workspace
def test_svn_mark_resolved_ok(client, workdir, fpath):
    with patch.object(svn_helper, "_run", return_value=(0, "Resolved", "")):
        r = client.post("/api/merge/svn-mark-resolved", json={"file": "items.xml"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


@t("svn-mark-resolved：svn resolve 失败 → 500")
@with_workspace
def test_svn_mark_resolved_fail(client, workdir, fpath):
    with patch.object(svn_helper, "_run", return_value=(1, "", "svn resolve failed")):
        r = client.post("/api/merge/svn-mark-resolved", json={"file": "items.xml"})
    assert r.status_code == 500


# ── 4. SVN update 冲突检测 ───────────────────────────────


@t("files：递归列出子目录 .xls 文件")
def test_files_lists_nested_xls():
    workdir = tempfile.mkdtemp(prefix="xmldev_test_")
    try:
        nested_dir = os.path.join(workdir, "configs")
        os.makedirs(nested_dir, exist_ok=True)
        with open(os.path.join(nested_dir, "items.xls"), "wb") as f:
            f.write(b"placeholder")
        client = server.app.test_client()
        with patch.object(server, "_get_work_dir", return_value=workdir):
            r = client.get("/api/files")
        assert r.status_code == 200
        body = r.get_json()
        names = [f["name"] for f in body["files"]]
        assert "configs/items.xls" in names
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@t("svn/modified：子目录 .xls 使用工作区相对路径作为 name")
def test_svn_modified_nested_xls_name_is_relative():
    workdir = tempfile.mkdtemp(prefix="xmldev_test_")
    try:
        nested = os.path.join(workdir, "configs", "items.xls")
        client = server.app.test_client()
        with patch.object(server, "_get_work_dir", return_value=workdir), \
             patch.object(svn_helper, "is_available", return_value=True), \
             patch.object(svn_helper, "get_modified_files", return_value=[
                 {"path": nested, "status": "modified", "name": "items.xls"},
             ]):
            r = client.get("/api/svn/modified")
        assert r.status_code == 200
        body = r.get_json()
        assert body["files"][0]["name"] == "configs/items.xls"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@t("api/parse：路径穿越（.. / 绝对路径）被拒绝 → 400")
def test_parse_path_traversal_rejected():
    workdir = tempfile.mkdtemp(prefix="xmldev_test_")
    try:
        outside_abs = os.path.abspath(os.path.join(workdir, "..", "outside.xml"))
        client = server.app.test_client()
        with patch.object(server, "_get_work_dir", return_value=workdir):
            r1 = client.get("/api/parse?file=../escape.xml")
            r2 = client.get(f"/api/parse?file={outside_abs}")
            r3 = client.post("/api/merge/apply", json={
                "file": "../escape.xml", "resolutions": []})
        assert r1.status_code == 400, f"..穿越未被拒绝: {r1.status_code}"
        assert r2.status_code == 400, f"绝对路径未被拒绝: {r2.status_code}"
        assert r3.status_code in (400, 503), f"merge 穿越未被拒绝: {r3.status_code}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@t("svn/update check_only：子目录文件按工作区相对路径匹配冲突")
def test_svn_update_check_only_nested_conflict():
    workdir = tempfile.mkdtemp(prefix="xmldev_test_")
    try:
        nested = os.path.join(workdir, "configs", "items.xml")
        local_only = os.path.join(workdir, "configs", "local_only.xml")
        client = server.app.test_client()
        with patch.object(server, "_get_work_dir", return_value=workdir), \
             patch.object(svn_helper, "is_available", return_value=True), \
             patch.object(svn_helper, "get_modified_files", return_value=[
                 {"path": nested, "status": "modified", "name": "items.xml"},
                 {"path": local_only, "status": "modified", "name": "local_only.xml"},
             ]), \
             patch.object(svn_helper, "get_remote_changed_files", return_value=[
                 "configs/items.xml",
                 "configs/remote_only.xml",
             ]):
            r = client.post("/api/svn/update", json={"check_only": True})
        assert r.status_code == 200, f"body={r.get_data(as_text=True)}"
        body = r.get_json()
        assert body["conflicts"] == ["configs/items.xml"]
        assert body["safe_updates"] == 1
        assert body["local_only"] == ["configs/local_only.xml"]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ── 5. preview/apply 二次幂等 ────────────────────────────


@t("apply 后再次 preview：summary 显示已无冲突")
@with_workspace
def test_idempotent_after_apply(client, workdir, fpath):
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "theirs"},
        {"sheet": "Items", "row_key": "1010", "choice": "accept_theirs"},
        {"sheet": "Items", "row_key": "1011", "choice": "accept_theirs_delete"},
        {"sheet": "Items", "row_key": "2004", "choice": "accept_theirs"},
    ]
    r = client.post("/api/merge/apply", json={
        "file": "items.xml",
        "resolutions": resolutions,
    })
    assert r.status_code == 200

    # MINE 文件已被覆盖；用合并后的内容当 MINE，再用同样的 BASE/THEIRS 跑一次 preview
    # 这次本地（MINE）已经 == THEIRS（除被本地保留的部分），冲突应大幅减少
    r2 = client.post("/api/merge/preview", json={"file": "items.xml"})
    assert r2.status_code == 200
    s = r2.get_json()["summary"]
    # 接受了所有远程后，与 BASE 的 diff 是合并后的状态；冲突应为 0
    assert s["conflicts"] == 0, f"二次 preview 仍有冲突: {s}"


# ── Main ────────────────────────────────────────────────


def main():
    print(f"{CYAN}/api/merge/* 端到端测试（mocked SVN）{RESET}")
    print(f"  数据目录: {DATA_DIR}")

    section("1. /api/merge/preview")
    test_preview_structure()
    test_preview_summary()
    test_preview_rejects_xlsx()
    test_preview_missing_file()
    test_preview_missing_actual_file()

    section("2. /api/merge/apply")
    test_apply_unresolved()
    test_apply_full()
    test_apply_mark_resolved()
    test_apply_rejects_xlsx()

    section("3. /api/merge/svn-mark-resolved")
    test_svn_mark_resolved_ok()
    test_svn_mark_resolved_fail()

    section("4. SVN update 冲突检测")
    test_files_lists_nested_xls()
    test_svn_modified_nested_xls_name_is_relative()
    test_parse_path_traversal_rejected()
    test_svn_update_check_only_nested_conflict()

    section("5. 幂等性")
    test_idempotent_after_apply()

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
