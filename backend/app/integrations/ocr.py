"""Local OCR and image similarity signals for member payment proof.

Screenshots are evidence for a staff decision, not a source of settlement truth.
This module extracts only visible text and a dHash; it cannot establish that a
transfer reached the organization's account.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OCRResult:
    raw_text: str
    amount: float | None
    date: str | None
    payer: str | None
    payee: str | None
    txn_id: str | None
    method: str | None
    authenticity_score: float | None
    perceptual_hash: str
    flags: list[str] = field(default_factory=list)


_MAX_PIXELS = 40_000_000
_OCR_TIMEOUT_SECONDS = 12
_HASH_TIMEOUT_SECONDS = 8
_SUPPORTED = {
    "png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "webp": lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


def _image_format(image_bytes: bytes) -> str:
    for image_format, matches in _SUPPORTED.items():
        if matches(image_bytes):
            return image_format
    raise ValueError("Upload a valid PNG, JPEG, or WebP receipt image.")


def validate_image(image_bytes: bytes) -> str:
    """Validate file signature and dimensions, returning a trusted media type."""

    image_format = _image_format(image_bytes)
    identify = shutil.which("identify")
    if not identify:
        raise ValueError("Image validation is unavailable on this server.")
    try:
        dims = _run(
            [identify, "-format", "%w %h", f"{image_format}:-[0]"],
            image_bytes,
            4,
        ).decode("ascii", "ignore")
        width, height = (int(value) for value in dims.split())
    except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError("Could not read the uploaded image.") from exc
    if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
        raise ValueError("Receipt image dimensions exceed the 40-megapixel limit.")
    return {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}[image_format]


def _run(command: list[str], image_bytes: bytes, timeout: int) -> bytes:
    result = subprocess.run(
        command,
        input=image_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Image processing failed")
    return result.stdout


def _dhash(image_bytes: bytes, image_format: str) -> str:
    """Build a 64-bit difference hash after bounded grayscale normalization."""

    convert = shutil.which("convert")
    if not convert:
        raise RuntimeError("ImageMagick is unavailable")
    raw = _run(
        [convert, f"{image_format}:-", "-auto-orient", "-resize", "9x8!", "-colorspace", "Gray", "-depth", "8", "gray:-"],
        image_bytes,
        _HASH_TIMEOUT_SECONDS,
    )
    if len(raw) != 72:
        raise RuntimeError("Image normalization failed")
    bits = [raw[row * 9 + col] > raw[row * 9 + col + 1] for row in range(8) for col in range(8)]
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def _ocr_text(image_bytes: bytes) -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise RuntimeError("Tesseract OCR is unavailable")
    return _run([tesseract, "stdin", "stdout", "--psm", "6"], image_bytes, _OCR_TIMEOUT_SECONDS).decode(
        "utf-8", errors="replace"
    )[:20_000]


def _parse_amount(text: str) -> float | None:
    patterns = (
        r"(?im)\b(?:amount|total|paid|payment|transfer|sent)\s*[:：-]?\s*(?:PKR|Rs\.?|USD|\$)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"(?im)\b(?:PKR|Rs\.?|USD|\$)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                return amount if math.isfinite(amount) and 0 <= amount <= 1_000_000_000 else None
            except ValueError:
                pass
    return None


def _parse_date(text: str) -> str | None:
    candidates = re.findall(
        r"\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b", text
    )
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _parse_labeled(text: str, labels: tuple[str, ...]) -> str | None:
    label = "|".join(labels)
    match = re.search(rf"(?im)^\s*(?:{label})\s*[:：-]\s*(.+?)\s*$", text)
    if not match:
        return None
    value = match.group(1).strip()
    return value[:120] or None


def _redact_sensitive_text(text: str) -> str:
    """Avoid persisting long account/card-like number sequences from screenshots."""

    return re.sub(r"(?<!\w)(?:\d[ -]?){9,}(?!\w)", "[redacted number]", text)[:20_000]


def _extract_sync(image_bytes: bytes) -> OCRResult:
    image_format = _image_format(image_bytes)
    # Identify decompression bombs before handing data to OCR. ImageMagick's
    # identify reports dimensions without retaining a full decoded bitmap here.
    validate_image(image_bytes)

    phash = _dhash(image_bytes, image_format)
    try:
        text = _ocr_text(image_bytes)
        flags: list[str] = []
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return OCRResult(
            raw_text="",
            amount=None,
            date=None,
            payer=None,
            payee=None,
            txn_id=None,
            method=None,
            authenticity_score=None,
            perceptual_hash=phash,
            flags=["ocr_unavailable", "manual_settlement_verification_required"],
        )
    if not text.strip():
        flags.append("no_text_detected")
    amount = _parse_amount(text)
    receipt_date = _parse_date(text)
    payer = _parse_labeled(text, ("payer", "sender", "from", "account name"))
    payee = _parse_labeled(text, ("payee", "recipient", "beneficiary", "to"))
    txn_id = _parse_labeled(text, ("transaction id", "transaction ref(?:erence)?", "reference", "trace id", "rrn"))
    method_match = re.search(r"(?i)\b(jazzcash|easypaisa|bank transfer|bank|wallet|sadapay|nayapay)\b", text)
    if method_match:
        method = (
            "mobile_wallet"
            if method_match.group(1).lower() in {"jazzcash", "easypaisa", "wallet", "sadapay", "nayapay"}
            else "bank_transfer"
        )
    else:
        method = None
    if amount is None:
        flags.append("amount_not_detected")
    if receipt_date is None:
        flags.append("date_not_detected")
    # An image cannot prove payment settlement or authenticity. This is only a
    # readable-field signal; the pipeline never uses it to auto-approve.
    flags.append("manual_settlement_verification_required")
    return OCRResult(
        raw_text=_redact_sensitive_text(text),
        amount=amount,
        date=receipt_date,
        payer=payer,
        payee=payee,
        txn_id=txn_id,
        method=method,
        authenticity_score=None,
        perceptual_hash=phash,
        flags=flags,
    )


async def extract_receipt(
    image_bytes: bytes,
) -> OCRResult:
    """Extract visible evidence without filling missing fields from request data."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_extract_sync, image_bytes), timeout=25)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        # Missing OCR/image tooling must route to a human; never invent fields.
        phash = f"sha256:{hashlib.sha256(image_bytes).hexdigest()}"
        return OCRResult(
            raw_text="",
            amount=None,
            date=None,
            payer=None,
            payee=None,
            txn_id=None,
            method=None,
            authenticity_score=None,
            perceptual_hash=phash,
            flags=[
                "image_processing_unavailable",
                "perceptual_hash_unavailable",
                "manual_settlement_verification_required",
            ],
        )
