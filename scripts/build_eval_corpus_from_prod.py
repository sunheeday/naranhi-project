"""운영 공지의 한국어 원문으로 평가 이터레이션 폴더를 만든다. 읽기 전용 조회.

다양성 매트릭스(.agents/translation-quality/workflow.md)를 사람이 채우기 쉽도록
manifest 의 태그는 자동 추정값으로 채워두고, 착수 전에 사람이 검토·수정한다.
held-out 비율은 workflow.md 정책(대략 1/3)을 따른다.

APPLY=1 일 때만 파일을 쓴다. 기본은 미리보기.

주의(2026-08-27, Task 2 구현 중 확인): `notices` 테이블에는 `content_text` 컬럼이
없다. 실제 컬럼은 `original_text`(운영 번역 파이프라인이 우선 소비하는 원문,
notice_service.py `_resolve_notice_source_text`) 다. `content_text`는
`crawl_result` JSON 내부의 중첩 키 이름일 뿐이다. 아래 fetch/source_text는
`original_text`를 우선 사용하도록 고쳤다.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
APPLY = os.environ.get("APPLY") == "1"
TARGET_UNIQUE = int(os.environ.get("TARGET_UNIQUE") or "30")
ITER_DIR = Path(os.environ.get("ITER_DIR") or
                ".agents/translation-quality/iterations/2026-08-27_iter-bedrock-001")

MEAL_CUES = ("식단", "급식", "알레르기", "메뉴")
FEE_CUES = ("납부", "수납", "스쿨뱅킹", "계좌", "회비", "참가비")
CONSENT_CUES = ("동의서", "서명", "신청서", "제출", "회신")
URGENT_CUES = ("긴급", "즉시", "안전", "주의", "폭염", "감염")


def fetch(offset: int, page: int = 1000) -> list[dict]:
    path = (
        f"/rest/v1/notices?select=id,title,original_text,extracted_content"
        f"&order=created_at.desc&limit={page}&offset={offset}"
    )
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def source_text(row: dict) -> str:
    # notice_service.py `_resolve_notice_source_text` 와 동일한 우선순위:
    # original_text 를 최우선으로 쓴다(운영 번역 파이프라인이 실제로 소비하는 값).
    original_text = row.get("original_text")
    if isinstance(original_text, str) and original_text.strip():
        return original_text.strip()
    extracted = row.get("extracted_content") or {}
    if isinstance(extracted, dict):
        refined = extracted.get("refined_text") or extracted.get("body_markdown")
        if isinstance(refined, str) and refined.strip():
            return refined.strip()
    return ""


def tags(text: str) -> dict:
    lowered = text.lower()
    return {
        "kind": (
            "meal-menu" if any(cue in text for cue in MEAL_CUES)
            else "event-consent-form" if any(cue in text for cue in CONSENT_CUES)
            else "safety-notice" if any(cue in text for cue in URGENT_CUES)
            else "general-notice"
        ),
        "length": "short" if len(text) < 600 else "medium" if len(text) < 1600 else "long",
        "fact_density": (
            "meal-heavy" if any(cue in text for cue in MEAL_CUES)
            else "date-and-fee-heavy" if any(cue in text for cue in FEE_CUES)
            else "action-heavy" if any(cue in text for cue in CONSENT_CUES)
            else "low"
        ),
        "tone": "urgent" if any(cue in text for cue in URGENT_CUES) else "routine",
        "audience": "school-wide",
        "time_reference": "absolute-dates" if re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text) else "no-deadline",
        "cultural_sensitivity": "critical-allergen" if "알레르기" in text else "neutral",
        "_needs_human_review": True,
    }


def slug(title: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title or "").strip("-").lower()
    return (cleaned[:32] or fallback).strip("-")


rows: list[dict] = []
offset = 0
while len(rows) < 4000:
    page = fetch(offset)
    if not page:
        break
    rows.extend(page)
    offset += len(page)
    if len(page) < 1000:
        break

seen: set[str] = set()
picked: list[dict] = []
for row in rows:
    text = source_text(row)
    if len(text) < 200:
        continue
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest in seen:
        continue
    seen.add(digest)
    picked.append({"row": row, "text": text, "tags": tags(text)})

# 다양성 확보: kind 별로 라운드로빈해 한 종류가 코퍼스를 독식하지 않게 한다.
by_kind: dict[str, list[dict]] = {}
for item in picked:
    by_kind.setdefault(item["tags"]["kind"], []).append(item)

selected: list[dict] = []
while len(selected) < TARGET_UNIQUE and any(by_kind.values()):
    for kind in sorted(by_kind):
        if by_kind[kind] and len(selected) < TARGET_UNIQUE:
            selected.append(by_kind[kind].pop(0))

print(f"조회 {len(rows)}건 → 고유 원문 {len(picked)}건 → 선정 {len(selected)}건")
for kind, items in sorted(by_kind.items()):
    used = sum(1 for s in selected if s["tags"]["kind"] == kind)
    print(f"  {kind:22s} 선정 {used} / 남음 {len(items)}")

if len(selected) < TARGET_UNIQUE:
    print(f"\n경고: 목표 {TARGET_UNIQUE}건에 미달했다. 중단하고 보고할 것.")

notices = []
for index, item in enumerate(selected, start=1):
    role = "held_out" if index % 3 == 0 else "training"
    folder = "held-out" if role == "held_out" else "training"
    notice_id = f"p{index:02d}-{slug(item['row'].get('title'), 'notice')}"
    entry = {
        "id": notice_id,
        "role": role,
        **{k: v for k, v in item["tags"].items() if not k.startswith("_")},
        "issuer": "(운영 공지 — 검토 시 기입)",
        "origin": "prod-notice",
        "prod_notice_id": item["row"]["id"],
        "needs_human_review": True,
        "source_path": f"notices/{folder}/{notice_id}/source.ko.md",
    }
    notices.append((entry, item["text"]))

manifest = {
    "iteration": "bedrock-001",
    "date": "2026-08-27",
    "target_languages": ["en", "ru", "ar"],
    "split": {
        "training": sum(1 for e, _ in notices if e["role"] == "training"),
        "held_out": sum(1 for e, _ in notices if e["role"] == "held_out"),
    },
    "notices": [entry for entry, _ in notices],
}

if not APPLY:
    print("\n미리보기입니다. 실제로 쓰려면 APPLY=1 을 붙여 다시 실행하세요.")
    sys.exit(0)

for entry, text in notices:
    path = ITER_DIR / entry["source_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    # validate_translation_iteration.py 가 각 통신문 폴더에 source-meta.json 을
    # 요구한다(존재 여부만 검사). manifest 항목의 핵심 필드를 그대로 옮겨 담는다.
    meta = {
        "origin": entry["origin"],
        "kind": entry["kind"],
        "issuer": entry["issuer"],
        "notes": f"운영 공지 원문(prod_notice_id={entry['prod_notice_id']}). 자동 추출 — 사람 검토 전.",
        "prod_notice_id": entry["prod_notice_id"],
    }
    (path.parent / "source-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

(ITER_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)

# validate_translation_iteration.py 가 요구하는 나머지 스캐폴드 디렉터리.
# 이 스크립트는 코퍼스(원문)만 만든다 — 평가/엔지니어링 산출물은 Task 3+ 의 몫이므로
# 빈 디렉터리로만 존재를 보장한다.
for required_dir in (
    ITER_DIR / "evaluation",
    ITER_DIR / "evaluation" / "held-out-detail",
    ITER_DIR / "engineering",
    ITER_DIR / "pipeline-output-after" / "training",
    ITER_DIR / "pipeline-output-after" / "held_out",
):
    required_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = required_dir / ".gitkeep"
    if not any(required_dir.iterdir()):
        gitkeep.write_text("", encoding="utf-8")

print(f"\n{len(notices)}건 기록 완료 → {ITER_DIR}")
