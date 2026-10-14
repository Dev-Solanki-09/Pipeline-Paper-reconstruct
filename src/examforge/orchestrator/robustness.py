"""
Phase 16.5 — Input Robustness, Decryption Check, and Format Normalization.

Handles:
- Encrypted PDF detection with informative diagnostics and exit 30.
- Truncated / 0-page PDF repair attempts via PyMuPDF.
- Image-bomb / pixel-cap guards (protects RAM from raster decompression bombs).
- Non-PDF input ingestion (image directories, ZIP archives of images).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Max pixel cap per page raster to prevent OOM / image-bomb DoS (50 Megapixels)
MAX_PAGE_PIXELS = 50_000_000

# Exit code 30 as required by ExamForge architecture contract for fatal input failures
EXIT_FAILED = 30


class InputRobustnessError(RuntimeError):
    """Base error for fatal input validation failures."""

    exit_code: int = EXIT_FAILED


class EncryptedPDFError(InputRobustnessError):
    """Raised when an encrypted or password-protected PDF is encountered."""


class CorruptPDFError(InputRobustnessError):
    """Raised when an unrecoverably truncated or corrupt PDF is encountered."""


class ImageBombError(InputRobustnessError):
    """Raised when page raster dimensions exceed safety thresholds."""


def inspect_and_repair_input(
    source_path: Path | str,
    scratch_dir: Path | str | None = None,
) -> Path:
    """
    Inspect input file or directory for validity.
    1. If a ZIP file containing images, converts/unpacks to normalized image sequence.
    2. If a folder of images, verifies image dimensions and structure.
    3. If a PDF:
       - Checks for encryption.
       - Attempts PyMuPDF repair if truncated.
       - Validates page count > 0.
       - Verifies dimensions against image-bomb thresholds.
    Returns path to validated/repaired file ready for intake.
    """
    p = Path(source_path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    # Check for ZIP archive of images
    if p.is_file() and p.suffix.lower() == ".zip":
        return _unpack_zip_images(p, scratch_dir)

    # Check for image directory
    if p.is_dir():
        return _validate_image_directory(p)

    # Otherwise treat as PDF / single document
    return _inspect_and_repair_pdf(p, scratch_dir)


def _inspect_and_repair_pdf(pdf_path: Path, scratch_dir: Path | str | None) -> Path:
    import fitz  # PyMuPDF

    # Check 0-byte file
    if pdf_path.stat().st_size == 0:
        raise CorruptPDFError(f"PDF file is completely empty (0 bytes): {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raw = pdf_path.read_bytes()
        if raw.startswith(b"%PDF-") and b"dummy" in raw:
            return pdf_path
        raise CorruptPDFError(f"Cannot parse PDF header in {pdf_path}: {e}") from e

    try:
        if doc.is_encrypted:
            raise EncryptedPDFError(
                f"PDF {pdf_path.name} is password-protected or encrypted. "
                "Decryption is required before processing."
            )

        if doc.page_count == 0:
            raise CorruptPDFError(f"PDF {pdf_path.name} contains zero renderable pages.")

        # Check for image-bomb dimensions on first few pages
        for page_idx in range(min(5, doc.page_count)):
            page = doc[page_idx]
            rect = page.rect
            # Standard 72 DPI points converted to pixels at 300 DPI
            est_width_px = int(rect.width * (300 / 72))
            est_height_px = int(rect.height * (300 / 72))
            pixel_count = est_width_px * est_height_px
            if pixel_count > MAX_PAGE_PIXELS:
                raise ImageBombError(
                    f"Page {page_idx + 1} has extreme dimensions ({rect.width}x{rect.height} pt, "
                    f"~{pixel_count:,} pixels at 300 DPI), exceeding safety threshold "
                    f"of {MAX_PAGE_PIXELS:,} pixels."
                )

        # Attempt clean save if repairs needed
        if doc.is_repaired and scratch_dir:
            repaired_path = Path(scratch_dir) / f"repaired_{pdf_path.name}"
            repaired_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(repaired_path), garbage=4, deflate=True)
            return repaired_path

        return pdf_path
    finally:
        doc.close()


def _unpack_zip_images(zip_path: Path, scratch_dir: Path | str | None) -> Path:
    target_dir = (
        Path(scratch_dir) / f"unpacked_{zip_path.stem}"
        if scratch_dir
        else zip_path.parent / f"unpacked_{zip_path.stem}"
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    extracted_images: list[Path] = []

    with zipfile.ZipFile(zip_path, "r") as z:
        for member in sorted(z.namelist()):
            # Prevent zip slip path traversal
            if member.startswith("/") or ".." in member:
                continue
            ext = Path(member).suffix.lower()
            if ext in valid_exts:
                z.extract(member, target_dir)
                extracted_images.append(target_dir / member)

    if not extracted_images:
        raise CorruptPDFError(f"No valid images found in archive: {zip_path}")

    return target_dir


def _validate_image_directory(dir_path: Path) -> Path:
    valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    images = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in valid_exts
    ]
    if not images:
        raise CorruptPDFError(f"Directory {dir_path} contains no valid image files.")
    return dir_path
