"""
xml_differ 单元测试
===================

覆盖：
- 单元格修改的精确定位（行 / 列 / 旧值 / 新值）
- 插入 / 删除行不产生级联假修改（Pass 1 ID 匹配）
- 无 ID 列时内容哈希匹配（Pass 2）
- 移动 + 修改的行号回退匹配（Pass 3）
- 重复 ID 不崩溃且 diff 正确
- 无表头列（注释列）从 diff 排除
- header_row > 1 时 ID 列自动检测跳过元信息行
- UTF-16 字节内容解析（按 XML 声明自动解码）

直接运行：python tests/test_differ.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import xml_parser
import xml_differ
from xml_differ import _auto_detect_id_column


RESET = "\033[0m"; RED = "\033[91m"; GREEN = "\033[92m"; CYAN = "\033[96m"

_passed = 0
_failed = 0
_failures = []


def t(name):
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
        return wrapper
    return deco


def section(title):
    print(f"\n{CYAN}── {title} ──{RESET}")


def book(rows):
    """构造 SpreadsheetML 字符串。rows 是 list[tuple]，按 1..n 物理行排布，
    空字符串单元格跳过（用 ss:Index 保持列位置）。"""
    out = [
        '<?xml version="1.0"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="Sheet1"><Table>',
    ]
    for row in rows:
        cells = []
        for i, v in enumerate(row, start=1):
            if v is None or v == "":
                continue
            cells.append(f'<Cell ss:Index="{i}"><Data ss:Type="String">{v}</Data></Cell>')
        out.append("<Row>" + "".join(cells) + "</Row>")
    out.append("</Table></Worksheet></Workbook>")
    return "\n".join(out)


def parse(rows, header_row=1):
    return xml_parser.parse_string(book(rows), header_row=header_row)


HEADER = ("ID", "名称", "数值")


def diff(old_rows, new_rows, header_row=1, id_column=None):
    old = parse(old_rows, header_row=header_row)
    new = parse(new_rows, header_row=header_row)
    return xml_differ.diff_workbooks(old, new, id_column=id_column)


# ── 1. 基础单元格修改 ────────────────────────────────────


@t("修改单元格：精确报告 行/列/旧值/新值，无 added/removed")
def test_modified_cell_precise():
    old = [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    new = [HEADER, ("1001", "甲", "10"), ("1002", "乙", "25"), ("1003", "丙", "30")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert sheet["status"] == "modified"
    assert len(sheet["modified_cells"]) == 1, f"实际 {sheet['modified_cells']}"
    c = sheet["modified_cells"][0]
    assert c["col"] == "C" and c["old"] == "20" and c["new"] == "25"
    assert c["header"] == "数值"
    assert not sheet["added_rows"] and not sheet["removed_rows"]


@t("无变化：summary.has_changes 为 False")
def test_no_changes():
    rows = [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    d = diff(rows, rows)
    assert d["summary"]["has_changes"] is False


# ── 2. 插入 / 删除不级联（Pass 1 ID 匹配） ───────────────


@t("中间插入一行：只有 1 个 added_row，无级联假修改")
def test_insert_no_cascade():
    old = [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    new = [HEADER, ("1001", "甲", "10"), ("1500", "新", "99"),
           ("1002", "乙", "20"), ("1003", "丙", "30")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["added_rows"]) == 1, f"added: {sheet['added_rows']}"
    assert sheet["added_rows"][0]["cells"]["A"] == "1500"
    assert len(sheet["removed_rows"]) == 0
    assert len(sheet["modified_cells"]) == 0, f"级联假修改: {sheet['modified_cells']}"


@t("中间删除一行：只有 1 个 removed_row，无级联假修改")
def test_delete_no_cascade():
    old = [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    new = [HEADER, ("1001", "甲", "10"), ("1003", "丙", "30")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["removed_rows"]) == 1
    assert sheet["removed_rows"][0]["cells"]["A"] == "1002"
    assert len(sheet["added_rows"]) == 0
    assert len(sheet["modified_cells"]) == 0


# ── 3. 无 ID 列：Pass 2 内容哈希 / Pass 3 行号回退 ───────


NO_ID_HEADER = ("名称", "数值")


@t("Pass 2：无可用 ID 列时插入行，内容哈希匹配不产生级联")
def test_pass2_content_hash():
    # 前 3 列值都有重复 → ID 自动检测失败
    old = [NO_ID_HEADER, ("甲", "1"), ("甲", "1"), ("乙", "2"), ("乙", "2")]
    new = [NO_ID_HEADER, ("甲", "1"), ("丙", "9"), ("甲", "1"), ("乙", "2"), ("乙", "2")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["added_rows"]) == 1
    assert sheet["added_rows"][0]["cells"]["A"] == "丙"
    assert len(sheet["removed_rows"]) == 0
    assert len(sheet["modified_cells"]) == 0, f"级联假修改: {sheet['modified_cells']}"


@t("Pass 3：无 ID 且内容变化的行按行号回退匹配为 modified")
def test_pass3_row_number_fallback():
    # 两边 A/B 列都有重复值 → 任何一边都检测不出 ID 列
    old = [NO_ID_HEADER, ("甲", "1"), ("甲", "1"), ("乙", "2"), ("乙", "2")]
    new = [NO_ID_HEADER, ("甲", "1"), ("甲", "9"), ("乙", "2"), ("乙", "2")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["modified_cells"]) == 1, f"实际 {sheet['modified_cells']}"
    c = sheet["modified_cells"][0]
    assert c["col"] == "B" and c["old"] == "1" and c["new"] == "9"
    assert not sheet["added_rows"] and not sheet["removed_rows"]


# ── 4. 重复 ID ───────────────────────────────────────────


@t("重复 ID：不崩溃，修改仍被正确检测（指定 id_column='A'）")
def test_duplicate_ids():
    old = [HEADER, ("1001", "甲", "10"), ("1001", "乙", "20"), ("1002", "丙", "30")]
    new = [HEADER, ("1001", "甲", "10"), ("1001", "乙", "20"), ("1002", "丁", "30")]
    d = diff(old, new, id_column="A")
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["modified_cells"]) == 1, f"实际 {sheet['modified_cells']}"
    c = sheet["modified_cells"][0]
    assert c["col"] == "B" and c["old"] == "丙" and c["new"] == "丁"
    assert not sheet["added_rows"] and not sheet["removed_rows"]


# ── 5. 无表头列过滤 ─────────────────────────────────────


@t("注释列（无表头）变更不进入 diff")
def test_headerless_column_excluded():
    header = ("ID", "名称")  # C 列无表头
    old = [header, ("1001", "甲", "备注1"), ("1002", "乙", "备注2")]
    new = [header, ("1001", "甲", "改了"), ("1002", "乙", "备注2")]
    d = diff(old, new)
    sheet = d["sheets"]["Sheet1"]
    assert sheet["status"] == "unchanged", f"注释列变更不应计入: {sheet['modified_cells']}"
    assert d["summary"]["has_changes"] is False


# ── 6. header_row > 1 ────────────────────────────────────


META_ROWS = [
    ("meta", "meta", "meta"),
    ("meta", "meta", "meta"),
    ("meta", "meta", "meta"),
    ("meta", "meta", "meta"),
]


@t("header_row=5：ID 列检测跳过元信息行 → 返回 'A'")
def test_id_detection_with_header_row():
    rows = META_ROWS + [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    parsed = parse(rows, header_row=5)
    sheet = parsed["sheets"]["Sheet1"]
    assert sheet["header_row"] == 5
    assert _auto_detect_id_column(sheet) == "A", \
        f"实际 {_auto_detect_id_column(sheet)}（元信息行重复值不应破坏唯一性判断）"


@t("header_row=5：中间插入行不级联")
def test_header_row_insert_no_cascade():
    old = META_ROWS + [HEADER, ("1001", "甲", "10"), ("1002", "乙", "20"), ("1003", "丙", "30")]
    new = META_ROWS + [HEADER, ("1001", "甲", "10"), ("1500", "新", "99"),
                       ("1002", "乙", "20"), ("1003", "丙", "30")]
    d = diff(old, new, header_row=5)
    sheet = d["sheets"]["Sheet1"]
    assert len(sheet["added_rows"]) == 1
    assert sheet["added_rows"][0]["cells"]["A"] == "1500"
    assert len(sheet["modified_cells"]) == 0, f"级联假修改: {sheet['modified_cells']}"


# ── 7. 编码 ──────────────────────────────────────────────


@t("UTF-16 字节内容：按 XML 声明自动解码并正常解析")
def test_utf16_bytes():
    content = book([HEADER, ("1001", "中文名", "10")])
    content = content.replace('<?xml version="1.0"?>',
                              '<?xml version="1.0" encoding="UTF-16"?>')
    raw = content.encode("utf-16")
    parsed = xml_parser.parse_string(raw)
    rows = parsed["sheets"]["Sheet1"]["rows"]
    assert rows[1]["cells"]["B"] == "中文名", f"实际 {rows[1]['cells']}"


# ── Main ────────────────────────────────────────────────


def main():
    print(f"{CYAN}xml_differ 测试套件{RESET}")

    section("1. 基础单元格修改")
    test_modified_cell_precise()
    test_no_changes()

    section("2. 插入/删除不级联")
    test_insert_no_cascade()
    test_delete_no_cascade()

    section("3. Pass 2 / Pass 3 匹配")
    test_pass2_content_hash()
    test_pass3_row_number_fallback()

    section("4. 重复 ID")
    test_duplicate_ids()

    section("5. 无表头列过滤")
    test_headerless_column_excluded()

    section("6. header_row > 1")
    test_id_detection_with_header_row()
    test_header_row_insert_no_cascade()

    section("7. 编码")
    test_utf16_bytes()

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
