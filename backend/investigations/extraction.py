"""
Text extraction service for Catalyst documents.

Milestone 1 — Direct PDF extraction (digital PDFs via PyMuPDF).
Milestone 2 — Synchronous OCR fallback (Tesseract) for scanned PDFs ≤ 30 MB.

Usage:
    from investigations.extraction import extract_from_pdf

    text, ocr_status = extract_from_pdf("/abs/path/to/document.pdf", file_size=uploaded.size)
"""

import concurrent.futures
import io
import logging
import os
import platform
import shutil

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger("investigations.extraction")

# ---------------------------------------------------------------------------
# Tesseract binary discovery
# ---------------------------------------------------------------------------
# On Windows pytesseract needs the full path to tesseract.exe unless it is
# already on PATH.  We check common install locations automatically.

_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract() -> None:
    """Set pytesseract.pytesseract_cmd if tesseract isn't already on PATH."""
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path:
        pytesseract.pytesseract.tesseract_cmd = env_path
        return

    # Already on PATH?
    if shutil.which("tesseract"):
        return

    if platform.system() == "Windows":
        for candidate in _WINDOWS_TESSERACT_PATHS:
            if os.path.isfile(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                return

    logger.warning(
        "tesseract_not_found",
        extra={
            "hint": (
                "Install Tesseract-OCR and ensure it is on PATH, or set the "
                "TESSERACT_CMD environment variable to the full binary path."
            )
        },
    )


_configure_tesseract()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum extracted characters to consider a PDF "digital" (not scanned/blank).
_MIN_MEANINGFUL_LENGTH = 100

# Files larger than this will NOT have OCR attempted synchronously.
# They stay PENDING for a future background task.
MAX_SYNC_OCR_BYTES = 30 * 1024 * 1024  # 30 MB

# PyMuPDF render resolution for OCR — 200 DPI is enough for Tesseract accuracy
# without making every page image excessively large.
_OCR_DPI = 200
_OCR_MATRIX = fitz.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)

# Maximum seconds to wait for Tesseract to OCR a single page.
_OCR_PAGE_TIMEOUT_SECONDS = int(os.environ.get("OCR_PAGE_TIMEOUT", "60"))

# Maximum seconds for the entire OCR pass on one PDF.
_OCR_TOTAL_TIMEOUT_SECONDS = int(os.environ.get("OCR_TOTAL_TIMEOUT", "300"))


def _extract_text_direct(absolute_path: str) -> str:
    """
    Open a PDF with PyMuPDF and concatenate embedded text from every page.
    Returns an empty string if the file has no embedded text layer.
    """
    pages = []
    with fitz.open(absolute_path) as doc:
        for page in doc:
            pages.append(page.get_text())
    return "\n\n".join(pages).strip()


def _ocr_page(page: fitz.Page) -> str:
    """
    Render a single PDF page to a PIL Image and run Tesseract on it.
    Returns the recognised text, or an empty string on failure.

    Applies a per-page timeout so a single difficult page cannot hang the
    entire upload pipeline.
    """
    try:
        pixmap = page.get_pixmap(matrix=_OCR_MATRIX, alpha=False)
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))
    except Exception:
        logger.exception("ocr_page_render_failed", extra={"page_number": page.number})
        return ""

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pytesseract.image_to_string, img)
            return future.result(timeout=_OCR_PAGE_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        logger.warning(
            "ocr_page_timeout",
            extra={
                "page_number": page.number,
                "timeout_seconds": _OCR_PAGE_TIMEOUT_SECONDS,
            },
        )
        return ""
    except Exception:
        logger.exception("ocr_page_tesseract_failed", extra={"page_number": page.number})
        return ""


def _extract_text_ocr(absolute_path: str) -> str:
    """
    Render every page of a PDF to an image and OCR each one with Tesseract.
    Returns concatenated text from all pages.

    Enforces a total-document timeout so very long PDFs do not block the
    request indefinitely.
    """
    import time

    deadline = time.monotonic() + _OCR_TOTAL_TIMEOUT_SECONDS
    pages = []

    with fitz.open(absolute_path) as doc:
        for page in doc:
            if time.monotonic() > deadline:
                logger.warning(
                    "ocr_total_timeout",
                    extra={
                        "path": absolute_path,
                        "pages_completed": len(pages),
                        "total_pages": len(doc),
                        "timeout_seconds": _OCR_TOTAL_TIMEOUT_SECONDS,
                    },
                )
                break
            pages.append(_ocr_page(page))

    return "\n\n".join(pages).strip()


def extract_from_pdf(absolute_path: str, file_size: int = 0) -> tuple[str, str]:
    """
    Extract text from a PDF using a two-stage pipeline:

      Stage 1 — Direct extraction (PyMuPDF): fast, works on digital PDFs.
      Stage 2 — OCR fallback (Tesseract): used when Stage 1 returns sparse
                 text and the file is within the synchronous size limit.

    Args:
        absolute_path: Filesystem path to the saved PDF.
        file_size:     File size in bytes (from upload or os.path.getsize).
                       Used to gate OCR for large files.

    Returns:
        A (extracted_text, ocr_status) tuple where ocr_status is one of:
          - OcrStatus.NOT_NEEDED  — digital PDF; Stage 1 found meaningful text
          - OcrStatus.COMPLETED   — scanned PDF; Stage 2 OCR succeeded
          - OcrStatus.PENDING     — file too large for sync OCR (> 30 MB)
          - OcrStatus.FAILED      — unexpected error during extraction or OCR
    """
    from .models import OcrStatus

    # Stage 1: direct text extraction
    try:
        text = _extract_text_direct(absolute_path)
    except FileNotFoundError:
        logger.error("pdf_file_not_found", extra={"path": absolute_path})
        return "", OcrStatus.FAILED
    except PermissionError:
        logger.error("pdf_permission_denied", extra={"path": absolute_path})
        return "", OcrStatus.FAILED
    except Exception:
        logger.exception("pdf_direct_extraction_failed", extra={"path": absolute_path})
        return "", OcrStatus.FAILED

    if len(text) >= _MIN_MEANINGFUL_LENGTH:
        return text, OcrStatus.NOT_NEEDED

    # Sparse or no embedded text — file is likely scanned.
    if file_size > MAX_SYNC_OCR_BYTES:
        # Too large for synchronous OCR; leave for a future background task.
        return text, OcrStatus.PENDING

    # Stage 2: OCR fallback
    try:
        ocr_text = _extract_text_ocr(absolute_path)
    except Exception:
        logger.exception("pdf_ocr_extraction_failed", extra={"path": absolute_path})
        return text, OcrStatus.FAILED

    return ocr_text, OcrStatus.COMPLETED
