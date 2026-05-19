from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Any

from extractor.budget import ExtractionBudget
from extractor.http_security import sanitize_error
from extractor.models import CanonicalSummary, SourceExtraction, StructuredSource


DATE_RE = re.compile(r"(?:20\d{2}\s*[년./-]\s*\d{1,2}\s*[월./-]\s*\d{1,2}\s*일?|(?:\d{1,2}\s*[./]\s*\d{1,2}))")
PHONE_RE = re.compile(r"(?:0\d{1,2}-\d{3,4}-\d{4}|1[0-9]{2}|117)")
MONEY_RE = re.compile(r"\d[\d,]*\s*원")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
TARGET_RE = re.compile(r"(?:[1-6]\s*학년(?:\s*[0-9,~\- ]+반)?|전교생|전체 학생|신입생|학부모|보호자|학생)")


async def structure_source(
    source: SourceExtraction,
    gemini: Any | None = None,
    budget: ExtractionBudget | None = None,
) -> dict[str, Any]:
    if not source.raw_text.strip():
        return StructuredSource(warnings=["empty_raw_text"], confidence=0.0).to_dict()

    if _use_gemini_structuring() and gemini is not None:
        if budget is not None:
            decision = budget.reserve_gemini_call(
                f"{source.source_id}:structuring",
                len(source.raw_text.encode("utf-8")),
            )
            if not decision.ok:
                fallback = _heuristic_structure(source)
                fallback.warnings.append(f"gemini_structuring_budget_exhausted: {decision.reason}")
                return fallback.to_dict()
        try:
            structured = await _structure_with_gemini(source, gemini)
        except Exception as exc:  # noqa: BLE001 - preserve structuring failure while falling back.
            fallback = _heuristic_structure(source)
            fallback.warnings.append(f"gemini_structuring_failed: {type(exc).__name__}: {sanitize_error(exc)}")
            return fallback.to_dict()
        if structured:
            return _normalize_structured_dict(structured)

    return _heuristic_structure(source).to_dict()


def build_canonical_summary(sources: list[SourceExtraction], included_source_ids: list[str]) -> dict[str, Any]:
    selected = [source for source in sources if source.source_id in included_source_ids]
    summary = CanonicalSummary()
    if not selected:
        unreadable = [source.source_id for source in sources if source.status not in {"success", "partial_success"}]
        if unreadable:
            summary.warnings.append(f"unreadable_sources={','.join(unreadable[:8])}")
        return summary.to_dict()

    document_types: list[str] = []
    confidences: list[float] = []
    for source in selected:
        structured = _normalize_structured_dict(source.structured)
        if not summary.summary_oneliner and structured.get("summary_oneliner"):
            summary.summary_oneliner = str(structured["summary_oneliner"])
        if not summary.deadline and structured.get("deadline"):
            summary.deadline = str(structured["deadline"])
        if structured.get("requires_response"):
            summary.requires_response = True
        if structured.get("urgency") == "urgent":
            summary.urgency = "urgent"
        document_type = str(structured.get("document_type") or "")
        if document_type and document_type != "other":
            document_types.append(document_type)
        confidences.append(float(structured.get("confidence") or 0.0))

        _extend_unique(summary.targets, structured.get("targets", []))
        _extend_unique(summary.key_facts, structured.get("key_facts", []))
        _extend_unique(summary.required_actions, structured.get("required_actions", []))
        _extend_unique(summary.important_dates, structured.get("important_dates", []))
        _extend_unique(summary.preparation_items, structured.get("preparation_items", []))
        _extend_unique(summary.fees, structured.get("fees", []))
        _extend_unique(summary.contacts, structured.get("contacts", []))
        _extend_unique(summary.links, structured.get("links", []))
        _extend_unique(summary.locations, structured.get("locations", []))
        _extend_unique(summary.forms_to_submit, structured.get("forms_to_submit", []))
        _extend_unique(summary.unclassified, structured.get("unclassified", []))
        _extend_unique(summary.warnings, structured.get("warnings", []))
        _extend_unique_dict(summary.sections, structured.get("sections", []))
        _extend_unique_dict(summary.tables, structured.get("tables", []))

        if source.source_role == "activity":
            _extend_unique(summary.activity_summary, structured.get("key_facts", [])[:3])
        elif source.source_role == "supplement":
            _extend_unique(summary.supplement_summary, structured.get("key_facts", [])[:3])

    if document_types:
        summary.document_type = _most_common(document_types)
    if summary.urgency != "urgent" and summary.deadline:
        summary.urgency = "normal"
    summary.confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    return summary.to_dict()


def combined_raw_text(sources: list[SourceExtraction], included_source_ids: list[str]) -> str:
    by_id = {source.source_id: source for source in sources}
    parts: list[str] = []
    for source_id in included_source_ids:
        source = by_id.get(source_id)
        if not source:
            continue
        text = source.raw_text.strip()
        if text:
            label = f"[{source.source_id} {source.source_type}]"
            parts.append(f"{label}\n{text}")
    return "\n\n---\n\n".join(parts)


def _heuristic_structure(source: SourceExtraction) -> StructuredSource:
    text = source.raw_text.strip()
    lines = _meaningful_lines(text)
    title = _find_title(lines, source.filename)
    document_type = _document_type(text, source.source_type)
    dates = _dedupe(DATE_RE.findall(text))
    contacts = _dedupe(PHONE_RE.findall(text))
    links = _dedupe(URL_RE.findall(text))
    fees = _dedupe(MONEY_RE.findall(text))
    key_facts = _key_facts(lines)
    actions = _required_actions(lines)
    preparation_items = _matching_lines(lines, ("준비물", "지참", "개인별", "준비"))
    forms_to_submit = _matching_lines(lines, ("동의서", "신청서", "제출", "회신"))
    targets = _dedupe(TARGET_RE.findall(text))
    deadline = _deadline(lines)
    requires_response = bool(actions or forms_to_submit or fees or any(term in text for term in ("동의", "신청", "제출", "회신", "응답", "납부")))

    warnings: list[str] = []
    if source.source_type in {"inline_image", "attachment_image"}:
        warnings.append("ocr_source_verify_numbers")
    if source.confidence < 0.65 and source.extraction_method.startswith("gemini"):
        warnings.append("low_ocr_confidence")

    return StructuredSource(
        title=title,
        document_type=document_type,
        summary_oneliner=title or (key_facts[0] if key_facts else ""),
        requires_response=requires_response,
        urgency="urgent" if any(term in text for term in ("긴급", "필독", "반드시", "마감")) else "normal",
        deadline=deadline,
        targets=targets,
        key_facts=key_facts,
        sections=_sections(lines),
        required_actions=actions,
        important_dates=dates,
        preparation_items=preparation_items,
        fees=fees,
        contacts=contacts,
        links=links,
        forms_to_submit=forms_to_submit,
        unclassified=[],
        warnings=warnings,
        confidence=_structured_confidence(source, text, dates, actions),
    )


async def _structure_with_gemini(source: SourceExtraction, gemini: Any) -> dict[str, Any] | None:
    prompt = f"""
You extract structured facts from Korean school notices for later translation.
Return ONLY JSON. Do not summarize facts that are not explicit in the raw text.
If a field is not present, use an empty string, false, or [].

Schema:
{json.dumps(asdict(StructuredSource()), ensure_ascii=False)}

Source metadata:
source_id={source.source_id}
source_type={source.source_type}
filename={source.filename}

Raw text:
{source.raw_text[:18000]}
"""
    result = await gemini.generate_json(prompt, model=os.getenv("GEMINI_STRUCT_MODEL", "gemini-2.5-flash"))
    return result if isinstance(result, dict) else None


def _normalize_structured_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    base = asdict(StructuredSource())
    if not isinstance(value, dict):
        return base
    for key, default in base.items():
        candidate = value.get(key, default)
        if isinstance(default, list):
            base[key] = candidate if isinstance(candidate, list) else []
        elif isinstance(default, bool):
            base[key] = bool(candidate)
        elif isinstance(default, float):
            try:
                base[key] = float(candidate)
            except (TypeError, ValueError):
                base[key] = default
        else:
            base[key] = "" if candidate is None else str(candidate)
    return base


def _use_gemini_structuring() -> bool:
    return os.getenv("ENABLE_GEMINI_STRUCTURING", "false").strip().lower() in {"1", "true", "yes", "on"}


def _meaningful_lines(text: str) -> list[str]:
    lines = []
    for line in re.split(r"[\r\n]+", text):
        cleaned = re.sub(r"\s+", " ", line).strip(" -\t")
        if len(cleaned) >= 2:
            lines.append(cleaned)
    return lines


def _find_title(lines: list[str], filename: str) -> str:
    ignored = ("가정통신문", "학교장", "담당", "전화", "교육연구부")
    for line in lines[:12]:
        if len(line) > 80:
            continue
        if any(token == line for token in ignored):
            continue
        if any(term in line for term in ("안내", "실시", "신청", "모집", "동의", "예방", "교육")):
            return line
    for line in lines[:8]:
        if 4 <= len(line) <= 80:
            return line
    return filename


def _document_type(text: str, source_type: str) -> str:
    if any(term in text for term in ("동의서", "동의 여부")):
        return "consent_form"
    if any(term in text for term in ("신청서", "신청 기간", "신청 방법")):
        return "application_form"
    if "설문" in text:
        return "survey"
    if any(term in text for term in ("활동지", "학습지", "문항", "평가지")):
        return "worksheet"
    if source_type in {"inline_image", "attachment_image"} and any(term in text for term in ("홍보", "캠페인", "예방")):
        return "poster"
    if any(term in text for term in ("일정", "시간표", "운영 계획")):
        return "schedule"
    return "notice"


def _key_facts(lines: list[str], limit: int = 8) -> list[str]:
    facts = []
    for line in lines:
        if len(line) > 250:
            continue
        if any(term in line for term in ("대상", "일시", "기간", "장소", "내용", "방법", "준비", "문의", "신청", "제출", "납부", "결과")):
            facts.append(line)
        if len(facts) >= limit:
            break
    if not facts:
        facts = [line for line in lines[:limit] if len(line) <= 250]
    return _dedupe(facts)


def _required_actions(lines: list[str]) -> list[str]:
    return _matching_lines(lines, ("제출", "신청", "동의", "납부", "작성", "회신", "응답", "참여", "지참", "접종"))


def _matching_lines(lines: list[str], terms: tuple[str, ...], limit: int = 8) -> list[str]:
    matches = [line for line in lines if any(term in line for term in terms) and len(line) <= 260]
    return _dedupe(matches[:limit])


def _deadline(lines: list[str]) -> str:
    for line in lines:
        if any(term in line for term in ("마감", "기한", "까지", "제출", "신청")):
            match = DATE_RE.search(line)
            if match:
                return match.group(0)
    return ""


def _sections(lines: list[str]) -> list[dict[str, Any]]:
    sections = []
    for line in lines:
        if len(sections) >= 12:
            break
        if re.match(r"^\s*(?:[0-9]+[.)]|[가-하][.)]|[▶■●-])", line) and len(line) <= 180:
            sections.append({"heading": "", "text": line})
    return sections


def _structured_confidence(source: SourceExtraction, text: str, dates: list[str], actions: list[str]) -> float:
    score = 0.35
    if source.quality_score >= 40:
        score += 0.2
    if dates:
        score += 0.12
    if actions:
        score += 0.1
    if len(text) >= 500:
        score += 0.1
    if source.confidence:
        score = (score + source.confidence) / 2
    return round(max(0.0, min(score, 0.95)), 3)


def _extend_unique(target: list[str], values: Any) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        text = str(value).strip()
        if text and text not in target:
            target.append(text)


def _extend_unique_dict(target: list[dict[str, Any]], values: Any) -> None:
    if not isinstance(values, list):
        return
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in target if isinstance(item, dict)}
    for value in values:
        if not isinstance(value, dict):
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            target.append(value)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value)).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _most_common(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]
