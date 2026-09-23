// Walks the rendered DOM and returns one record per text block, with tri-state visibility and
// page-coordinate boxes. A block is the joined text of one block-level container: inline
// elements (links, strong, spans) merge into their nearest non-inline ancestor.
(vendored) => {
  const sx = window.scrollX, sy = window.scrollY;
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "TITLE"]);
  const inlineDisplay = (d) => d === "inline" || d === "contents" || d.startsWith("ruby");
  const collapse = (s) => s.replace(/\s+/g, " ").trim();
  const union = (rs) => {
    if (!rs.length) return null;
    const l = Math.min(...rs.map((r) => r.left)), t = Math.min(...rs.map((r) => r.top));
    const rr = Math.max(...rs.map((r) => r.right)), b = Math.max(...rs.map((r) => r.bottom));
    return [l + sx, t + sy, rr - l, b - t];
  };
  const pathOf = (el) => {
    const parts = [];
    for (let e = el; e && e.nodeType === 1 && e !== document.documentElement; e = e.parentElement) {
      const sibs = e.parentElement ? Array.from(e.parentElement.children).filter((c) => c.tagName === e.tagName) : [e];
      parts.unshift(e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (sibs.length > 1 ? ":" + (sibs.indexOf(e) + 1) : ""));
    }
    return parts.join(">");
  };

  const groups = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.nodeValue.trim()) continue;
    const pe = n.parentElement;
    if (!pe || SKIP.has(pe.tagName)) continue;
    let c = pe;
    while (c && c !== document.body && inlineDisplay(getComputedStyle(c).display)) c = c.parentElement;
    if (!c) continue;
    if (!groups.has(c)) groups.set(c, []);
    groups.get(c).push(n);
  }

  const tables = Array.from(document.querySelectorAll("table"));
  const tableIndex = (t) => tables.indexOf(t);
  const isHeaderRow = (tr) => tr.cells.length > 0 && Array.from(tr.cells).every((c) => c.tagName === "TH");
  const tableCoords = (c) => {
    const cell = c.closest("td,th");
    if (!cell) return null;
    const tr = cell.parentElement, table = tr.closest("table");
    if (!table) return null;
    let row = -1;
    if (!isHeaderRow(tr)) {
      row = 0;
      for (const r of table.rows) { if (r === tr) break; if (!isHeaderRow(r)) row++; }
    }
    return { table: tableIndex(table), row, col: cell.cellIndex };
  };

  const visibleAncestorBox = (c) => {
    const det = c.closest("details");
    if (det && !det.open) {
      const sum = det.querySelector("summary");
      const r = (sum || det).getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return [r.left + sx, r.top + sy, r.width, r.height];
    }
    for (let a = c.parentElement; a; a = a.parentElement) {
      const r = a.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && getComputedStyle(a).display !== "none") return [r.left + sx, r.top + sy, r.width, r.height];
    }
    return null;
  };

  const out = [{ kind: "title", text: collapse(document.title || ""), path: "head>title", visible: "visible",
                 bbox: null, anchor_bbox: null, table: null, tag: "title" }];
  for (const [c, nodes] of groups) {
    const rects = [];
    for (const tn of nodes) {
      const r = document.createRange();
      r.selectNodeContents(tn);
      for (const q of r.getClientRects()) if (q.width > 0 && q.height > 0) rects.push(q);
    }
    const text = collapse(nodes.map((x) => x.nodeValue).join(""));
    if (!text) continue;
    let hidden = rects.length === 0;
    let opacity = 1, ariaHidden = false;
    for (let a = nodes[0].parentElement; a; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (a === nodes[0].parentElement && cs.visibility !== "visible") hidden = true;
      if (cs.display === "none") hidden = true;
      opacity *= parseFloat(cs.opacity);
      if (a.getAttribute("aria-hidden") === "true") ariaHidden = true;
      if (a.hasAttribute("hidden")) hidden = true;
      if (a !== document.body && a !== document.documentElement && (cs.overflowX !== "visible" || cs.overflowY !== "visible") && rects.length) {
        const ar = a.getBoundingClientRect();
        const u = union(rects);
        const ux = u[0] - sx, uy = u[1] - sy;
        if (ar.height < 1 || ar.width < 1 || ux >= ar.right || ux + u[2] <= ar.left || uy >= ar.bottom || uy + u[3] <= ar.top) hidden = true;
      }
    }
    if (opacity === 0) hidden = true;
    if (rects.length && rects.every((r) => r.right + sx <= 0)) hidden = true;
    const visible = hidden ? "hidden" : (ariaHidden || !vendored ? "undetermined" : "visible");
    const bbox = union(rects);
    out.push({ kind: "block", text, path: pathOf(c), visible, bbox,
               anchor_bbox: visible === "hidden" ? (visibleAncestorBox(c) || bbox) : bbox,
               table: tableCoords(c), tag: c.tagName.toLowerCase() });
  }
  return out;
}
