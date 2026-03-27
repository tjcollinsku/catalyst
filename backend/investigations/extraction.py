"""
Text extraction service for Catalyst documents.

Milestone 1 — Direct PDF extraction (digital PDFs via PyMuPDF).
Milestone 2 — Synchronous OCR fallback (Tesseract) for scanned PDFs ≤ 30 MB.

Usage:
    from investigations.extraction import extract_from_pdf

    text, ocr_status = extract_from_pdf("/abs/path/to/document.pdf", file_size=uploaded.size)
"""

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

# Minimum extracted characters to consider a PDF "digital" (not scanned/blank).
_MIN_MEANINGFUL_LENGTH = 100

# Files larger than this will NOT have OCR attempted synchronously.
# They stay PENDING for a future background task.
MAX_SYNC_OCR_BYTES = 30 * 1024 * 1024  # 30 MB

# PyMuPDF render resolution for OCR — 200 DPI is enough for Tesseract accuracy
# without making every page image excessively large.
_OCR_DPI = 200
_OCR_MATRIX = fitz.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)


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
    """
    pixmap = page.get_pixmap(matrix=_OCR_MATRIX, alpha=False)
    img = Image.open(io.BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(img)


def _extract_text_ocr(absolute_path: str) -> str:
    """
    Render every page of a PDF to an image and OCR each one with Tesseract.
    Returns concatenated text from all pages.
    """
    pages = []
    with fitz.open(absolute_path) as doc:
        for page in doc:
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
    except Exception:
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
        return text, OcrStatus.FAILED

    return ocr_text, OcrStatus.COMPLETED
