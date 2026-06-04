# 开发文档

[English](DEVELOPMENT.md) · **中文**

---

## 目录

- [项目架构](#项目架构)
- [技术栈](#技术栈)
- [模块详解](#模块详解)
  - [xml_parser.py / xlsx_parser.py — 工作簿解析器](#xml_parserpy--xlsx_parserpy--工作簿解析器)
  - [xml_differ.py — 语义 Diff 引擎](#xml_differpy--语义-diff-引擎)
  - [xml_merger.py — 三方语义合并引擎](#xml_mergerpy--三方语义合并引擎)
  - [svn_helper.py — SVN 集成](#svn_helperpy--svn-集成)
  - [server.py — Flask REST API](#serverpy--flask-rest-api)
  - [static/ — 前端 SPA](#static--前端-spa)
- [扩展指南](#扩展指南)
- [测试](#测试)
- [后续开发计划](#后续开发计划)

---

## 项目架构

```
smartdiff/
├── server.py            # Flask 后端，REST API 入口
├── xml_parser.py        # SpreadsheetML 2003 解析器
├── xlsx_parser.py       # XLSX (Office Open XML) 解析器
├── xml_differ.py        # 语义 Diff 引擎
├── xml_merger.py        # 三方语义合并引擎（BASE/MINE/THEIRS）
├── svn_helper.py        # SVN CLI 集成
├── config.json          # 工作区配置（运行时生成，已 .gitignore）
├── requirements.txt     # Python 依赖
├── start.bat            # Windows 一键启动脚本
├── static/              # 前端 SPA（index.html + css + js + img）
├── tests/
│   ├── TESTING.md / TESTING.zh-CN.md   # 测试指南
│   ├── test_merger.py                  # xml_merger 单元测试（27 用例）
│   ├── test_api_merge.py               # HTTP API + mock SVN 端到端（15 用例）
│   ├── setup_demo_svn.bat              # 一键搭建 SVN 演示仓库供手工 UI 测试
│   └── data/                           # 三方测试数据：base.xml / mine.xml / theirs.xml
├── README.md / README.zh-CN.md
└── DEVELOPMENT.md / DEVELOPMENT.zh-CN.md
```

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python 3 + Flask | 轻量 Web 框架，无需数据库 |
| 前端 | Vanilla JS + CSS | 零依赖 SPA，无需构建工具 |
| XML 解析 | `xml.etree.ElementTree` | 标准库 |
| XLSX 解析 | openpyxl | `read_only` + `data_only` 模式 |
| 版本控制 | SVN CLI (subprocess) | 调用 svn 命令行获取版本信息 |
| 打包 | PyInstaller | 通过 `build.bat` 打包独立 exe |

---

## 模块详解

### `xml_parser.py` / `xlsx_parser.py` — 工作簿解析器

两个解析器对外暴露相同的输出结构，下游不需要关心实际格式。

**`xml_parser.py`** — SpreadsheetML 2003：

- 命名空间：`urn:schemas-microsoft-com:office:spreadsheet`
- 处理 `ss:Index`（非连续编号）和 `ss:MergeAcross` / `ss:MergeDown`（跳过合并单元格的占位）
- 仅在单元格有实际值时才推进 `max_col`，末尾空列被丢弃
- 末尾连续空表头自动裁剪

**`xlsx_parser.py`** — Office Open XML：

- 使用 `openpyxl` 的 `read_only=True, data_only=True` 模式（只读值，不加载公式 / 样式）
- 整数浮点数归一化：`1.0` → `"1"`，与 `xml_parser` 字符串输出一致
- 两种输入：`parse_file(path)` 和 `parse_bytes(data)`，后者用于 SVN 历史版本

**共用输出结构**：

```python
{
    "sheets": {
        "Sheet1": {
            "headers": ["ID", "名称", "数值"],
            "rows": [
                {"_row": 1, "cells": {"A": "ID", "B": "名称", "C": "数值"}},
                {"_row": 2, "cells": {"A": "1001", "B": "道具", "C": "100"}},
            ],
            "row_count": 10,
            "col_count": 3,
        }
    },
    "_parse_ms": 12.5,
}
```

### `xml_differ.py` — 语义 Diff 引擎

对比两个解析后的工作簿，产出结构化的变更信息。

1. **自动 ID 列检测**（`_auto_detect_id_column`）：扫描表头中包含 `ID / 编号 / Key / 序号 / 索引` 的列，要求 ≥ 50% 非空且唯一；回退到前 3 列检查唯一性。对 old / new 两个 sheet 检测取一致结果。
2. **有效列过滤**（`valid_cols`）：只比较有非空表头的列；没有表头的列视为注释数据。
3. **三轮行匹配**（`_diff_sheet`）：
   - Pass 1：按 ID 列值匹配
   - Pass 2：按内容哈希 + 位置就近优先（解决插入 / 删除导致的行号偏移）
   - Pass 3：按行号匹配（兜底：内容变更 + 位置偏移的行）
4. **空行**（`_is_empty_row`）从 ID 检测和所有匹配 pass 中跳过。

### `xml_merger.py` — 三方语义合并引擎

对 SpreadsheetML 2003 (`.xml`) 工作簿做单元格级 + 行级三方合并（BASE / MINE / THEIRS），输出可交互的合并预览结构，并将用户决议写回 MINE 的 XML 文件。

**核心函数**：

- `three_way_diff(base, mine, theirs, id_column=None)`：返回结构化对比；每行 cells 字典提供 `base / mine / theirs / status / resolved`。
- `apply_resolutions(result, resolutions)`：写入用户选择（`mine / theirs / base / custom` + 行级决议），校验是否还有未解决冲突，返回 `{ok, unresolved, applied}`。
- `write_merged_xml(source_path, result, output_path)`：基于 MINE 原始 XML AST 做增量修改（Cell/Data 文本更新、Row 节点克隆 / 移除），重新输出文件。

**单元格三方语义**：

| BASE | MINE | THEIRS | 结果 |
|---|---|---|---|
| X | X | X | `unchanged` |
| X | X | Y | `auto_theirs` |
| X | Y | X | `auto_mine` |
| X | Y | Y | `auto_both` |
| X | Y | Z | `conflict`（待用户决议） |

**行级语义**（依赖 ID 列匹配）：

- `added_mine` / `added_theirs`：单方新增
- `added_both_same` / `added_both_diff`：双方加同 ID；不同则需要决议（`keep_mine` / `accept_theirs` / `merge`）
- `removed_mine` / `removed_theirs` / `removed_both`：单方或双方删除
- `mine_del_theirs_mod` / `mine_mod_theirs_del`：删除 vs 修改的强冲突

**XML 写回保真**：原文件的 BOM、`<?xml ?>` 声明、`<?mso-application ?>` PI、注释、命名空间风格（默认 ns 或 `ss:` 前缀）都会保留。新增 Row / Cell 显式设置 `ss:Index` 避免破坏隐式编号；修改单元格时只重写 `<Data>` 文本节点，`<Cell>` 的样式属性（如 `ss:StyleID`）和内联注释保持不变。

### `svn_helper.py` — SVN 集成

封装 SVN CLI 调用，处理编码问题。

- 自动检测 `svn` 路径（PATH 中的 svn、TortoiseSVN 路径）
- `_decode_output`：依次尝试 UTF-8、GBK、UTF-8(replace) 解码
- 所有操作都有超时保护
- **远程 URL 策略**：`get_log` / `get_dir_log` / `get_file_at_revision` / `get_changed_files_between_revisions` 优先使用远程 URL（通过 `get_svn_info`），无需 `svn update` 即可看到最新版本历史
- **版本过滤**：`--stop-on-copy` 避免显示拷贝前的历史；`get_log` 额外按路径过滤；`get_changed_files_between_revisions` 跳过当前目录之外的文件
- **二进制支持**：`_run_raw` / `get_file_at_revision_raw` / `get_base_content_raw` 返回原始字节流，用于 XLSX 等二进制格式的 SVN 版本获取
- **`smart_update`** 支持三种冲突策略：`skip / theirs / mine`

### `server.py` — Flask REST API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 配置 + SVN 状态 + 工作区列表 |
| GET, POST | `/api/workspaces`, `/workspaces/{switch,add,remove}` | 工作区 CRUD |
| POST, GET | `/api/pick-dir`, `/api/browse-dir?path=` | 目录选择（原生 tkinter，fallback 到自制浏览器） |
| GET | `/api/file-mtime?file=` | 文件最后修改时间（自动刷新用） |
| GET | `/api/files` | 列出工作区文件（XML + XLSX） |
| GET | `/api/svn/modified[-classify]` | 本地修改文件；`classify` 区分 `data`（实质数据变更）vs `meta`（仅格式） |
| GET | `/api/svn/log`, `/api/svn/dir-log`, `/api/svn/changed-files` | 版本历史（文件 / 目录 / 两版本之间） |
| GET | `/api/svn/remote-revision` | 远程 HEAD vs 本地 BASE 版本号对比 |
| POST | `/api/svn/update` | 智能 SVN 更新（`check_only` 检测冲突） |
| GET | `/api/parse?file=` | 解析文件（自动识别 XML/XLSX） |
| POST | `/api/diff/{local,revisions,overview,batch}` | Diff 接口 |
| POST | `/api/merge/preview` | 三方合并预览（仅 .xml） |
| POST | `/api/merge/apply` | 应用合并决议并写回 |
| POST | `/api/merge/svn-mark-resolved` | 调用 `svn resolve --accept working` |

### `static/` — 前端 SPA

**state 管理**：全局 `state` 对象，包含当前模式、文件列表、diff 结果等。所有 UI 更新通过 `render*` 函数从 state 重新渲染。

**渲染优化**：分批渲染（`BATCH_SIZE = 150` 行），用 `requestAnimationFrame` 追加后续行；每个 tbody 有唯一 ID，支持多表格同时展开。

**Inline Diff**（`inlineDiff`）：基于 LCS 算法的字符级 diff，在修改单元格内高亮变更字符。短字符串（≤ 200 字符）逐字符对比，长字符串先按分隔符分词。输出 `<del>` / `<ins>` 标签，样式参照 GitHub Dark 配色。

**自动刷新与远程版本检测**：`/api/file-mtime` 每 3 秒轮询一次，文件变更时自动重新加载 diff（本地变更 / 浏览模式）；`/api/svn/remote-revision` 每 30 秒轮询一次，远程 HEAD 领先于本地 BASE 时顶部显示黄色横幅，点击"更新"触发智能更新流程（冲突检测 + 分类处理）。切换工作区会重置所有轮询状态。

**语义合并模式**：第四个模式 tab；侧边栏自动过滤为仅 `.xml`。选中文件后调 `/api/merge/preview`，按 Sheet → Row → Cell 三层渲染：

- 顶部 sticky：sheet tabs + 版本来源对比条（BASE ← 本地 · 远程）
- 每行是一张卡片，包含 header（行 ID / 状态徽章 / 行级决议按钮 / 折叠开关）、始终显示的行数据表（根据 `row_decision` 自动选择显示来源 mine / theirs / base / 已合并；删除决议带 strike-through）、可折叠的"变更详情"面板（modified 行展示每个变更单元格的 BASE / 本地 / 远程 + 决议按钮组；`added_both_diff` 展示双方对比）
- 单元格 badge：`本`（蓝）、`远`（紫）、`=`（绿）、`✎`（黄）、`!`（红，未决议）
- 工具栏：自动 / 冲突 / 待解决统计 + 进度条 + "只看待解决"过滤 + "全部展开 / 折叠 / 智能"三态切换；智能模式（默认）展开需要手动决议的行，折叠自动决议的行
- **应用合并** 调 `/api/merge/apply`，前端通过 `collectResolutions()` 同时下发单元格选择和行级选择
- SVN 冲突弹窗的 `.conflict-item` 上对 `.xml` 文件额外渲染**语义合并**按钮；合并完成后自动 `svn resolve --accept working`

**其它细节**：

- 修改文件圆点指示器（橙 = 实质数据变更、灰 = 仅元数据、绿 = 新增、红 = 删除）通过 `/api/svn/modified-classify` 周期性分类
- 宽表格两侧浮动滚动提示 `← 左侧有 N 处变更` / `右侧有 N 处变更 →`，点击滚动到最近变更列
- 总览面板高度根据视口动态适配（200~600 px clamp）确保水平滚动条始终可见；展开 / 折叠用局部 DOM 操作保留滚动位置
- 版本对比默认选最近两个 SVN 版本；0 / 1 个版本的文件有降级 UI 提示
- 目录选择优先 `tkinter.filedialog.askdirectory()`，PyInstaller 打包环境下 fallback 到自制弹窗（支持路径输入 / 面包屑 / 单击返回上级）

---

## 扩展指南

### 添加新的合规规则

在 `xml_differ.py` 中扩展 `diff_workbooks`，或新增独立的 `validate_workbook` 函数：

```python
def validate_workbook(parsed: dict, rules: list) -> list:
    """对解析后的工作簿执行合规检查。
    rules: [{"type": "range_check", "sheet": "...", "col": "C", "min": 0, "max": 100}, ...]
    returns: [{"sheet": "...", "row": N, "col": "C", "message": "..."}]
    """
```

然后在 `server.py` 中添加 `/api/validate` 端点。

### 添加新的数据源

如果需要支持其他表格格式（参考 `xlsx_parser.py` 的实现）：

1. 在 `xml_parser.py` 同级创建新的解析器
2. 保持相同的输出格式（`sheets` > `headers` + `rows`）
3. 在 `server.py` 的 `_parse_file` / `_parse_content` 调度函数中按扩展名分发
4. 二进制格式使用 `svn_helper` 的 `_raw` 系列函数获取原始字节

### PyInstaller 打包

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "static;static" --name SmartDiff server.py
```

生成的 `dist/SmartDiff.exe` 可独立运行，无需 Python 环境。`config.json` 会在首次启动时自动生成，无需打包进去。

---

## 测试

```powershell
# 1) 合并引擎单元测试（无需 SVN）
python tests\test_merger.py     # 27 用例

# 2) HTTP API 端到端（mock SVN）
python tests\test_api_merge.py  # 15 用例

# 3) 手工 UI 测试（需要 svn CLI）
tests\setup_demo_svn.bat        # 在 %TEMP%\xmldev_demo_svn\ 搭一个三方对齐的演示仓库
start.bat                       # 然后在头部添加 wc 目录作为工作区
```

详见 [tests/TESTING.zh-CN.md](tests/TESTING.zh-CN.md)：每条测试数据预期结果、UI 操作步骤、SVN 冲突集成验证、常见问题。

---

## 后续开发计划

| 功能 | 说明 | 涉及模块 |
|---|---|---|
| 合规引擎 | 可配置的规则系统：数值范围检查、必填字段验证、跨表引用验证（如表 A 的某列值必须存在于表 B） | 新增 `validator.py`、`/api/validate` |
| 文件收藏夹 | 常用文件快速访问，每个工作区独立配置 | `config.json` 扩展 |

完整的版本变更历史见 [CHANGELOG.md](CHANGELOG.md)。
