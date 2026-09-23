import http.server
import pathlib
import re
import tempfile
import threading
import unittest

from qa_review.render import assign_numbers
from qa_review.schema import ChecklistItem, Finding, FindingsRecord
from tests.test_visibility import BROWSER

if BROWSER:
    from qa_review.capture import offline_page, render_snapshot
    from qa_review.overlay import build_overlay

PAGE = """<html><head><title>T</title></head><body>
<h1>Headline block</h1><p>Second paragraph block</p><p>Third paragraph block</p>
<details><summary>Read more</summary><p>Legal text hidden</p></details></body></html>"""


def setup(html=PAGE, vendored=True):
    d = pathlib.Path(tempfile.mkdtemp())
    snap = d / "snapshot.html"
    snap.write_text(html, encoding="utf-8")
    blocks, _ = render_snapshot(snap, vendored, screenshot=False)
    return d, snap, blocks


def idx(blocks, text):
    return next(b.index for b in blocks if text in b.text)


def record(blocks, vendored=True, quote="Second paragraph block"):
    fs = [Finding(item_id="f.1", verdict="FAIL", approved_text="a", quote=quote, block=idx(blocks, "Second")),
          Finding(item_id="n.1", verdict="NOT FOUND ON PAGE", approved_text="missing copy", quote=""),
          Finding(item_id="o.1", verdict="OPEN — PAGE INCONSISTENT", approved_text="year", quote="Headline block",
                  block=idx(blocks, "Headline")),
          Finding(item_id="h.1", verdict="FAIL", approved_text="legal", quote="Legal text hidden", block=idx(blocks, "Legal")),
          Finding(item_id="e.1", verdict="WARN", approved_text="v", quote="Third paragraph block",
                  block=idx(blocks, "Third"), check_by_eye=True)]
    rec = FindingsRecord(run_id="r", baseline={"slug": "b", "hash": "h" * 12, "path": "b.md"},
                         page={"key": "p", "kind": "file", "snapshot": "snapshot.html", "styles_vendored": vendored},
                         findings=fs, items=[ChecklistItem(id=f.item_id, section="s", type="verbatim", text=f.approved_text) for f in fs])
    assign_numbers(rec)
    return rec


@unittest.skipUnless(BROWSER, "Playwright and Chrome are required")
class OverlayTests(unittest.TestCase):
    def test_badges_use_the_numbers_on_the_record_and_skip_findings_with_no_location(self):    # AE5
        d, snap, blocks = setup()
        rec = record(blocks)
        out = build_overlay(rec, blocks, snap, d)
        placed = {p["number"] for p in out["placed"]}
        numbers = {f.item_id: f.number for f in rec.findings}
        self.assertNotIn(numbers["n.1"], placed)
        self.assertEqual(placed, {numbers[k] for k in ("f.1", "o.1", "h.1", "e.1")})
        html = out["html"].read_text(encoding="utf-8")
        self.assertIn("missing copy", html)
        self.assertIn("no location on the page", html)
        self.assertTrue(out["png"].read_bytes().startswith(b"\x89PNG"))

    def test_each_severity_has_its_own_color_and_a_text_label(self):
        d, snap, blocks = setup()
        out = build_overlay(record(blocks), blocks, snap, d)
        by = {p["label"]: p["color"] for p in out["placed"]}
        self.assertEqual(set(by), {"FAIL", "OPEN", "CHECK"})
        self.assertEqual(len(set(by.values())), 3)

    def test_findings_sharing_one_box_get_stacked_labels_so_none_is_covered(self):
        d, snap, blocks = setup()
        rec = record(blocks)
        hidden = idx(blocks, "Legal")
        rec.findings.append(Finding(item_id="h.2", verdict="FAIL", approved_text="legal2", quote="Legal text hidden", block=hidden))
        rec.items.append(ChecklistItem(id="h.2", section="s", type="verbatim", text="legal2"))
        assign_numbers(rec)
        out = build_overlay(rec, blocks, snap, d)
        shared = sorted(p["stack"] for p in out["placed"] if p["item_id"] in ("h.1", "h.2"))
        self.assertEqual(shared, [0, 1])

    def test_a_hidden_block_anchors_to_its_visible_toggle(self):
        d, snap, blocks = setup()
        rec = record(blocks)
        out = build_overlay(rec, blocks, snap, d)
        hidden = next(b for b in blocks if "Legal" in b.text)
        placed = next(p for p in out["placed"] if p["item_id"] == "h.1")
        self.assertEqual(hidden.visible, "hidden")
        self.assertEqual([round(v) for v in placed["box"]], [round(v) for v in hidden.anchor_bbox])

    def test_unvendored_snapshot_has_no_screenshot_and_a_notice(self):
        d, snap, blocks = setup(vendored=False)
        rec = record(blocks, vendored=False)
        out = build_overlay(rec, blocks, snap, d)
        self.assertIsNone(out["png"])
        self.assertEqual(out["placed"], [])
        self.assertIn("styles were not vendored", out["html"].read_text(encoding="utf-8"))

    def test_report_html_is_self_contained_and_escapes_page_text(self):
        d, snap, blocks = setup()
        rec = record(blocks, quote='<script>alert(1)</script><img src=x onerror=alert(2)>')
        html = build_overlay(rec, blocks, snap, d)["html"].read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertEqual(len(re.findall(r"<script", html)), 1)         # only the report's own script
        self.assertIsNone(re.search(r"(src|href)=[\"']https?://", html))
        self.assertIn('src="data:image/png;base64,', html)

    def test_the_injected_script_actually_draws_one_marker_per_placed_finding(self):
        # testing:test_overlay.py:54 -- every existing assertion is against out["placed"],
        # which build_overlay computes from the record BEFORE rendering, and the PNG
        # assertion elsewhere only checks an 8-byte header. If the injected script drew
        # nothing, drew the wrong count, or drew one for the NOT FOUND item, every overlay
        # test would still pass. Re-runs the same INJECT script the way _render does and
        # inspects the resulting DOM directly.
        from qa_review.overlay import INJECT

        d, snap, blocks = setup()
        rec = record(blocks)
        out = build_overlay(rec, blocks, snap, d)
        with offline_page(snap) as page:
            page.evaluate(INJECT, [{k: e[k] for k in ("number", "label", "color", "box", "stack")}
                                   for e in out["placed"]])
            labels = page.evaluate(
                "() => Array.from(document.querySelectorAll('body > div[style*=\"2147483646\"] > span'))"
                ".map(s => s.textContent)")
        self.assertEqual(len(labels), len(out["placed"]))
        for p in out["placed"]:
            self.assertIn(f'{p["number"]} {p["label"]}', labels)
        numbers = {f.item_id: f.number for f in rec.findings}
        self.assertFalse(any(label.startswith(f'{numbers["n.1"]} ') for label in labels))   # NOT FOUND: never drawn

    def test_the_annotated_screenshot_actually_differs_from_a_plain_render(self):
        d, snap, blocks = setup()
        rec = record(blocks)
        _, plain_png = render_snapshot(snap, True, screenshot=True)
        out = build_overlay(rec, blocks, snap, d)
        self.assertNotEqual(out["png"].read_bytes(), plain_png)

    def test_overlay_rerender_blocks_the_network(self):
        hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            html = PAGE.replace("<h1>", f'<img src="http://127.0.0.1:{srv.server_port}/x.png"><h1>')
            d, snap, blocks = setup(html)
            build_overlay(record(blocks), blocks, snap, d)
        finally:
            srv.shutdown()
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
