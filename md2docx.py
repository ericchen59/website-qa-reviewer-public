#!/usr/bin/env python3
"""Convert the ground-truth Markdown baseline into a real .docx with native Word tables.

textutil flattens <table> into tab runs, which destroys the spec comparison grid,
so we emit OOXML directly. Stdlib only.
"""
import re, sys, zipfile

RPR_ORDER = ['rFonts', 'b', 'i', 'strike', 'color', 'sz', 'szCs', 'shd']


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def rpr(props):
    """Emit <w:rPr> with children in schema order. Word rejects any other sequence."""
    parts = [f'<w:{t}{props[t]}/>' for t in RPR_ORDER if t in props]
    return f'<w:rPr>{"".join(parts)}</w:rPr>' if parts else ''


def runs(text, base=None):
    """Inline markdown -> OOXML runs, inheriting `base` run properties."""
    base = base or {}
    tok = re.split(r'(\*\*.+?\*\*|`.+?`|~~.+?~~|(?<!\w)\*(?!\*).+?(?<!\*)\*(?!\w))', text)
    out = []
    for t in tok:
        if not t:
            continue
        p = dict(base)
        if t.startswith('**') and t.endswith('**') and len(t) > 4:
            t, p['b'] = t[2:-2], ''
        elif t.startswith('~~') and t.endswith('~~') and len(t) > 4:
            t, p['strike'] = t[2:-2], ''
        elif t.startswith('`') and t.endswith('`') and len(t) > 2:
            t = t[1:-1]
            p['rFonts'] = ' w:ascii="Consolas" w:hAnsi="Consolas"'
            p['shd'] = ' w:val="clear" w:fill="EFEFEF"'
        elif t.startswith('*') and t.endswith('*') and len(t) > 2:
            t, p['i'] = t[1:-1], ''
        t = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1', t).replace('&nbsp;', ' ')
        out.append(f'<w:r>{rpr(p)}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    return ''.join(out) or f'<w:r>{rpr(base)}<w:t/></w:r>'


def para(text='', size=22, bold=False, before=60, after=60, shade=None,
         bar=False, ind=0, color=None, align=None, serif=False):
    base = {'sz': f' w:val="{size}"', 'szCs': f' w:val="{size}"'}
    if bold:
        base['b'] = ''
    if color:
        base['color'] = f' w:val="{color}"'
    if serif:
        base['rFonts'] = ' w:ascii="Georgia" w:hAnsi="Georgia"'
    pr = '<w:pPr>'
    if shade:
        pr += f'<w:shd w:val="clear" w:fill="{shade}"/>'
    if bar:
        pr += '<w:pBdr><w:left w:val="single" w:sz="24" w:space="8" w:color="1A1A1A"/></w:pBdr>'
    if ind:
        pr += f'<w:ind w:left="{ind}"/>'
    if align:
        pr += f'<w:jc w:val="{align}"/>'
    pr += f'<w:spacing w:before="{before}" w:after="{after}" w:line="264" w:lineRule="auto"/>'
    pr += rpr(base) + '</w:pPr>'
    return f'<w:p>{pr}{runs(text, base) if text else rpr(base).join(("<w:r>", "<w:t/></w:r>"))}</w:p>'


def cell(text, w, head=False, alt=False):
    fill = '1A1A1A' if head else ('F7F7F7' if alt else 'FFFFFF')
    col = 'FFFFFF' if head else None
    p = para(text, size=19, bold=head, before=30, after=30, color=col)
    return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>'
            f'<w:shd w:val="clear" w:fill="{fill}"/>'
            f'<w:tcMar><w:top w:w="60" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/>'
            f'<w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tcMar>'
            f'<w:vAlign w:val="center"/></w:tcPr>{p}</w:tc>')

def table(rows):
    ncol = max(len(r) for r in rows)
    total = 9360
    w = total // ncol
    b = ('<w:tblBorders>' + ''.join(
        f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
        for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>')
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/>{b}'
           f'<w:tblLayout w:type="fixed"/></w:tblPr>'
           f'<w:tblGrid>{"".join(f"<w:gridCol w:w={chr(34)}{w}{chr(34)}/>" for _ in range(ncol))}</w:tblGrid>']
    for ri, r in enumerate(rows):
        r = list(r) + [''] * (ncol - len(r))
        tr = ''.join(cell(c, w, head=(ri == 0), alt=(ri % 2 == 0)) for c in r)
        hdr = '<w:trPr><w:tblHeader/></w:trPr>' if ri == 0 else ''
        out.append(f'<w:tr>{hdr}{tr}</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)

def convert(md):
    lines = md.split('\n')
    body, i = [], 0
    while i < len(lines):
        l = lines[i]
        if re.match(r'^\|.*\|$', l) and i + 1 < len(lines) and re.match(r'^\|[\s:|-]+\|$', lines[i + 1]):
            rows = [[c.strip() for c in l.strip('|').split('|')]]
            i += 2
            while i < len(lines) and re.match(r'^\|.*\|$', lines[i]):
                rows.append([c.strip() for c in lines[i].strip('|').split('|')])
                i += 1
            body.append(table(rows))
            body.append(para(before=0, after=80))
            continue
        if l.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].startswith('>'):
                buf.append(lines[i].lstrip('>').strip())
                i += 1
            buf = [b for b in buf if b]
            for n, b in enumerate(buf):
                body.append(para(b, size=22, shade='F2F2F2', bar=True, ind=180,
                                 before=60 if n == 0 else 0,
                                 after=60 if n == len(buf) - 1 else 0, serif=True))
            continue
        m = re.match(r'^(#{1,6}) (.*)', l)
        if m:
            n = len(m.group(1))
            sz = {1: 40, 2: 32, 3: 26, 4: 23}.get(n, 22)
            body.append(para(m.group(2), size=sz, bold=True, before=260 if n <= 2 else 200, after=90))
            i += 1
            continue
        if re.match(r'^---+$', l):
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="6" '
                        'w:color="C8C8C8"/></w:pBdr><w:spacing w:before="80" w:after="80"/>'
                        '</w:pPr><w:r><w:t/></w:r></w:p>')
            i += 1
            continue
        m = re.match(r'^\s*[-*] (.*)', l)
        if m:
            while i < len(lines) and re.match(r'^\s*[-*] (.*)', lines[i]):
                body.append(para('•  ' + re.match(r'^\s*[-*] (.*)', lines[i]).group(1),
                                 ind=360, before=20, after=20))
                i += 1
            continue
        m = re.match(r'^\s*(\d+)\. (.*)', l)
        if m:
            while i < len(lines) and re.match(r'^\s*(\d+)\. (.*)', lines[i]):
                mm = re.match(r'^\s*(\d+)\. (.*)', lines[i])
                body.append(para(f'{mm.group(1)}.  {mm.group(2)}', ind=360, before=20, after=20))
                i += 1
            continue
        if l.strip():
            body.append(para(l))
        i += 1
    return ''.join(body)

def validate(doc_xml):
    """Word rejects out-of-order or duplicated <w:rPr> children with 'unreadable content'.
    Neither minidom nor textutil catches this, so assert it explicitly."""
    for m in re.finditer(r'<w:rPr>(.*?)</w:rPr>', doc_xml, re.S):
        tags = re.findall(r'<w:(\w+)', m.group(1))
        if len(tags) != len(set(tags)):
            raise AssertionError(f'duplicate run properties: {tags}')
        if tags != sorted(set(tags), key=RPR_ORDER.index):
            raise AssertionError(f'run properties out of schema order: {tags}')


def build(md_path, out_path):
    body = convert(open(md_path, encoding='utf-8').read())
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{body}'
           '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
           '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/></w:sectPr>'
           '</w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
              '<w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="1A1A1A"/>'
              '</w:rPr></w:rPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
              '<w:name w:val="Normal"/></w:style></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')
    validate(doc)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/_rels/document.xml.rels', drels)
        z.writestr('word/styles.xml', styles)
        z.writestr('word/document.xml', doc)

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
    print('wrote', sys.argv[2])
