"""
Excel XML Spreadsheet 2003 parser.
Extracts pure cell data from SpreadsheetML format, ignoring all
metadata noise (styles, view state, window size, etc.).
"""
import xml.etree.ElementTree as ET
import os
import time
from typing import Optional

NS = {
    'ss': 'urn:schemas-microsoft-com:office:spreadsheet',
    'o': 'urn:schemas-microsoft-com:office:office',
    'x': 'urn:schemas-microsoft-com:office:excel',
    'html': 'http://www.w3.org/TR/REC-html40',
}

WORKSHEET_TAG = f'{{{NS["ss"]}}}Worksheet'
TABLE_TAG = f'{{{NS["ss"]}}}Table'
ROW_TAG = f'{{{NS["ss"]}}}Row'
CELL_TAG = f'{{{NS["ss"]}}}Cell'
DATA_TAG = f'{{{NS["ss"]}}}Data'
COMMENT_TAG = f'{{{NS["ss"]}}}Comment'

SS_NAME = f'{{{NS["ss"]}}}Name'
SS_INDEX = f'{{{NS["ss"]}}}Index'
SS_TYPE = f'{{{NS["ss"]}}}Type'
SS_MERGE_ACROSS = f'{{{NS["ss"]}}}MergeAcross'
SS_MERGE_DOWN = f'{{{NS["ss"]}}}MergeDown'
SS_HREF = f'{{{NS["ss"]}}}HRef'
SS_FORMULA = f'{{{NS["ss"]}}}Formula'


def col_to_letter(n: int) -> str:
    """Convert 1-based column number to Excel-style letter (1->A, 27->AA)."""
    result = ""
    while n > 0:
        n -= 1
        result = chr(65 + n % 26) + result
        n //= 26
    return result


def letter_to_col(s: str) -> int:
    """Convert Excel-style letter to 1-based column number (A->1, AA->27)."""
    n = 0
    for c in s.upper():
        n = n * 26 + (ord(c) - 64)
    return n


def _get_text_recursive(el) -> str:
    """Get all text content from an element recursively (handles mixed content)."""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(_get_text_recursive(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _extract_comment_text(cell_el) -> Optional[str]:
    """Extract comment/annotation text from a Cell element."""
    comment = cell_el.find(COMMENT_TAG)
    if comment is None:
        return None
    return _get_text_recursive(comment).strip() or None


def parse_workbook(source) -> dict:
    """
    Parse an Excel XML Spreadsheet file or string.

    Args:
        source: file path (str) or XML string content

    Returns:
        dict with structure:
        {
            "sheets": {
                "SheetName": {
                    "headers": ["col1", "col2", ...],
                    "header_comments": {"A": "comment text", ...},
                    "rows": [
                        {"_row": 1, "cells": {"A": "val", "B": "val", ...}},
                        ...
                    ],
                    "row_count": int,
                    "col_count": int,
                }
            },
            "_parse_ms": float,
        }
    """
    t0 = time.perf_counter()

    if os.path.isfile(source) if isinstance(source, str) and len(source) < 500 else False:
        tree = ET.parse(source)
        root = tree.getroot()
    else:
        if isinstance(source, bytes):
            root = ET.fromstring(source)
        else:
            root = ET.fromstring(source.encode('utf-8') if isinstance(source, str) else source)

    result = {"sheets": {}}

    for ws in root.iter(WORKSHEET_TAG):
        sheet_name = ws.get(SS_NAME, "Unknown")
        table = ws.find(TABLE_TAG)
        if table is None:
            result["sheets"][sheet_name] = {
                "headers": [], "header_comments": {},
                "rows": [], "row_count": 0, "col_count": 0
            }
            continue

        rows_data = []
        max_col = 0
        row_idx = 0

        for row_el in table.findall(ROW_TAG):
            row_idx_attr = row_el.get(SS_INDEX)
            if row_idx_attr:
                row_idx = int(row_idx_attr)
            else:
                row_idx += 1

            col_idx = 0
            cells = {}
            comments = {}

            for cell_el in row_el.findall(CELL_TAG):
                col_idx_attr = cell_el.get(SS_INDEX)
                if col_idx_attr:
                    col_idx = int(col_idx_attr)
                else:
                    col_idx += 1

                data_el = cell_el.find(DATA_TAG)
                if data_el is not None:
                    value = _get_text_recursive(data_el).strip()
                else:
                    value = ""

                col_key = col_to_letter(col_idx)
                if value:
                    cells[col_key] = value
                    if col_idx > max_col:
                        max_col = col_idx

                comment_text = _extract_comment_text(cell_el)
                if comment_text:
                    comments[col_key] = comment_text

                merge = cell_el.get(SS_MERGE_ACROSS)
                if merge:
                    col_idx += int(merge)

            if cells:
                row_entry = {"_row": row_idx, "cells": cells}
                if comments:
                    row_entry["_comments"] = comments
                rows_data.append(row_entry)

        headers = []
        header_comments = {}
        if rows_data:
            first_row = rows_data[0]
            for c in range(1, max_col + 1):
                ck = col_to_letter(c)
                headers.append(first_row["cells"].get(ck, ""))
            while headers and not headers[-1]:
                headers.pop()
            header_comments = first_row.get("_comments", {})

        result["sheets"][sheet_name] = {
            "headers": headers,
            "header_comments": header_comments,
            "rows": rows_data,
            "row_count": len(rows_data),
            "col_count": max_col,
        }

    result["_parse_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


def parse_file(filepath: str) -> dict:
    """Convenience wrapper: parse a file and include file metadata."""
    data = parse_workbook(filepath)
    data["file"] = os.path.basename(filepath)
    data["file_path"] = filepath
    data["file_size"] = os.path.getsize(filepath)
    return data


def parse_string(content: str) -> dict:
    """Parse XML content from a string (e.g. from svn cat)."""
    return parse_workbook(content)
