"""
SVN integration helper.
Auto-detects svn CLI, retrieves version history, file contents at revisions,
and local modification status.
"""
import subprocess
import xml.etree.ElementTree as ET
import os
import re
import urllib.parse
from typing import Optional


def _is_url(target: str) -> bool:
    return target.startswith(("http://", "https://", "svn://", "svn+ssh://", "file://"))


_svn_path: Optional[str] = None
_svn_checked = False


def _find_svn() -> Optional[str]:
    """Auto-detect svn CLI path."""
    global _svn_path, _svn_checked
    if _svn_checked:
        return _svn_path
    _svn_checked = True

    for candidate in ["svn"]:
        try:
            r = subprocess.run(
                [candidate, "--version", "--quiet"],
                capture_output=True, timeout=5
            )
            if r.returncode == 0:
                _svn_path = candidate
                return _svn_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    tortoise_paths = [
        r"C:\Program Files\TortoiseSVN\bin\svn.exe",
        r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe",
    ]
    for tp in tortoise_paths:
        if os.path.isfile(tp):
            try:
                r = subprocess.run([tp, "--version", "--quiet"],
                                   capture_output=True, timeout=5)
                if r.returncode == 0:
                    _svn_path = tp
                    return _svn_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    return None


def is_available() -> bool:
    svn = _find_svn()
    if svn:
        print(f"[SVN] Using: {svn}", flush=True)
    return svn is not None


def _decode_output(data: bytes) -> str:
    """Decode subprocess output, trying UTF-8 first, then system encoding (GBK on Chinese Windows)."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gbk")
    except UnicodeDecodeError:
        pass
    return data.decode("utf-8", errors="replace")


def _run(*args, cwd=None, timeout=30) -> tuple:
    """Run svn command, return (returncode, stdout_str, stderr_str)."""
    svn = _find_svn()
    if not svn:
        return (-1, "", "svn not found")
    cmd = [svn] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd)
        stdout = _decode_output(r.stdout)
        stderr = _decode_output(r.stderr)
        return (r.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", "timeout")
    except Exception as e:
        return (-1, "", str(e))


def _run_raw(*args, cwd=None, timeout=30) -> tuple:
    """Run svn command, return (returncode, stdout_bytes, stderr_str).
    Unlike _run, stdout is kept as raw bytes for binary file content.
    """
    svn = _find_svn()
    if not svn:
        return (-1, b"", "svn not found")
    cmd = [svn] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd)
        stderr = _decode_output(r.stderr)
        return (r.returncode, r.stdout, stderr)
    except subprocess.TimeoutExpired:
        return (-1, b"", "timeout")
    except Exception as e:
        return (-1, b"", str(e))


def get_svn_info(path: str) -> Optional[dict]:
    """Get svn info for a path."""
    rc, out, err = _run("info", "--xml", path)
    if rc != 0:
        return None
    try:
        root = ET.fromstring(out)
        entry = root.find(".//entry")
        if entry is None:
            return None
        return {
            "url": entry.findtext("url", ""),
            "root": entry.findtext("repository/root", ""),
            "revision": entry.get("revision", ""),
            "last_changed_rev": entry.find("commit").get("revision", "")
                if entry.find("commit") is not None else "",
            "last_changed_author": entry.findtext("commit/author", ""),
            "last_changed_date": entry.findtext("commit/date", ""),
        }
    except ET.ParseError:
        return None


def get_log(path: str, limit: int = 20) -> list:
    """Get SVN log entries for a file or directory. Uses remote URL for latest history."""
    info = get_svn_info(path)
    target = info["url"] if info and info.get("url") else path
    rc, out, err = _run("log", "-l", str(limit), "--xml", "-v",
                        "--stop-on-copy", target, timeout=60)
    if rc != 0 and target != path:
        rc, out, err = _run("log", "-l", str(limit), "--xml", "-v",
                            "--stop-on-copy", path, timeout=60)
    if rc != 0:
        return []

    target_svn_path = ""
    if info and info.get("url") and info.get("root"):
        target_svn_path = info["url"][len(info["root"]):]

    try:
        root = ET.fromstring(out)
        entries = []
        for entry in root.iter("logentry"):
            rev = entry.get("revision", "")
            author = entry.findtext("author", "")
            date_str = entry.findtext("date", "")
            msg = (entry.findtext("msg", "") or "").strip()
            paths_changed = []
            paths_el = entry.find("paths")
            if paths_el is not None:
                for p in paths_el.findall("path"):
                    paths_changed.append({
                        "path": p.text or "",
                        "action": p.get("action", ""),
                    })

            if target_svn_path and paths_changed:
                if not any(cp["path"] == target_svn_path or
                           cp["path"].startswith(target_svn_path + "/") or
                           target_svn_path.startswith(cp["path"] + "/")
                           for cp in paths_changed):
                    continue

            entries.append({
                "revision": int(rev) if rev.isdigit() else rev,
                "author": author,
                "date": date_str,
                "message": msg,
                "paths": paths_changed,
            })
        return entries
    except ET.ParseError:
        return []


def get_file_at_revision(filepath: str, revision: int) -> Optional[str]:
    """Get file content at a specific SVN revision. Uses remote URL for reliability.
    Accepts either a local working-copy path or a direct repository URL.
    """
    if _is_url(filepath):
        rc, out, _ = _run("cat", "-r", str(revision), filepath, timeout=60)
        return out if rc == 0 else None
    info = get_svn_info(filepath)
    target = info["url"] if info and info.get("url") else filepath
    rc, out, err = _run("cat", "-r", str(revision), target, timeout=60)
    if rc == 0:
        return out
    if target != filepath:
        rc2, out2, _ = _run("cat", "-r", str(revision), filepath, timeout=60)
        if rc2 == 0:
            return out2
    return None


def get_base_content(filepath: str) -> Optional[str]:
    """Get the BASE (pristine) version of a working copy file.
    Tries -r BASE first (local, no network), falls back to plain svn cat (network).
    """
    rc, out, err = _run("cat", "-r", "BASE", filepath, timeout=60)
    if rc == 0:
        return out
    print(f"[SVN] cat -r BASE failed (rc={rc}): {err.strip()}", flush=True)
    rc2, out2, err2 = _run("cat", filepath, timeout=60)
    if rc2 == 0:
        print(f"[SVN] Fallback svn cat succeeded for: {filepath}", flush=True)
        return out2
    print(f"[SVN] Fallback svn cat also failed (rc={rc2}): {err2.strip()}", flush=True)
    return None


def get_file_at_revision_raw(filepath: str, revision: int) -> Optional[bytes]:
    """Get file content as raw bytes at a specific SVN revision (for binary files like .xlsx).
    Accepts either a local working-copy path or a direct repository URL.
    """
    if _is_url(filepath):
        rc, out, _ = _run_raw("cat", "-r", str(revision), filepath, timeout=60)
        return out if rc == 0 else None
    info = get_svn_info(filepath)
    target = info["url"] if info and info.get("url") else filepath
    rc, out, err = _run_raw("cat", "-r", str(revision), target, timeout=60)
    if rc == 0:
        return out
    if target != filepath:
        rc2, out2, _ = _run_raw("cat", "-r", str(revision), filepath, timeout=60)
        if rc2 == 0:
            return out2
    return None


def get_base_content_raw(filepath: str) -> Optional[bytes]:
    """Get the BASE version of a working copy file as raw bytes (for binary files like .xlsx)."""
    rc, out, err = _run_raw("cat", "-r", "BASE", filepath, timeout=60)
    if rc == 0:
        return out
    rc2, out2, err2 = _run_raw("cat", filepath, timeout=60)
    if rc2 == 0:
        return out2
    return None


def get_modified_files(working_dir: str, extensions: tuple = (".xml", ".xlsx", ".xls")) -> list:
    """Get list of locally modified files in the working directory."""
    rc, out, err = _run("status", "--xml", working_dir, timeout=60)
    if rc != 0:
        rc2, out2, err2 = _run("status", working_dir, timeout=60)
        if rc2 != 0:
            return []
        result = []
        for line in out2.splitlines():
            if not line or len(line) < 8:
                continue
            status_char = line[0]
            fpath = line[7:].strip()
            if status_char in ("M", "A", "D", "R") and any(fpath.lower().endswith(e) for e in extensions):
                result.append({
                    "path": fpath,
                    "status": {"M": "modified", "A": "added", "D": "deleted", "R": "replaced"}.get(status_char, status_char),
                    "name": os.path.basename(fpath),
                })
        return result

    try:
        root = ET.fromstring(out)
        result = []
        for entry in root.iter("entry"):
            path = entry.get("path", "")
            if not any(path.lower().endswith(e) for e in extensions):
                continue
            wc_status = entry.find("wc-status")
            if wc_status is None:
                continue
            item_status = wc_status.get("item", "")
            if item_status in ("modified", "added", "deleted", "replaced"):
                result.append({
                    "path": path,
                    "status": item_status,
                    "name": os.path.basename(path),
                    "revision": wc_status.get("revision", ""),
                })
        return result
    except ET.ParseError:
        return []


def get_changed_files_between_revisions(path: str, rev_old: int, rev_new: int,
                                        extensions: tuple = (".xml", ".xlsx", ".xls")) -> list:
    """Get list of changed files between two SVN revisions using 'svn diff --summarize'.
    Uses remote URL for reliability, falls back to local path.
    """
    info = get_svn_info(path)
    target = info["url"] if info and info.get("url") else path
    use_url = (target != path)

    rc, out, err = _run("diff", "--summarize", "-r",
                        f"{rev_old}:{rev_new}", target, timeout=120)
    if rc != 0:
        if use_url:
            rc, out, err = _run("diff", "--summarize", "-r",
                                f"{rev_old}:{rev_new}", path, timeout=120)
            if rc != 0:
                return []
            use_url = False
        else:
            return []

    result = []
    if use_url:
        base_url = target.rstrip("/")
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            status_char = line[0]
            fpath = line[1:].strip()
            if not fpath:
                continue
            if not any(fpath.lower().endswith(e) for e in extensions):
                continue
            if fpath.startswith(base_url + "/"):
                rel = fpath[len(base_url) + 1:]
            elif fpath.startswith(base_url):
                rel = fpath[len(base_url):]
            else:
                continue
            # SVN URLs percent-encode non-ASCII (e.g. Chinese) names; decode for
            # local paths and display, keep an encoded-safe URL for direct cat.
            rel_decoded = urllib.parse.unquote(rel)
            file_url = base_url + "/" + rel if rel else fpath
            result.append({
                "path": os.path.join(path, rel_decoded) if rel_decoded else fpath,
                "name": rel_decoded.replace("\\", "/") if rel_decoded else os.path.basename(fpath),
                "url": file_url,
                "status": {"M": "modified", "A": "added", "D": "deleted"}.get(status_char, "modified"),
            })
    else:
        norm_base = os.path.normcase(os.path.normpath(path))
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            status_char = line[0]
            fpath = line[1:].strip()
            if not fpath:
                continue
            if not any(fpath.lower().endswith(e) for e in extensions):
                continue
            norm_fp = os.path.normcase(os.path.normpath(fpath))
            if not norm_fp.startswith(norm_base + os.sep) and norm_fp != norm_base:
                continue
            result.append({
                "path": fpath,
                "name": os.path.basename(fpath),
                "status": {"M": "modified", "A": "added", "D": "deleted"}.get(status_char, "modified"),
            })
    return result


def get_dir_log(path: str, limit: int = 50) -> list:
    """Get SVN log for a specific directory only.
    Uses remote URL for latest history, falls back to local path.
    """
    info = get_svn_info(path)
    target = info["url"] if info and info.get("url") else path
    rc, out, err = _run("log", "-l", str(limit), "--xml",
                        "--stop-on-copy", target, timeout=120)
    if rc != 0 and target != path:
        rc, out, err = _run("log", "-l", str(limit), "--xml",
                            "--stop-on-copy", path, timeout=120)
    if rc != 0:
        return []
    try:
        root = ET.fromstring(out)
        entries = []
        for entry in root.iter("logentry"):
            rev = entry.get("revision", "")
            author = entry.findtext("author", "")
            date_str = entry.findtext("date", "")
            msg = (entry.findtext("msg", "") or "").strip()
            entries.append({
                "revision": int(rev) if rev.isdigit() else rev,
                "author": author,
                "date": date_str,
                "message": msg,
            })
        return entries
    except ET.ParseError:
        return []


def get_remote_head_revision(url: str) -> Optional[int]:
    """Get the latest revision number from remote repository."""
    rc, out, err = _run("info", "--xml", url, timeout=30)
    if rc != 0:
        return None
    try:
        root = ET.fromstring(out)
        commit_el = root.find(".//commit")
        if commit_el is not None:
            rev = commit_el.get("revision")
            return int(rev) if rev else None
        entry_el = root.find(".//entry")
        if entry_el is not None:
            rev = entry_el.get("revision")
            return int(rev) if rev else None
        return None
    except (ET.ParseError, AttributeError):
        return None


def get_remote_changed_files(path: str, extensions: tuple = (".xml", ".xlsx", ".xls")) -> list:
    """Get files changed between local BASE and remote HEAD."""
    info = get_svn_info(path)
    if not info:
        return []
    local_rev = info.get("revision", "0")
    url = info.get("url", "")
    if not url:
        return []
    rc, out, err = _run("diff", "--summarize", "-r", f"{local_rev}:HEAD", url, timeout=120)
    if rc != 0:
        return []
    files = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        file_url = parts[1].strip()
        if file_url.startswith(url + "/"):
            fname = file_url[len(url) + 1:]
        elif file_url.startswith(url):
            fname = file_url[len(url):]
        else:
            fname = os.path.basename(file_url)
        if fname and any(fname.lower().endswith(e) for e in extensions):
            files.append(fname)
    return files


def smart_update(path: str, skip_files: list, theirs_files: list, mine_files: list) -> dict:
    """Execute svn update, handling conflicts per user choice.

    - skip_files: files to keep at current state (resolve as mine after update)
    - theirs_files: files to accept server version
    - mine_files: files to keep local modifications
    """
    results = {"updated": 0, "skipped": [], "theirs": [], "mine": [], "errors": []}

    rc, out, err = _run("update", "--accept", "postpone", path, timeout=300)
    if rc != 0 and "conflict" not in err.lower() and "conflicts" not in out.lower():
        results["errors"].append(err)
        return results

    update_lines = out.strip().splitlines() if out else []
    results["updated"] = len([l for l in update_lines if l and l[0] in "ADUCG"])

    for f in theirs_files:
        fpath = os.path.join(path, f)
        _run("resolve", "--accept", "theirs-full", fpath)
        results["theirs"].append(f)

    for f in mine_files:
        fpath = os.path.join(path, f)
        _run("resolve", "--accept", "mine-full", fpath)
        results["mine"].append(f)

    for f in skip_files:
        fpath = os.path.join(path, f)
        _run("resolve", "--accept", "mine-full", fpath)
        results["skipped"].append(f)

    return results


def get_version() -> Optional[str]:
    """Get SVN client version string."""
    rc, out, err = _run("--version", "--quiet")
    if rc == 0:
        return out.strip()
    return None
