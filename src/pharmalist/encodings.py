from __future__ import annotations

from pathlib import Path


ENCODING_CANDIDATES = (
    "utf-8-sig",
    "utf-8",
    "cp932",
    "shift_jis",
    "euc_jp",
)


def _can_decode_sample(sample: bytes, encoding: str) -> bool:
    # A fixed-size sample can end in the middle of a multibyte character.
    # Trim a few bytes from the tail before rejecting the encoding.
    for trim_bytes in range(0, min(4, len(sample)) + 1):
        candidate = sample if trim_bytes == 0 else sample[:-trim_bytes]
        if not candidate:
            return True
        try:
            candidate.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def detect_text_encoding(path: Path, sample_size: int = 65536) -> str:
    sample = path.read_bytes()[:sample_size]
    if not sample:
        return "utf-8"

    for encoding in ENCODING_CANDIDATES:
        if _can_decode_sample(sample, encoding):
            return encoding

    raise UnicodeDecodeError(
        "unknown",
        sample,
        0,
        min(1, len(sample)),
        f"Could not decode sample from {path.name} using supported encodings",
    )