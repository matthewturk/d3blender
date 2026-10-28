import datetime
import math

import d3blender as d3
from d3blender.fetch import auto_type_value


def test_auto_type_value_rules():
    assert auto_type_value('') is None
    assert auto_type_value('  ') is None
    assert auto_type_value('true') is True
    assert auto_type_value('FALSE') is False
    assert auto_type_value('42') == 42 and isinstance(auto_type_value('42'), int)
    assert auto_type_value('-3.5e2') == -350.0
    assert auto_type_value('.5') == 0.5
    assert math.isnan(auto_type_value('NaN'))
    assert auto_type_value('2026-03-01') == datetime.date(2026, 3, 1)
    assert auto_type_value('2026-03-01T12:30:00') == datetime.datetime(2026, 3, 1, 12, 30)
    assert auto_type_value('2026-03-01T12:30:00Z').tzinfo is not None
    assert auto_type_value('Jan') == 'Jan'
    assert auto_type_value('2026-13-45') == '2026-13-45'


def test_csv_types_rows_and_keeps_columns(tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('﻿name,value,ok,when\nA,1,true,2026-01-02\nB,,false,\n', encoding='utf-8')

    rows = d3.csv(path)

    assert rows.columns == ['name', 'value', 'ok', 'when']
    assert rows == [
        {'name': 'A', 'value': 1, 'ok': True, 'when': datetime.date(2026, 1, 2)},
        {'name': 'B', 'value': None, 'ok': False, 'when': None},
    ]


def test_csv_untyped_and_row_function(tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('id,v\n007,1\n008,2\n')

    assert d3.csv(path, typed=False)[0] == {'id': '007', 'v': '1'}
    rows = d3.csv(path, row=lambda d, i: None if i == 0 else {**d, 'i': i})
    assert rows == [{'id': 8, 'v': 2, 'i': 1}]


def test_tsv_and_json(tmp_path):
    (tmp_path / 'd.tsv').write_text('a\tb\n1\tx\n')
    (tmp_path / 'd.json').write_text('{"a": [1, 2]}')
    assert d3.tsv(tmp_path / 'd.tsv') == [{'a': 1, 'b': 'x'}]
    assert d3.json(tmp_path / 'd.json') == {'a': [1, 2]}
