# Changelog

**English** · [中文](CHANGELOG.zh-CN.md)

All notable changes to SmartDiff are documented here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

## v1.5.0 (2026-06-17)

Rebuilt SVN conflict merge flow + system tray.

**Bug fixes**
- Files in SVN text-conflict state could not be semantically merged: the working copy was already polluted with `<<<<<<<` markers and `svn cat -r BASE` returned the freshly pulled HEAD rather than the true common ancestor, so the three-way comparison was completely wrong. The app now detects conflicts and reads the `.r<old>` / `.mine` / `.r<new>` sidecar files exposed by `svn info --xml` as BASE / MINE / THEIRS
- "Semantic merge from the conflict dialog jumped away immediately, so `svn update` was never actually executed and remote-only files stayed on the old revision": semantic merge is now the 4th choice in the conflict dialog (alongside mine/theirs/skip). Pressing "Confirm update" hands the marked files to a managed semantic-merge queue, guides through them one by one, then runs a single consolidated `svn update`; already-merged files are resolved with `--accept working`
- "After jumping into semantic merge, the top banner / update button got stuck on 'checking' and required a page refresh to re-trigger": every key step in the update flow (and `applyMerge`) now re-checks the remote revision
- "Semantic merge mode listed every .xml (including non-conflict ones like `battle_act_data`) while not showing the actually-conflicted `item_data`": merge mode now defaults to listing only the .xml files currently in SVN conflict, with an "All XML" toggle. Conflicted files get a red status dot, and `get_modified_files` reports the `conflicted` state

**New features**
- System-tray runtime: launched via `pythonw` / `--noconsole` by default, the main process runs the pystray icon with menu items: Open browser / Show log / Open workspace / Quit
- Server output is redirected to `logs/server.log` (rotated 3 × 1 MB); use the new `start_console.bat` (equivalent to `python server.py --console`) when you need a live console

**Internal**
- New `svn_helper.get_conflict_info()` parses `<conflict><prev-base-file/><prev-wc-file/><cur-base-file/></conflict>` from `svn info --xml`
- New `/api/svn/conflicted` endpoint; `/api/svn/update` accepts a `semantic_files` parameter
- New frontend `state.updateContext` queue with `_processNextSemantic` / `_finishSemanticQueue` / `cancelSemanticQueue`
- Fixed tray-mode Flask startup crash: `_StreamToLogger.write` now accepts bytes / bytearray and exposes `encoding` / `isatty` / `fileno` / `writelines`, so `click.echo` no longer hits a `TypeError` when writing the Flask startup banner (which otherwise killed the background Flask thread silently — the tray icon stayed up but the port never opened)
- Fixed constant flashing of console windows from svn / netstat / taskkill subprocesses in tray mode: `svn_helper._run` / `_run_raw` / `_find_svn` probing and `server.kill_existing_on_port` now all pass `subprocess.CREATE_NO_WINDOW` (Windows only)
- Fixed `xml_merger.write_merged_xml` raising `ParseError` when semantic-merging an SVN-conflicted file: the working copy already contains `<<<<<<<` markers and cannot be parsed as XML. `_resolve_merge_sources` now also returns a `template_path` — the `.mine` sidecar (the clean local-side XML) in the conflict branch and the working-copy path otherwise — and the merge result is still written back to the working-copy path
- Stopped spamming `[SVN] Using: svn` in the log: `is_available()` used to print on every call (frontend polling + 15 API entry points), now an `_svn_announced` flag prints it only once on first successful detection
- Fixed the apply-merge popup misleadingly reporting "0 resolutions applied" when the on-disk merge succeeded: the count used to be "the user-supplied resolutions", excluding the auto-decided non-conflict merges (THEIRS-only adds, THEIRS-only modifications, etc.) that `three_way_diff` resolves automatically. `/api/merge/apply` now returns a `total_changes` field that counts the actual row-level ops written to disk and the popup uses that; copy reworded from "resolutions" to "changes"
- Tightened the semantic-merge view to "only show what needs handling": removed the "All XML" escape hatch from the file list (the merge view now always lists exactly the SVN-conflicted .xml files, so you can no longer accidentally drill into a locally-modified-only file and see hundreds of `added_mine` no-op rows); the "Unresolved only" toolbar toggle is now on by default; a new `isLocalNoiseRow` filter unconditionally hides four pure-local-noise row classes (`added_mine` / `added_both_same` / `removed_mine` / `removed_both`) so that even with "Unresolved only" disabled you only see "changes brought by THEIRS + already-resolved items"
- Unlocked cell-resolution buttons for auto-decided cells: previously only `conflict` cells exposed the Keep mine / Use theirs / Custom buttons; the three auto-decided states (`auto_mine` / `auto_theirs` / `auto_both`) were read-only. They now show the same buttons with the current default `selected`, so once you uncheck "Unresolved only" you can review and override each auto decision — primarily to prevent `auto_mine` from silently discarding the remote-correct value when your working copy carries uncommitted dirty edits. `collectResolutions` uses a new `isCellOverridden` helper to forward only the cells the user actually changed away from the default. README (en/zh) gains a short section explaining the BASE / mine / theirs semantics and auto-resolution rules

## v1.4.2 (2026-06-12)

Auto-update restart fix.

**Bug fixes**
- The app now restarts automatically after an in-app update; previously the new exe was installed but the program stayed closed and had to be reopened manually
- GitHub release titles no longer repeat the version number; CI releases now get a "vX.Y.Z - summary" title taken from the changelog

**Internal**
- Root cause: the update helper script inherited PyInstaller bootloader environment variables (`_PYI_*` / `_MEIPASS2`) from the dying process, so the relaunched executable mistook itself for the extracted child stage, pointed at the deleted `_MEIxxxx` temp dir and crashed on startup; `apply_update` now strips these variables
- The helper script waits with `ping` instead of `timeout` (which can exit immediately when stdin is redirected), and the give-up branch now also restarts with the correct working directory
- 3 new updater tests: bootloader env stripping, script template guard, and a locked-file integration test of the swap script (Windows)

## v1.4.1 (2026-06-11)

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
