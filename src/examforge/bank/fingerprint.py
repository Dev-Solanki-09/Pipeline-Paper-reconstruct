"""Deterministic fingerprinting algorithms for the question bank (Phase 12.2)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

import numpy as np

from examforge.ir.schema import Question

_DEVANAGARI_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

_MATH_DELIMS = re.compile(r"(\$\$|\$|\\\(|\\\)|\\\[|\\\])")
_NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?(?:\d+\.\d+|\d+)(?![A-Za-z_])")
_UNIT_RE = re.compile(
    r"\b(kg|g|mg|m/s\^2|m/s|km/h|cm|mm|nm|km|m|s|ms|min|h|mol|J|kJ|cal|kcal|"
    r"V|mV|kV|A|mA|N|kN|Pa|kPa|atm|bar|Hz|kHz|MHz|W|kW|MW|T|G|ohm|Omega|rad|deg)\b",
    re.IGNORECASE,
)


def normalize_text_for_fingerprint(text: str) -> str:
    """Normalize text with NFC Unicode, digit canonicalization, and delimiter stripping."""
    if not text:
        return ""
    # 1. NFC normalization
    t = unicodedata.normalize("NFC", text)

    # 2. Map Indic/script digits to Western ASCII digits
    for k, v in _DEVANAGARI_DIGITS.items():
        t = t.replace(k, v)

    # 3. Strip math delimiters
    t = _MATH_DELIMS.sub(" ", t)

    # 4. Collapse whitespace and lowercase
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def compute_simhash_64(text: str) -> int:
    """
    Compute a 64-bit SimHash over word 3-grams of normalized text.

    Deterministic, offline, stdlib-based.
    """
    norm = normalize_text_for_fingerprint(text)
    words = norm.split()
    if not words:
        return 0

    # Extract 3-grams (fallback to unigrams/bigrams if text is short)
    if len(words) >= 3:
        shingles = [
            f"{words[i]} {words[i+1]} {words[i+2]}"
            for i in range(len(words) - 2)
        ]
    elif len(words) == 2:
        shingles = [f"{words[0]} {words[1]}", words[0], words[1]]
    else:
        shingles = [words[0]]

    v = [0] * 64
    for shingle in shingles:
        # 64-bit hash from SHA-256
        digest = hashlib.sha256(shingle.encode("utf-8")).digest()
        shingle_hash = int.from_bytes(digest[:8], byteorder="big")
        for i in range(64):
            bit = (shingle_hash >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1

    simhash = 0
    for i in range(64):
        if v[i] > 0:
            simhash |= (1 << i)

    return simhash


def hamming_distance_64(h1: int, h2: int) -> int:
    """Calculate the Hamming bit distance between two 64-bit integers."""
    return (h1 ^ h2).bit_count()


def compute_number_signature(question: Question) -> str:
    """
    Extract a canonical signature of numerals, units, and option count.

    Any difference in digits or units strictly invalidates reuse.
    """
    # Collect all text in stem and options
    texts = []
    if question.stem_text_en:
        texts.append(question.stem_text_en)
    if question.stem_text_hi:
        texts.append(question.stem_text_hi)

    for opt in question.options:
        if opt.text_str_en:
            texts.append(opt.text_str_en)
        if opt.text_str_hi:
            texts.append(opt.text_str_hi)

    full_text = " ".join(texts)
    norm = normalize_text_for_fingerprint(full_text)

    # Extract and normalize numerals
    raw_nums = _NUMBER_RE.findall(norm)
    canonical_nums: list[float] = []
    for rn in raw_nums:
        try:
            val = float(rn)
            canonical_nums.append(val)
        except ValueError:
            pass

    sorted_nums = sorted(canonical_nums)
    # Format floats without trailing .0 if integer
    formatted_nums = [
        f"{int(n)}" if n.is_integer() else f"{n:.4f}".rstrip("0").rstrip(".")
        for n in sorted_nums
    ]

    # Extract units
    units = sorted({u.lower() for u in _UNIT_RE.findall(norm)})

    opts_count = len(question.options)
    return f"opts:{opts_count}|nums:{','.join(formatted_nums)}|units:{','.join(units)}"


def compute_figure_dhash(img: np.ndarray) -> str:
    """
    Compute a 64-bit perceptual difference hash (dHash) for an image array.

    Returns a 16-character hexadecimal string.
    """
    # Handle multichannel color images
    if img.ndim == 3:
        # Convert RGB to grayscale (standard ITU-R 601-2 luma)
        gray = np.dot(img[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
    else:
        gray = img.astype(np.float32)

    h, w = gray.shape[:2]
    if h == 0 or w == 0:
        return "0" * 16

    # Downsample to 8x9 using uniform step sampling
    row_indices = np.linspace(0, h - 1, 8).astype(int)
    col_indices = np.linspace(0, w - 1, 9).astype(int)
    sampled = gray[row_indices[:, None], col_indices[None, :]]

    # Compare adjacent pixels: 8 rows of 8 comparisons = 64 bits
    diff = sampled[:, 1:] > sampled[:, :-1]
    bits = diff.flatten()

    hash_val = 0
    for i, b in enumerate(bits):
        if b:
            hash_val |= (1 << (63 - i))

    return f"{hash_val:016x}"
