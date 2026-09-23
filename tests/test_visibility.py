import http.server
import pathlib
import tempfile
import threading
import unittest

from tests.support import ROOT

try:
    from qa_review.capture import render_snapshot
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _p.chromium.launch(channel="chrome", headless=True).close()
    BROWSER = True
except Exception:          # Playwright or Chrome missing: browser tests skip cleanly
    BROWSER = False

PAGES = ROOT / "tests" / "data" / "pages"


def render(html: str, vendored=True, screenshot=False):
    d = pathlib.Path(tempfile.mkdtemp())
    f = d / "s.html"
    f.write_text(html, encoding="utf-8")
    return render_snapshot(f, vendored, screenshot)


def block(blocks, text):
    hits = [b for b in blocks if text in b.text]
    assert hits, f"no block containing {text!r}: {[b.text for b in blocks]}"
    return hits[0]


@unittest.skipUnless(BROWSER, "Playwright and Chrome are required")
class VisibilityTests(unittest.TestCase):
    def test_closed_details_hidden_open_visible_with_summary_anchor(self):
        blocks, _ = render("<body><details><summary>Read more</summary><p>Legal text here</p></details>"
                           "<details open><summary>Open</summary><p>Shown text</p></details></body>")
        closed = block(blocks, "Legal text here")
        self.assertEqual(closed.visible, "hidden")
        self.assertIsNotNone(closed.anchor_bbox)            # the "Read more" toggle
        self.assertEqual(block(blocks, "Shown text").visible, "visible")

    def test_common_hiding_patterns_are_hidden(self):
        html = """<body>
        <p style="display:none">A-none</p>
        <p style="visibility:hidden">B-vis</p>
        <p style="opacity:0">C-opacity</p>
        <p style="text-indent:-9999px">D-indent</p>
        <div style="max-height:0;overflow:hidden"><p>E-clipped</p></div>
        <div style="height:40px;overflow:hidden"><p style="margin-top:200px">F-outside</p></div>
        <p>G-plain</p></body>"""
        blocks, _ = render(html)
        for t in ("A-none", "B-vis", "C-opacity", "D-indent", "E-clipped", "F-outside"):
            self.assertEqual(block(blocks, t).visible, "hidden", t)
        self.assertEqual(block(blocks, "G-plain").visible, "visible")

    def test_aria_hidden_but_visible_by_style_is_undetermined(self):
        blocks, _ = render('<body><div aria-hidden="true"><p>Tab panel copy</p></div></body>')
        self.assertEqual(block(blocks, "Tab panel copy").visible, "undetermined")

    def test_plain_paragraph_is_visible_with_a_box_inside_the_viewport(self):
        blocks, _ = render("<body><p>Hello world</p></body>")
        b = block(blocks, "Hello world")
        self.assertEqual(b.visible, "visible")
        x, y, w, h = b.bbox
        self.assertGreater(w, 0)
        self.assertLessEqual(x + w, 1440)

    def test_unvendored_snapshot_visible_looking_becomes_undetermined_hidden_stays_hidden(self):
        blocks, _ = render("<body><p>Looks fine</p><p style='display:none'>Nope</p></body>", vendored=False)
        self.assertEqual(block(blocks, "Looks fine").visible, "undetermined")
        self.assertEqual(block(blocks, "Nope").visible, "hidden")

    def test_title_is_a_block_without_a_box(self):
        blocks, _ = render("<html><head><title>My Tab</title></head><body><p>x</p></body></html>")
        t = blocks[0]
        self.assertEqual((t.kind, t.text, t.bbox), ("title", "My Tab", None))

    def test_breadcrumb_is_one_block_and_bold_label_is_one_cell_block(self):
        html = (PAGES / "breadcrumb_table.html").read_text(encoding="utf-8")
        blocks, _ = render(html)
        crumb = block(blocks, "You are here")
        self.assertIn("Home » Widget Deluxe 2026", crumb.text)
        label = block(blocks, "Price*")
        self.assertEqual(label.text, "Price*")
        self.assertEqual(label.table, {"table": 0, "row": 0, "col": 1})
        self.assertEqual(block(blocks, "$20").table, {"table": 0, "row": 0, "col": 2})
        self.assertEqual(block(blocks, "Weight").table, {"table": 0, "row": 1, "col": 1})
        self.assertEqual(block(blocks, "VS").table, {"table": 0, "row": -1, "col": 1})

    def test_remote_image_reference_triggers_no_outbound_request(self):
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
            render(f'<body><img src="http://127.0.0.1:{srv.server_port}/pixel.png"><p>x</p></body>')
        finally:
            srv.shutdown()
        self.assertEqual(hits, [])

    def test_screenshot_is_produced_when_vendored_and_skipped_when_not(self):
        _, png = render("<body><p>x</p></body>", vendored=True, screenshot=True)
        self.assertTrue(png and png.startswith(b"\x89PNG"))
        _, png = render("<body><p>x</p></body>", vendored=False, screenshot=True)
        self.assertIsNone(png)


if __name__ == "__main__":
    unittest.main()
