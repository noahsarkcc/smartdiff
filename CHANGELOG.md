# Changelog

**English** · [中文](#更新日志)

All notable changes to SmartDiff are documented here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

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

---

# 更新日志

[English](#changelog) · **中文**

SmartDiff 的所有重要变更都记录在这里，格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 风格。

## v1.3.2（2026-05-27）

**文件列表**
- 修复子目录 `.xls` 在 SVN 变更列表 / 仅变更过滤中无法按相对路径匹配的问题
- 补充 `/api/files` 递归列出 `configs/items.xls` 与 `/api/svn/modified` 相对路径返回的回归测试

## v1.3.1（2026-05-15）

**SVN 冲突检测**
- `check_only` 改为按工作区相对路径匹配本地修改和远端变更，修复子目录文件被 `basename` 匹配漏判的问题
- 补充 API 回归测试，覆盖 `configs/items.xml` 这类子目录冲突场景

## v1.3.0（2026-05-15）

**单元格级三方语义合并**
- 新增 `xml_merger.py`，支持 `BASE / MINE / THEIRS` 三方 Diff、自动决议、手动决议和写回
- 新增 `/api/merge/preview`、`/api/merge/apply`、`/api/merge/svn-mark-resolved`
- SVN 冲突弹窗集成"语义合并"入口，XML 冲突可直接按单元格解决
- 新增自动化测试套件与演示 SVN 仓库脚本

<details>
<summary><b>历史版本（v1.0 – v1.2）</b></summary>

## v1.2.0（2026-05-14）

**Excel 二进制文件支持**
- 新增 `.xlsx` / `.xls` 解析，使用 `openpyxl` / `xlrd` 提取纯单元格数据
- SVN 历史版本读取支持二进制 raw bytes，版本 Diff 可用于 Excel 文件

## v1.1.0（2026-05-13）

**Diff 引擎**
- 重构三轮行匹配算法：Pass 1 按 ID 值匹配 → Pass 2 按内容哈希 + 位置就近匹配 → Pass 3 按行号兜底。插入 / 删除少量行时不再产生大量假修改
- SVN 日志过滤改进：正确包含通过目录拷贝（分支 / 标签）创建的文件版本

**版本总览（Overview）**
- 修复水平滚动条不可见与缩放后双 Y 轴滚动条问题（动态计算 diff 容器高度 + 外层容器显式禁用水平溢出）
- 内滚动条使用高对比度样式；动态插入 HTML 后强制重排确保立即渲染

**版本对比**
- 版本下拉不再包含"工作副本"，默认选中最近两个 SVN 版本
- 单版本文件显示"仅有 1 个版本，无法进行版本间对比"
- Scroll hints（浮动变更提示）支持 overview 模式，使用 `position: fixed` 精确定位

**其他**
- 打开工作区目录时 Explorer 窗口自动前台聚焦（Windows）
- 修正 `start.bat` 端口号显示（5000 → 5566）
- 新增 `__version__` 版本号管理，`/api/config` 接口返回版本信息

## v1.0.0

首个发布版本。包含本地变更、版本对比、浏览、版本总览四种模式，SVN 智能更新，inline diff，PyInstaller 打包等功能。

</details>
