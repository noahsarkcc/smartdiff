# Changelog

**English** · [中文](CHANGELOG.zh-CN.md)

All notable changes to SmartDiff are documented here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

Diff table display fixes.

**Bug fixes**
- Split view: the old-value (red) / new-value (green) backgrounds of modified cells now always fill the full cell height, so the red/green boundary no longer looks misaligned across cells with different content lengths
- Long text in diff tables now wraps and shows in full by default, instead of requiring a mouse hover to expand

## v1.4.0 (2026-06-10)

In-app auto-update.

**New features**
- In-app update check: 5 seconds after startup the app silently queries GitHub Releases; when a newer version exists, a red dot appears on the settings (gear) button
- New "Version & Updates" section in the settings dialog: shows the current version, a manual check button and the new release notes
- One-click update (exe mode): downloads the new `SmartDiff.exe` in the background → shows a progress bar → swaps the executable and restarts → the page reloads on the new version automatically; user config (`config.json`) is untouched
- When a direct GitHub connection fails, both the check and the download automatically retry through the acceleration proxy (`github.2436666.xyz`); the working channel is remembered for the session
- When running from source, the dialog suggests `git pull` and offers direct/proxied release page links

**Release infrastructure**
- New `.github/workflows/release.yml`: pushing a `v*` tag runs the full test suite on Windows, builds with PyInstaller and attaches `SmartDiff.exe` to the release (previous releases had no exe asset; one-click updates are fully closed-loop from this version on)
- `build.bat` fixed: installs `requirements.txt` (adds the missing openpyxl/xlrd) and uses the same build flags as CI

**API**
- New `GET /api/update/check` (result cached for 1 hour, `?force=1` bypasses), `POST /api/update/download`, `GET /api/update/progress`, `POST /api/update/apply`

**Tests**
- New `tests/test_updater.py` (20 cases): version comparison, proxy fallback, `check_update` parsing, download state machine, all four endpoints; wired into CI, all 76 cases pass

## v1.3.7 (2026-06-10)

Reliability hardening release (12 fixes from a full code review).

**Data safety (high)**
- Semantic merge write-back is now atomic: the result is written to a temp file in the same directory and swapped in with `os.replace()`, so a failed write can no longer corrupt the working copy and lose uncommitted local edits
- `ss:ExpandedRowCount` / `ss:ExpandedColumnCount` are kept in sync after merge inserts rows, preventing Excel from refusing to open files whose actual extent exceeds the declared counts
- Remote conflict detection and per-file history now decode SVN percent-encoded URLs consistently, so Chinese/non-ASCII file names no longer miss conflicts or lose history entries

**Robustness (medium)**
- All file-name-accepting APIs validate that the resolved path stays inside the workspace, rejecting `..` and absolute-path traversal
- Startup port cleanup matches the local-address port exactly instead of substring matching, so processes on neighboring ports (e.g. 55660-55669) are never killed by mistake
- Smart SVN update detects conflicts via `svn status --xml` instead of sniffing localized output strings (works correctly under Chinese locales); the updated-file count excludes `Updating` / `At revision` noise lines
- Merge write-back preserves `<!-- -->` XML comments inside the document (previously silently dropped by ElementTree)

**Other improvements (low)**
- SVN file content is fetched as raw bytes and decoded per the XML declaration, supporting UTF-16 and other non-UTF-8 spreadsheet files
- Auto ID-column detection respects the "Header Row" setting; metadata rows (obj/type/desc/key) no longer break the uniqueness check
- Config reads/writes are guarded by a lock; a failed `config.json` save now surfaces a `warning` in the API response instead of being silently ignored
- Opening the workspace directory uses `os.startfile`, removing the simulated Alt-key foreground-focus hack

**Tests**
- New `tests/test_differ.py` (11 cases): non-cascading insert/delete, Pass 2/3 matching, duplicate IDs, comment-column filtering, ID detection with header_row > 1, UTF-16 parsing; wired into CI
- `test_merger.py` gains ExpandedRowCount growth and XML comment preservation regression cases (29 total)
- `test_api_merge.py` gains a path-traversal rejection case (16 total); all 56 cases pass

## v1.3.6 (2026-06-09)

**Cell diff readability**
- Smart token-level diff: consecutive digits and ASCII letters are now treated as whole tokens, so a value change like `738` -> `7074` is highlighted as one block instead of scattered red/green character fragments. Greatly improves readability for compact structured data like `{5:738626,40,6:4235,400,...}`
- New "Split" view: shows the old value and new value on two separate lines (old on top, new below), each complete and with changed parts highlighted, so old -> new can be read at a glance
- View toggle (Inline / Split) in the toolbar for local, revision and overview modes; the preference is persisted to localStorage
- Long values now wrap at token boundaries instead of mid-number

## v1.3.5 (2026-06-04)

**New feature**
- Configurable header row: a new global "Header Row" setting lets users specify which row contains column headers (default: 1). Tables with metadata rows (obj/type/desc/key) before the actual headers are now fully supported — all columns are correctly recognized and compared
- Settings dialog accessible from the header toolbar (gear icon)
- Setting is persisted in `config.json` and takes effect immediately across all modes (local diff, revision diff, browse, overview, merge)

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
