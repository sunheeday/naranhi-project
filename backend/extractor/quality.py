from __future__ import annotations

import hashlib
import re
from pathlib import Path


HANGUL_RE = re.compile(r"[가-힣]")
ALNUM_HANGUL_RE = re.compile(r"[0-9A-Za-z가-힣]+")
DATE_RE = re.compile(r"(?:20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}|(?:\d{1,2}[./]\d{1,2}))")
PHONE_RE = re.compile(r"(?:0\d{1,2}-\d{3,4}-\d{4}|1[0-9]{2}|117)")
MONEY_RE = re.compile(r"\d[\d,]*\s*원")
ACTION_TERMS = ("제출", "신청", "동의", "납부", "참여", "작성", "회신", "응답", "지참", "제출")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text(text: str) -> str:
    return "".join(ALNUM_HANGUL_RE.findall(text.lower()))


def text_fingerprint(text: str) -> str:
    normalized = normalized_text(text)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]


def text_quality_score(text: str, confidence: float | None = None) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0

    hangul_count = len(HANGUL_RE.findall(stripped))
    hangul_ratio = hangul_count / max(len(stripped), 1)
    replacement_ratio = stripped.count("�") / max(len(stripped), 1)
    score = 0.0
    score += min(len(stripped) / 2000, 1.0) * 30
    score += min(hangul_ratio / 0.45, 1.0) * 25
    score += 8 if DATE_RE.search(stripped) else 0
    score += 6 if PHONE_RE.search(stripped) else 0
    score += 6 if MONEY_RE.search(stripped) else 0
    score += 10 if any(term in stripped for term in ACTION_TERMS) else 0
    score += 10 if any(term in stripped for term in ("가정통신문", "안내", "학부모", "학생")) else 0
    if confidence is not None:
        score += max(0.0, min(confidence, 1.0)) * 10
    score -= min(replacement_ratio / 0.03, 1.0) * 20
    return round(max(0.0, min(score, 100.0)), 2)


def is_low_quality_text(text: str, *, min_chars: int = 20) -> bool:
    stripped = text.strip()
    if len(stripped) < min_chars:
        return True
    if len(HANGUL_RE.findall(stripped)) < 10 and len(stripped) < 200:
        return True
    return text_quality_score(stripped) < 12


def token_set(text: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", text.lower())
    return set(re.findall(r"[0-9A-Za-z가-힣]{2,}", normalized))


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
