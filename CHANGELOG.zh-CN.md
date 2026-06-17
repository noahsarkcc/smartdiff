# 更新日志

[English](CHANGELOG.md) · **中文**

SmartDiff 的所有重要变更都记录在这里，格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 风格。

## v1.5.0（2026-06-17）

SVN 冲突合并流程重做 + 系统托盘运行。

**问题修复**
- 修复处于 SVN 文本冲突状态的 .xml 文件无法做语义合并的问题：原先工作副本已被 `<<<<<<<` 标记污染、`svn cat -r BASE` 返回的是更新后的 HEAD 而非真正的祖先版本，三方对比完全错位。现在检测到冲突时改用 `svn info --xml` 暴露的 `.r<old>` / `.mine` / `.r<new>` 三个旁路文件作为 BASE / MINE / THEIRS
- 修复"在冲突弹窗里点语义合并就跳走，导致 `svn update` 没被真正执行，落后远端的纯远程更新文件停留在旧版本"的问题：语义合并现在是冲突文件的第 4 种选择（与 mine/theirs/skip 并列），点"确认更新"后由更新流程托管成语义合并队列，逐个引导完成后再统一执行一次 svn update，已合并文件以 `--accept working` 解析
- 修复"语义合并跳走后顶部 banner / 更新按钮卡在'检查中'，需要刷新页面才能再次触发更新"的问题：在更新流程各关键节点 + applyMerge 完成后主动重新检查远端版本
- 修复"语义合并模式左侧文件列表显示了所有 .xml（包括非冲突的 battle_act_data），却没显示真正处于 SVN 冲突状态的 item_data"的问题：merge 模式默认只显示当前 SVN 冲突的 .xml，提供「全部 XML」切换；冲突文件用红色色点高亮，`get_modified_files` 也会把 conflicted 状态返回

**新功能**
- 系统托盘运行：默认通过 `pythonw` / `--noconsole` 隐藏控制台窗口，主进程跑 pystray 托盘图标，右键菜单：打开浏览器 / 显示日志 / 打开工作目录 / 退出
- 服务器输出重定向到 `logs/server.log`（轮转 3 × 1 MB）；想看实时日志可用新增的 `start_console.bat`（等价于 `python server.py --console`）

**内部改进**
- 后端新增 `svn_helper.get_conflict_info()` 解析 `svn info --xml` 中的 `<conflict><prev-base-file/><prev-wc-file/><cur-base-file/></conflict>`
- 后端新增 `/api/svn/conflicted` 接口；`/api/svn/update` 接受 `semantic_files` 参数
- 前端新增 `state.updateContext` 队列、`_processNextSemantic` / `_finishSemanticQueue` / `cancelSemanticQueue` 等
- 修复托盘模式下 Flask 启动横幅崩溃：`_StreamToLogger.write` 现在兼容 bytes / bytearray，并暴露 `encoding` / `isatty` / `fileno` / `writelines`，避免 `click.echo` 走 bytes 路径时把后台 Flask 线程整个打挂（用户看不到错误，但端口起不来）
- 修复托盘模式下 svn / netstat / taskkill 子进程不停闪黑窗口：`svn_helper._run` / `_run_raw` / `_find_svn` 探测、以及 `server.kill_existing_on_port` 全部加上 `subprocess.CREATE_NO_WINDOW`（仅 Windows）
- 修复对 SVN 冲突状态文件做语义合并时 `xml_merger.write_merged_xml` 直接 `ParseError`：原先把已被 `<<<<<<<` 标记污染的工作副本当模板解析，现在 `_resolve_merge_sources` 额外返回 `template_path`，冲突分支用 `.mine` 旁路文件（合法 XML 本地版本）作为模板，合并结果仍写回工作副本路径
- 修复日志被 `[SVN] Using: svn` 刷屏：原先 `is_available()` 每次被调用（前端轮询 / 各 API 入口共 15 处）都打印一次，现在用 `_svn_announced` 标志只在首次探测成功时打印一次

## v1.4.2（2026-06-12）

自动更新重启修复。

**问题修复**
- 应用内更新完成后程序现在会自动重启；此前新版 exe 已替换成功，但程序不会重新拉起，需要手动再次打开
- GitHub release 标题不再重复版本号；CI 发布现在自动生成"vX.Y.Z - 一句话摘要"形式的标题

**内部改进**
- 根因：更新脚本继承了垂死旧进程的 PyInstaller 引导器环境变量（`_PYI_*` / `_MEIPASS2`），重启的新 exe 误认为自己是已解压的子阶段，指向已删除的 `_MEIxxxx` 临时目录导致启动即崩；`apply_update` 现在会剔除这些变量
- 更新脚本等待改用 `ping` 实现（`timeout` 在 stdin 重定向下可能立即退出），放弃分支重启也补上了工作目录参数
- 新增 3 个更新模块测试：引导器环境变量剔除、脚本模板守卫、锁文件换包集成测试（Windows）

## v1.4.1（2026-06-11）

Diff 表格显示修复。

**问题修复**
- 分行视图：修改单元格的旧值（红）/ 新值（绿）背景现在始终铺满整格高度，相邻单元格的红绿分界线不再因内容长短不一而错位露底
- Diff 表格长文本默认完整换行显示，不再需要把鼠标悬停到单元格上才展开

## v1.4.0（2026-06-10）

应用内自动更新。

**新功能**
- 应用内检查更新：启动 5 秒后静默检查 GitHub Releases，发现新版本时设置按钮（齿轮）显示红点提示
- 设置弹窗新增「版本与更新」区：显示当前版本、手动检查更新、查看新版本说明
- 一键更新（exe 模式）：后台下载新版 `SmartDiff.exe` → 显示进度条 → 自动替换并重启 → 页面自动刷新到新版本；`config.json` 等用户配置不受影响
- GitHub 直连失败时自动走加速代理（`github.2436666.xyz`）重试，检查与下载均支持；会话内记住可用通道
- 源码模式运行时提示使用 `git pull` 更新，并提供发布页直连/加速双链接

**发版基建**
- 新增 `.github/workflows/release.yml`：推送 `v*` tag 自动在 Windows 上跑全量测试、PyInstaller 构建并把 `SmartDiff.exe` 上传到对应 release（此前 release 无 exe 资产，一键更新自此版本起闭环）
- 修正 `build.bat`：依赖改为安装 `requirements.txt`（补齐 openpyxl/xlrd），构建参数与 CI 对齐

**API**
- 新增 `GET /api/update/check`（结果缓存 1 小时，`?force=1` 跳过）、`POST /api/update/download`、`GET /api/update/progress`、`POST /api/update/apply`

**测试**
- 新增 `tests/test_updater.py`（20 个用例）：版本号比较、代理回退、`check_update` 解析、下载状态机、四个端点行为；已接入 CI，全量 76 个用例通过

## v1.3.7（2026-06-10）

可靠性专项修复（来自全量代码评审，共 12 项）。

**数据安全（高危）**
- 语义合并写回改为原子操作：先写同目录临时文件再 `os.replace()` 替换，写入中途失败不再损坏工作副本、丢失未提交的本地修改
- 合并新增行后自动维护 `ss:ExpandedRowCount` / `ss:ExpandedColumnCount`，避免 Excel 因行列数超出声明值而拒绝打开文件
- 远程冲突检测与单文件版本历史对 SVN 百分号编码的 URL 统一解码，中文/非 ASCII 文件名不再漏判冲突或丢失历史记录

**健壮性（中危）**
- 所有接收文件名的 API 增加工作区路径前缀校验，拒绝 `..` 与绝对路径穿越
- 启动时端口清理改为精确匹配本地地址端口列，不再误杀 55660-55669 等相邻端口的进程
- SVN 智能更新改用 `svn status --xml` 判断冲突状态，不再依赖英文输出嗅探（中文 locale 下也正确）；更新文件计数排除 `Updating` / `At revision` 等非文件行
- 合并写回保留文档内部的 `<!-- -->` XML 注释（此前被 ElementTree 静默丢弃）

**其他改进（低危）**
- SVN 文件内容统一走原始字节读取，由 XML 声明自动解码，支持 UTF-16 等非 UTF-8 编码的表格文件
- ID 列自动检测尊重「表头起始行」设置，元信息行（obj/type/desc/key）不再干扰唯一性判断
- 配置读写加锁防并发竞争；`config.json` 保存失败时在 API 响应中返回 `warning` 而非静默忽略
- 打开工作区目录改用 `os.startfile`，移除模拟 Alt 按键的前台聚焦 hack

**测试**
- 新增 `tests/test_differ.py`（11 个用例）：插入/删除不级联、Pass 2/3 匹配、重复 ID、注释列过滤、header_row>1 的 ID 检测、UTF-16 解析；已接入 CI
- `test_merger.py` 新增 ExpandedRowCount 增长与 XML 注释保留回归用例（29 个）
- `test_api_merge.py` 新增路径穿越拒绝用例（16 个），全量 56 个用例通过

## v1.3.6（2026-06-09）

**单元格 Diff 可读性**
- 智能 token 级 diff：连续数字、英文字母作为整块对比，`738` -> `7074` 这样的值变化会整块高亮，不再被打散成零碎的红绿字符。对 `{5:738626,40,6:4235,400,...}` 这类紧凑结构化数据可读性大幅提升
- 新增「分行」视图：旧值、新值上下两行分开展示（旧值在上、新值在下），各自完整并高亮变化部分，一眼看清「原值 -> 新值」
- 工具栏新增「内联 / 分行」视图切换（本地变更、版本对比、版本总览三种模式均可用），偏好通过 localStorage 记忆
- 长值改为在 token 边界换行，不再从数字中间断开

## v1.3.5（2026-06-04）

**新功能**
- 可配置表头起始行：新增全局「表头起始行」设置，用户可指定表头所在行号（默认 1）。对于前几行是 obj/type/desc/key 等元信息的特殊表格，不再整列忽略，所有列都能被正确识别和对比
- 标题栏新增设置按钮（齿轮图标），可打开设置弹窗
- 设置持久化到 `config.json`，保存后立即在所有模式（本地变更、版本对比、浏览、版本总览、语义合并）中生效

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
