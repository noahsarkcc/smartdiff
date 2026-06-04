# 更新日志

[English](CHANGELOG.md) · **中文**

SmartDiff 的所有重要变更都记录在这里，格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 风格。

## v1.3.4（2026-06-04）

**问题修复**
- 版本总览：中文（非 ASCII）文件名不再报「Cannot get revision content」。SVN 在远程 URL 中对这类文件名做百分号编码，变更列表现在会解码，使文件名正确显示并能取到版本内容
- 版本总览改为通过仓库 URL 获取版本内容，本地未 checkout 的文件也能对比
- `get_file_at_revision` / `get_file_at_revision_raw` 支持直接传入仓库 URL

## v1.3.3（2026-06-04）

**国际化（i18n）**
- Web UI 新增中英文双语切换，Header 一键切换
- 首次访问自动检测浏览器语言（zh-* → 中文，其他 → 英文）
- 用户选择通过 localStorage (`smartdiff_locale`) 持久化
- 覆盖范围：标题栏、侧栏、四种 Diff 模式、语义合并 UI、SVN 冲突弹窗、所有 alert 和错误提示

**文档**
- CHANGELOG 拆分为 `CHANGELOG.md`（英文）和 `CHANGELOG.zh-CN.md`（中文），与 README/DEVELOPMENT 双语风格一致

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
