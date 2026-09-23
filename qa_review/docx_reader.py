"""Read a Word baseline into the same element stream as the markdown reader.

Standard library only. Boxed quotes are paragraphs with a left border (what md2docx.py
writes); headings are recognized by style name or, failing that, by large font size.
"""

import re
import xml.etree.ElementTree as ET
import zipfile

from .elements import Element

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NUM = re.compile(r"^\d+\.\s+")


def _text(el) -> str:
    out = []
    for n in el.iter():
        if n.tag == W + "t":
            out.append(n.text or "")
        elif n.tag == W + "tab":
            out.append(" ")
    return "".join(out)


def _heading_level(p) -> int | None:
    ppr = p.find(W + "pPr")
    if ppr is not None:
        st = ppr.find(W + "pStyle")
        if st is not None:
            m = re.match(r"Heading(\d)", st.get(W + "val", ""))
            if m:
                return int(m.group(1))
    r = p.find(W + "r")
    if r is not None:
        rpr = r.find(W + "rPr")
        if rpr is not None:
            sz = rpr.find(W + "sz")
            if sz is not None:
                size = int(sz.get(W + "val", "0"))
                if size >= 36:
                    return 1
                if size >= 28:
                    return 2
    return None


def _boxed(p) -> bool:
    ppr = p.find(W + "pPr")
    return ppr is not None and ppr.find(W + "pBdr") is not None and \
        ppr.find(W + "pBdr").find(W + "left") is not None


def read_docx(path) -> list[Element]:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("refusing a document that declares entities")
    body = ET.fromstring(xml).find(W + "body")
    els: list[Element] = []
    table = -1
    for child in body:
        if child.tag == W + "p":
            text = _text(child).strip()
            if not text:
                continue
            level = _heading_level(child)
            if level == 1:
                els.append(Element("title", text))
            elif level == 2:
                els.append(Element("section", text))
            elif _boxed(child):
                els.append(Element("quote", text))
            else:
                ppr = child.find(W + "pPr")
                numbered = ppr is not None and ppr.find(W + "numPr") is not None
                if numbered or _NUM.match(text):
                    els.append(Element("condition", _NUM.sub("", text)))
        elif child.tag == W + "tbl":
            table += 1
            body_row = -1
            for tr in child.findall(W + "tr"):
                trpr = tr.find(W + "trPr")
                header = trpr is not None and trpr.find(W + "tblHeader") is not None
                row = -1 if header else (body_row := body_row + 1)
                for col, tc in enumerate(tr.findall(W + "tc")):
                    text = " ".join(_text(p).strip() for p in tc.findall(W + "p")).strip()
                    els.append(Element("header_cell" if header else "cell", text, table, row, col))
    return els


def raw_counts(path) -> dict:
    """A second, simpler pass over the raw XML, independent of read_docx (the count guard).

    Word round-trips a saved file with rsid/paraId attributes on nearly every element
    (`<w:p w:rsidR="00A2"...>`), so every tag here is matched by its start (`<w:p\\b`) rather
    than a bare, attribute-free open tag -- a guard that only matches unattributed XML silently
    counts 0 against a real Word document and never actually verifies anything (KTD-like: a
    guard nobody can trip is the same as no guard)."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    boxed = 0
    conditions = 0
    outside = re.sub(r"<w:tbl\b[^>]*>.*?</w:tbl>", "", xml, flags=re.S)
    for p in re.findall(r"<w:p\b[^>]*>.*?</w:p>", outside, flags=re.S):
        text = "".join(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", p, flags=re.S)).strip()
        if re.search(r"<w:pBdr\b", p) and re.search(r"<w:left\b", p):
            boxed += 1
        elif re.match(r"\d+\.\s", text):
            conditions += 1
    cells = 0
    for tr in re.findall(r"<w:tr\b[^>]*>.*?</w:tr>", xml, flags=re.S):
        if not re.search(r"<w:tblHeader\b", tr):
            cells += len(re.findall(r"<w:tc\b", tr))
    return {"verbatim": boxed + cells, "conditions": conditions}
