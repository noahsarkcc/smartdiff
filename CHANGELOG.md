# Changelog

**English** · [中文](CHANGELOG.zh-CN.md)

All notable changes to SmartDiff are documented here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

## v1.3.4 (2026-06-04)

**Bug fixes**
- Overview mode: files with non-ASCII (e.g. Chinese) names no longer fail with "Cannot get revision content". SVN percent-encodes such names in remote URLs; the change list now decodes them so the file name displays correctly and revision content can be fetched
- Overview now fetches revision content via the repository URL, so files that are not checked out locally can still be compared
- `get_file_at_revision` / `get_file_at_revision_raw` accept a repository URL directly

## v1.3.3 (2026-06-04)

**Internationalization (i18n)**
- Web UI now supports both English and Chinese with a one-click toggle in the header
- Auto-detects browser language on first visit (zh-* → Chinese, otherwise English)
- User selection is persisted to localStorage (`smartdiff_locale`)
- Bilingual coverage: header, sidebar, all four diff modes, semantic merge UI, SVN conflict dialog, alerts, error messages

**Documentation**
- CHANGELOG split into separate `CHANGELOG.md` (English) and `CHANGELOG.zh-CN.md` (Chinese), matching README/DEVELOPMENT bilingual style

## v1.3.2 (2026-05-27)

**File list**
- Fixed subdirectory `.xls` files not matching by relative path in the SVN change list / changes-only filter
- Added regression tests for `/api/files` recursively listing `configs/items.xls` and `/api/svn/modified` returning relative paths

## v1.3.1 (2026-05-15)

**SVN conflict detection**
- `check_only` now matches local edits and remote changes by workspace-relative path, fixing subdirectory files being missed by `basename` matching
- Added API regression tests covering subdirectory conflict scenarios like `configs/items.xml`

## v1.3.0 (2026-05-15)

**Cell-level three-way semantic merge**
- Added `xml_merger.py` supporting `BASE / MINE / THEIRS` three-way diff, auto resolution, manual resolution, and write-back
- Added `/api/merge/preview`, `/api/merge/apply`, `/api/merge/svn-mark-resolved`
- Integrated a "Semantic merge" entry into the SVN conflict dialog; XML conflicts can be resolved cell-by-cell
- Added an automated test suite and a demo SVN repository script

<details>
<summary><b>Earlier versions (v1.0 – v1.2)</b></summary>

## v1.2.0 (2026-05-14)

**Excel binary file support**
- Added `.xlsx` / `.xls` parsing using `openpyxl` / `xlrd` to extract pure cell data
- SVN historical revisions support raw bytes, so revision diffs work for Excel files

## v1.1.0 (2026-05-13)

**Diff engine**
- Reworked the three-pass row matching algorithm: Pass 1 by ID value → Pass 2 by content hash + position proximity → Pass 3 by row number fallback. Inserting/deleting a few rows no longer produces large numbers of false diffs
- Improved SVN log filtering: correctly includes file revisions created via directory copy (branches/tags)

**Overview**
- Fixed the invisible horizontal scrollbar (dynamic diff-container height) and double Y-axis scrollbars after browser zoom
- Higher-contrast scrollbars; force reflow after dynamic HTML insertion so they render immediately

**Revision compare**
- The revision dropdown no longer includes "working copy"; defaults to the two most recent SVN revisions
- Single-revision files show "only 1 revision, cannot diff between revisions"
- Scroll hints (floating change indicators) support overview mode using `position: fixed`

**Other**
- The Explorer window auto-focuses to the foreground when opening a workspace directory (Windows)
- Fixed the port number shown in `start.bat` (5000 → 5566)
- Added `__version__` version management; `/api/config` now returns version info

## v1.0.0

First release. Includes local changes, revision compare, browse, and overview modes, smart SVN update, inline diff, PyInstaller packaging, and more.

</details>
