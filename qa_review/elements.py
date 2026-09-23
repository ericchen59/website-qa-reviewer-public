"""The neutral element stream both baseline readers produce."""

from dataclasses import dataclass


@dataclass
class Element:
    kind: str            # section | title | quote | cell | header_cell | condition
    text: str
    table: int | None = None
    row: int | None = None     # body rows count from 0; the header row is -1
    col: int | None = None
