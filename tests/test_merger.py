"""
xml_merger 综合测试用例
======================

覆盖：
- 单元格 5 种状态：unchanged / auto_mine / auto_theirs / auto_both / conflict
- 行级 9 种状态：modified / added_mine / added_theirs / added_both_same /
                added_both_diff / removed_mine / removed_theirs / removed_both /
                mine_del_theirs_mod / mine_mod_theirs_del
- apply_resolutions 决议流程（自动 + 手动）
- write_merged_xml roundtrip：写回 → 重新解析 → 内容匹配
- 命名空间风格保留（默认 ns vs ss: 前缀）
- XML 声明 / mso-application PI 保留

直接运行：python tests/test_merger.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import xml_parser
import xml_merger


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BASE_PATH = os.path.join(DATA_DIR, "base.xml")
MINE_PATH = os.path.join(DATA_DIR, "mine.xml")
THEIRS_PATH = os.path.join(DATA_DIR, "theirs.xml")


# 颜色输出
RESET = "\033[0m"; RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"; CYAN = "\033[96m"


_passed = 0
_failed = 0
_failures = []


def t(name):
    """装饰器：标记一个测试用例"""
    def deco(fn):
        def wrapper():
            global _passed, _failed
            try:
                fn()
                _passed += 1
                print(f"  {GREEN}PASS{RESET} {name}")
            except AssertionError as e:
                _failed += 1
                _failures.append((name, str(e)))
                print(f"  {RED}FAIL{RESET} {name}")
                print(f"       {e}")
            except Exception as e:
                _failed += 1
                _failures.append((name, f"EXCEPTION: {e}"))
                print(f"  {RED}ERROR{RESET} {name}")
                print(f"       {type(e).__name__}: {e}")
        wrapper.__test_name = name
        return wrapper
    return deco


def section(title):
    print(f"\n{CYAN}── {title} ──{RESET}")


def load_three_way():
    base = xml_parser.parse_file(BASE_PATH)
    mine = xml_parser.parse_file(MINE_PATH)
    theirs = xml_parser.parse_file(THEIRS_PATH)
    return base, mine, theirs


def find_row(sheet, row_key):
    """在 sheet.rows 中找到 row_key 对应的行；找不到返回 None。"""
    for r in sheet["rows"]:
        if r["row_key"] == row_key:
            return r
    return None


# ── 1. 单元格 5 种状态 ───────────────────────────────────


@t("单元格 unchanged：1001 三方相同 → 行被省略（不出现在 rows 中）")
def test_cell_unchanged_row_omitted():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    sheet = result["sheets"]["Items"]
    assert find_row(sheet, "1001") is None, "未变更行不应出现在 rows 中"


@t("单元格 auto_mine：1002.B 仅本地改 → status=auto_mine, resolved=本地值")
def test_cell_auto_mine():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1002")
    assert row is not None
    cell = row["cells"]["B"]
    assert cell["status"] == "auto_mine", f"实际: {cell['status']}"
    assert cell["resolved"] == "本地新名称"
    assert cell["mine"] == "本地新名称"


@t("单元格 auto_theirs：1003.C 仅远程改 → status=auto_theirs, resolved=远程值")
def test_cell_auto_theirs():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1003")
    cell = row["cells"]["C"]
    assert cell["status"] == "auto_theirs", f"实际: {cell['status']}"
    assert cell["resolved"] == "33"


@t("单元格 auto_both：1004.B 双方改成同值 → status=auto_both")
def test_cell_auto_both():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1004")
    cell = row["cells"]["B"]
    assert cell["status"] == "auto_both", f"实际: {cell['status']}"
    assert cell["resolved"] == "双方同改后"


@t("单元格 conflict：1006.B 双方改成不同值 → status=conflict, resolved=None")
def test_cell_conflict():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1006")
    cell = row["cells"]["B"]
    assert cell["status"] == "conflict", f"实际: {cell['status']}"
    assert cell["resolved"] is None


@t("同行多列混合：1005 仅本地改 B + 仅远程改 C → 都自动决议，无冲突")
def test_modified_row_mixed_no_conflict():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1005")
    assert row["cells"]["B"]["status"] == "auto_mine"
    assert row["cells"]["B"]["resolved"] == "本地改名称"
    assert row["cells"]["C"]["status"] == "auto_theirs"
    assert row["cells"]["C"]["resolved"] == "55"
    assert row["is_row_conflict"] is False


# ── 2. 行级 9 种状态 ─────────────────────────────────────


@t("行级 modified：1006 双方都改但无行级冲突 → row_decision='merge'")
def test_row_modified():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1006")
    assert row["status"] == "modified"
    assert row["row_decision"] == "merge"


@t("行级 removed_mine：1007 仅本地删 + 远程未改 → 默认 keep_mine_delete")
def test_row_removed_mine():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1007")
    assert row["status"] == "removed_mine"
    assert row["row_decision"] == "keep_mine_delete"
    assert row["is_row_conflict"] is False


@t("行级 removed_theirs：1008 仅远程删 + 本地未改 → 默认 accept_theirs_delete")
def test_row_removed_theirs():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1008")
    assert row["status"] == "removed_theirs"
    assert row["row_decision"] == "accept_theirs_delete"


@t("行级 removed_both：1009 双方都删 → 自动 delete")
def test_row_removed_both():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1009")
    assert row["status"] == "removed_both"
    assert row["row_decision"] == "delete"


@t("行级冲突 mine_del_theirs_mod：1010 本删远改 → row_decision=None")
def test_row_mine_del_theirs_mod():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1010")
    assert row["status"] == "mine_del_theirs_mod"
    assert row["is_row_conflict"] is True
    assert row["row_decision"] is None


@t("行级冲突 mine_mod_theirs_del：1011 本改远删 → row_decision=None")
def test_row_mine_mod_theirs_del():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "1011")
    assert row["status"] == "mine_mod_theirs_del"
    assert row["is_row_conflict"] is True


@t("行级 added_mine：2001 仅本地新增 → 默认 keep_mine")
def test_row_added_mine():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "2001")
    assert row["status"] == "added_mine"
    assert row["row_decision"] == "keep_mine"


@t("行级 added_theirs：2002 仅远程新增 → 默认 accept_theirs")
def test_row_added_theirs():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "2002")
    assert row["status"] == "added_theirs"
    assert row["row_decision"] == "accept_theirs"


@t("行级 added_both_same：2003 双方加同行 → 自动 keep")
def test_row_added_both_same():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "2003")
    assert row["status"] == "added_both_same"
    assert row["row_decision"] == "keep"
    assert row["is_row_conflict"] is False


@t("行级冲突 added_both_diff：2004 双方加同 ID 不同内容 → row_decision=None")
def test_row_added_both_diff():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    row = find_row(result["sheets"]["Items"], "2004")
    assert row["status"] == "added_both_diff"
    assert row["is_row_conflict"] is True
    assert row["row_decision"] is None


# ── 3. summary 统计准确性 ────────────────────────────────


@t("summary 统计：3 行级冲突 + 1 单元格冲突")
def test_summary_counts():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    s = result["summary"]
    assert s["row_conflicts"] == 3, f"行级冲突数: {s['row_conflicts']} (期望 3：1010, 1011, 2004)"
    assert s["cell_conflicts"] == 1, f"单元格冲突数: {s['cell_conflicts']} (期望 1：1006.B)"
    assert s["conflicts"] == 4
    assert s["auto_resolved"] >= 4, f"自动决议至少 4 项 (1002.B, 1003.C, 1004.B, 1005.B, 1005.C)"


@t("ID 列自动检测：第一列名称含 ID → id_column='A'")
def test_id_column_detected():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    assert result["sheets"]["Items"]["id_column"] == "A"


# ── 4. apply_resolutions ────────────────────────────────


@t("apply_resolutions：未决议时返回 unresolved 列表（4 个）")
def test_apply_unresolved_initial():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    applied = xml_merger.apply_resolutions(result, [])
    assert applied["ok"] is False
    assert len(applied["unresolved"]) == 4
    kinds = [u["kind"] for u in applied["unresolved"]]
    assert kinds.count("row") == 3
    assert kinds.count("cell") == 1


@t("apply_resolutions：全部决议后 ok=True, unresolved 为空")
def test_apply_all_resolved():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "theirs"},
        {"sheet": "Items", "row_key": "1010", "choice": "accept_theirs"},
        {"sheet": "Items", "row_key": "1011", "choice": "keep_mine"},
        {"sheet": "Items", "row_key": "2004", "choice": "accept_theirs"},
    ]
    applied = xml_merger.apply_resolutions(result, resolutions)
    assert applied["ok"] is True, f"unresolved: {applied['unresolved']}"
    assert applied["applied"] == 4


@t("apply_resolutions：custom 自定义值生效")
def test_apply_custom_value():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "custom", "value": "调和后名称"},
        {"sheet": "Items", "row_key": "1010", "choice": "keep_mine_delete"},
        {"sheet": "Items", "row_key": "1011", "choice": "keep_mine"},
        {"sheet": "Items", "row_key": "2004", "choice": "keep_mine"},
    ]
    applied = xml_merger.apply_resolutions(result, resolutions)
    assert applied["ok"] is True
    cell = find_row(result["sheets"]["Items"], "1006")["cells"]["B"]
    assert cell["resolved"] == "调和后名称"


# ── 5. write_merged_xml roundtrip ───────────────────────


@t("写回：默认全自动决议 + 用户冲突选择 → 输出文件可重新解析")
def test_write_merged_roundtrip():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "theirs"},  # 用远程"远程改后"
        {"sheet": "Items", "row_key": "1010", "choice": "accept_theirs"},  # 恢复远程修改的行
        {"sheet": "Items", "row_key": "1011", "choice": "accept_theirs_delete"},  # 接受远程删除
        {"sheet": "Items", "row_key": "2004", "choice": "accept_theirs"},  # 用远程版本
    ]
    xml_merger.apply_resolutions(result, resolutions)

    out_path = os.path.join(tempfile.gettempdir(), "_merger_roundtrip.xml")
    xml_merger.write_merged_xml(MINE_PATH, result, out_path)

    parsed = xml_parser.parse_file(out_path)
    rows = parsed["sheets"]["Items"]["rows"]
    by_id = {r["cells"]["A"]: r["cells"] for r in rows[1:] if r["cells"].get("A")}

    # 1001 unchanged，应该原样保留
    assert by_id["1001"]["B"] == "原始道具"
    # 1002 取本地（仅本地改）
    assert by_id["1002"]["B"] == "本地新名称"
    # 1003 取远程（仅远程改 C）
    assert by_id["1003"]["C"] == "33"
    # 1004 双方同改后
    assert by_id["1004"]["B"] == "双方同改后"
    # 1005 取本地 B + 远程 C
    assert by_id["1005"]["B"] == "本地改名称"
    assert by_id["1005"]["C"] == "55"
    # 1006 用户选了 theirs
    assert by_id["1006"]["B"] == "远程改后"
    assert by_id["1006"]["C"] == "66"
    # 1007 已被本地删除（默认 keep_mine_delete），不在
    assert "1007" not in by_id
    # 1008 接受远程删除，不在
    assert "1008" not in by_id
    # 1009 双方删除，不在
    assert "1009" not in by_id
    # 1010 用户选 accept_theirs：恢复并接受远程修改
    assert "1010" in by_id, "1010 应该被恢复"
    assert by_id["1010"]["D"] == "远程修改"
    # 1011 用户选 accept_theirs_delete：删掉
    assert "1011" not in by_id, "1011 应被删除"
    # 2001 本地新增保留
    assert by_id["2001"]["B"] == "本地新增"
    # 2002 接受远程新增
    assert "2002" in by_id, "2002 应该被加进来"
    assert by_id["2002"]["B"] == "远程新增"
    # 2003 双方都加且相同，保留
    assert by_id["2003"]["B"] == "双方都加"
    # 2004 用户选 accept_theirs，本地的"本地版本"被替换为"远程版本"
    assert by_id["2004"]["B"] == "远程版本"
    assert by_id["2004"]["D"] == "远程说"


@t("写回：保留 XML 声明 与 mso-application PI")
def test_write_preserves_preamble():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "mine"},
        {"sheet": "Items", "row_key": "1010", "choice": "keep_mine_delete"},
        {"sheet": "Items", "row_key": "1011", "choice": "keep_mine"},
        {"sheet": "Items", "row_key": "2004", "choice": "keep_mine"},
    ]
    xml_merger.apply_resolutions(result, resolutions)

    out_path = os.path.join(tempfile.gettempdir(), "_merger_preamble.xml")
    xml_merger.write_merged_xml(MINE_PATH, result, out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content.startswith('<?xml'), "缺少 XML 声明"
    assert '<?mso-application progid="Excel.Sheet"?>' in content, "缺少 mso-application PI"


@t("写回：保留默认命名空间风格（不出现 ss:Workbook 等元素前缀）")
def test_write_preserves_default_ns_style():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    resolutions = [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "mine"},
        {"sheet": "Items", "row_key": "1010", "choice": "keep_mine_delete"},
        {"sheet": "Items", "row_key": "1011", "choice": "keep_mine"},
        {"sheet": "Items", "row_key": "2004", "choice": "keep_mine"},
    ]
    xml_merger.apply_resolutions(result, resolutions)

    out_path = os.path.join(tempfile.gettempdir(), "_merger_ns.xml")
    xml_merger.write_merged_xml(MINE_PATH, result, out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "<ss:Workbook" not in content, "Workbook 不应有 ss: 前缀"
    assert "<ss:Worksheet" not in content, "Worksheet 不应有 ss: 前缀"
    assert "<ss:Row" not in content, "Row 不应有 ss: 前缀"
    assert "<ss:Cell" not in content, "Cell 不应有 ss: 前缀"
    assert 'xmlns="urn:schemas-microsoft-com:office:spreadsheet"' in content, "缺少默认 xmlns"
    assert 'ss:Type="String"' in content, "属性应保留 ss: 前缀"


def _make_book(rows, expanded_row_count):
    """构造一个带 ss:ExpandedRowCount 的最小 SpreadsheetML 文件内容。
    rows 是 [(id, name), ...]，首行固定为表头 ID/名称。"""
    head = (
        '<?xml version="1.0"?>\n'
        '<?mso-application progid="Excel.Sheet"?>\n'
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'
        '<Worksheet ss:Name="Items">\n'
        f'<Table ss:ExpandedColumnCount="2" ss:ExpandedRowCount="{expanded_row_count}">\n'
        '<Row><Cell><Data ss:Type="String">ID</Data></Cell>'
        '<Cell><Data ss:Type="String">名称</Data></Cell></Row>\n'
    )
    body = ""
    for rid, name in rows:
        body += (f'<Row><Cell><Data ss:Type="String">{rid}</Data></Cell>'
                 f'<Cell><Data ss:Type="String">{name}</Data></Cell></Row>\n')
    tail = '</Table>\n</Worksheet>\n</Workbook>\n'
    return head + body + tail


def _write_tmp(name, content):
    p = os.path.join(tempfile.gettempdir(), name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


@t("写回：接受远程新增行后 ss:ExpandedRowCount 同步增长且文件可解析")
def test_write_updates_expanded_row_count():
    import re as _re
    bp = _write_tmp("_erc_base.xml", _make_book([("1001", "甲")], 2))
    mp = _write_tmp("_erc_mine.xml", _make_book([("1001", "甲")], 2))
    tp = _write_tmp("_erc_theirs.xml", _make_book([("1001", "甲"), ("1002", "乙")], 3))

    base = xml_parser.parse_file(bp)
    mine = xml_parser.parse_file(mp)
    theirs = xml_parser.parse_file(tp)
    result = xml_merger.three_way_diff(base, mine, theirs)

    applied = xml_merger.apply_resolutions(result, [])
    assert applied["ok"] is True, f"不应有冲突: {applied['unresolved']}"

    out = os.path.join(tempfile.gettempdir(), "_erc_out.xml")
    xml_merger.write_merged_xml(mp, result, out)

    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    m = _re.search(r'ExpandedRowCount="(\d+)"', content)
    assert m is not None, "输出缺少 ExpandedRowCount"
    assert int(m.group(1)) >= 3, f"ExpandedRowCount 未增长到 >=3: {m.group(1)}"

    parsed = xml_parser.parse_file(out)
    ids = {r["cells"].get("A") for r in parsed["sheets"]["Items"]["rows"]}
    assert "1002" in ids, "接受的远程新增行应写入文件"


@t("写回：保留文档内部 XML 注释（不再被 ET 丢弃）")
def test_write_preserves_comments():
    xml = (
        '<?xml version="1.0"?>\n'
        '<?mso-application progid="Excel.Sheet"?>\n'
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'
        '<!-- 重要：这是配置说明注释 -->\n'
        '<Worksheet ss:Name="Items">\n'
        '<Table ss:ExpandedColumnCount="2" ss:ExpandedRowCount="2">\n'
        '<Row><Cell><Data ss:Type="String">ID</Data></Cell>'
        '<Cell><Data ss:Type="String">名称</Data></Cell></Row>\n'
        '<Row><Cell><Data ss:Type="String">1001</Data></Cell>'
        '<Cell><Data ss:Type="String">甲</Data></Cell></Row>\n'
        '</Table>\n</Worksheet>\n</Workbook>\n'
    )
    p = _write_tmp("_cmt.xml", xml)
    base = xml_parser.parse_file(p)
    result = xml_merger.three_way_diff(base, base, base)

    out = os.path.join(tempfile.gettempdir(), "_cmt_out.xml")
    xml_merger.write_merged_xml(p, result, out)

    with open(out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "这是配置说明注释" in content, f"内部注释丢失: {content}"


# ── 6. 边界情况 ──────────────────────────────────────────


@t("边界：MINE/BASE/THEIRS 完全相同 → summary 全部 0")
def test_no_changes():
    base = xml_parser.parse_file(BASE_PATH)
    result = xml_merger.three_way_diff(base, base, base)
    s = result["summary"]
    assert s["conflicts"] == 0
    assert s["auto_resolved"] == 0


@t("边界：未决议时 unresolved 列表精确指向 (sheet, row_key, col)")
def test_unresolved_pointers():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    applied = xml_merger.apply_resolutions(result, [])
    cell_unresolved = [u for u in applied["unresolved"] if u["kind"] == "cell"]
    assert len(cell_unresolved) == 1
    u = cell_unresolved[0]
    assert u["sheet"] == "Items"
    assert u["row_key"] == "1006"
    assert u["col"] == "B"


@t("边界：apply_resolutions 部分决议后剩余冲突仍被检测")
def test_partial_apply():
    base, mine, theirs = load_three_way()
    result = xml_merger.three_way_diff(base, mine, theirs)
    applied = xml_merger.apply_resolutions(result, [
        {"sheet": "Items", "row_key": "1006", "col": "B", "choice": "mine"},
    ])
    assert applied["ok"] is False
    assert len(applied["unresolved"]) == 3  # 还有 3 个行冲突


# ── Main ────────────────────────────────────────────────


def main():
    print(f"{CYAN}xml_merger 测试套件{RESET}")
    print(f"  数据目录: {DATA_DIR}")

    section("1. 单元格 5 状态")
    test_cell_unchanged_row_omitted()
    test_cell_auto_mine()
    test_cell_auto_theirs()
    test_cell_auto_both()
    test_cell_conflict()
    test_modified_row_mixed_no_conflict()

    section("2. 行级 9 状态")
    test_row_modified()
    test_row_removed_mine()
    test_row_removed_theirs()
    test_row_removed_both()
    test_row_mine_del_theirs_mod()
    test_row_mine_mod_theirs_del()
    test_row_added_mine()
    test_row_added_theirs()
    test_row_added_both_same()
    test_row_added_both_diff()

    section("3. summary / id_column")
    test_summary_counts()
    test_id_column_detected()

    section("4. apply_resolutions")
    test_apply_unresolved_initial()
    test_apply_all_resolved()
    test_apply_custom_value()

    section("5. write_merged_xml roundtrip")
    test_write_merged_roundtrip()
    test_write_preserves_preamble()
    test_write_preserves_default_ns_style()
    test_write_updates_expanded_row_count()
    test_write_preserves_comments()

    section("6. 边界")
    test_no_changes()
    test_unresolved_pointers()
    test_partial_apply()

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
