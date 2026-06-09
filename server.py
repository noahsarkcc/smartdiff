"""
Flask server for SmartDiff.
Provides REST API for parsing, diffing, and SVN integration.
"""
__version__ = "1.3.6"

import os
import sys
import json
import webbrowser
import threading
from flask import Flask, request, jsonify, send_from_directory

import xml_parser
import xlsx_parser
import xml_differ
import xml_merger
import svn_helper


SUPPORTED_EXTENSIONS = (".xml", ".xlsx", ".xls")


def _is_excel_binary(filename: str) -> bool:
    low = filename.lower()
    return low.endswith(".xlsx") or low.endswith(".xls")


def _parse_file(filepath: str, header_row: int = 1) -> dict:
    """Parse a file, auto-selecting parser by extension."""
    if _is_excel_binary(filepath):
        return xlsx_parser.parse_file(filepath, header_row=header_row)
    return xml_parser.parse_file(filepath, header_row=header_row)


def _parse_content(content, filename: str, header_row: int = 1) -> dict:
    """Parse file content from SVN (str for XML, bytes for Excel binary)."""
    if _is_excel_binary(filename):
        raw = content if isinstance(content, bytes) else content.encode("latin-1")
        return xlsx_parser.parse_bytes(raw, header_row=header_row)
    return xml_parser.parse_string(content, header_row=header_row)


def _get_base_content(filepath: str):
    """Get SVN BASE content: raw bytes for Excel binary, decoded string for XML."""
    if _is_excel_binary(filepath):
        return svn_helper.get_base_content_raw(filepath)
    return svn_helper.get_base_content(filepath)


def _get_file_at_revision(filepath: str, revision: int):
    """Get file at SVN revision: raw bytes for Excel binary, decoded string for XML."""
    if _is_excel_binary(filepath):
        return svn_helper.get_file_at_revision_raw(filepath, revision)
    return svn_helper.get_file_at_revision(filepath, revision)

def _base_dir():
    """Return the base directory — handles both normal and PyInstaller frozen mode."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _resource_dir():
    """Return the resource directory for bundled assets (static/, etc.)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            static_folder=os.path.join(_resource_dir(), "static"),
            static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

CONFIG_PATH = os.path.join(_base_dir(), "config.json")
DEFAULT_WORK_DIR = os.path.join(_base_dir(), "workspace")

_config = None


def _load_config() -> dict:
    global _config
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _config = json.load(f)
        except (json.JSONDecodeError, OSError):
            _config = None
    if not _config or not isinstance(_config.get("workspaces"), list):
        if os.path.isdir(DEFAULT_WORK_DIR):
            _config = {
                "workspaces": [{"name": os.path.basename(DEFAULT_WORK_DIR), "path": DEFAULT_WORK_DIR}],
                "active_workspace": 0,
            }
        else:
            _config = {
                "workspaces": [],
                "active_workspace": 0,
            }
    if _config["active_workspace"] >= len(_config["workspaces"]):
        _config["active_workspace"] = 0
    try:
        hr = int(_config.get("header_row", 1))
        if hr < 1:
            hr = 1
    except (TypeError, ValueError):
        hr = 1
    _config["header_row"] = hr
    return _config


def _save_config():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _get_work_dir() -> str:
    cfg = _load_config()
    if not cfg["workspaces"]:
        return ""
    idx = min(cfg["active_workspace"], len(cfg["workspaces"]) - 1)
    return cfg["workspaces"][idx]["path"]


def _get_header_row() -> int:
    cfg = _load_config()
    return cfg.get("header_row", 1)


def _rel_to_workdir(path: str, work_dir: str) -> str:
    """Normalize SVN local/remote paths to a comparable workspace-relative form."""
    if not path:
        return ""
    norm_path = os.path.normpath(path)
    norm_work = os.path.normpath(work_dir) if work_dir else ""
    if norm_work:
        try:
            if os.path.isabs(norm_path) and os.path.commonpath([norm_work, norm_path]) == norm_work:
                norm_path = os.path.relpath(norm_path, norm_work)
        except (ValueError, OSError):
            pass
    return norm_path.replace("\\", "/").lstrip("./")


def _normalize_svn_item(item: dict, work_dir: str) -> dict:
    """Keep SVN item names aligned with /api/files relative names."""
    out = dict(item)
    rel = _rel_to_workdir(out.get("path", "") or out.get("name", ""), work_dir)
    if rel:
        out["name"] = rel
    return out


@app.route("/")
def index():
    return send_from_directory(os.path.join(_resource_dir(), "static"), "index.html")


@app.route("/api/config")
def api_config():
    """Return current configuration and SVN availability."""
    svn_avail = svn_helper.is_available()
    cfg = _load_config()
    wd = _get_work_dir()
    return jsonify({
        "version": __version__,
        "work_dir": wd,
        "svn_available": svn_avail and bool(wd) and os.path.isdir(wd),
        "svn_version": svn_helper.get_version() if svn_avail else None,
        "svn_info": svn_helper.get_svn_info(wd) if svn_avail and wd and os.path.isdir(wd) else None,
        "workspaces": cfg["workspaces"],
        "active_workspace": cfg["active_workspace"],
        "header_row": cfg.get("header_row", 1),
    })


@app.route("/api/workspaces", methods=["GET"])
def api_workspaces():
    """Return workspace list."""
    cfg = _load_config()
    return jsonify({
        "workspaces": cfg["workspaces"],
        "active_workspace": cfg["active_workspace"],
    })


@app.route("/api/workspaces/switch", methods=["POST"])
def api_workspaces_switch():
    """Switch active workspace by index."""
    body = request.get_json(force=True)
    idx = body.get("index")
    cfg = _load_config()
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(cfg["workspaces"]):
        return jsonify({"error": "Invalid workspace index"}), 400
    cfg["active_workspace"] = idx
    _save_config()
    return jsonify({"ok": True, "work_dir": cfg["workspaces"][idx]["path"]})


@app.route("/api/workspaces/add", methods=["POST"])
def api_workspaces_add():
    """Add a new workspace directory."""
    body = request.get_json(force=True)
    path = body.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return jsonify({"error": f"Directory not found: {path}"}), 404
    cfg = _load_config()
    for ws in cfg["workspaces"]:
        if os.path.normpath(ws["path"]) == path:
            return jsonify({"error": "Workspace already exists"}), 409
    name = body.get("name", "") or os.path.basename(path)
    cfg["workspaces"].append({"name": name, "path": path})
    cfg["active_workspace"] = len(cfg["workspaces"]) - 1
    _save_config()
    return jsonify({"ok": True, "workspaces": cfg["workspaces"], "active_workspace": cfg["active_workspace"]})


@app.route("/api/workspaces/remove", methods=["POST"])
def api_workspaces_remove():
    """Remove a workspace by index (cannot remove last one)."""
    body = request.get_json(force=True)
    idx = body.get("index")
    cfg = _load_config()
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(cfg["workspaces"]):
        return jsonify({"error": "Invalid workspace index"}), 400
    if len(cfg["workspaces"]) <= 1:
        return jsonify({"error": "Cannot remove the last workspace"}), 400
    cfg["workspaces"].pop(idx)
    if cfg["active_workspace"] >= len(cfg["workspaces"]):
        cfg["active_workspace"] = len(cfg["workspaces"]) - 1
    _save_config()
    return jsonify({"ok": True, "workspaces": cfg["workspaces"], "active_workspace": cfg["active_workspace"]})


@app.route("/api/pick-dir", methods=["POST"])
def api_pick_dir():
    """Open native OS directory picker dialog."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="选择工作区目录")
        root.destroy()
        if not folder:
            return jsonify({"path": None})
        return jsonify({"path": folder})
    except Exception:
        return jsonify({"error": "native_unavailable"}), 501


@app.route("/api/open-dir", methods=["POST"])
def api_open_dir():
    """Open the current workspace directory in the system file manager."""
    wd = _get_work_dir()
    if not os.path.isdir(wd):
        return jsonify({"error": "Directory not found"}), 404
    try:
        import subprocess as sp
        if os.name == "nt":
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x12, 0, 0, 0)   # Alt down
            user32.keybd_event(0x12, 0, 2, 0)   # Alt up
            sp.Popen(["explorer.exe", os.path.normpath(wd)])
        else:
            sp.Popen(["xdg-open", wd])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/browse-dir")
def api_browse_dir():
    """Browse directories on server filesystem for workspace selection."""
    import string
    path = request.args.get("path", "").strip()
    if not path:
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return jsonify({"path": "", "dirs": drives, "is_root": True})
        else:
            return jsonify({"path": "/", "dirs": ["/"], "is_root": True})
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return jsonify({"error": "Not a directory"}), 404
    dirs = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    dirs.append(entry.path)
                except OSError:
                    pass
    except PermissionError:
        pass
    return jsonify({"path": path, "dirs": dirs, "is_root": False})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """Update application settings (e.g. header_row)."""
    body = request.get_json(force=True)
    cfg = _load_config()
    if "header_row" in body:
        try:
            hr = int(body["header_row"])
            if hr < 1:
                return jsonify({"error": "header_row must be >= 1"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "header_row must be an integer"}), 400
        cfg["header_row"] = hr
    _save_config()
    return jsonify({"ok": True, "header_row": cfg.get("header_row", 1)})


@app.route("/api/files")
def api_files():
    """List supported files in work directory (including subdirectories)."""
    wd = _get_work_dir()
    if not wd or not os.path.isdir(wd):
        return jsonify({"files": [], "message": "Please add a workspace directory"})

    files = []
    for dirpath, _dirnames, filenames in os.walk(wd):
        for f in filenames:
            if f.lower().endswith(SUPPORTED_EXTENSIONS):
                fpath = os.path.join(dirpath, f)
                rel = os.path.relpath(fpath, wd).replace("\\", "/")
                files.append({
                    "name": rel,
                    "size": os.path.getsize(fpath),
                    "modified": os.path.getmtime(fpath),
                })
    files.sort(key=lambda x: x["name"].lower())
    return jsonify({"files": files, "count": len(files)})


@app.route("/api/file-mtime")
def api_file_mtime():
    """Get last modification time of a file (for auto-refresh polling)."""
    filename = request.args.get("file", "")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"mtime": 0})
    return jsonify({"mtime": os.path.getmtime(fpath)})


@app.route("/api/svn/modified")
def api_svn_modified():
    """Get locally modified XML files."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    wd = _get_work_dir()
    modified = [_normalize_svn_item(item, wd) for item in svn_helper.get_modified_files(wd)]
    return jsonify({"files": modified, "count": len(modified)})


@app.route("/api/svn/modified-classify")
def api_svn_modified_classify():
    """Classify modified files: 'data' (substantive cell changes) or 'meta' (format/structure only)."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    wd = _get_work_dir()
    modified = [_normalize_svn_item(item, wd) for item in svn_helper.get_modified_files(wd)]
    hr = _get_header_row()
    result = {}
    for item in modified:
        fname = item["name"]
        if item["status"] in ("added", "deleted"):
            result[fname] = item["status"]
            continue
        try:
            base = _get_base_content(item["path"])
            if base is None:
                result[fname] = "data"
                continue
            old_data = _parse_content(base, fname, header_row=hr)
            new_data = _parse_file(item["path"], header_row=hr)
            diff = xml_differ.diff_workbooks(old_data, new_data)
            s = diff.get("summary", {})
            has_data = (s.get("total_modified_cells", 0) +
                        s.get("total_added_rows", 0) +
                        s.get("total_removed_rows", 0)) > 0
            result[fname] = "data" if has_data else "meta"
        except Exception:
            result[fname] = "data"
    return jsonify({"classify": result})


@app.route("/api/svn/log")
def api_svn_log():
    """Get SVN log for a file."""
    filename = request.args.get("file", "")
    limit = int(request.args.get("limit", "20"))
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404
    entries = svn_helper.get_log(fpath, limit=limit)
    return jsonify({"entries": entries, "count": len(entries)})


@app.route("/api/parse")
def api_parse():
    """Parse an XML file and return its data structure."""
    filename = request.args.get("file", "")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404
    try:
        data = _parse_file(fpath, header_row=_get_header_row())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/diff/local", methods=["POST"])
def api_diff_local():
    """Diff local working copy vs SVN BASE for a file."""
    body = request.get_json(force=True)
    filename = body.get("file", "")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400

    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404

    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503

    base_content = _get_base_content(fpath)
    if base_content is None:
        print(f"[WARN] Failed to get SVN BASE for: {fpath}", flush=True)
        return jsonify({"error": f"Failed to get SVN BASE version for {filename}. "
                        "Please ensure the file is under SVN version control."}), 500

    try:
        hr = _get_header_row()
        old_data = _parse_content(base_content, filename, header_row=hr)
        new_data = _parse_file(fpath, header_row=hr)
        diff = xml_differ.diff_workbooks(old_data, new_data, id_column=body.get("id_column"))
        diff["old_label"] = "SVN BASE"
        diff["new_label"] = "工作副本"
        diff["file"] = filename
        return jsonify(diff)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/diff/revisions", methods=["POST"])
def api_diff_revisions():
    """Diff two SVN revisions of a file."""
    body = request.get_json(force=True)
    filename = body.get("file", "")
    rev_old = body.get("rev_old")
    rev_new = body.get("rev_new")

    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    if rev_old is None or rev_new is None:
        return jsonify({"error": "rev_old and rev_new required"}), 400

    fpath = os.path.join(_get_work_dir(), filename)

    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503

    old_content = _get_file_at_revision(fpath, int(rev_old))
    if old_content is None:
        return jsonify({"error": f"Failed to get revision {rev_old}"}), 500

    hr = _get_header_row()
    if str(rev_new).upper() == "WORKING":
        if not os.path.exists(fpath):
            return jsonify({"error": f"File not found: {filename}"}), 404
        new_data = _parse_file(fpath, header_row=hr)
        new_label = "工作副本"
    else:
        new_content = _get_file_at_revision(fpath, int(rev_new))
        if new_content is None:
            return jsonify({"error": f"Failed to get revision {rev_new}"}), 500
        new_data = _parse_content(new_content, filename, header_row=hr)
        new_label = f"r{rev_new}"

    try:
        old_data = _parse_content(old_content, filename, header_row=hr)
        diff = xml_differ.diff_workbooks(old_data, new_data, id_column=body.get("id_column"))
        diff["old_label"] = f"r{rev_old}"
        diff["new_label"] = new_label
        diff["file"] = filename
        return jsonify(diff)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/svn/dir-log")
def api_svn_dir_log():
    """Get SVN log for the entire work directory."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    limit = int(request.args.get("limit", "50"))
    entries = svn_helper.get_dir_log(_get_work_dir(), limit=limit)
    return jsonify({"entries": entries, "count": len(entries)})


@app.route("/api/svn/changed-files")
def api_svn_changed_files():
    """Get list of files changed between two SVN revisions."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    rev_old = request.args.get("rev_old")
    rev_new = request.args.get("rev_new")
    if not rev_old or not rev_new:
        return jsonify({"error": "rev_old and rev_new required"}), 400
    files = svn_helper.get_changed_files_between_revisions(
        _get_work_dir(), int(rev_old), int(rev_new))
    return jsonify({"files": files, "count": len(files)})


@app.route("/api/diff/overview", methods=["POST"])
def api_diff_overview():
    """Diff all changed XML files between two SVN revisions (version overview)."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    body = request.get_json(force=True)
    rev_old = body.get("rev_old")
    rev_new = body.get("rev_new")
    if rev_old is None or rev_new is None:
        return jsonify({"error": "rev_old and rev_new required"}), 400

    wd = _get_work_dir()
    changed = svn_helper.get_changed_files_between_revisions(
        wd, int(rev_old), int(rev_new))

    hr = _get_header_row()
    results = []
    for item in changed:
        fname = item["name"]
        fpath = item.get("url") or os.path.join(wd, fname)

        if item["status"] == "deleted":
            results.append({
                "file": fname, "status": "deleted",
                "summary": {"has_changes": True, "total_removed_rows": 0},
            })
            continue

        if item["status"] == "added":
            try:
                new_content = _get_file_at_revision(fpath, int(rev_new))
                if new_content is None and os.path.exists(fpath):
                    new_data = _parse_file(fpath, header_row=hr)
                elif new_content is not None:
                    new_data = _parse_content(new_content, fname, header_row=hr)
                else:
                    results.append({"file": fname, "status": "added",
                                    "summary": {"has_changes": True}})
                    continue
                total_rows = sum(s["row_count"] for s in new_data["sheets"].values())
                results.append({
                    "file": fname, "status": "added",
                    "summary": {"has_changes": True, "total_added_rows": total_rows,
                                "sheets": len(new_data["sheets"])},
                })
            except Exception as e:
                results.append({"file": fname, "status": "error", "error": str(e)})
            continue

        try:
            old_content = _get_file_at_revision(fpath, int(rev_old))
            new_content = _get_file_at_revision(fpath, int(rev_new))
            if old_content is None or new_content is None:
                results.append({"file": fname, "status": "error",
                                "error": "Cannot get revision content"})
                continue
            old_data = _parse_content(old_content, fname, header_row=hr)
            new_data = _parse_content(new_content, fname, header_row=hr)
            diff = xml_differ.diff_workbooks(old_data, new_data)
            results.append({
                "file": fname, "status": item["status"],
                "summary": diff["summary"], "diff": diff,
            })
        except Exception as e:
            results.append({"file": fname, "status": "error", "error": str(e)})

    has_data_changes = sum(1 for r in results
                          if r.get("summary", {}).get("has_changes", False)
                          and r.get("summary", {}).get("total_modified_cells", 0) +
                              r.get("summary", {}).get("total_added_rows", 0) +
                              r.get("summary", {}).get("total_removed_rows", 0) > 0)

    return jsonify({
        "files": results,
        "total_files": len(results),
        "data_changed_files": has_data_changes,
        "rev_old": rev_old,
        "rev_new": rev_new,
    })


@app.route("/api/diff/batch", methods=["POST"])
def api_diff_batch():
    """Batch diff all locally modified XML files."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503

    wd = _get_work_dir()
    modified = [_normalize_svn_item(item, wd) for item in svn_helper.get_modified_files(wd)]
    hr = _get_header_row()
    results = []
    for item in modified:
        fpath = item["path"]
        if item["status"] == "deleted":
            results.append({
                "file": item["name"],
                "status": "deleted",
                "summary": {"has_changes": True},
            })
            continue
        if item["status"] == "added":
            try:
                new_data = _parse_file(fpath, header_row=hr)
                total_rows = sum(s["row_count"] for s in new_data["sheets"].values())
                results.append({
                    "file": item["name"],
                    "status": "added",
                    "summary": {
                        "has_changes": True,
                        "total_added_rows": total_rows,
                        "sheets": len(new_data["sheets"]),
                    },
                })
            except Exception as e:
                results.append({"file": item["name"], "status": "error", "error": str(e)})
            continue

        try:
            base_content = _get_base_content(fpath)
            if base_content is None:
                results.append({"file": item["name"], "status": "error", "error": "Cannot get BASE"})
                continue
            old_data = _parse_content(base_content, item["name"], header_row=hr)
            new_data = _parse_file(fpath, header_row=hr)
            diff = xml_differ.diff_workbooks(old_data, new_data)
            results.append({
                "file": item["name"],
                "status": "modified",
                "summary": diff["summary"],
            })
        except Exception as e:
            results.append({"file": item["name"], "status": "error", "error": str(e)})

    return jsonify({"files": results, "count": len(results)})


@app.route("/api/merge/preview", methods=["POST"])
def api_merge_preview():
    """Three-way semantic merge preview: BASE / MINE (working copy) / THEIRS (SVN HEAD or specific revision).

    Body: {"file": "...", "theirs_rev"?: int or "HEAD"}
    XML-only feature; other extensions return 400.
    """
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    body = request.get_json(force=True) or {}
    filename = body.get("file", "")
    theirs_rev = body.get("theirs_rev", "HEAD")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    if _is_excel_binary(filename) or not filename.lower().endswith(".xml"):
        return jsonify({"error": "\u8bed\u4e49\u5408\u5e76\u4ec5\u652f\u6301 .xml (SpreadsheetML 2003)"}), 400

    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404

    base_content = svn_helper.get_base_content(fpath)
    if base_content is None:
        return jsonify({"error": "\u65e0\u6cd5\u83b7\u53d6 SVN BASE \u7248\u672c"}), 500

    if str(theirs_rev).upper() == "HEAD":
        info = svn_helper.get_svn_info(fpath)
        head = svn_helper.get_remote_head_revision(info["url"]) if info and info.get("url") else None
        if head is None:
            return jsonify({"error": "\u65e0\u6cd5\u83b7\u53d6\u8fdc\u7a0b HEAD \u7248\u672c"}), 500
        theirs_rev_int = int(head)
    else:
        try:
            theirs_rev_int = int(theirs_rev)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid theirs_rev"}), 400

    theirs_content = svn_helper.get_file_at_revision(fpath, theirs_rev_int)
    if theirs_content is None:
        return jsonify({"error": f"\u65e0\u6cd5\u83b7\u53d6 r{theirs_rev_int} \u7248\u672c"}), 500

    try:
        hr = _get_header_row()
        base = xml_parser.parse_string(base_content, header_row=hr)
        mine = xml_parser.parse_file(fpath, header_row=hr)
        theirs = xml_parser.parse_string(theirs_content, header_row=hr)
        result = xml_merger.three_way_diff(base, mine, theirs,
                                           id_column=body.get("id_column"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    result["file"] = filename
    result["base_label"] = "SVN BASE"
    result["mine_label"] = "\u5de5\u4f5c\u526f\u672c"
    result["theirs_label"] = f"r{theirs_rev_int}"
    result["theirs_revision"] = theirs_rev_int
    return jsonify(result)


@app.route("/api/merge/apply", methods=["POST"])
def api_merge_apply():
    """Apply user resolutions and write the merged file back to the working copy.

    Body: {"file", "resolutions": [...], "theirs_rev"?, "mark_resolved"?}
    Re-runs three_way_diff so the merge plan is computed fresh from current
    on-disk state (so the merge is robust against concurrent edits).
    """
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    body = request.get_json(force=True) or {}
    filename = body.get("file", "")
    resolutions = body.get("resolutions", [])
    theirs_rev = body.get("theirs_rev", "HEAD")
    mark_resolved = bool(body.get("mark_resolved", False))
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    if _is_excel_binary(filename) or not filename.lower().endswith(".xml"):
        return jsonify({"error": "\u8bed\u4e49\u5408\u5e76\u4ec5\u652f\u6301 .xml"}), 400

    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404

    base_content = svn_helper.get_base_content(fpath)
    if base_content is None:
        return jsonify({"error": "\u65e0\u6cd5\u83b7\u53d6 SVN BASE"}), 500

    if str(theirs_rev).upper() == "HEAD":
        info = svn_helper.get_svn_info(fpath)
        head = svn_helper.get_remote_head_revision(info["url"]) if info and info.get("url") else None
        if head is None:
            return jsonify({"error": "\u65e0\u6cd5\u83b7\u53d6\u8fdc\u7a0b HEAD"}), 500
        theirs_rev_int = int(head)
    else:
        try:
            theirs_rev_int = int(theirs_rev)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid theirs_rev"}), 400

    theirs_content = svn_helper.get_file_at_revision(fpath, theirs_rev_int)
    if theirs_content is None:
        return jsonify({"error": f"\u65e0\u6cd5\u83b7\u53d6 r{theirs_rev_int}"}), 500

    try:
        hr = _get_header_row()
        base = xml_parser.parse_string(base_content, header_row=hr)
        mine = xml_parser.parse_file(fpath, header_row=hr)
        theirs = xml_parser.parse_string(theirs_content, header_row=hr)
        result = xml_merger.three_way_diff(base, mine, theirs,
                                           id_column=body.get("id_column"))
        applied = xml_merger.apply_resolutions(result, resolutions)
        if not applied["ok"]:
            return jsonify({
                "error": "\u5b58\u5728\u672a\u51b3\u8bae\u7684\u51b2\u7a81",
                "unresolved": applied["unresolved"],
            }), 400

        xml_merger.write_merged_xml(fpath, result, fpath)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    svn_resolved = False
    if mark_resolved:
        rc, _out, _err = svn_helper._run("resolve", "--accept", "working", fpath)
        svn_resolved = (rc == 0)

    return jsonify({
        "ok": True,
        "file": filename,
        "applied": applied["applied"],
        "svn_resolved": svn_resolved,
    })


@app.route("/api/merge/svn-mark-resolved", methods=["POST"])
def api_merge_svn_mark_resolved():
    """Mark a file as resolved in SVN's conflict state (svn resolve --accept working)."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    body = request.get_json(force=True) or {}
    filename = body.get("file", "")
    if not filename:
        return jsonify({"error": "file parameter required"}), 400
    fpath = os.path.join(_get_work_dir(), filename)
    if not os.path.exists(fpath):
        return jsonify({"error": f"File not found: {filename}"}), 404
    rc, _out, err = svn_helper._run("resolve", "--accept", "working", fpath)
    if rc != 0:
        return jsonify({"error": err or "svn resolve failed"}), 500
    return jsonify({"ok": True, "file": filename})


@app.route("/api/svn/remote-revision")
def api_svn_remote_revision():
    """Get remote HEAD revision and local BASE revision for comparison."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    wd = _get_work_dir()
    local_info = svn_helper.get_svn_info(wd)
    if not local_info or not local_info.get("url"):
        return jsonify({"error": "Not an SVN working copy"}), 400
    remote_rev = svn_helper.get_remote_head_revision(local_info["url"])
    local_rev = int(local_info.get("revision", 0)) if local_info.get("revision", "").isdigit() else 0
    return jsonify({
        "remote_revision": remote_rev,
        "local_revision": local_rev,
        "has_update": remote_rev > local_rev if remote_rev else False,
    })


@app.route("/api/svn/update", methods=["POST"])
def api_svn_update():
    """Smart SVN update with conflict detection."""
    if not svn_helper.is_available():
        return jsonify({"error": "SVN not available"}), 503
    wd = _get_work_dir()
    body = request.get_json(force=True) or {}

    if body.get("check_only"):
        local_modified = svn_helper.get_modified_files(wd)
        local_mod_names = {
            _rel_to_workdir(f.get("path", ""), wd)
            for f in local_modified
            if f.get("path")
        }
        remote_changed = [
            _rel_to_workdir(f, wd)
            for f in svn_helper.get_remote_changed_files(wd)
            if f
        ]
        conflicts = [f for f in remote_changed if f in local_mod_names]
        safe = [f for f in remote_changed if f not in local_mod_names]
        return jsonify({
            "conflicts": conflicts,
            "safe_updates": len(safe),
            "local_only": [f for f in sorted(local_mod_names) if f not in set(remote_changed)],
        })

    skip_files = body.get("skip_files", [])
    theirs_files = body.get("theirs_files", [])
    mine_files = body.get("mine_files", [])
    result = svn_helper.smart_update(wd, skip_files, theirs_files, mine_files)
    return jsonify(result)


def open_browser(port):
    """Open browser after a short delay to let server start."""
    import time
    time.sleep(1)
    webbrowser.open(f"http://localhost:{port}")


def kill_existing_on_port(port):
    """Kill any existing processes listening on the given port."""
    try:
        import subprocess
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(["taskkill", "/PID", pid, "/F"],
                                   capture_output=True, timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5566))
    kill_existing_on_port(port)
    print(f"SmartDiff starting on http://localhost:{port}")
    print(f"Work directory: {_get_work_dir()}")
    print(f"SVN: {'available' if svn_helper.is_available() else 'not found'}")

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host="127.0.0.1", port=port, debug=False)
