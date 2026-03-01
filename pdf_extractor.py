import base64
import requests
import fitz  # pymupdf

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}


def download_pdf_bytes(url: str) -> bytes:
    """Download a PDF from a URL and return the raw bytes."""
    response = requests.get(url, timeout=60, headers=_HEADERS)
    response.raise_for_status()
    return response.content


def render_pages(pdf_bytes: bytes, page_nums: list[int] | None = None, zoom: float = 1.0) -> list[str]:
    """
    Render PDF pages as base64-encoded PNG strings.

    Args:
        pdf_bytes: raw PDF bytes
        page_nums: 0-based page indices to render; renders all pages if None
        zoom: render scale factor (0.5 = thumbnail, 1.5 = hi-res)

    Returns:
        List of base64 PNG strings, one per rendered page.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matrix = fitz.Matrix(zoom, zoom)

    indices = page_nums if page_nums is not None else list(range(len(doc)))
    images = []
    for idx in indices:
        if 0 <= idx < len(doc):
            pix = doc[idx].get_pixmap(matrix=matrix)
            b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append(b64)

    return images


def page_count(pdf_bytes: bytes) -> int:
    """Return the total number of pages in a PDF."""
    return len(fitz.open(stream=pdf_bytes, filetype="pdf"))
