"""
Convert a roster PDF (bytes) to a self-contained, styled HTML document.

Uses PyMuPDF (fitz) which is already in requirements.txt (pymupdf).
Each PDF page is rendered as a position-relative container whose child
<p> elements use the pt-unit absolute coordinates emitted by PyMuPDF.
A tiny inline script scales oversized pages down to fit the viewport.
"""
import re

import fitz  # PyMuPDF


class RosterHtmlService:
    """Convert roster PDF bytes → self-contained HTML string."""

    def convert(self, pdf_bytes: bytes) -> str:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: list[str] = []

        for page in doc:
            rect = page.rect  # dimensions in points
            raw = page.get_text("html")
            # PyMuPDF wraps each page in <div id="pageN">…</div> — strip that
            # wrapper so we can substitute our own styled container.
            inner = re.sub(r"^\s*<div[^>]*>", "", raw.strip(), count=1)
            inner = re.sub(r"</div>\s*$", "", inner.strip())
            pages.append(
                f'<div class="page" style="width:{rect.width:.1f}pt;height:{rect.height:.1f}pt">'
                f"{inner}</div>"
            )

        doc.close()
        return _build_document("\n".join(pages))


def _build_document(body: str) -> str:
    """Wrap page fragments in a complete HTML document with embedded CSS + scaling script."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  background: #e8e8e8;
  padding: 20px 16px;
  font-family: serif;
}}
.page {{
  position: relative;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(0,0,0,.18);
  margin: 0 auto 24px auto;
  overflow: hidden;
}}
/* PyMuPDF emits <p> elements with position:absolute and pt-unit coordinates */
.page p {{ position: absolute; white-space: pre; margin: 0; padding: 0; }}
@media print {{
  html, body {{ background: #fff; padding: 0; }}
  .page {{ box-shadow: none; margin-bottom: 0; page-break-after: always; }}
}}
</style>
</head>
<body>
{body}
<script>
/* Scale pages down when they are wider than the viewport. */
(function() {{
  var pad = 32;
  function fit() {{
    var avail = document.documentElement.clientWidth - pad;
    document.querySelectorAll('.page').forEach(function(p) {{
      /* pt → px: 1pt = 96/72 px at standard screen density */
      var wPx = parseFloat(p.style.width)  * (96 / 72);
      var hPx = parseFloat(p.style.height) * (96 / 72);
      if (wPx > avail) {{
        var s = avail / wPx;
        p.style.transform       = 'scale(' + s + ')';
        p.style.transformOrigin = 'top left';
        /* Collapse the layout height so scaled page doesn't leave a gap */
        p.style.height = (hPx * s) + 'px';
      }} else {{
        p.style.transform = '';
        p.style.height    = hPx + 'px';
      }}
    }});
  }}
  fit();
  window.addEventListener('resize', fit);
}})();
</script>
</body>
</html>"""
