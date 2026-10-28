"""
fetch.py -- d3-fetch's csv()/tsv()/json() plus d3-dsv's autoType(), for
local files. Stdlib only (csv, json, datetime), no bpy.

    import d3blender as d3
    rows = d3.csv('sales.csv')          # [{'month': 'Jan', 'revenue': 12.5, ...}, ...]
    rows.columns                         # ['month', 'revenue', ...]

Differences from d3, on purpose:
  - Typing is on by default (`typed=True`), since that's what d3 code
    almost always asks for (`d3.csv(url, d3.autoType)`). Pass
    `typed=False` for raw strings.
  - Synchronous, local paths only -- there's no event loop to hand a
    Promise to inside a Blender script. Blender-relative paths ("//data.csv")
    must be resolved by the caller with `bpy.path.abspath()` first (this
    module deliberately doesn't import bpy).
"""

import csv as _csv
import datetime as _datetime
import json as _json
import re as _re

_INT_RE = _re.compile(r'^[-+]?\d+$')
_FLOAT_RE = _re.compile(r'^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$')
_DATE_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DATETIME_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')


class Rows(list):
    """A plain list of row dicts, plus `.columns` (header order), like the
    array d3.csv() resolves to."""

    columns = ()


def auto_type_value(value):
    """d3.autoType for one string: '' -> None, 'true'/'false' -> bool,
    'NaN' -> float('nan'), integers -> int, other numbers -> float,
    'YYYY-MM-DD' -> datetime.date, ISO date-times -> datetime.datetime
    (timezone-aware if the string carries an offset or 'Z'). Anything else
    stays a string. Surrounding whitespace is ignored, as in d3.

    One deliberate split from d3, which only has one number type: whole
    numbers become Python ints, so ids and counts stay ints. Leading
    zeros are dropped either way ('007' -> 7), same as d3 -- read with
    typed=False, or a row function, if a column is an identifier."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return None
    low = s.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if s == 'NaN':
        return float('nan')
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    if _DATE_RE.match(s):
        try:
            return _datetime.date.fromisoformat(s)
        except ValueError:
            return value
    if _DATETIME_RE.match(s):
        try:
            return _datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
        except ValueError:
            return value
    return value


def auto_type(row):
    """d3.autoType: apply auto_type_value() to every field of a row dict.
    Returns a new dict."""
    return {k: auto_type_value(v) for k, v in row.items()}


def _call_row(row_fn, d, i, columns):
    """d3's row-conversion callback is `(d, i, columns)`; accept any
    leading subset of those, by parameter count."""
    import inspect
    try:
        n = len(inspect.signature(row_fn).parameters)
    except (TypeError, ValueError):
        n = 1
    return row_fn(*(d, i, columns)[:max(1, min(n, 3))])


def dsv(path, delimiter=',', row=None, typed=True, encoding='utf-8-sig'):
    """Parse a delimited text file into Rows (list of dicts + `.columns`).

    `row` is d3's row-conversion function: called with the (already
    typed, unless typed=False) row dict -- or `(d, i)` / `(d, i, columns)`
    if it takes more parameters -- and its return value is kept; return
    None to drop the row. `encoding` defaults to 'utf-8-sig' so an Excel
    byte-order mark doesn't end up glued to the first column name."""
    with open(path, newline='', encoding=encoding) as fh:
        reader = _csv.DictReader(fh, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        out = Rows()
        out.columns = columns
        for i, raw in enumerate(reader):
            d = auto_type(raw) if typed else dict(raw)
            if row is not None:
                d = _call_row(row, d, i, columns)
                if d is None:
                    continue
            out.append(d)
    return out


def csv(path, row=None, typed=True, encoding='utf-8-sig'):
    """d3.csv (+ d3.autoType by default) -- see dsv()."""
    return dsv(path, ',', row=row, typed=typed, encoding=encoding)


def tsv(path, row=None, typed=True, encoding='utf-8-sig'):
    """d3.tsv (+ d3.autoType by default) -- see dsv()."""
    return dsv(path, '\t', row=row, typed=typed, encoding=encoding)


def json(path, encoding='utf-8'):
    """d3.json for a local file: just the parsed JSON, no typing (JSON
    already has numbers/booleans/null)."""
    with open(path, encoding=encoding) as fh:
        return _json.load(fh)
