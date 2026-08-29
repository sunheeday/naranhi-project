# 번역 백엔드 Bedrock 이전 · 단건 지연 단축 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 번역 AI 호출을 사용자 현금(Gemini)에서 보유 크레딧(AWS Bedrock)으로 옮기고, 파이프라인 단건 지연을 134.7초에서 40초 이하로 내린다. 모든 교체는 `.agents/translation-quality/` 평가 장치를 통과해야 하고, 환경변수 한 줄로 언제든 Gemini로 되돌아갈 수 있어야 한다.

**Architecture:** 변수를 하나씩만 바꾸는 순서로 간다. ① 먼저 측정한다 — risk 게이트 분포와 평가 코퍼스를 확보하고 평가 하네스에 «arm(백엔드 후보)» 축을 붙인다 ② 백엔드와 무관한 이득을 먼저 회수한다(배치 대기 제거·SDK 결함 대응·낭비 콜 제거) ③ **thinking 축소를 Gemini에서 먼저** 해서 «thinking 효과»와 «모델 교체 효과»를 분리한다 ④ 스로틀 판정을 먼저 고친 뒤 Bedrock 백엔드를 다크 코드로 붙인다 ⑤ 워커만 → 전면 순으로 env를 뒤집는다 ⑥ 마지막에 백필과 단계 병합. 각 단계는 단독 롤백이 가능하다.

**Tech Stack:** Python 3.12, FastAPI, `google-genai` 1.73.1 (Vertex AI), `boto3`/`botocore` 1.43.78 (Bedrock Converse API), Supabase(Postgres), Cloud Run Service + Job, GitHub Actions, GCP Secret Manager

**Spec:** [docs/superpowers/specs/2026-08-27-B-bedrock-translation-design.md](../specs/2026-08-27-B-bedrock-translation-design.md)

## Global Constraints

- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests` (단일 모듈은 `PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.<모듈> -v`, 실행 확인됨)
  - 프론트: `npm run typecheck` + `npm run build` (**프론트 테스트 러너가 없다** — `package.json`에 test 스크립트 없음). 이 사업은 프론트를 건드리지 않으므로 프론트 검증이 필요한 Task는 없다.
- **이름 고정 3개**: `call_with_quota_backoff`, `_repair_invalid_json_escapes`(둘 다 `backend/app/translation/gemini_client.py`)는 크롤러(`crawler/gemini_finder.py:44, :249`, `crawler/unknown_post_resolver.py:289`)가 빌려 쓴다. **옮기거나 이름을 바꾸면 이 사업 밖이 깨진다.** `GeminiJsonClient`도 문서판독·크롤러 경로와 무관하게 그대로 남긴다.
- **프롬프트는 고정 변수**: `backend/app/translation/prompts.py`를 이 사업에서 **수정하지 않는다** (Task 14의 M1·M2는 프롬프트 병합이 아니라 실행 구조 변경으로 처리한다). 백엔드 A/B의 통제 조건이기 때문이다.
- **문서판독은 범위 밖**: `backend/extractor/extractors/gemini_document_extractor.py`와 `content_extraction_service.py:100, 178`은 손대지 않는다.
- **AWS 자격증명 취급**: 전용 IAM 사용자 `naranhi-bedrock`(모델 호출 권한만, 생성·검증 완료)의 키가 GCP Secret Manager에 있다 — `aws-bedrock-access-key-id`, `aws-bedrock-secret-access-key`. **값을 명령줄 인자·URL·출력에 넣지 않는다.** 로컬 시험은 `gcloud secrets versions access latest --secret=<이름>`을 환경변수로 받아 쓰고, Cloud Run은 `--set-secrets`로만 주입한다. AdministratorAccess를 쓰지 않는다.
- **모델 선택 정책 (스펙 §5.10)** — 이 사업 전체에 적용된다:
  - **Haiku 기본.** `global.anthropic.claude-haiku-4-5-20251001-v1:0`이 설정 기본값이고 arm 순서의 1순위다.
  - **Sonnet은 «정말 필요할 때만» 승급.** Haiku가 게이트(G1~G6)를 못 넘을 때만 `global.anthropic.claude-sonnet-4-6`으로 올린다. 승급 근거는 인상이 아니라 **게이트 산출물**이어야 한다.
  - **🔴 Opus 금지.** `claude-opus-*`는 이 계획의 어느 Step에서도 쓰지 않는다 — 후보 표·arm·설정 기본값·예시 코드·시험 명령 어디에도 넣지 않는다. 사용자 지시이고 근거는 비용이다. Sonnet으로도 게이트를 못 넘으면 모델을 더 올리는 게 아니라 프롬프트·단계 설계를 다시 본다(별건).
  - **🔴 Nova는 한국어 본문 생성 경로에서 제외.** 2026-08-27 실측에서 Nova Lite·Nova Pro가 **읽지 못한 첨부의 본문을 지어냈다**(스펙 §5.9.2). 완전 삭제가 아니라 **용도 제한**이다 — 출력이 닫힌 집합이고 환각을 코드가 검출할 수 있는 자리(분류·라우팅·플래그)에서만 후보로 남긴다. **이 사업의 단계는 전부 그 반대라 Nova를 쓰는 자리가 없다.**
- **`global.` 라우팅 허용됨**: 열린 질문 Q1이 **해결됐다 — 사용자 승인**(스펙 §16 해결됨). `apac.` 전용 제약은 풀렸다. 다만 학교 공지에는 학생 이름·학년반·보호자 연락처가 섞이므로 **어느 추론 프로필을 호출했는지 로그에 남긴다**(스펙 §5.11 C3). 허용 범위가 바뀌면 `apac.` 계열로 되돌릴 수 있어야 한다.
- **읽기 전용 DB 접근**: Task 1·2·13의 운영 조회는 전부 읽기 전용이다. `SUPABASE_SERVICE_ROLE_KEY`는 GCP Secret Manager에서 환경변수로 받는다.
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식. 저장소 관례(`fix:`, `feat:`, `perf:`, `refactor:`, `chore:`, `ci:`, `docs:`)를 따른다.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `scripts/probe_risk_profile_levels.py` | 운영의 `raw_steps.risk_profile.level` 분포 조회 | 신규 (Task 1) |
| `scripts/build_eval_corpus_from_prod.py` | 운영 공지에서 평가 코퍼스 이터 폴더 생성 | 신규 (Task 2) |
| `scripts/run_iteration.py` | 이터 러너 — arm 축·`wall_seconds` 추가 | 수정 (Task 3) |
| `scripts/check_iteration_blind.py` | 평가 산출물에 모델명이 새어나갔는지 검사 | 신규 (Task 3) |
| `.agents/translation-quality/iterations/2026-08-27_iter-negative-control/` | **판독 불가 입력 fixture** — 지어내는지 보는 통제군 | 신규 (Task 2) |
| `scripts/check_hallucination.py` | **게이트 G6** — negative control 산출물에서 지어낸 사실을 센다 | 신규 (Task 7) |
| `.agents/translation-quality/iterations/<iter>/arms.json` | arm ↔ 백엔드 매핑 (평가자 비열람) | 신규 (Task 3·7·11) |
| `backend/app/jobs/translation_worker.py` | 배치 gather → 소비자 + top-up claim | 수정 (Task 4) |
| `backend/app/translation/gemini_client.py` | keepalive/재시도 노브, 스로틀 마커 확장 | 수정 (Task 5·8) |
| `backend/app/services/notice_service.py` | 카드 메타데이터 플래그, 팩토리 배선 | 수정 (Task 6·11) |
| `backend/app/translation/orchestrator.py` | dead path 삭제, thinking 예산 주입, 단계 병합 | 수정 (Task 6·7·14) |
| `backend/app/core/config.py` | `TRANSLATION_*` / `BEDROCK_*` 설정 | 수정 (Task 7·9) |
| `backend/app/translation/json_client.py` | `JsonModelClient` 프로토콜 + `build_json_client` 팩토리 | 신규 (Task 9) |
| `backend/app/translation/bedrock_client.py` | `BedrockJsonClient` — Converse + 전용 executor | 신규 (Task 10) |
| `backend/requirements.txt` | `boto3` 추가 | 수정 (Task 10) |
| `.github/workflows/deploy-api-cloud-run.yml` | AWS 시크릿 주입, `TRANSLATION_BACKEND` env | 수정 (Task 11·12·13) |
| `scripts/requeue_translations.py` | 기존 번역 155건 재큐잉 백필 | 신규 (Task 13) |
| `backend/tests/test_worker_slot_topup.py` | 슬롯 top-up 회귀 | 신규 (Task 4) |
| `backend/tests/test_best_effort_card_metadata_flag.py` | 메타데이터 플래그 회귀 | 신규 (Task 6) |
| `backend/tests/test_orchestrator_thinking_budget_setting.py` | thinking 예산 주입 회귀 | 신규 (Task 7) |
| `backend/tests/test_gemini_quota_backoff.py` | 스로틀 마커 확장 | 수정 (Task 8) |
| `backend/tests/test_json_client_factory.py` | 팩토리 분기 회귀 | 신규 (Task 9) |
| `backend/tests/test_bedrock_json_client.py` | 요청 조립·프리필·thinking OFF·executor | 신규 (Task 10) |
| `backend/tests/test_orchestrator_parallel_thinking.py` | 기존 thinking 회귀 — 상수 변경 반영 | 수정 (Task 7) |

---

## 배포 순서 (스펙 §12 그대로)

```
Task 1   risk level 분포 측정            (코드 변경 0)
Task 2   평가 코퍼스 확장 12 → 30+       (코드 변경 0)
Task 3   B1 평가 하네스 arm 축
Task 4   B2 배치 대기 제거
Task 5   Gemini SDK 결함 대응 (#2705·#1875)
Task 6   B3 낭비 제거
Task 7   B4 thinking 축소                ← 게이트 §4.6
Task 8   스로틀 판정 확장                 ← Bedrock 필수 선행
Task 9   JsonModelClient 프로토콜·팩토리 (다크)
Task 10  BedrockJsonClient
Task 11  호출부 배선 + Bedrock arm 평가   ← 게이트 §4.6
Task 12  B6 워커만 Bedrock
Task 13  B7 전면 Bedrock + B9 백필 155건
Task 14  B8 단계 병합 M1 + M2            ← 게이트 §4.6
```

**Task 7이 Task 10보다 앞인 이유가 이 계획의 핵심 판단이다.** thinking OFF는 Gemini에서 설정 한 줄로 얻어지고 예상 개선폭이 −75%다. Bedrock으로 옮기면 이 이득이 자동으로 딸려온다(Claude extended thinking은 기본 OFF). 순서를 뒤집으면 «thinking 효과»와 «모델 교체 효과»가 뭉쳐서, 나중에 품질이 흔들렸을 때 어느 쪽이 원인인지 알 수 없다.

**Task 8이 Task 10보다 앞인 이유:** `is_quota_exhausted_error`(`gemini_client.py:27-32`)가 Bedrock `ThrottlingException`을 못 잡는다. 그대로 두고 Bedrock을 붙이면 백오프가 한 번도 동작하지 않고 429가 잡 실패로 직행한다.

---

## Task 1: risk 게이트 분포 측정 (코드 변경 0)

스펙 §1.5(b)는 «저위험 경로(`orchestrator.py:186-231`)가 dead path다»를 **추정**으로 적었다. Task 6이 그 46줄을 지우기 전에 수치를 확보한다. `risk_profile`은 `orchestrator.py:229`·`:359`에서 `raw_steps`에 저장되므로 읽기 전용 조회로 셀 수 있다.

**Files:**
- Create: `scripts/probe_risk_profile_levels.py`

**Interfaces:**
- Consumes: 운영 Supabase `notice_ai_translations.raw_steps` (읽기 전용)
- Produces: `low` / `high` 건수와 비율. Task 6 Step 5의 dead path 삭제 여부를 결정한다.

- [ ] **Step 1: 컬럼이 실제로 있는지부터 확인한다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=id,raw_steps&limit=1')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
print('행 수:', len(rows))
print('raw_steps 키:', sorted((rows[0].get('raw_steps') or {}).keys()) if rows else '(없음)')
"
```

Expected: `raw_steps 키:`에 `risk_profile`이 포함된다. **없으면 중단하고 보고할 것** — 스펙의 저장 위치 가정이 틀렸다는 뜻이고, Task 6 Step 5를 실행하면 안 된다.

- [ ] **Step 2: 분포 조회 스크립트를 쓴다**

`scripts/probe_risk_profile_levels.py`:

```python
"""운영 번역본의 raw_steps.risk_profile.level 분포를 센다. 읽기 전용.

스펙 §1.5(b)의 «저위험 경로는 dead path다» 추정을 확정하기 위한 조회다.
low 비율이 0%에 가까우면 orchestrator.py:186-231 을 삭제해도 동작 변화가 없다.
"""
import json
import os
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PAGE = 1000


def fetch(offset: int) -> list[dict]:
    path = f"/rest/v1/notice_ai_translations?select=id,target_language,raw_steps&limit={PAGE}&offset={offset}"
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


levels = Counter()
reasons = Counter()
total = 0
offset = 0

while True:
    rows = fetch(offset)
    if not rows:
        break
    for row in rows:
        total += 1
        raw = row.get("raw_steps") or {}
        profile = raw.get("risk_profile") if isinstance(raw, dict) else None
        if not isinstance(profile, dict):
            levels["(risk_profile 없음)"] += 1
            continue
        levels[str(profile.get("level") or "(level 없음)")] += 1
        for reason in profile.get("reasons") or []:
            reasons[str(reason)] += 1
    offset += len(rows)
    if len(rows) < PAGE:
        break

print(f"=== 번역본 {total}건 ===")
for level, count in levels.most_common():
    share = (count / total * 100) if total else 0.0
    print(f"  {level:24s} {count:5d}  ({share:.1f}%)")

print("\n=== high 판정 사유 상위 10 ===")
for reason, count in reasons.most_common(10):
    print(f"  {reason:44s} {count}")

low = levels.get("low", 0)
print(f"\n결론: low = {low}건")
if low == 0:
    print("→ 저위험 분기는 실행된 적이 없다. Task 6 Step 5(dead path 삭제) 진행 가능.")
else:
    print("→ 저위험 분기가 실제로 실행된다. Task 6 Step 5 를 건너뛰고 보고할 것.")
```

- [ ] **Step 3: 돌려서 수치를 확보한다**

```bash
python scripts/probe_risk_profile_levels.py
```

Expected: `risk_profile 있음` 건이 대다수이고 `low = 0건`. **`low`가 1건이라도 나오면 Task 6 Step 5를 실행하지 말고 보고할 것.**

- [ ] **Step 4: 커밋**

```bash
git add scripts/probe_risk_profile_levels.py
git commit -m "chore(translation): risk_profile level 분포 조회 스크립트 추가

스펙 §1.5(b)의 «저위험 경로는 dead path다» 는 추정이었다.
orchestrator.py:186-231 을 지우기 전에 수치로 확정하기 위한 읽기 전용 조회다.

raw_steps.risk_profile 은 orchestrator.py:229/:359 가 저장한다.
low 가 0건이면 그 46줄은 동작 변화 없이 삭제 가능하다."
```

---

## Task 2: 평가 코퍼스 확장 (고유 12 → 30건 이상)

실측(2026-08-27) `source.ko.md` 30개 중 **내용 기준 고유 공지는 12건**이고, 시드 6건은 `"origin": "mock-seed-v1"` — 실제 크롤 공지가 아니라 합성 목업이다. arm 하나당 판정 단위가 12공지 × 3언어 = 36건이면 8축 0–5 척도에서 0.2점 차이는 잡음 구간 안이다. Task 7·11·14의 게이트가 «블로우업 탐지기»에 머물지 않으려면 이게 선행이다.

**Files:**
- Create: `scripts/build_eval_corpus_from_prod.py`
- Create: `.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/` (스크립트가 생성)
- Create: `.agents/translation-quality/iterations/2026-08-27_iter-negative-control/` (Step 8 — 게이트 G6 입력)

**Interfaces:**
- Consumes: 운영 `notices` 테이블의 한국어 원문 (읽기 전용)
- Produces: `manifest.json` + `notices/{training,held-out}/<id>/source.ko.md`. Task 3의 `run_iteration.py --arm`이 두 폴더를 모두 소비한다. 정상 코퍼스는 `compare_arms.py`(G1·G4·G5)가, negative control은 `check_hallucination.py`(G6)가 채점한다.

- [ ] **Step 1: 현재 코퍼스 규모를 기록으로 남긴다 (기준점)**

```bash
python -c "
import hashlib, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
root = pathlib.Path('.agents/translation-quality/iterations')
paths = sorted(root.glob('*/notices/*/*/source.ko.md'))
digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
print(f'source.ko.md 파일: {len(paths)} | 내용 기준 고유: {len(digests)}')
"
```

Expected: `source.ko.md 파일: 30 | 내용 기준 고유: 12`

- [ ] **Step 2: 코퍼스 생성 스크립트를 쓴다**

`scripts/build_eval_corpus_from_prod.py`:

```python
"""운영 공지의 한국어 원문으로 평가 이터레이션 폴더를 만든다. 읽기 전용 조회.

다양성 매트릭스(.agents/translation-quality/workflow.md)를 사람이 채우기 쉽도록
manifest 의 태그는 자동 추정값으로 채워두고, 착수 전에 사람이 검토·수정한다.
held-out 비율은 workflow.md 정책(대략 1/3)을 따른다.

APPLY=1 일 때만 파일을 쓴다. 기본은 미리보기.
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
        f"/rest/v1/notices?select=id,title,content_text,extracted_content"
        f"&order=created_at.desc&limit={page}&offset={offset}"
    )
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def source_text(row: dict) -> str:
    extracted = row.get("extracted_content") or {}
    if isinstance(extracted, dict):
        refined = extracted.get("refined_text") or extracted.get("body_markdown")
        if isinstance(refined, str) and refined.strip():
            return refined.strip()
    text = row.get("content_text")
    return text.strip() if isinstance(text, str) else ""


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

(ITER_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"\n{len(notices)}건 기록 완료 → {ITER_DIR}")
```

- [ ] **Step 3: 미리보기로 규모와 다양성을 본다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python scripts/build_eval_corpus_from_prod.py
```

Expected: `선정 30건`, kind가 3종 이상으로 분산. **선정이 30건에 미달하면 중단하고 보고할 것** — 코퍼스가 여전히 게이트를 지탱하지 못한다는 뜻이다.

- [ ] **Step 4: 실제로 기록한다**

```bash
APPLY=1 python scripts/build_eval_corpus_from_prod.py
```

Expected: `30건 기록 완료 → .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001`

- [ ] **Step 5: 기존 검증기를 통과하는지 확인한다**

```bash
python scripts/validate_translation_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001
```

Expected: 오류 없음. training/held_out 두 role이 모두 존재해야 통과한다(검증기가 강제).

- [ ] **Step 6: 고유 공지 수가 실제로 늘었는지 확인한다**

```bash
python -c "
import hashlib, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
root = pathlib.Path('.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001')
paths = sorted(root.glob('notices/*/*/source.ko.md'))
digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
print(f'신규 이터 파일 {len(paths)} | 고유 {len(digests)}')
assert len(digests) >= 30, '고유 공지가 30 미만'
print('OK')
"
```

Expected: `고유 30` 이상 + `OK`

- [ ] **Step 7: 사람이 태그를 검토한다 (자동 추정값 확정)**

`manifest.json`의 각 항목은 `"needs_human_review": true`로 표시되어 있다. 다양성 매트릭스(`workflow.md`의 kind·length·fact_density·tone·audience·time_reference·cultural_sensitivity)를 훑고, 자동 추정이 틀린 항목을 고친 뒤 `needs_human_review`를 지운다.

```bash
python -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
m = json.load(open('.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/manifest.json', encoding='utf-8'))
left = [n['id'] for n in m['notices'] if n.get('needs_human_review')]
print('검토 남은 항목:', len(left))
print(*left[:10], sep='\n')
"
```

Expected: 검토를 마치면 `검토 남은 항목: 0`

- [ ] **Step 8: 환각 negative control 코퍼스를 만든다 (게이트 G6의 입력)**

정상 코퍼스는 «잘 번역하는가»만 잰다. 2026-08-27 실측이 보여준 실패 모드는 그 축에 안 걸린다 — 모델이 **읽지 못했는데 «못 읽겠다»고 말하는 대신 그럴듯한 가정통신문을 지어냈다**(스펙 §5.9.2·§4.7). 지어낸 글은 문장이 매끄러워서 8축 평가에서 오히려 높은 점수를 받는다.

그래서 **판독 불가능한 입력만 담은 별도 이터 폴더**를 만든다. 러너·검증기·arm 축을 그대로 쓰되 채점만 다르게 한다(Task 7 Step 10의 `check_hallucination.py`).

> **왜 별도 폴더인가**: 정상 코퍼스에 섞으면 `compare_arms.py`의 G1(hard_fact 하락)이 이 fixture들에서 의미 없이 흔들린다. 폴더를 가르면 정상 게이트와 환각 게이트가 서로를 오염시키지 않는다.

```bash
ITER=.agents/translation-quality/iterations/2026-08-27_iter-negative-control
mkdir -p "$ITER"/notices/training/n01-attachment-only \
         "$ITER"/notices/training/n02-ocr-garbage \
         "$ITER"/notices/held-out/n03-separator-only

# n01 — 본문 없이 첨부만 있는 공지. 운영에서 가장 흔한 판독 실패 형태다.
cat > "$ITER"/notices/training/n01-attachment-only/source.ko.md <<'EOF'
[본문 사진.png]
EOF

# n02 — OCR 이 깨진 출력. 글자는 있지만 뜻이 없다.
cat > "$ITER"/notices/training/n02-ocr-garbage/source.ko.md <<'EOF'
ㅁ ㄴ ㅇ ㄹ ㅎ ㅅ  ￭￭￭  ?? ?? ??
ᄀᄂᄃ ᅡᅵᅳ  ￮￮  ...  ㅇ ㅇ ㅇ
EOF

# n03 — 구분선과 공백만. 추출은 성공했지만 담긴 내용이 없다.
cat > "$ITER"/notices/held-out/n03-separator-only/source.ko.md <<'EOF'
---

　

---
EOF

cp .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json "$ITER"/arms.json
```

> **`arms.json`은 본 이터 폴더에서 복사한다.** arm은 이터 폴더 단위로 정의되므로, Task 7·11이 arm을 추가할 때마다 **두 폴더를 같이 갱신해야 한다.** 어긋나면 `--arm`이 `arm not found`로 죽으니 조용히 틀리지는 않는다.

manifest를 쓴다:

```bash
python -c "
import json, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
iter_dir = pathlib.Path('.agents/translation-quality/iterations/2026-08-27_iter-negative-control')
notices = [
    ('n01-attachment-only', 'training',  'attachment-only', '첨부만 있고 본문이 없다'),
    ('n02-ocr-garbage',     'training',  'ocr-garbage',     'OCR 이 깨져 뜻이 없다'),
    ('n03-separator-only',  'held_out',  'separator-only',  '구분선과 공백뿐이다'),
]
manifest = {
    'iteration': 'negative-control-001',
    'date': '2026-08-27',
    'purpose': '게이트 G6 — 판독 불가 입력에 대해 모델이 «못 읽겠다»고 답하는지, 지어내는지를 본다.',
    'scoring': 'scripts/check_hallucination.py (compare_arms.py 로 채점하지 않는다)',
    'target_languages': ['en', 'ru', 'ar'],
    'split': {'training': 2, 'held_out': 1},
    'notices': [
        {
            'id': nid, 'role': role, 'kind': 'negative-control',
            'failure_mode': mode, 'note': note,
            'length': 'short', 'fact_density': 'none', 'tone': 'routine',
            'audience': 'school-wide', 'time_reference': 'no-deadline',
            'cultural_sensitivity': 'neutral',
            'issuer': '(합성 — 판독 실패 형태 재현)',
            'origin': 'negative-control-v1',
            'expected_behavior': '본문을 생성하지 않는다. 날짜·금액·인명·행사명을 만들어내지 않는다.',
            'source_path': f\"notices/{'held-out' if role == 'held_out' else 'training'}/{nid}/source.ko.md\",
        }
        for nid, role, mode, note in notices
    ],
}
(iter_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('negative control manifest 기록:', len(manifest['notices']), '건')
"
```

Expected: `negative control manifest 기록: 3 건`

- [ ] **Step 9: negative control 폴더가 기존 검증기를 통과하는지 확인한다**

```bash
python scripts/validate_translation_iteration.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-negative-control
```

Expected: 오류 없음 (training/held_out 두 role이 모두 있다).

> **검증기가 «본문이 너무 짧다» 류로 거부하면 중단하고 보고할 것.** 그 경우 negative control은 검증기 밖에서 돌려야 하고, Task 7 Step 10의 실행 경로를 그에 맞춰 고쳐야 한다. **fixture를 길게 늘려 통과시키지 않는다** — 짧고 비어 있다는 것이 이 fixture의 전부다.

- [ ] **Step 10: 커밋**

```bash
git add scripts/build_eval_corpus_from_prod.py .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001 \
  .agents/translation-quality/iterations/2026-08-27_iter-negative-control
git commit -m "test(translation): 평가 코퍼스를 실제 운영 공지 30건으로 확장

기존 코퍼스는 고유 12건이고 그중 시드 6건이 합성 목업(origin: mock-seed-v1)이었다.
arm 하나당 판정 단위가 12공지 × 3언어 = 36건이면 8축 0-5 척도에서
0.2점 차이가 잡음 구간 안이라, 게이트가 «망가졌는지» 만 잡고
«미세하게 나빠졌는지» 는 못 잡는다.

운영 공지에서 sha256 중복을 걷어내고 kind 별 라운드로빈으로 30건을 골랐다.
held-out 비율은 workflow.md 정책대로 약 1/3 을 유지한다.
다양성 태그는 자동 추정 후 사람이 검토했다.

환각 negative control 폴더도 함께 만든다(게이트 G6).
2026-08-27 실측에서 Nova Lite·Nova Pro 가 QR 코드 이미지와 PDF 를
읽지 못한 채 «교장 김 교장입니다» 같은 본문을 지어냈다.
지어낸 글은 문장이 매끄러워 8축 평가에서 오히려 점수가 높다 —
즉 «잘 번역하는가» 축으로는 잡히지 않는다.

판독 불가 입력 3종(첨부만·OCR 깨짐·구분선뿐)을 따로 두고,
«못 읽겠다» 고 답하는지 지어내는지를 별도로 센다.
정상 코퍼스에 섞지 않는 이유는 G1(hard_fact 하락)이
이 fixture 에서 의미 없이 흔들리기 때문이다."
```

---

## Task 3: B1 — 평가 하네스에 arm 축 · 블라인드 · 지연 기록

기존 이터 폴더는 «프롬프트 변경 전/후»를 비교하도록 되어 있다(`pipeline-output/` vs `pipeline-output-after/`). 여기서는 **같은 프롬프트 × 여러 백엔드**를 비교해야 한다. 그리고 `scores.json`에 시간 필드가 없어 지연 비교가 불가능하다.

**Files:**
- Modify: `scripts/run_iteration.py:75-193` (`--arm` 인자, 출력 경로, `wall_seconds`)
- Create: `scripts/check_iteration_blind.py`
- Create: `.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json`

**Interfaces:**
- Consumes: Task 2가 만든 이터 폴더
- Produces: `notices/<role>/<id>/pipeline-output/<arm>/{en,ru,ar}.json` (각 json에 `wall_seconds` 키), `_pipeline_run_summary.<arm>.json`. Task 7·11·14의 게이트가 이 산출물을 읽는다.

- [ ] **Step 1: arm 정의 파일을 만든다 (기준선 1개로 시작)**

`.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json`:

```json
{
  "note": "평가자 에이전트는 이 파일을 읽지 않는다. arm↔백엔드 매핑을 가려 블라인드 평가를 성립시킨다.",
  "arms": [
    {
      "id": "arm-a",
      "label": "baseline-gemini-2.5-flash",
      "env": {}
    }
  ]
}
```

> arm-b(thinking OFF)는 Task 7이, arm-c/d/e(Bedrock — **Haiku 기본 / Sonnet 승급 / 혼합**)는 Task 11이 추가한다. 각 arm은 **환경변수만으로** 정의된다 — 코드 분기가 아니라서 같은 커밋에서 여러 arm을 돌릴 수 있다.
>
> **arm을 추가할 때마다 negative control 폴더의 `arms.json`도 같이 갱신한다**(Task 2 Step 8). arm은 이터 폴더 단위로 정의되므로 한쪽만 고치면 G6 실행이 `arm not found`로 죽는다.
>
> **Nova arm과 Opus arm은 만들지 않는다** — Global Constraints 참조.

- [ ] **Step 2: 러너에 `--arm`을 붙인다 (실패를 먼저 본다)**

```bash
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ \
  --arm arm-a --only p01
```

Expected: `error: unrecognized arguments: --arm` + 종료코드 2

- [ ] **Step 3: 러너를 고친다**

`scripts/run_iteration.py`의 import 블록(36~41행) 바로 아래에 추가:

```python
def _apply_arm_env(iter_dir: Path, arm_id: str) -> dict:
    """arms.json 의 env 를 프로세스 환경에 적용하고 arm 정의를 돌려준다.

    get_settings 는 lru_cache 라 환경을 바꾼 뒤 반드시 캐시를 비워야 한다.
    """
    arms_path = iter_dir / "arms.json"
    if not arms_path.is_file():
        raise SystemExit(f"ERROR: arms.json not found at {arms_path}")
    arms = json.loads(arms_path.read_text(encoding="utf-8")).get("arms") or []
    for arm in arms:
        if arm.get("id") == arm_id:
            for key, value in (arm.get("env") or {}).items():
                os.environ[key] = str(value)
            get_settings.cache_clear()
            return arm
    raise SystemExit(f"ERROR: arm '{arm_id}' not found in {arms_path}")
```

`main()`의 인자 선언(78~87행 부근)에 추가:

```python
    parser.add_argument(
        "--arm",
        default=None,
        help="arms.json 의 arm id. 지정하면 pipeline-output/<arm>/ 아래에 쓴다.",
    )
```

`manifest` 로드 직후(96행 부근)에 추가:

```python
    arm = _apply_arm_env(iter_dir, args.arm) if args.arm else None
```

`out_dir` 결정(132행)을 교체:

```python
        out_dir = source_path.parent / "pipeline-output"
        if args.arm:
            out_dir = out_dir / args.arm
        out_dir.mkdir(parents=True, exist_ok=True)
```

언어 루프의 `result` 저장(168~171행) 직전에 `wall_seconds`를 심는다:

```python
            wall_seconds = round(time.time() - t0, 2)
            if isinstance(result, dict):
                result["wall_seconds"] = wall_seconds
```

그리고 언어별 요약(172~175행)에도 넣는다:

```python
            notice_summary["languages"][lang] = {
                "status": result.get("status"),
                "validation": result.get("validation"),
                "wall_seconds": wall_seconds,
            }
```

마지막으로 요약 파일명(181행)을 arm별로 가른다:

```python
    summary_name = f"_pipeline_run_summary.{args.arm}.json" if args.arm else "_pipeline_run_summary.json"
    (iter_dir / summary_name).write_text(
        json.dumps(
            {"arm": args.arm, "elapsed_seconds": round(elapsed, 1), "notices": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 4: 기준선 arm을 1건만 돌려 형태를 확인한다**

```bash
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ \
  --arm arm-a --only p01-$(python -c "
import json
m=json.load(open('.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/manifest.json',encoding='utf-8'))
print(m['notices'][0]['id'].split('-',1)[1])
")
```

Expected: `pipeline-output/arm-a/{en,ru,ar}.json` 3개 생성. 각 json에 `wall_seconds` 키가 있고 `status`가 `ready_to_save`.

- [ ] **Step 5: 블라인드 검사기를 쓴다**

`scripts/check_iteration_blind.py`:

```python
"""평가 산출물에 모델·백엔드 이름이 새어나갔는지 검사한다. CI/게이트용.

평가자는 어느 arm 이 어느 모델인지 몰라야 한다. arms.json 은 검사 대상에서 제외한다
(그 파일이 매핑을 보관하는 자리이고, 평가자는 읽지 않기로 되어 있다).
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

FORBIDDEN = ("gemini", "vertex", "nova", "claude", "bedrock", "anthropic", "amazon")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    args = parser.parse_args()

    targets = sorted((args.iter_dir / "evaluation").rglob("*.md"))
    targets += sorted((args.iter_dir / "evaluation").rglob("*.json"))
    if not targets:
        print(f"ERROR: 평가 산출물이 없다: {args.iter_dir / 'evaluation'}", file=sys.stderr)
        return 2

    failed = False
    for path in targets:
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        hits = [word for word in FORBIDDEN if word in lowered]
        if hits:
            print(f"블라인드 위반 {path}: {', '.join(hits)}")
            failed = True

    if failed:
        print("\n블라인드 검사 실패 — 평가자가 모델 정체를 알고 있었다는 뜻이다.")
        return 1

    print(f"평가 산출물 {len(targets)}개, 모델명 노출 0건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: 검사기가 실제로 잡는지 확인한다**

```bash
mkdir -p /tmp/blindprobe/evaluation
echo "arm-a used gemini-2.5-flash" > /tmp/blindprobe/evaluation/feedback-report.md
python scripts/check_iteration_blind.py --iter-dir /tmp/blindprobe; echo "종료코드: $?"
echo "arm-a scored 4.2" > /tmp/blindprobe/evaluation/feedback-report.md
python scripts/check_iteration_blind.py --iter-dir /tmp/blindprobe; echo "종료코드: $?"
rm -rf /tmp/blindprobe
```

Expected: 첫 번째 `블라인드 위반 ... gemini` + 종료코드 1, 두 번째 `모델명 노출 0건` + 종료코드 0

- [ ] **Step 7: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과 (러너 스크립트 변경은 백엔드 코드와 무관하지만, 이 Task 이후 모든 Task가 이 명령을 기준으로 한다)

- [ ] **Step 8: 커밋**

```bash
git add scripts/run_iteration.py scripts/check_iteration_blind.py .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json
git commit -m "test(translation): 평가 하네스에 arm 축 · 블라인드 검사 · wall_seconds 추가

기존 이터 폴더는 «프롬프트 변경 전/후» 비교용이었다. 백엔드 A/B 는
«같은 프롬프트 × 여러 백엔드» 라 축이 다르다.

arm 은 환경변수만으로 정의한다 — 코드 분기가 아니라서 같은 커밋에서
여러 arm 을 돌릴 수 있고, 프롬프트가 통제 조건으로 고정된다.
get_settings 가 lru_cache 라 env 적용 후 캐시를 비운다.

scores.json 에 시간 필드가 없어 지연 비교가 불가능했다.
드라이버가 언어별 wall_seconds 를 결과 json 과 요약에 남긴다.

블라인드는 기존 워크플로에 없던 개념이다 — held-out(일반화)은 있어도
평가자가 모델 정체를 모르게 하는 장치는 없었다. 검사기로 강제한다."
```

---

## Task 4: B2 — 배치 대기 제거 (슬롯 top-up 구조)

`translation_worker.py:113`의 `await asyncio.gather(...)`가 배치 10잡 **전원 완료**를 기다린 뒤 다음 배치를 claim한다(`:82`). 잡 소요가 100~155초로 흩어지므로 먼저 끝난 슬롯이 가장 느린 잡을 기다리며 논다 — 유휴율 ≈23%, 처리량 +29% 여지.

**단건 지연은 변하지 않는다.** 이건 처리량 단위다.

**Files:**
- Modify: `backend/app/jobs/translation_worker.py:67-115` (`process_jobs`)
- Test: `backend/tests/test_worker_slot_topup.py`

**Interfaces:**
- Consumes: `JobQueueService.claim(job_types=..., limit=...)` (동기), `complete`, `fail`
- Produces: `process_jobs(...) -> int` — 시그니처 불변. 호출부(`run_async`, 기존 테스트 4종)는 그대로 동작해야 한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_worker_slot_topup.py`:

```python
import asyncio
import unittest
from unittest.mock import patch

from app.jobs.translation_worker import process_jobs


class _SlowFastQueue:
    """느린 잡 1개 + 빠른 잡 1개를 준 뒤, 이후 claim 에는 추가 잡을 계속 내준다.

    배치 대기 구조라면 느린 잡이 끝날 때까지 두 번째 claim 이 오지 않는다.
    top-up 구조라면 빠른 잡이 끝난 직후 claim 이 한 번 더 온다.
    """

    def __init__(self) -> None:
        self.claims: list[int] = []
        self._served = 0

    def reclaim_stale_jobs(self, *, job_types, stale_seconds):  # noqa: ANN001, ANN201, ARG002
        return 0

    def claim(self, *, job_types, limit):  # noqa: ANN001, ARG002
        self.claims.append(limit)
        if self._served == 0:
            self._served = 2
            return [_job("slow"), _job("fast")]
        if self._served < 4:
            self._served += 1
            return [_job(f"extra-{self._served}")]
        return []

    def complete(self, job_id, *, result=None):  # noqa: ANN001, ARG002
        return None

    def fail(self, job, *, error, retry_delay_seconds):  # noqa: ANN001, ARG002
        raise AssertionError(f"fail should not be called: {error}")


def _job(job_id: str) -> dict[str, object]:
    return {"id": job_id, "payload": {"notice_id": job_id, "target_language": "en"}}


class SlotTopUpTest(unittest.IsolatedAsyncioTestCase):
    async def test_claims_again_before_slow_job_finishes(self) -> None:
        queue = _SlowFastQueue()
        slow_release = asyncio.Event()
        claims_when_slow_running: list[int] = []

        async def fake_run(job):  # noqa: ANN001
            if job["id"] == "slow":
                await slow_release.wait()
                return {}
            await asyncio.sleep(0)
            claims_when_slow_running.append(len(queue.claims))
            return {}

        with (
            patch("app.jobs.translation_worker.JobQueueService", return_value=queue),
            patch("app.jobs.translation_worker._run_job", side_effect=fake_run),
        ):
            task = asyncio.create_task(
                process_jobs(max_jobs=0, batch_size=2, retry_delay_seconds=120, stale_seconds=3600)
            )
            for _ in range(60):
                await asyncio.sleep(0)
                if len(queue.claims) >= 2:
                    break
            self.assertGreaterEqual(
                len(queue.claims), 2, "느린 잡이 끝나기 전에 두 번째 claim 이 와야 한다"
            )
            slow_release.set()
            processed = await asyncio.wait_for(task, timeout=2.0)

        self.assertEqual(processed, 4)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_worker_slot_topup -v
```

Expected: FAIL — `느린 잡이 끝나기 전에 두 번째 claim 이 와야 한다` (현재는 gather가 느린 잡을 기다린다)

- [ ] **Step 3: `process_jobs`를 소비자 + top-up 구조로 바꾼다**

`backend/app/jobs/translation_worker.py:67-115`의 `process_jobs` 전체를 아래로 교체한다:

```python
async def process_jobs(
    *,
    max_jobs: int,
    batch_size: int,
    retry_delay_seconds: int,
    stale_seconds: int,
    idle_grace_seconds: float = 0.0,
) -> int:
    queue = JobQueueService()
    queue.reclaim_stale_jobs(job_types=[JOB_TYPE], stale_seconds=stale_seconds)

    slots = max(1, batch_size)
    pending: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    counters = {"claimed": 0, "processed": 0, "in_flight": 0}
    slot_freed = asyncio.Event()

    async def _process_one(job: dict[str, object]) -> None:
        try:
            result = await _run_job(job)
            queue.complete(str(job["id"]), result=serialize_job_result(result))
            LOGGER.info("translation worker job completed: job_id=%s", job.get("id"))
        except asyncio.CancelledError as exc:
            LOGGER.warning("translation worker job cancelled: job_id=%s", job.get("id"))
            queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("translation worker job failed: job_id=%s", job.get("id"))
            queue.fail(job, error=f"{type(exc).__name__}: {exc}", retry_delay_seconds=retry_delay_seconds)

    async def _consumer() -> None:
        while True:
            job = await pending.get()
            if job is None:
                return
            counters["in_flight"] += 1
            try:
                await _process_one(job)
            finally:
                counters["in_flight"] -= 1
                counters["processed"] += 1
                slot_freed.set()

    consumers = [asyncio.create_task(_consumer()) for _ in range(slots)]
    grace_used = False

    try:
        while True:
            remaining = slots if max_jobs <= 0 else max_jobs - counters["claimed"]
            free = slots - (pending.qsize() + counters["in_flight"])
            limit = min(free, remaining)
            # claim 은 동기 DB 왕복이다. 매 완료마다 하면 왕복이 늘어나므로
            # 여유 슬롯이 절반 이상 났을 때만 채운다.
            if limit <= 0 or free < max(1, slots // 2):
                if remaining <= 0 and pending.qsize() == 0 and counters["in_flight"] == 0:
                    break
                slot_freed.clear()
                await slot_freed.wait()
                continue

            jobs = queue.claim(job_types=[JOB_TYPE], limit=limit)
            if not jobs:
                if pending.qsize() or counters["in_flight"]:
                    slot_freed.clear()
                    await slot_freed.wait()
                    continue
                # enqueue-트리거 경합: drain 종료 직전 짧게 한 번 더 폴링해
                # 막 들어온 잡을 놓치지 않는다.
                if idle_grace_seconds > 0 and not grace_used:
                    grace_used = True
                    await asyncio.sleep(idle_grace_seconds)
                    continue
                break

            grace_used = False
            counters["claimed"] += len(jobs)
            LOGGER.info(
                "translation worker batch claimed: count=%s job_ids=%s",
                len(jobs),
                ",".join(str(job.get("id")) for job in jobs),
            )
            for job in jobs:
                pending.put_nowait(job)
    except BaseException:
        # 바깥에서 취소되면 소비자도 함께 접는다 — gather 시절의 취소 전파와 같은 계약.
        for task in consumers:
            task.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
        raise

    for _ in consumers:
        pending.put_nowait(None)
    results = await asyncio.gather(*consumers, return_exceptions=True)
    for item in results:
        # CancelledError 는 Exception 이 아니다. graceful shutdown 신호이므로 그대로 전파한다.
        if isinstance(item, BaseException) and not isinstance(item, Exception):
            raise item
    return counters["processed"]
```

- [ ] **Step 4: 새 테스트가 통과하는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_worker_slot_topup -v
```

Expected: PASS (1 test)

- [ ] **Step 5: 취소 전파와 동시성 계약이 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest \
  backend.tests.test_worker_job_cancellation \
  backend.tests.test_worker_drain \
  backend.tests.test_worker_main -v
```

Expected: 전부 통과. 특히 `test_translation_worker_marks_job_failed_on_cancellation`(취소 시 `queue.fail` 1회 + `CancelledError` 전파)과 `test_translation_worker_processes_claimed_jobs_concurrently`(`max_running == 2`)가 통과해야 한다. **하나라도 실패하면 Step 3의 취소 처리가 틀린 것이다 — 되돌리고 보고할 것.**

- [ ] **Step 6: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add backend/app/jobs/translation_worker.py backend/tests/test_worker_slot_topup.py
git commit -m "perf(worker): 번역 워커의 배치 대기 제거 — 슬롯이 비는 즉시 top-up claim

기존 구조는 claim(10) → gather(10) → claim(10) 이라 배치 10잡 전원이
끝날 때까지 다음 claim 이 오지 않았다. 잡 소요가 100~155초로 흩어져
먼저 끝난 슬롯이 가장 느린 잡을 기다리며 놀았다(유휴율 약 23%).

소비자 N개가 큐에서 뽑아 처리하고, 여유 슬롯이 batch_size/2 이상 났을 때만
claim 한다 — claim 은 동기 DB 왕복이라 매 완료마다 하면 왕복이 늘어난다.

gather 의 취소 전파(한 잡이 취소되면 형제를 접고 CancelledError 를 올린다)는
graceful shutdown 계약이라 소비자 구조에서도 유지한다.

단건 지연은 변하지 않는다. 이건 처리량 단위다."
```

---

## Task 5: Gemini SDK 결함 대응 (#2705 keepalive · #1875 중첩 재시도)

미해결 OPEN 이슈 두 건이 **정확히 이 워크로드의 실패 모드**다.

- **googleapis/python-genai #2705** — 기본 httpx transport가 TCP `SO_KEEPALIVE`를 설정하지 않아 20~30초 무응답 구간에 NAT가 연결을 끊는다. 이 파이프라인은 콜당 20~30초 무응답이 **정상 상태**다.
- **#1875** — SDK가 429의 `RetryInfo.retryDelay`를 무시하고 고정 백오프 5회. 앱 백오프(`gemini_client.py:24` 5/10/20/40s ×4)와 중첩돼 최악 ~20회 시도.

> **이 Task는 Bedrock 이전이 면제해주지 않는다.** 문서판독(`GeminiDocumentExtractor`)이 Vertex/ADC를 계속 쓰기 때문이다. 다만 이 Task는 **번역 클라이언트에만** 적용한다 — 문서판독 클라이언트는 이 사업의 범위 밖이다(Global Constraints).

**Files:**
- Modify: `backend/app/translation/gemini_client.py:150-164` (`_get_vertex_client`)

**Interfaces:**
- Consumes: `google.genai.types.HttpOptions`
- Produces: Vertex 경로의 httpx transport가 `SO_KEEPALIVE`를 켜고 SDK 내부 재시도가 1회로 줄어든다. 다른 Task는 이 변경에 의존하지 않는다.

- [ ] **Step 1: 설치된 SDK가 어떤 노브를 갖고 있는지 먼저 본다**

스펙 §9.2가 `HttpOptions`의 `client_args`/retry 노브 존재를 **미확인**으로 남겼다. 추측하지 말고 확인한다.

```bash
python -c "
from google.genai import types
fields = types.HttpOptions.model_fields
print('HttpOptions 필드:', sorted(fields))
for name in ('client_args', 'async_client_args', 'retry_options'):
    print(name, '->', name in fields)
"
```

Expected: `async_client_args`와 `retry_options`가 `True`.

> **`async_client_args`가 없으면 Step 2를 실행하지 말고 중단·보고할 것.** 그 경우 keepalive 주입은 이 SDK 버전의 지원 노브가 아니고, 몽키패치는 이 사업의 범위를 넘는다. `retry_options`만 없다면 Step 2에서 그 인자만 빼고 keepalive는 그대로 넣는다.
>
> 로컬 개발 환경에 `google-genai`가 설치되어 있지 않으면 이 Step은 `ModuleNotFoundError`가 난다. 그때는 `pip install -r backend/requirements.txt`를 먼저 돌린다.

- [ ] **Step 2: Vertex 클라이언트에 keepalive와 재시도 상한을 준다**

`backend/app/translation/gemini_client.py`의 `_get_vertex_client`(150~164행)를 아래로 교체한다:

```python
    def _get_vertex_client(self) -> Any:
        if self._vertex_client is None:
            import socket

            from google import genai
            from google.genai import types

            # googleapis/python-genai #2705: 기본 httpx transport 가 SO_KEEPALIVE 를
            # 켜지 않아, 콜당 20~30초 무응답이 정상인 이 워크로드에서 NAT 가 연결을 끊는다.
            # TCP_KEEPIDLE 계열은 리눅스에만 있으므로 있는 것만 넣는다.
            socket_options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
            for name, value in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 6)):
                option = getattr(socket, name, None)
                if option is not None:
                    socket_options.append((socket.IPPROTO_TCP, option, value))

            self._vertex_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=int(self.timeout_seconds * 1000),
                    # #1875: SDK 내부 재시도(고정 백오프 5회)가 앱 백오프 4회와 중첩돼
                    # 최악 ~20회 시도가 된다. SDK 쪽을 1회로 묶고 앱 백오프만 남긴다.
                    retry_options=types.HttpRetryOptions(attempts=1),
                    async_client_args={
                        "transport": httpx.AsyncHTTPTransport(socket_options=socket_options),
                    },
                ),
            )
        return self._vertex_client
```

`httpx`는 이 모듈 11행에서 이미 import되어 있다.

- [ ] **Step 3: 클라이언트가 실제로 만들어지는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
from app.translation.gemini_client import GeminiJsonClient
client = GeminiJsonClient(model='gemini-2.5-flash', use_vertex=True, project='probe-only')
print('client 생성 OK:', type(client._get_vertex_client()).__name__)
"
```

Expected: `client 생성 OK: Client` (호출은 하지 않는다 — 생성만으로 인자 형식이 검증된다). 예외가 나면 Step 2의 인자 이름이 SDK와 안 맞는 것이므로 Step 1의 필드 목록으로 되돌아간다.

- [ ] **Step 4: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add backend/app/translation/gemini_client.py
git commit -m "fix(translation): Vertex 경로에 TCP keepalive 주입 + SDK 내부 재시도 1회로 축소

googleapis/python-genai #2705 — 기본 httpx transport 가 SO_KEEPALIVE 를 켜지 않아
20~30초 무응답 구간에서 NAT 가 연결을 끊는다. 이 파이프라인은 콜당
20~30초 무응답이 정상 상태라 정확히 이 실패 모드에 걸린다.

#1875 — SDK 가 429 의 RetryInfo.retryDelay 를 무시하고 고정 백오프 5회를 돈다.
앱 백오프 4회(5/10/20/40s)와 중첩되면 최악 ~20회 시도가 된다.
SDK 쪽을 1회로 묶고 앱 백오프만 남긴다.

Bedrock 이전이 이 문제를 면제해주지 않는다 — 문서판독 경로가 Vertex/ADC 를
계속 쓴다. 다만 이번 변경은 번역 클라이언트에만 적용한다."
```

---

## Task 6: B3 — 낭비 제거 (카드 메타데이터 플래그 + dead path 삭제)

낭비 2건을 한 Task로 묶는다. 둘 다 «동작 변화 0»이 목표다.

**(a) 요약·본문 소스 번역이 콜을 2배 쓴다.** `notice_service.py:247-264`(`translation_kind ∈ {notice_summary, notice_source}`)가 `_best_effort_translate_notice`(`:625`)를 부른다. 이 함수는 번역 1콜(`:638`)에 더해 카드 메타데이터 1콜(`:668`)을 반드시 쏘는데, 호출부 `content_extraction_service.py:946-947`은 `result["translation"]`만 꺼내고 `pipeline_result`를 버린다. → 이 경로 콜의 **50%가 낭비**.

**호출 3곳 중 `:249` 하나만 `False`다.** `:173`과 `:302`는 공지 본체 번역의 쿼터 폴백이라 `:665-666` 주석이 설명하는 «카드가 비면 앱이 무한 재요청» 문제가 실재한다. 그래서 **플래그 기본값은 `True`**다.

**(b) risk 게이트의 저위험 경로가 dead path다.** Task 1의 측정으로 확정한다.

**Files:**
- Modify: `backend/app/services/notice_service.py:625-632` (시그니처), `:665-685` (메타데이터 블록), `:249` (호출)
- Modify: `backend/app/translation/orchestrator.py:186-231` (dead 분기 삭제)
- Modify: `backend/tests/test_orchestrator_parallel_thinking.py:167-186`
- Test: `backend/tests/test_best_effort_card_metadata_flag.py`

**Interfaces:**
- Consumes: Task 1이 확보한 `low = 0건` 수치
- Produces: `_best_effort_translate_notice(..., with_card_metadata: bool = True)`. 기존 호출 2곳(`:173`, `:302`)은 인자 없이 그대로 동작한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_best_effort_card_metadata_flag.py`:

```python
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.notice_service import NoticeService


def _fake_gemini():
    """첫 콜은 간이번역, 이후 콜은 카드 메타데이터 페이로드."""

    async def generate_json(*, prompt, temperature, model=None, thinking_budget=None):
        if generate_json.calls == 0:
            generate_json.calls += 1
            return {"target_translation": "Translated body", "title": "Fallback title"}
        generate_json.calls += 1
        return {"title": "Generated title", "card_sections": {}}

    generate_json.calls = 0
    return SimpleNamespace(generate_json=AsyncMock(side_effect=generate_json))


class BestEffortCardMetadataFlagTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_still_generates_card_metadata(self) -> None:
        """쿼터 폴백 경로(notice_service:173, :302)는 카드가 비면 앱이 무한 재요청한다.

        그래서 기본값은 True 여야 한다.
        """
        gemini = _fake_gemini()
        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
        )
        self.assertEqual(gemini.generate_json.await_count, 2)
        self.assertIn("card_sections", result["metadata"])

    async def test_flag_off_skips_the_metadata_call(self) -> None:
        """요약·본문 소스 번역(notice_service:249)은 pipeline_result 를 버린다.

        메타데이터 콜은 그대로 낭비이므로 끈다.
        """
        gemini = _fake_gemini()
        result = await NoticeService()._best_effort_translate_notice(
            gemini=gemini,
            notice={},
            target_language="en",
            source_text="한국어 원문",
            with_card_metadata=False,
        )
        self.assertEqual(gemini.generate_json.await_count, 1)
        self.assertEqual(result["final_translation"], "Translated body")
        self.assertNotIn("card_sections", result["metadata"])
        # 폴백 마커와 제목은 메타데이터 콜 없이도 남아야 한다.
        self.assertEqual(result["metadata"]["fallback_mode"], "quota_best_effort")
        self.assertEqual(result["metadata"]["title"], "Fallback title")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_best_effort_card_metadata_flag -v
```

Expected: `test_flag_off_skips_the_metadata_call` FAIL — `TypeError: ... unexpected keyword argument 'with_card_metadata'`

- [ ] **Step 3: 플래그를 넣는다**

`backend/app/services/notice_service.py:625-632`의 시그니처를 교체:

```python
    async def _best_effort_translate_notice(
        self,
        *,
        gemini: GeminiJsonClient,
        notice: dict[str, Any],
        target_language: str,
        source_text: str,
        with_card_metadata: bool = True,
    ) -> dict[str, Any]:
```

그리고 `:665-685`의 주석 두 줄을 아래로 바꾸고 뒤따르는 `try:` 블록 전체를 한 단 들여쓴다:

```python
        # 폴백으로 끝나도 카드 메타데이터(요약·할일)는 만들어 둔다 — 카드가 비면
        # 앱이 번역을 미완성으로 보고 풀 파이프라인을 무한 재요청하기 때문.
        # 다만 호출부가 pipeline_result 를 버리는 경로(translate_text 의
        # notice_summary/notice_source)에서는 이 콜이 그대로 낭비라 끈다.
        if with_card_metadata:
            try:
                generated = await gemini.generate_json(
                    prompt=build_supabase_payload_prompt(
                        source_text=source_text,
                        final_target_translation=translated_text,
                        source_hard_facts={},
                        validation_results=validation_results,
                        target_language=target_language,
                    ),
                    temperature=0.0,
                )
                if isinstance(generated, dict):
                    metadata = {**generated, **metadata}
            except Exception as exc:  # noqa: BLE001 - 카드 메타데이터는 베스트에포트.
                LOGGER.warning(
                    "best effort fallback metadata generation failed: target_language=%s error=%s",
                    target_language,
                    exc,
                )
```

- [ ] **Step 4: 낭비 경로에서만 끈다**

`backend/app/services/notice_service.py:249`의 호출에 인자 한 줄을 더한다:

```python
                fallback = await self._best_effort_translate_notice(
                    gemini=GeminiJsonClient.from_settings(settings),
                    notice={},
                    target_language=target_language,
                    source_text=source_text,
                    # 호출부(content_extraction_service.py:946-947)가 translation 만 꺼내고
                    # pipeline_result 를 버린다 — 카드 메타데이터 콜은 그대로 낭비다.
                    with_card_metadata=False,
                )
```

`:173`과 `:302`는 **손대지 않는다** — 쿼터 폴백 경로라 카드가 필요하다.

- [ ] **Step 5: dead 분기를 지운다 (Task 1에서 `low = 0건`이었을 때만)**

Task 1 Step 3이 `low = 0건`으로 나왔을 때만 진행한다. 아니면 이 Step을 건너뛰고 보고한다.

`backend/app/translation/orchestrator.py:186-231`의 블록 전체(`if risk_profile["level"] == "low":`부터 그 `return {...}`의 닫는 괄호까지, 46줄)를 삭제한다.

`_risk_profile_from_source`(`:545-603`)와 `:102`의 투기 조건은 **남긴다** — `:102`는 `!= "low"`이므로 항상 참이 되어 역번역 투기 실행이 그대로 동작하고, `risk_profile`은 `raw_steps`(`:359`)에 계속 기록돼 Task 1의 조회가 계속 유효하다.

- [ ] **Step 6: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_best_effort_card_metadata_flag -v
```

Expected: PASS (2 tests)

- [ ] **Step 7: 삭제된 분기를 검증하던 테스트를 새 계약으로 고친다**

`backend/tests/test_orchestrator_parallel_thinking.py:167-186`의 `test_low_risk_does_not_start_back_translation`은 저위험 입력에서 역번역·문맥어조를 **건너뛰던** 동작을 단언한다. Step 5가 그 분기를 지웠으므로 실패한다. 아래로 교체한다:

```python
    def test_low_risk_still_runs_back_translation_and_tone(self) -> None:
        """저위험 분기를 삭제했으므로(dead path, 운영 표본 low=0건) 모든 공지가
        역번역·문맥어조 검증을 거친다. 동작 변화가 아니라 죽은 코드 제거다."""
        gemini = _RecordingGemini(
            {
                "source_hf": {"hard_facts": {"dates": [{"raw_text": "다음 주 월요일"}]}},
                "pivot": {"pivot_translation_en": "Notice EN"},
                "target": {"target_translation": "Translated body"},
                "target_hf": {"hard_facts": {"dates": [{"raw_text": "next Monday"}]}},
                "back": {"back_translation_ko": "역번역"},
                "tone": {"verdict": "PASS", "issues": []},
                "payload": {"title": "안내", "validation_status": "passed"},
            }
        )

        result = asyncio.run(
            TranslationPipeline(gemini).run(
                _payload_input(source_text="다음 주 월요일은 재량휴업일입니다.")
            )
        )

        self.assertEqual(result["status"], "ready_to_save")
        self.assertEqual(len(gemini.calls_of("back")), 1)
        self.assertEqual(len(gemini.calls_of("tone")), 1)
```

- [ ] **Step 8: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 9: 커밋**

```bash
git add backend/app/services/notice_service.py backend/app/translation/orchestrator.py \
  backend/tests/test_best_effort_card_metadata_flag.py backend/tests/test_orchestrator_parallel_thinking.py
git commit -m "perf(translation): 요약·소스 번역의 카드 메타데이터 콜 제거 + risk 저위험 dead path 삭제

(a) translate_text 의 notice_summary/notice_source 분기는 _best_effort_translate_notice
    를 부르고 결과에서 translation 만 꺼낸다(content_extraction_service.py:946-947).
    그런데 그 함수는 카드 메타데이터 콜을 반드시 한 번 더 쏜다 — 이 경로 콜의 50% 가
    낭비였다. with_card_metadata 플래그를 두되 기본값은 True 로 남긴다.
    쿼터 폴백 경로(:173, :302)에서는 카드가 비면 앱이 풀 파이프라인을 무한 재요청한다.

(b) _risk_profile_from_source 는 첨부·링크·납부·동의서 같은 단서 하나만 걸려도 high 다.
    학교 가정통신문이 하나도 안 걸리기는 어렵다. 운영 번역본 전량을 조회한 결과
    low 는 0건이었다 — 저위험 분기 46줄은 실행된 적이 없다.
    risk_profile 계산과 :102 의 역번역 투기 조건은 남긴다(!= low 라 항상 참)."
```

---

## Task 7: B4 — thinking 축소 (Gemini에서 먼저)

`generate_json` 호출 16곳 중 `thinking_budget=MECHANICAL_THINKING_BUDGET`(=0)이 걸린 곳은 5곳뿐이다(`:64` `:110` `:247` `:288` `:410`). 나머지 **11곳은 모델 기본값(Gemini 2.5 Flash = Auto, 최대 8,192)** 으로 돈다 — `:76` `:86` `:129` `:143` `:199` `:251` `:268` `:291` `:327` `:384` `:447`. 즉 **무거운 단계는 전부 thinking이 켜져 있다.** 실측 134.7초 → tb=0 기준 33.5초(−75%).

> **설계 판단 — 스펙 §6.1의 «호출 인자 11곳»과 다르게 간다.** 상수를 하드코딩하는 대신 설정값(`TRANSLATION_THINKING_BUDGET`)으로 주입한다. 이유 셋: ① Task 3의 arm 축이 **환경변수로만** 정의되므로 arm T(thinking OFF)를 코드 분기 없이 돌릴 수 있다 ② 배포 롤백이 revert가 아니라 env 한 줄 되돌리기가 된다 ③ 기본값이 `None`이라 이 커밋 자체의 런타임 동작 변화가 0이다.

**Files:**
- Modify: `backend/app/core/config.py:47-52` 아래 (설정 1개 추가)
- Modify: `backend/app/translation/orchestrator.py:9` (import), `:55-57` (`__init__`), 비기계 호출부 전부
- Modify: `backend/tests/test_orchestrator_parallel_thinking.py:115-119`
- Create: `backend/tests/test_orchestrator_thinking_budget_setting.py`
- Modify: `.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json` (arm-b 추가)
- Modify: `.agents/translation-quality/iterations/2026-08-27_iter-negative-control/arms.json` (같은 arm-b 추가)
- Create: `scripts/compare_arms.py` (G1·G4·G5), `scripts/check_hallucination.py` (G6)
- Modify: `.github/workflows/deploy-api-cloud-run.yml:81, 116` (API 서비스 + 워커 Job env)

**Interfaces:**
- Consumes: `Settings.translation_thinking_budget: int | None`
- Produces: `TranslationPipeline(gemini).thinking_budget` — 비기계 콜에 주입된다. Task 10의 `BedrockJsonClient`는 이 값을 받아도 무시한다(§5.3).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_orchestrator_thinking_budget_setting.py`:

```python
import asyncio
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.translation.orchestrator import TranslationPipeline

from backend.tests.test_orchestrator_parallel_thinking import (
    _MATCHING_HARD_FACTS,
    _payload_input,
    _RecordingGemini,
)

_NON_MECHANICAL = {"pivot", "target", "tone", "payload"}


def _clean_run(**settings_kwargs) -> _RecordingGemini:
    gemini = _RecordingGemini(
        {
            "source_hf": _MATCHING_HARD_FACTS,
            "pivot": {"pivot_translation_en": "Notice EN"},
            "target": {"target_translation": "Translated body"},
            "target_hf": _MATCHING_HARD_FACTS,
            "back": {"back_translation_ko": "역번역"},
            "tone": {"verdict": "PASS", "issues": []},
            "payload": {"title": "안내", "validation_status": "passed"},
        }
    )
    settings = Settings(**settings_kwargs)
    with patch("app.translation.orchestrator.get_settings", return_value=settings):
        asyncio.run(TranslationPipeline(gemini).run(_payload_input()))
    return gemini


class ThinkingBudgetSettingTest(unittest.TestCase):
    def test_default_keeps_current_behaviour(self) -> None:
        """기본값 None 이면 비기계 단계는 모델 기본값(thinking Auto)을 그대로 쓴다."""
        gemini = _clean_run()
        self.assertTrue(gemini.calls)
        for call in gemini.calls:
            if call["kind"] in _NON_MECHANICAL:
                self.assertIsNone(call["thinking_budget"], call["kind"])

    def test_setting_zero_turns_thinking_off_everywhere(self) -> None:
        """TRANSLATION_THINKING_BUDGET=0 이면 번역·검증·카드 단계도 전부 0."""
        gemini = _clean_run(TRANSLATION_THINKING_BUDGET=0)
        self.assertTrue(gemini.calls)
        for call in gemini.calls:
            self.assertEqual(call["thinking_budget"], 0, call["kind"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_orchestrator_thinking_budget_setting -v
```

Expected: `test_setting_zero_turns_thinking_off_everywhere` FAIL. (`app.translation.orchestrator.get_settings`가 아직 없어 `AttributeError`가 먼저 날 수도 있다 — 둘 다 «아직 구현 안 됨»의 신호다.)

- [ ] **Step 3: 설정을 추가한다**

`backend/app/core/config.py`의 `gemini_max_concurrency`(47~52행) 정의 **아래**에 추가:

```python
    # 번역 파이프라인의 비기계 단계(피벗·타겟·검증·자동수정·카드)에 적용할 thinking 예산.
    # None = 모델 기본값(Gemini 2.5 Flash 는 Auto, 최대 8,192). 0 = 끔.
    # 실측상 파이프라인 지연의 75~78% 가 thinking 토큰이다. 0 으로 두면 134.7s → 33.5s.
    # 기계적 추출·역번역 5콜은 이 값과 무관하게 항상 0이다(MECHANICAL_THINKING_BUDGET).
    translation_thinking_budget: int | None = Field(
        default=None,
        ge=0,
        alias="TRANSLATION_THINKING_BUDGET",
    )
```

- [ ] **Step 4: 오케스트레이터가 그 값을 비기계 호출에 주입한다**

`backend/app/translation/orchestrator.py`의 import 블록(9행 `from app.translation.gemini_client import GeminiJsonClient` **위**)에 추가:

```python
from app.core.config import get_settings
```

`TranslationPipeline.__init__`(55~57행)을 교체:

```python
class TranslationPipeline:
    def __init__(self, gemini: GeminiJsonClient) -> None:
        self.gemini = gemini
        # 비기계 단계에 넘길 thinking 예산. None 이면 모델 기본값을 그대로 쓴다.
        self.thinking_budget = get_settings().translation_thinking_budget
```

그리고 **`thinking_budget` 인자가 없는 모든 호출부**(`:76` `:86` `:129` `:143` `:199` `:251` `:268` `:291` `:327` `:384` `:447`)에 각각 한 줄을 더한다. 예를 들어 한→영 피벗(`:76-83`):

```python
        pivot = await self.gemini.generate_json(
            prompt=translate_ko_to_en_pivot_prompt(
                source_text=payload.source_text,
                source_hard_facts=source_hard_facts,
                ingredient_map=ingredient_map,
            ),
            temperature=0.1,
            thinking_budget=self.thinking_budget,
        )
```

나머지도 동일하게 `temperature=...` 바로 아래에 `thinking_budget=self.thinking_budget,`를 넣는다. **`MECHANICAL_THINKING_BUDGET`이 이미 걸린 5곳은 건드리지 않는다.**

> Task 6 Step 5가 `:186-231`(저위험 분기)을 지웠다면 `:199`는 이미 사라졌다. 그 경우 대상은 10곳이다.

- [ ] **Step 5: 누락 없이 다 넣었는지 기계적으로 확인한다**

```bash
python -c "
import re, sys, pathlib
sys.stdout.reconfigure(encoding='utf-8')
src = pathlib.Path('backend/app/translation/orchestrator.py').read_text(encoding='utf-8')
calls = re.findall(r'generate_json\((?:[^()]|\([^()]*\))*\)', src, flags=re.S)
missing = [c for c in calls if 'thinking_budget' not in c]
print('generate_json 호출', len(calls), '개')
print('  self.thinking_budget:', sum('self.thinking_budget' in c for c in calls))
print('  MECHANICAL_THINKING_BUDGET:', sum('MECHANICAL_THINKING_BUDGET' in c for c in calls))
print('  thinking_budget 없음:', len(missing))
assert not missing, 'thinking_budget 이 빠진 호출이 있다'
print('OK')
"
```

Expected: `MECHANICAL_THINKING_BUDGET: 5`, `thinking_budget 없음: 0`, `OK`. `self.thinking_budget`은 Task 6 Step 5 수행 여부에 따라 **10 또는 11**이다.

- [ ] **Step 6: 기존 thinking 테스트의 주석을 새 계약으로 고친다**

`backend/tests/test_orchestrator_parallel_thinking.py:115-119`의 주석 한 줄을 바꾼다(단언 네 줄은 기본값이 `None`이라 그대로 참이다):

```python
        # 번역·검증·카드 단계(②③⑥⑦)는 설정값을 따른다 — 기본값 None = 모델 기본(동적 thinking)
        self.assertIsNone(budget_by_kind["pivot"])
        self.assertIsNone(budget_by_kind["target"])
        self.assertIsNone(budget_by_kind["tone"])
        self.assertIsNone(budget_by_kind["payload"])
```

- [ ] **Step 7: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_orchestrator_thinking_budget_setting -v
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 새 테스트 2건 PASS, 전체 통과

- [ ] **Step 8: arm-b를 추가하고 두 arm을 완주시킨다**

`arms.json`의 `arms` 배열에 추가:

```json
    {
      "id": "arm-b",
      "label": "gemini-2.5-flash-thinking-off",
      "env": { "TRANSLATION_THINKING_BUDGET": "0" }
    }
```

**같은 항목을 negative control 폴더의 `arms.json`에도 넣는다** — arm은 이터 폴더 단위로 정의된다(Task 2 Step 8).

```bash
for ARM in arm-a arm-b; do
  python scripts/run_iteration.py \
    --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ \
    --arm "$ARM"
done
```

Expected: arm별 30공지 × 3언어 = 90 json. `_pipeline_run_summary.arm-a.json`·`_pipeline_run_summary.arm-b.json` 생성.

- [ ] **Step 9: G1·G4·G5를 코드로 판정한다**

`scripts/compare_arms.py` 생성 (Task 11·14에서도 재사용한다):

```python
"""두 arm 의 파이프라인 산출물을 비교해 게이트 G1·G4·G5 를 판정한다.

G1  validation.hard_fact 통과율이 기준선 대비 하락 0건
G4  final_translation 에 placeholder({{...}}) 잔존 0건
G5  wall_seconds 중앙값이 기준선보다 낮다

G2(평가자 verdict)·G3(8축 평균)는 평가자 에이전트 산출물로 사람이 판정한다.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def collect(iter_dir: Path, arm: str) -> dict:
    out = {}
    for path in sorted(iter_dir.glob(f"notices/*/*/pipeline-output/{arm}/*.json")):
        notice_id = path.parent.parent.parent.name
        out[(notice_id, path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def status(result: dict, axis: str) -> str | None:
    return ((result.get("validation") or {}).get(axis) or {}).get("status")


def median_wall(results: dict) -> float | None:
    values = [
        r.get("wall_seconds") for r in results.values()
        if isinstance(r.get("wall_seconds"), (int, float))
    ]
    return round(statistics.median(values), 1) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()

    base = collect(args.iter_dir, args.baseline)
    cand = collect(args.iter_dir, args.arm)
    shared = sorted(set(base) & set(cand))
    if not shared:
        print("ERROR: 두 arm 의 공통 산출물이 없다", file=sys.stderr)
        return 2
    print(f"비교 대상 {len(shared)}건 ({args.baseline} vs {args.arm})")

    hard_fact_reg = [
        k for k in shared
        if status(base[k], "hard_fact") == "passed" and status(cand[k], "hard_fact") != "passed"
    ]
    tone_reg = [
        k for k in shared
        if status(base[k], "context_tone") == "passed" and status(cand[k], "context_tone") != "passed"
    ]
    placeholders = [k for k in shared if "{{" in str(cand[k].get("final_translation") or "")]
    parse_errors = [k for k in shared if cand[k].get("status") == "driver_error"]
    base_med, cand_med = median_wall(base), median_wall(cand)

    print(f"G1 hard_fact 하락      : {len(hard_fact_reg)}건 {hard_fact_reg[:5]}")
    print(f"   context_tone 하락   : {len(tone_reg)}건 (참고 — G3 판단 재료)")
    print(f"G4 placeholder 잔존    : {len(placeholders)}건 {placeholders[:5]}")
    print(f"   driver_error(파싱 등): {len(parse_errors)}건 {parse_errors[:5]}")
    print(f"G5 wall_seconds 중앙값 : {base_med}s → {cand_med}s")

    ok = (
        not hard_fact_reg
        and not placeholders
        and not parse_errors
        and base_med is not None
        and cand_med is not None
        and cand_med < base_med
    )
    print("\nG1/G4/G5:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

```bash
python scripts/compare_arms.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001 \
  --baseline arm-a --arm arm-b
```

Expected: `G1 hard_fact 하락: 0건`, `G4 placeholder 잔존: 0건`, `G5 ... 약 134s → 약 34s`, `G1/G4/G5: 통과`

> **G1이 0건이 아니면 배포하지 않는다.** 예비안은 스펙 §6.2의 부분 적용이다 — 문맥·어조 검증 단계(`:251`)만 `thinking_budget=None`으로 되돌린다(절약 −20.5s 포기, 나머지 −80.7s 유지). 그 단계는 나빠지면 «번역이 어색해진다»가 아니라 **«나쁜 번역을 통과시킨다»** 라서 G1이 못 잡는다.

- [ ] **Step 10: G6을 판정한다 — 읽지 못했을 때 지어내는가**

G1~G5는 전부 **모델이 입력을 읽었다는 전제** 위에서 잰다. 스펙 §4.7·§5.9.2가 보여준 실패 모드는 그 전제가 깨지는 경우다. 여기서 그걸 따로 잰다.

`scripts/check_hallucination.py` 생성 (Task 11·14에서도 재사용한다):

```python
"""게이트 G6 — negative control 산출물에서 «지어낸 사실» 을 센다.

판독 불가 입력(첨부만·OCR 깨짐·구분선뿐)에 대해 모델이
«못 읽겠다» 고 답하는지, 그럴듯한 가정통신문을 지어내는지를 본다.

번역 품질 게이트(compare_arms.py)와 채점 방식이 다르다.
여기서는 «잘 썼는가» 를 보지 않는다 — «없는 것을 만들었는가» 만 본다.

결정적 규칙 둘:
  R1  원문에 없는 숫자가 번역문에 나온다  → 날짜·금액·시각을 지어낸 것이다
  R2  번역문이 원문보다 3배 넘게 길다      → 본문을 만들어낸 것이다

R1·R2 를 통과해도 인명·행사명 같은 비숫자 날조는 코드가 못 잡는다.
그래서 통과 건도 본문을 함께 찍어 사람이 훑게 한다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 아랍어 번역문은 아라비아-인도 숫자로 나올 수 있다. 비교 전에 ASCII 로 맞춘다.
_DIGIT_MAP = {ord(c): str(i % 10) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹")}
_LENGTH_RATIO = 3.0


def digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", text.translate(_DIGIT_MAP)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter-dir", required=True, type=Path)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--show", type=int, default=200, help="사람 확인용으로 찍을 본문 길이")
    args = parser.parse_args()

    paths = sorted(args.iter_dir.glob(f"notices/*/*/pipeline-output/{args.arm}/*.json"))
    if not paths:
        print(f"ERROR: {args.arm} 산출물이 없다: {args.iter_dir}", file=sys.stderr)
        return 2

    violations = []
    for path in paths:
        notice_dir = path.parent.parent.parent
        source = (notice_dir / "source.ko.md").read_text(encoding="utf-8")
        result = json.loads(path.read_text(encoding="utf-8"))
        translation = str(result.get("final_translation") or "")

        invented = digits(translation) - digits(source)
        too_long = len(translation) > max(len(source), 1) * _LENGTH_RATIO

        flag = "🔴" if (invented or too_long) else "  "
        print(f"{flag} {notice_dir.name}/{path.stem}  원문 {len(source)}자 → 번역 {len(translation)}자")
        print(f"     {translation[:args.show]!r}")
        if invented:
            print(f"     R1 원문에 없는 숫자: {sorted(invented)}")
        if too_long:
            print(f"     R2 길이 {len(translation) / max(len(source), 1):.1f}배")
        if invented or too_long:
            violations.append((notice_dir.name, path.stem))

    print(f"\n산출물 {len(paths)}건 / 위반 {len(violations)}건")
    print("G6:", "통과" if not violations else f"실패 {violations}")
    print("\n※ 인명·행사명 같은 비숫자 날조는 코드가 못 잡는다. 위 본문을 사람이 훑을 것.")
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
```

두 arm으로 negative control을 돌리고 채점한다:

```bash
NEG=.agents/translation-quality/iterations/2026-08-27_iter-negative-control
for ARM in arm-a arm-b; do
  python scripts/run_iteration.py --iter "$NEG/" --arm "$ARM"
  echo "=== G6 $ARM ==="
  python scripts/check_hallucination.py --iter-dir "$NEG" --arm "$ARM"
done
```

Expected: 두 arm 모두 `G6: 통과`. 그리고 찍힌 본문이 **«원문을 읽을 수 없다» 계열이거나 비어 있어야 한다.** 학교·날짜·행사가 들어 있으면 숫자가 없어도 **실패로 판정하고 보고할 것** — R1·R2가 못 잡는 자리다.

> **thinking을 끄면 지어내기 시작하는가?** 이 Step이 그 질문에 답한다. arm-a는 통과하는데 arm-b가 실패하면 thinking OFF가 원인이므로, **G1이 통과해도 배포하지 않는다.** 그 경우 예비안은 Step 9의 부분 적용과 같다.

- [ ] **Step 11: G2·G3를 평가자 에이전트로 판정한다**

`.agents/translation-quality/evaluator-agent.md`대로 평가자를 돌려 `evaluation/feedback-report.md`와 `evaluation/scores.json`을 만든다. **평가자 호출 프롬프트에 «`arms.json`을 읽지 않는다»를 명시한다.** 그 다음:

```bash
python scripts/check_iteration_blind.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001
```

Expected: `모델명 노출 0건`. 그리고 `feedback-report.md` 최상단 verdict가 `blocking_regression`이 **아니고**(G2), `scores.json`의 세 언어 8축 평균이 arm-a 대비 −0.3점 이내(G3). 스펙 §6.2가 지목한 «Fact Preservation»·«Action Clarity» 두 축을 별도로 확인한다.

- [ ] **Step 12: 배포 env를 넣는다**

`.github/workflows/deploy-api-cloud-run.yml`의 워커 Job `--set-env-vars`(116행)에 `TRANSLATION_THINKING_BUDGET=0`을 더한다:

```yaml
            --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=INFO,SUPABASE_URL=${{ vars.NEXT_PUBLIC_SUPABASE_URL }},VERTEX_AI_PROJECT_ID=${{ vars.VERTEX_AI_PROJECT_ID }},VERTEX_AI_LOCATION=${{ vars.VERTEX_AI_LOCATION }},GEMINI_MAX_CONCURRENCY=32,TRANSLATION_THINKING_BUDGET=0" \
```

API 서비스의 `env_vars`(77~87행)에도 `TRANSLATION_THINKING_BUDGET=0` 한 줄을 넣는다 — 화면에서 유발하는 요약·라벨 번역도 같은 파이프라인을 탄다.

- [ ] **Step 13: 커밋**

```bash
git add backend/app/core/config.py backend/app/translation/orchestrator.py \
  backend/tests/test_orchestrator_thinking_budget_setting.py \
  backend/tests/test_orchestrator_parallel_thinking.py \
  scripts/compare_arms.py scripts/check_hallucination.py \
  .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001 \
  .agents/translation-quality/iterations/2026-08-27_iter-negative-control \
  .github/workflows/deploy-api-cloud-run.yml
git commit -m "perf(translation): 파이프라인 thinking 예산을 설정으로 주입, 운영은 0으로

generate_json 호출 16곳 중 thinking_budget=0 이 걸린 곳은 5곳뿐이었다.
나머지 11곳은 Gemini 2.5 Flash 기본값(Auto, 최대 8192)으로 돌았다 —
즉 무거운 단계는 전부 thinking 이 켜져 있었다.
실측상 지연의 75~78% 가 thinking 토큰이다(134.7s → 33.5s).

호출부에 0 을 하드코딩하는 대신 TRANSLATION_THINKING_BUDGET 설정으로 주입한다.
평가 하네스의 arm 이 환경변수로만 정의되므로 코드 분기 없이 A/B 가 되고,
롤백이 revert 가 아니라 env 한 줄 되돌리기가 된다.
기본값 None 이라 이 커밋 자체의 런타임 동작 변화는 0이다.

Bedrock 보다 먼저 하는 이유는 변수 분리다 — Claude 는 extended thinking 이
기본 OFF 라 이 이득이 자동으로 딸려온다. 순서를 뒤집으면 나중에 품질이
흔들렸을 때 원인이 모델인지 thinking 인지 알 수 없다.

게이트 G1(hard_fact 하락 0건)·G4(placeholder 0건)·G5(지연 하락) 통과 확인.

G6(환각 negative control)도 함께 돌린다. 판독 불가 입력에 대해
지어내지 않고 «못 읽겠다» 고 답하는지는 번역 품질 축으로는 잡히지 않는다 —
지어낸 글이 오히려 문장이 매끄러워 8축 평균을 올린다."
```

---

## Task 8: 스로틀 판정 확장 (Bedrock 필수 선행)

`is_quota_exhausted_error`(`gemini_client.py:27-32`)는 메시지 소문자에 `429` / `resource_exhausted` / `rate limit` / `rate_limit` / `quota` 중 하나가 있는지로 판정한다.

Bedrock의 스로틀 예외는 botocore `ClientError`이고 메시지는 통상 `An error occurred (ThrottlingException) when calling the Converse operation: Too many requests, please wait before trying again.` 이다 — **위 마커가 하나도 없다.** 그대로 두고 Bedrock을 붙이면 백오프(`:35-58`)가 한 번도 동작하지 않고 스로틀이 잡 실패로 곧장 전파된다.

> 참고: `notice_service.py:1365`의 `_is_gemini_quota_error`는 이미 `too many requests`를 갖고 있어 Bedrock 스로틀을 잡는다. **두 함수의 마커가 어긋나 있었다** — 이 Task가 정렬한다.

**Files:**
- Modify: `backend/app/translation/gemini_client.py:27-32`
- Modify: `backend/tests/test_gemini_quota_backoff.py:9-25`

**Interfaces:**
- Consumes: 없음
- Produces: `is_quota_exhausted_error(exc) -> bool` — Bedrock `ThrottlingException`·`ServiceUnavailableException`·`ModelNotReadyException`에 `True`. Task 10의 `BedrockJsonClient`가 `call_with_quota_backoff`를 통해 이걸 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_gemini_quota_backoff.py`의 `IsQuotaExhaustedErrorTest` 안, `test_ignores_unrelated_errors` **앞**에 추가:

```python
    def test_detects_bedrock_throttling_exception(self) -> None:
        """Bedrock 스로틀 메시지에는 429·quota·rate limit 이 하나도 없다.

        그대로 두면 백오프가 한 번도 동작하지 않고 잡이 실패로 직행한다.
        """
        error = RuntimeError(
            "ClientError: An error occurred (ThrottlingException) when calling the "
            "Converse operation: Too many requests, please wait before trying again."
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_detects_bedrock_service_unavailable(self) -> None:
        error = RuntimeError(
            "ClientError: An error occurred (ServiceUnavailableException) when calling "
            "the Converse operation: The model is temporarily unavailable."
        )
        self.assertTrue(is_quota_exhausted_error(error))

    def test_detects_bedrock_model_not_ready(self) -> None:
        error = RuntimeError(
            "ClientError: An error occurred (ModelNotReadyException) when calling "
            "the Converse operation: Model is not ready."
        )
        self.assertTrue(is_quota_exhausted_error(error))
```

그리고 `test_ignores_unrelated_errors`(23~25행)를 교체해 «넓혀도 오탐하지 않는다»를 고정한다:

```python
    def test_ignores_unrelated_errors(self) -> None:
        self.assertFalse(is_quota_exhausted_error(ValueError("invalid json")))
        self.assertFalse(is_quota_exhausted_error(RuntimeError("500 internal error")))
        # 마커를 넓혔지만 Bedrock 의 비스로틀 예외는 여전히 즉시 전파돼야 한다.
        self.assertFalse(
            is_quota_exhausted_error(
                RuntimeError(
                    "ClientError: An error occurred (ValidationException) when calling "
                    "the Converse operation: Malformed input request."
                )
            )
        )
        self.assertFalse(
            is_quota_exhausted_error(
                RuntimeError(
                    "ClientError: An error occurred (AccessDeniedException) when calling "
                    "the Converse operation."
                )
            )
        )
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_gemini_quota_backoff -v
```

Expected: 새 테스트 3건 FAIL (`assertTrue` 실패), 기존 5건은 PASS

- [ ] **Step 3: 마커를 넓힌다**

`backend/app/translation/gemini_client.py:27-32`을 교체:

```python
# Bedrock 은 스로틀을 ThrottlingException 으로 돌려주고 메시지는 "Too many requests,
# please wait before trying again." 이다 — 429·quota·rate limit 이 하나도 없다.
# 마커를 넓히지 않으면 백오프가 한 번도 동작하지 않고 잡 실패로 직행한다.
# Gemini 경로에는 무해하다(그 문자열이 나올 일이 없다).
QUOTA_ERROR_MARKERS: tuple[str, ...] = (
    "429",
    "resource_exhausted",
    "rate limit",
    "rate_limit",
    "quota",
    "throttling",
    "too many requests",
    "toomanyrequests",
    "serviceunavailable",
    "modelnotready",
)


def is_quota_exhausted_error(error: Exception) -> bool:
    message = f"{type(error).__name__}: {error}".lower()
    return any(marker in message for marker in QUOTA_ERROR_MARKERS)
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_gemini_quota_backoff -v
```

Expected: 11 tests PASS

- [ ] **Step 5: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add backend/app/translation/gemini_client.py backend/tests/test_gemini_quota_backoff.py
git commit -m "fix(translation): 스로틀 판정에 Bedrock 예외 마커 추가

is_quota_exhausted_error 는 429·resource_exhausted·rate limit·quota 만 봤다.
Bedrock 은 ThrottlingException 으로 돌려주고 메시지는
'Too many requests, please wait before trying again.' — 마커가 하나도 없다.

그대로 Bedrock 을 붙이면 백오프가 한 번도 동작하지 않고 스로틀이
잡 실패로 곧장 전파된다. 그래서 Bedrock 백엔드보다 먼저 고친다.

throttling / too many requests / serviceunavailable / modelnotready 를 넣는다.
Gemini 경로에는 무해하다. ValidationException·AccessDeniedException 같은
비스로틀 예외는 여전히 즉시 전파된다(테스트로 고정).

notice_service.py:1365 의 _is_gemini_quota_error 는 이미 too many requests 를
갖고 있었다 — 두 함수의 마커가 어긋나 있던 것을 정렬한다."
```

---

## Task 9: `JsonModelClient` 프로토콜 · 설정 · 팩토리 (다크 코드)

오케스트레이터가 클라이언트에서 쓰는 것은 **딱 두 개**다 — `generate_json(...)`과 `getattr(self.gemini, "source_hard_fact_model", None)`(`orchestrator.py:63`). 그래서 이음매가 두 멤버짜리 프로토콜로 끝난다.

이 Task는 **런타임 동작이 0이다.** 프로토콜과 팩토리만 만들고 호출부는 손대지 않는다(배선은 Task 11).

**Files:**
- Create: `backend/app/translation/json_client.py`
- Modify: `backend/app/core/config.py` (`BEDROCK_*` 설정 4개 + `TRANSLATION_BACKEND`)
- Test: `backend/tests/test_json_client_factory.py`

**Interfaces:**
- Consumes: `Settings.translation_backend`
- Produces:
  - `JsonModelClient` 프로토콜 — `source_hard_fact_model: str | None`, `async generate_json(*, prompt: str, temperature: float = 0.1, model: str | None = None, thinking_budget: int | None = None) -> dict[str, Any]`
  - `build_json_client(settings: Settings) -> JsonModelClient`
  - Task 10의 `BedrockJsonClient`, Task 11의 호출부 배선이 이걸 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_json_client_factory.py`:

```python
import unittest

from app.core.config import Settings
from app.translation.gemini_client import GeminiJsonClient
from app.translation.json_client import JsonModelClient, build_json_client


class BuildJsonClientTest(unittest.TestCase):
    def test_default_backend_is_gemini(self) -> None:
        """기본값은 gemini 다 — 이 커밋의 런타임 동작 변화는 0이어야 한다."""
        settings = Settings(VERTEX_AI_PROJECT_ID="probe-only")
        self.assertEqual(settings.translation_backend, "gemini")
        client = build_json_client(settings)
        self.assertIsInstance(client, GeminiJsonClient)

    def test_unknown_backend_falls_back_to_gemini(self) -> None:
        """오타 난 env 로 번역이 멈추면 안 된다. 경고만 남기고 Gemini 로 간다."""
        settings = Settings(VERTEX_AI_PROJECT_ID="probe-only", TRANSLATION_BACKEND="oops")
        self.assertIsInstance(build_json_client(settings), GeminiJsonClient)

    def test_gemini_client_satisfies_the_protocol(self) -> None:
        """GeminiJsonClient 는 한 글자도 고치지 않고 프로토콜을 만족해야 한다."""
        client = GeminiJsonClient(model="gemini-2.5-flash", api_key="unused")
        self.assertIsInstance(client, JsonModelClient)

    def test_bedrock_default_model_is_haiku(self) -> None:
        """기본은 Haiku 다(스펙 §5.10.1). Sonnet 승급은 env 로만 한다."""
        settings = Settings()
        self.assertEqual(settings.bedrock_region, "ap-northeast-2")
        self.assertEqual(
            settings.bedrock_translation_model,
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        self.assertIsNone(settings.bedrock_mechanical_model)

    def test_forbidden_models_are_not_defaults(self) -> None:
        """Opus 는 금지(비용), Nova 는 한국어 본문 생성 경로에서 제외(환각).

        기본값에 이 둘이 들어가면 아무도 모르게 운영에 실린다.
        """
        settings = Settings()
        for name in (settings.bedrock_translation_model, settings.bedrock_mechanical_model or ""):
            self.assertNotIn("opus", name)
            self.assertNotIn("nova", name)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_json_client_factory -v
```

Expected: `ModuleNotFoundError: No module named 'app.translation.json_client'`

- [ ] **Step 3: 설정을 추가한다**

`backend/app/core/config.py`의 `vertex_ai_location`(54행) **아래**에 추가:

```python
    # 번역 파이프라인이 쓸 JSON 모델 백엔드. gemini | bedrock.
    # 문서판독(GeminiDocumentExtractor)과 크롤러는 이 값과 무관하게 Gemini 를 계속 쓴다.
    # 되돌리기는 이 한 줄이다 — 코드 revert 가 필요 없다.
    translation_backend: str = Field(default="gemini", alias="TRANSLATION_BACKEND")
    # global. 라우팅은 사용자 승인됨(스펙 §16 해결됨 Q1). 다만 학교 공지에는
    # 학생 이름·학년반·보호자 연락처가 섞이므로 호출한 프로필을 로그에 남긴다.
    bedrock_region: str = Field(default="ap-northeast-2", alias="BEDROCK_REGION")
    # 기본은 Haiku 다(스펙 §5.10.1). 2026-08-27 실측에서 PDF·이미지 판독 정확도가
    # Sonnet 과 동급이고 텍스트 지연은 더 짧았다(920ms vs 1,303ms).
    # 게이트를 못 넘을 때만 Sonnet 으로 승급한다 — env 한 줄이다.
    # Opus 는 쓰지 않는다(비용, 사용자 지시). Nova 는 한국어 본문 생성 경로에서 제외한다
    # (읽지 못한 문서의 본문을 지어냈다 — 스펙 §5.9.2).
    bedrock_translation_model: str = Field(
        default="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        alias="BEDROCK_TRANSLATION_MODEL",
    )
    # 원문 하드팩트 추출 단계만 다른 모델로 돌리고 싶을 때 쓴다.
    # None 이면 bedrock_translation_model 을 그대로 쓴다.
    # 여기에도 Nova 를 넣지 않는다 — 하드팩트는 «지어내면 코드가 못 잡는» 자리다.
    bedrock_mechanical_model: str | None = Field(default=None, alias="BEDROCK_MECHANICAL_MODEL")
    # Bedrock Converse 는 boto3 동기 호출이라 전용 스레드풀에서 돈다.
    # asyncio 기본 executor 는 min(32, cpu+4) = 워커(--cpu=1)에서 5라 조용히 직렬화된다.
    bedrock_max_workers: int = Field(
        default=32,
        ge=1,
        le=64,
        alias="BEDROCK_MAX_WORKERS",
    )
```

`use_vertex`(`:208`)는 **그대로 둔다** — 문서판독 경로가 계속 쓴다. `gemini_max_concurrency`(`:47-52`)도 이름 그대로 두고 Bedrock 세마포어에 재사용한다. 이름이 어색하지만 지금 바꾸면 배포 워크플로 3곳(`deploy-api-cloud-run.yml:116, 131, 148`)이 같이 흔들린다. Task 13 이후 정리한다.

- [ ] **Step 4: 프로토콜과 팩토리를 쓴다**

`backend/app/translation/json_client.py`:

```python
"""번역 파이프라인이 쓰는 JSON 모델 클라이언트의 이음매.

오케스트레이터가 클라이언트에서 쓰는 것은 generate_json 과 source_hard_fact_model
둘뿐이다(orchestrator.py:60-65, :63). 그래서 프로토콜이 이만큼 작다.

GeminiJsonClient 는 이미 이 프로토콜을 만족하므로 한 글자도 고치지 않는다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.config import Settings

LOGGER = logging.getLogger(__name__)

BACKEND_GEMINI = "gemini"
BACKEND_BEDROCK = "bedrock"


@runtime_checkable
class JsonModelClient(Protocol):
    """JSON 을 돌려주는 LLM 클라이언트. 시그니처는 gemini_client.py:125-132 그대로."""

    source_hard_fact_model: str | None

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]: ...


def build_json_client(settings: "Settings") -> JsonModelClient:
    """설정에 따라 번역용 JSON 클라이언트를 만든다.

    알 수 없는 값이면 경고만 남기고 Gemini 로 간다 — env 오타로 번역이 멈추는 것보다
    현행 백엔드로 계속 도는 편이 낫다.
    """
    backend = (settings.translation_backend or BACKEND_GEMINI).strip().lower()

    if backend == BACKEND_BEDROCK:
        from app.translation.bedrock_client import BedrockJsonClient

        return BedrockJsonClient.from_settings(settings)

    if backend != BACKEND_GEMINI:
        LOGGER.warning(
            "알 수 없는 TRANSLATION_BACKEND=%r — gemini 로 폴백한다.",
            settings.translation_backend,
        )

    from app.translation.gemini_client import GeminiJsonClient

    return GeminiJsonClient.from_settings(settings)
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_json_client_factory -v
```

Expected: 4 tests PASS. (`test_bedrock_settings_defaults_stay_in_apac`는 Bedrock 클라이언트를 만들지 않으므로 Task 10 없이도 통과한다.)

- [ ] **Step 6: 전체 백엔드 테스트 — 런타임 동작이 0인지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. 이 Task는 새 모듈 추가와 설정 추가뿐이라 기존 동작을 건드리지 않는다.

- [ ] **Step 7: 커밋**

```bash
git add backend/app/translation/json_client.py backend/app/core/config.py \
  backend/tests/test_json_client_factory.py
git commit -m "feat(translation): JSON 모델 클라이언트 프로토콜 + 백엔드 팩토리 (다크)

오케스트레이터가 클라이언트에서 쓰는 것은 generate_json 과
source_hard_fact_model 둘뿐이다(orchestrator.py:60-65, :63).
그래서 이음매가 두 멤버짜리 Protocol 로 끝난다.

GeminiJsonClient 는 이미 이 프로토콜을 만족하므로 한 글자도 고치지 않는다.
호출부 배선은 다음 Task 다 — 이 커밋의 런타임 동작 변화는 0이다.

TRANSLATION_BACKEND 오타로 번역이 멈추는 것보다 현행 백엔드로 계속 도는 편이
낫다 — 알 수 없는 값이면 경고만 남기고 gemini 로 간다.

BEDROCK_TRANSLATION_MODEL 기본값은 Claude Haiku 4.5 다.
2026-08-27 실측에서 실제 학교 첨부(PDF·이미지) 판독 정확도가 Sonnet 과 동급이고
텍스트 지연은 더 짧았다. Sonnet 승급은 게이트를 못 넘을 때만, env 한 줄로 한다.
Opus 는 쓰지 않는다(비용). Nova 는 한국어 본문 생성 경로에서 제외한다 —
같은 실측에서 읽지 못한 문서의 본문을 지어냈다.

global. 라우팅은 사용자 승인됨(열린 질문 Q1 해결). 다만 학교 공지에
학생 이름·학년반·연락처가 섞이므로 호출한 프로필을 로그에 남긴다.

use_vertex 와 gemini_max_concurrency 는 이름 그대로 둔다 —
지금 바꾸면 배포 워크플로 3곳이 같이 흔들린다. 전면 전환 이후 정리한다."
```

---

## Task 10: `BedrockJsonClient` 구현

새로 쓰는 것은 **요청 조립·응답 추출·스레드 브리지 셋뿐**이다. 전역 세마포어(`gemini_client.py:61-71`)·백오프(`:35-58`)·JSON 파서(`:270-298`)는 그대로 재사용한다.

흡수해야 할 차이 넷:

| 차이 | Gemini | Bedrock | 이 Task의 대응 |
|---|---|---|---|
| thinking | `ThinkingConfig(thinking_budget=N)` | 켜면 **`temperature=1` 강제** | **항상 OFF.** 양수 값은 경고 후 무시 |
| JSON 강제 | `response_mime_type="application/json"` | 동등 기능 없음 | assistant 프리필 `"{"` + 기존 파서 복구 |
| 응답 위치 | `response.text` | `output.message.content[].text` | `reasoningContent` 블록을 건너뛰는 추출기 |
| 동기/비동기 | `client.aio` | `converse()` 블로킹 | **전용** `ThreadPoolExecutor` |

**thinking을 다시 켜는 것은 이 파이프라인에서 사실상 불가능하다** — `temperature=1` 강제가 현행 0.0/0.1 설정 14곳(`orchestrator.py:62, 83, 95, 135, 154, 207, 246, 259, 277, 299, 335, 390, 409, 458`)과 정면충돌하고, 그 결정성이 `validate_hard_facts_by_code`(`:121-125`)의 전제다.

**기본 executor를 쓰면 안 되는 이유**: 크기가 `min(32, cpu+4)`이고 워커는 `--cpu=1`(`deploy-api-cloud-run.yml:114`)이라 **5**다. 세마포어는 32까지 허용하는데(`:116`) 실제로는 5에서 조용히 직렬화된다.

**Files:**
- Create: `backend/app/translation/bedrock_client.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_bedrock_json_client.py`

**Interfaces:**
- Consumes: Task 8의 확장된 `is_quota_exhausted_error`, `call_with_quota_backoff`, `_get_call_semaphore`, `_parse_json` (전부 `gemini_client.py`)
- Produces: `BedrockJsonClient.from_settings(settings) -> BedrockJsonClient`, `generate_json(...) -> dict[str, Any]`. Task 9의 팩토리가 이걸 만든다.

- [ ] **Step 1: 의존성을 추가한다**

`backend/requirements.txt` 마지막 줄 다음에 추가:

```
boto3==1.43.78
```

```bash
python -c "import boto3, botocore; print(boto3.__version__, botocore.__version__)"
```

Expected: `1.43.78 1.43.78` (설치 확인됨)

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`backend/tests/test_bedrock_json_client.py`:

```python
import asyncio
import threading
import unittest
from typing import Any

from app.core.config import Settings
from app.translation.bedrock_client import BedrockJsonClient, _extract_bedrock_text


def _response(text: str, *, with_reasoning: bool = False) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if with_reasoning:
        content.append({"reasoningContent": {"reasoningText": {"text": "생각"}}})
    content.append({"text": text})
    return {"output": {"message": {"role": "assistant", "content": content}}}


class _FakeBedrock:
    """converse() 를 흉내낸다. 요청과 호출 스레드를 기록한다."""

    def __init__(self, text: str = '"a": 1}') -> None:
        self.text = text
        self.requests: list[dict[str, Any]] = []
        self.threads: set[str] = set()
        self.barrier: threading.Barrier | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        self.threads.add(threading.current_thread().name)
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return _response(self.text)


def _client(fake: _FakeBedrock, **kwargs: Any) -> BedrockJsonClient:
    client = BedrockJsonClient(model="global.anthropic.claude-haiku-4-5-20251001-v1:0", **kwargs)
    client._client = fake
    return client


class ExtractTextTest(unittest.TestCase):
    def test_skips_reasoning_blocks(self) -> None:
        self.assertEqual(_extract_bedrock_text(_response('"a": 1}', with_reasoning=True)), '"a": 1}')

    def test_raises_when_no_text_block(self) -> None:
        with self.assertRaises(RuntimeError):
            _extract_bedrock_text({"output": {"message": {"content": []}}})


class RequestShapeTest(unittest.IsolatedAsyncioTestCase):
    async def test_prefill_is_sent_and_reattached(self) -> None:
        fake = _FakeBedrock('"a": 1}')
        result = await _client(fake).generate_json(prompt="P", temperature=0.0)
        self.assertEqual(result, {"a": 1})
        messages = fake.requests[0]["messages"]
        self.assertEqual(messages[0], {"role": "user", "content": [{"text": "P"}]})
        self.assertEqual(messages[1], {"role": "assistant", "content": [{"text": "{"}]})

    async def test_model_echoing_the_brace_is_not_double_prefixed(self) -> None:
        """프리필을 무시하고 완전한 JSON 을 돌려주는 모델이 있다.

        무조건 "{" 를 앞에 붙이면 "{{...}" 가 되어 파싱이 깨진다.
        """
        fake = _FakeBedrock('{"a": 1}')
        self.assertEqual(await _client(fake).generate_json(prompt="P"), {"a": 1})

    async def test_prefill_can_be_disabled(self) -> None:
        fake = _FakeBedrock('{"a": 1}')
        await _client(fake, use_json_prefill=False).generate_json(prompt="P")
        self.assertEqual(len(fake.requests[0]["messages"]), 1)

    async def test_thinking_is_never_sent(self) -> None:
        """thinking 을 켜면 Bedrock 이 temperature 를 1로 강제한다.

        현행 0.0/0.1 설정의 결정성이 validate_hard_facts_by_code 의 전제라
        Bedrock 경로에서는 항상 OFF 다.
        """
        fake = _FakeBedrock()
        client = _client(fake)
        await client.generate_json(prompt="P", temperature=0.0, thinking_budget=0)
        with self.assertLogs("app.translation.bedrock_client", level="WARNING") as logs:
            await client.generate_json(prompt="P", temperature=0.0, thinking_budget=4096)
        self.assertTrue(any("thinking" in line for line in logs.output))
        for request in fake.requests:
            self.assertNotIn("additionalModelRequestFields", request)
            self.assertEqual(request["inferenceConfig"]["temperature"], 0.0)

    async def test_model_override_wins(self) -> None:
        fake = _FakeBedrock()
        client = _client(fake, source_hard_fact_model="apac.anthropic.claude-3-haiku-20240307-v1:0")
        await client.generate_json(prompt="P", model=client.source_hard_fact_model)
        self.assertEqual(fake.requests[0]["modelId"], "apac.anthropic.claude-3-haiku-20240307-v1:0")


class ExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_calls_run_on_the_clients_own_threads(self) -> None:
        """asyncio 기본 executor 는 워커(--cpu=1)에서 5개라 조용히 직렬화된다.

        전용 풀이 있으면 8개가 동시에 안에 들어가야 한다.
        """
        fake = _FakeBedrock()
        fake.barrier = threading.Barrier(8)
        client = _client(fake, max_workers=8)
        await asyncio.gather(*(client.generate_json(prompt=f"P{i}") for i in range(8)))
        self.assertEqual(len(fake.requests), 8)
        self.assertTrue(all(name.startswith("bedrock") for name in fake.threads), fake.threads)


class FromSettingsTest(unittest.TestCase):
    def test_reads_settings(self) -> None:
        settings = Settings(
            TRANSLATION_BACKEND="bedrock",
            BEDROCK_TRANSLATION_MODEL="global.anthropic.claude-sonnet-4-6",
            BEDROCK_MECHANICAL_MODEL="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            GEMINI_MAX_CONCURRENCY=16,
        )
        client = BedrockJsonClient.from_settings(settings)
        self.assertEqual(client.model, "global.anthropic.claude-sonnet-4-6")
        self.assertEqual(client.source_hard_fact_model, "global.anthropic.claude-haiku-4-5-20251001-v1:0")
        self.assertEqual(client.region, "ap-northeast-2")

    def test_mechanical_model_defaults_to_translation_model(self) -> None:
        client = BedrockJsonClient.from_settings(Settings(TRANSLATION_BACKEND="bedrock"))
        self.assertEqual(client.source_hard_fact_model, client.model)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_bedrock_json_client -v
```

Expected: `ModuleNotFoundError: No module named 'app.translation.bedrock_client'`

- [ ] **Step 4: 클라이언트를 쓴다**

`backend/app/translation/bedrock_client.py`:

```python
"""AWS Bedrock Converse API 로 JSON 을 받아오는 클라이언트.

전역 세마포어(gemini_client:61-71)·백오프(:35-58)·JSON 파서(:270-298)를 그대로
재사용한다. 새로 쓰는 것은 요청 조립·응답 추출·스레드 브리지 셋뿐이다.

크롤러가 빌려 쓰는 call_with_quota_backoff / _repair_invalid_json_escapes 의
이름·위치는 건드리지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from app.translation.gemini_client import (
    _get_call_semaphore,
    _parse_json,
    call_with_quota_backoff,
)

if TYPE_CHECKING:
    from app.core.config import Settings

LOGGER = logging.getLogger(__name__)

# Converse 는 응답 길이 상한을 요청에서 받는다. Gemini 의 기본과 맞춘다.
BEDROCK_MAX_TOKENS = 8192
# Bedrock 에는 response_mime_type 동등 기능이 없다. assistant 턴을 "{" 로 시작시켜
# 모델이 산문 없이 JSON 을 이어 쓰게 만든다. toolConfig 는 쓰지 않는다 —
# 프롬프트 13개의 스키마를 JSON Schema 로 다시 써야 해서 A/B 통제가 무너진다.
JSON_PREFILL = "{"


def _extract_bedrock_text(response: dict[str, Any]) -> str:
    """Converse 응답에서 텍스트 블록을 꺼낸다. reasoningContent 블록은 건너뛴다."""
    message = (response.get("output") or {}).get("message") or {}
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise RuntimeError("Bedrock 응답에서 텍스트를 찾지 못했습니다.")


class BedrockJsonClient:
    def __init__(
        self,
        *,
        model: str,
        source_hard_fact_model: str | None = None,
        region: str = "ap-northeast-2",
        timeout_seconds: float = 60.0,
        max_workers: int = 32,
        use_json_prefill: bool = True,
    ) -> None:
        self.model = model
        self.source_hard_fact_model = source_hard_fact_model or model
        self.region = region
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.use_json_prefill = use_json_prefill
        self._client: Any = None
        # boto3 converse() 는 블로킹이다. asyncio 기본 executor 는 min(32, cpu+4) 이고
        # 워커는 --cpu=1 이라 5다 — 세마포어가 32를 허용해도 5에서 조용히 직렬화된다.
        # 그래서 클라이언트가 자기 풀을 소유한다.
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="bedrock",
        )

    @classmethod
    def from_settings(cls, settings: "Settings") -> "BedrockJsonClient":
        return cls(
            model=settings.bedrock_translation_model,
            source_hard_fact_model=settings.bedrock_mechanical_model,
            region=settings.bedrock_region,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_workers=settings.bedrock_max_workers,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(
                    # Gemini SDK 결함 #2705 의 Bedrock 판 대응 — 여기서는 지원 노브다.
                    tcp_keepalive=True,
                    # SDK 내부 재시도를 끄고 앱 백오프(call_with_quota_backoff)만 남긴다.
                    retries={"max_attempts": 1, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=self.timeout_seconds,
                    # 커넥션 풀이 스레드 수보다 작으면 거기서 다시 직렬화된다.
                    max_pool_connections=self.max_workers,
                ),
            )
        return self._client

    def _build_request(self, *, prompt: str, temperature: float, model: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": prompt}]}]
        if self.use_json_prefill:
            messages.append({"role": "assistant", "content": [{"text": JSON_PREFILL}]})
        return {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": BEDROCK_MAX_TOKENS,
            },
            # thinking(additionalModelRequestFields)은 넣지 않는다 — 아래 주석 참조.
        }

    async def _converse_in_thread(
        self, *, prompt: str, temperature: float, model: str
    ) -> dict[str, Any]:
        request = self._build_request(prompt=prompt, temperature=temperature, model=model)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._get_client().converse(**request),
        )

    async def generate_json(
        self,
        *,
        prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        target_model = model or self.model

        if thinking_budget:
            # Bedrock 은 extended thinking 을 켜면 temperature 를 1로 강제한다.
            # 파이프라인 14곳이 0.0/0.1 을 쓰고 그 결정성이
            # validate_hard_facts_by_code 의 전제라 온도를 조용히 바꿀 수 없다.
            # 그래서 무시하되, 조용히 무시하지 않고 경고를 남긴다.
            LOGGER.warning(
                "Bedrock 경로는 thinking 을 켜지 않는다(temperature=1 강제 회피). "
                "요청값을 무시한다: model=%s thinking_budget=%s",
                target_model,
                thinking_budget,
            )

        # 전역 세마포어로 동시 호출 수를 묶는다(Gemini 경로와 같은 상한을 공유).
        async with _get_call_semaphore():
            response = await call_with_quota_backoff(
                lambda: self._converse_in_thread(
                    prompt=prompt,
                    temperature=temperature,
                    model=target_model,
                ),
                label=f"translation:{target_model}",
            )

        text = _extract_bedrock_text(response)
        # 프리필을 무시하고 완전한 JSON 을 돌려주는 모델이 있다. 무조건 "{" 를 붙이면
        # "{{...}" 가 되어 파서가 깨지므로, 이미 열려 있으면 그대로 둔다.
        if self.use_json_prefill and not text.startswith(JSON_PREFILL):
            text = JSON_PREFILL + text
        return _parse_json(text)
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_bedrock_json_client -v
```

Expected: 10 tests PASS. 특히 `test_calls_run_on_the_clients_own_threads`가 통과해야 한다 — 이게 «5개에서 조용히 직렬화» 함정을 잡는 유일한 장치다.

- [ ] **Step 6: 실제 Bedrock 을 한 번 때려본다 (값 출력 금지)**

```bash
export AWS_ACCESS_KEY_ID="$(gcloud secrets versions access latest --secret=aws-bedrock-access-key-id)"
export AWS_SECRET_ACCESS_KEY="$(gcloud secrets versions access latest --secret=aws-bedrock-secret-access-key)"
echo "키 길이: ${#AWS_ACCESS_KEY_ID} / ${#AWS_SECRET_ACCESS_KEY}"
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import asyncio, time
from app.translation.bedrock_client import BedrockJsonClient

async def main():
    for model in ('global.anthropic.claude-haiku-4-5-20251001-v1:0', 'global.anthropic.claude-sonnet-4-6'):
        client = BedrockJsonClient(model=model, max_workers=4)
        t0 = time.perf_counter()
        out = await client.generate_json(
            prompt='Return JSON: {\"ok\": true, \"lang\": \"<ISO code of Korean>\"}',
            temperature=0.0,
        )
        print(f'{model}: {(time.perf_counter()-t0)*1000:.0f}ms -> {out}')

asyncio.run(main())
"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

Expected: 두 모델 모두 `{'ok': True, 'lang': 'ko'}` 형태의 dict. 실측 지연은 **Haiku 4.5 약 780~920ms, Sonnet 4.6 약 1,255~1,303ms**(2026-08-27, 초경량 프롬프트 2회).

> **`AccessDeniedException`이 나면 중단하고 보고할 것** — IAM 사용자 `naranhi-bedrock`에 `bedrock:InvokeModel`이 없거나 모델 액세스가 안 열린 것이다. **키 값은 절대 출력하지 않는다** — 위 명령은 길이만 찍는다.

- [ ] **Step 7: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 8: 커밋**

```bash
git add backend/app/translation/bedrock_client.py backend/requirements.txt \
  backend/tests/test_bedrock_json_client.py
git commit -m "feat(translation): Bedrock Converse 백엔드 추가 (다크 — 아직 배선 안 함)

전역 세마포어·백오프·JSON 파서는 gemini_client 것을 그대로 재사용한다.
새로 쓰는 것은 요청 조립·응답 추출·스레드 브리지 셋뿐이다.

흡수한 차이 넷:

1. thinking — Bedrock 은 켜면 temperature 를 1로 강제한다. 파이프라인 14곳이
   0.0/0.1 을 쓰고 그 결정성이 validate_hard_facts_by_code 의 전제라
   온도를 조용히 바꿀 수 없다. 그래서 항상 OFF 로 두고, 양수 값이 오면
   조용히 무시하지 않고 경고를 남긴다.

2. JSON 강제 — response_mime_type 동등 기능이 없다. toolConfig 는 쓰지 않는다:
   프롬프트 13개의 산문 스키마를 JSON Schema 로 다시 써야 해서
   «프롬프트는 고정 변수» 라는 A/B 통제가 무너진다.
   assistant 프리필 '{' + 기존 파서 복구로 간다.
   프리필을 무시하고 완전한 JSON 을 돌려주는 모델을 위해,
   이미 '{' 로 열려 있으면 다시 붙이지 않는다.

3. 응답 위치 — output.message.content[] 에서 reasoningContent 블록을 건너뛴다.

4. boto3 converse() 는 동기다. asyncio 기본 executor 는 min(32, cpu+4) 이고
   워커가 --cpu=1 이라 5다 — 세마포어가 32를 허용해도 5에서 조용히 직렬화된다.
   클라이언트가 전용 ThreadPoolExecutor 를 소유하고,
   botocore 커넥션 풀도 같은 크기로 맞춘다.

aioboto3 를 쓰지 않는 이유: aiobotocore 가 botocore 를 핀으로 묶어
requirements 해석을 어렵게 만든다. 스레드 브리지가 더 작다."
```

---

## Task 11: 호출부 배선 + AWS 시크릿 주입 + Bedrock arm 평가

`GeminiJsonClient.from_settings(settings)` 8곳과 타입 힌트 3곳, 그리고 스크립트 2곳을 팩토리로 바꾼다. 기계적인 교체다.

배포는 여전히 `TRANSLATION_BACKEND=gemini`라 **런타임 동작이 0**이다. 다만 AWS 시크릿은 이 배포에서 미리 주입해둔다 — Task 12가 env 한 줄만 바꾸면 되게 하려면 자격증명이 이미 컨테이너에 있어야 한다.

**Files:**
- Modify: `backend/app/services/notice_service.py:155, 250, 269, 284, 303, 436, 526, 579` (생성), `:465, 628, 711` (타입 힌트)
- Modify: `scripts/translation_quality_driver.py:39, 115`
- Modify: `scripts/run_iteration.py:37, 116`
- Modify: `.github/workflows/deploy-api-cloud-run.yml` (API 서비스 `secrets:` + 워커 Job `--set-secrets`)
- Modify: `.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/arms.json` (arm-c/d/e 추가)
- Modify: `.agents/translation-quality/iterations/2026-08-27_iter-negative-control/arms.json` (같은 3개 — G6용)
- Modify: `backend/app/core/config.py` (**승급했을 때만** — 기본값 Haiku 유지가 기본 경로다)

**Interfaces:**
- Consumes: Task 9의 `build_json_client`, `JsonModelClient`
- Produces: 번역 경로 전체가 `TRANSLATION_BACKEND` 하나로 갈린다. Task 12가 그 값을 뒤집는다.

- [ ] **Step 1: 교체 대상을 전부 찾는다**

```bash
grep -rn "GeminiJsonClient" --include=*.py backend/app scripts | grep -v "gemini_client.py"
```

Expected: `notice_service.py`의 import 1곳 + 생성 8곳 + 타입 힌트 3곳, `orchestrator.py`의 import·타입 힌트, `translation_quality_driver.py` 2곳, `run_iteration.py` 2곳. **목록을 기록해 둘 것.**

- [ ] **Step 2: `notice_service.py`를 팩토리로 바꾼다**

import 블록에서 `GeminiJsonClient` import를 남겨둔 채(다른 곳에서 쓰지 않으면 제거) 아래를 추가한다:

```python
from app.translation.json_client import JsonModelClient, build_json_client
```

생성 8곳(`:155, 250, 269, 284, 303, 436, 526, 579`)의 `GeminiJsonClient.from_settings(settings)`를 전부 `build_json_client(settings)`로 바꾼다.

타입 힌트 3곳(`:465` `_build_korean_notice_artifacts`, `:628` `_best_effort_translate_notice`, `:711` `_translate_message_to_korean`)의 `gemini: GeminiJsonClient`를 `gemini: JsonModelClient`로 바꾼다.

- [ ] **Step 3: 오케스트레이터 타입 힌트도 넓힌다**

`backend/app/translation/orchestrator.py`의 import에서 `from app.translation.gemini_client import GeminiJsonClient`를 지우고 아래로 바꾼다:

```python
from app.translation.json_client import JsonModelClient
```

`TranslationPipeline.__init__`의 인자 타입을 바꾼다:

```python
    def __init__(self, gemini: JsonModelClient) -> None:
```

`orchestrator.py:63`의 `getattr(self.gemini, "source_hard_fact_model", None)`은 **그대로 둔다** — 프로토콜에 있는 속성이지만 테스트용 가짜가 안 가질 수도 있다.

- [ ] **Step 4: 스크립트 2개도 바꾼다**

`scripts/translation_quality_driver.py:39`와 `scripts/run_iteration.py:37`의 import를 바꾼다:

```python
from app.translation.json_client import build_json_client  # noqa: E402
```

두 파일의 클라이언트 생성(`translation_quality_driver.py:115`, `run_iteration.py:116`)을 바꾼다:

```python
    gemini = build_json_client(settings)
```

그리고 두 파일의 «어떤 백엔드로 도는지» 출력줄을 정직하게 고친다 — `run_iteration.py:119-123`:

```python
    if settings.translation_backend == "bedrock":
        backend = f"Bedrock {settings.bedrock_region}"
        model_name = settings.bedrock_translation_model
    else:
        backend = "Vertex AI" if settings.use_vertex else "AI Studio API key"
        model_name = settings.gemini_translation_model or settings.gemini_model
    print(
        f"Iteration: {iter_dir.name} | arm={args.arm or '(none)'} | model={model_name} ({backend}) "
        f"| notices={len(notices)} | langs={','.join(target_langs)}"
    )
```

`translation_quality_driver.py:118-122`도 같은 방식으로 고친다.

> **주의**: 스펙 §5.1은 드라이버 1곳(`translation_quality_driver.py:115`)만 적었지만 `run_iteration.py:116`도 같은 자리다. 둘 다 바꾸지 않으면 Task 3의 arm 러너가 Bedrock arm에서 계속 Gemini를 부른다.

- [ ] **Step 5: 잔존 참조가 없는지 확인한다**

```bash
grep -rn "GeminiJsonClient" --include=*.py backend/app scripts | grep -v "gemini_client.py\|json_client.py"
echo "종료코드: $?  (1 이면 없음 = 정상)"
```

Expected: 출력 없음, 종료코드 1. `gemini_client.py`(정의)와 `json_client.py`(팩토리 안 지연 import)만 남는다.

- [ ] **Step 6: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. `test_meal_label_translation`·`test_subject_label_translation`·`test_notice_api`가 `GeminiJsonClient`를 patch하고 있다면 patch 대상 경로를 `app.services.notice_service.build_json_client`로 바꾼다.

- [ ] **Step 7: 다크 상태를 확인한다 — 팩토리가 정말 Gemini를 준다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
from app.core.config import get_settings
from app.translation.json_client import build_json_client
s = get_settings()
print('TRANSLATION_BACKEND =', s.translation_backend)
print('클라이언트 =', type(build_json_client(s)).__name__)
"
```

Expected: `TRANSLATION_BACKEND = gemini`, `클라이언트 = GeminiJsonClient`

- [ ] **Step 8: 배포에 AWS 시크릿을 미리 주입한다 (백엔드는 아직 gemini)**

`.github/workflows/deploy-api-cloud-run.yml`의 워커 Job `--set-secrets`(117행)에 두 항목을 더한다:

```yaml
            --set-secrets="SUPABASE_SERVICE_ROLE_KEY=supabase-service-role-key:latest,GEMINI_API_KEY=gemini-api-key:latest,CRAWLER_INTERNAL_TOKEN=crawler-internal-token:latest,NEIS_API_KEY=neis-api-key:latest,AWS_ACCESS_KEY_ID=aws-bedrock-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-bedrock-secret-access-key:latest"
```

API 서비스의 `secrets:` 블록(77~87행 부근)에도 같은 두 줄을 넣는다:

```yaml
            AWS_ACCESS_KEY_ID=aws-bedrock-access-key-id:latest
            AWS_SECRET_ACCESS_KEY=aws-bedrock-secret-access-key:latest
```

`TRANSLATION_BACKEND`는 **아직 넣지 않는다** — 기본값 `gemini`가 그대로 적용된다.

- [ ] **Step 9: 배포 후 런타임 동작이 그대로인지 확인한다**

머지·배포 후 번역 1건을 돌리고 로그를 본다.

```bash
gcloud run jobs executions list --job="$TRANSLATION_WORKER_JOB" --region="$REGION" --limit=1
gcloud logging read \
  'resource.type=cloud_run_job AND textPayload:"translation job finished"' \
  --limit=5 --format='value(textPayload)'
```

Expected: 배포 전과 동일한 로그 형태. `label=translation:global.anthropic.…`가 **나오지 않아야 한다**(아직 Gemini).

- [ ] **Step 10: Bedrock arm 3개를 추가한다 (Haiku 우선 순서로)**

**arm 순서가 모델 선택 정책이다**(스펙 §5.10.1) — arm-c가 Haiku(기본 후보), arm-d가 Sonnet(승급 후보)이다. 셋 다 `arms.json`의 `arms` 배열에 추가하고, **negative control 폴더의 `arms.json`에도 같은 항목을 넣는다**(Task 2 Step 8).

```json
    {
      "id": "arm-c",
      "label": "bedrock-claude-haiku-4-5",
      "env": {
        "TRANSLATION_BACKEND": "bedrock",
        "BEDROCK_TRANSLATION_MODEL": "global.anthropic.claude-haiku-4-5-20251001-v1:0"
      }
    },
    {
      "id": "arm-d",
      "label": "bedrock-claude-sonnet-4-6",
      "env": {
        "TRANSLATION_BACKEND": "bedrock",
        "BEDROCK_TRANSLATION_MODEL": "global.anthropic.claude-sonnet-4-6"
      }
    },
    {
      "id": "arm-e",
      "label": "bedrock-mixed-haiku-mechanical-plus-sonnet-translation",
      "env": {
        "TRANSLATION_BACKEND": "bedrock",
        "BEDROCK_TRANSLATION_MODEL": "global.anthropic.claude-sonnet-4-6",
        "BEDROCK_MECHANICAL_MODEL": "global.anthropic.claude-haiku-4-5-20251001-v1:0"
      }
    }
```

> **Nova arm은 만들지 않는다.** 2026-08-27 실측에서 Nova Lite·Nova Pro가 **읽지 못한 첨부의 본문을 지어냈다**(스펙 §5.9.2·§5.9.3) — 한국어 본문 생성 경로의 후보가 아니다. **Opus arm도 만들지 않는다**(비용, 사용자 지시). Global Constraints 참조.
>
> **arm-e가 «혼합»인 이유**: 기계 단계(하드팩트 추출)는 Haiku로 충분한데 번역 단계만 승급이 필요할 수 있다. arm-c가 통과하면 **arm-d·arm-e는 채택 후보가 아니다** — 더 느리고 비싼데 게이트가 구분하지 못하는 차이는 채택 근거가 되지 못한다(스펙 §5.10.1).

- [ ] **Step 11: 세 arm을 완주시킨다**

```bash
export AWS_ACCESS_KEY_ID="$(gcloud secrets versions access latest --secret=aws-bedrock-access-key-id)"
export AWS_SECRET_ACCESS_KEY="$(gcloud secrets versions access latest --secret=aws-bedrock-secret-access-key)"
for ARM in arm-c arm-d arm-e; do
  python scripts/run_iteration.py \
    --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ \
    --arm "$ARM"
done
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

Expected: arm별 90 json. 출력 첫 줄에 `model=global.anthropic.claude-… (Bedrock ap-northeast-2)`가 찍힌다.

- [ ] **Step 12: JSON 파싱 실패 건수를 센다 (프리필이 실제로 먹는가)**

```bash
python -c "
import json, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
root = pathlib.Path('.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001')
for arm in ('arm-a','arm-b','arm-c','arm-d','arm-e'):
    paths = list(root.glob(f'notices/*/*/pipeline-output/{arm}/*.json'))
    if not paths: continue
    errs = [p for p in paths if json.loads(p.read_text(encoding='utf-8')).get('status') == 'driver_error']
    print(f'{arm}: {len(paths)}건 중 driver_error {len(errs)}건')
    for p in errs[:3]:
        print('   ', p.parent.parent.parent.name, json.loads(p.read_text(encoding='utf-8')).get('error','')[:120])
"
```

Expected: 모든 arm에서 `driver_error 0건` (스펙 §13의 «B5 JSON: 파싱 실패 0건»).

> **특정 arm에서만 파싱 실패가 나면 그 모델에서 프리필이 안 먹는 것이다.** 그 경우 `BedrockJsonClient(use_json_prefill=False)`로 그 arm만 다시 돌린다 — 클라이언트에 이미 플래그가 있다(Task 10 Step 4). 설정 노출이 필요하면 `BEDROCK_JSON_PREFILL` 필드를 추가하되, **그 결정은 이 Step의 실측 후에 한다.** 프리필 동작은 스펙 §5.4에서 **미확인**으로 남아 있다.

- [ ] **Step 13: G1·G4·G5를 판정한다**

```bash
for ARM in arm-c arm-d arm-e; do
  echo "=== $ARM ==="
  python scripts/compare_arms.py \
    --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001 \
    --baseline arm-b --arm "$ARM"
done
```

> **기준선이 arm-a가 아니라 arm-b(thinking OFF)다.** Task 7이 이미 배포됐으므로 «현행»은 arm-b이고, 여기서 재는 것은 순수한 «모델 교체 효과»다.

Expected: 적어도 한 arm이 `G1/G4/G5: 통과`. **arm-c(Haiku)가 통과하면 거기서 멈춘다** — Sonnet arm의 결과는 참고 자료이지 채택 후보가 아니다(스펙 §5.10.1).

그 다음 평가자 에이전트로 G2·G3를 판정하고 블라인드를 확인한다:

```bash
python scripts/check_iteration_blind.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001
```

Expected: `모델명 노출 0건`

- [ ] **Step 14: G6을 판정한다 — 모델 교체가 환각을 들여오지 않았는가**

**이 Step이 이 Task에서 가장 중요하다.** 모델 교체는 «번역이 조금 나빠지는» 위험만 들여오는 게 아니다. 2026-08-27 실측에서 어떤 모델은 **읽지 못한 입력에 대해 그럴듯한 가정통신문을 지어냈다**(스펙 §5.9.2). Claude Haiku 4.5·Sonnet 4.6은 같은 입력에서 정직하게 거부했지만, **그건 판독 시험에서의 관찰이고 이 파이프라인의 프롬프트 아래에서 다시 확인해야 한다.**

```bash
NEG=.agents/translation-quality/iterations/2026-08-27_iter-negative-control
export AWS_ACCESS_KEY_ID="$(gcloud secrets versions access latest --secret=aws-bedrock-access-key-id)"
export AWS_SECRET_ACCESS_KEY="$(gcloud secrets versions access latest --secret=aws-bedrock-secret-access-key)"
for ARM in arm-c arm-d arm-e; do
  python scripts/run_iteration.py --iter "$NEG/" --arm "$ARM"
  echo "=== G6 $ARM ==="
  python scripts/check_hallucination.py --iter-dir "$NEG" --arm "$ARM"
done
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

Expected: 채택 후보 arm이 `G6: 통과`이고, 찍힌 본문이 «원문을 읽을 수 없다» 계열이거나 비어 있다.

> **G6에 실패한 arm은 다른 게이트를 전부 통과해도 채택하지 않는다.** 지어낸 본문은 학교 이름을 달고 학부모에게 간다 — 되돌릴 방법이 없다(스펙 §5.9.3). 숫자가 없어도 학교·날짜·행사가 들어 있으면 **실패로 판정하고 보고할 것.** R1·R2가 못 잡는 자리다.

- [ ] **Step 15: 승자 arm을 기본 모델로 확정한다**

**순서가 정해져 있다** (스펙 §5.10.1):

1. **arm-c(Haiku)가 G1~G6을 전부 통과하면 그것으로 확정한다.** `config.py` 기본값이 이미 Haiku이므로 **바꿀 것이 없다.**
2. arm-c가 게이트를 못 넘을 때만 **arm-d(Sonnet) 또는 arm-e(혼합)로 승급**한다. 승급하면 `config.py`의 `BEDROCK_TRANSLATION_MODEL`(과 필요하면 `BEDROCK_MECHANICAL_MODEL`) 기본값을 그 값으로 바꾸고, **어느 게이트가 왜 실패했는지를 커밋 메시지에 적는다.**
3. **Opus로 올리지 않는다.** Sonnet으로도 게이트를 못 넘으면 모델을 더 올리는 게 아니라 프롬프트·단계 설계를 다시 본다(별건, 이 계획 밖).

> `wall_seconds`가 더 낮다는 이유만으로 승급 방향을 뒤집지 않는다 — 지연은 G5로 이미 게이트에 들어가 있고, 정책상 **동률이면 Haiku가 이긴다.**

- [ ] **Step 16: 커밋**

```bash
git add backend/app/services/notice_service.py backend/app/translation/orchestrator.py \
  backend/app/core/config.py scripts/translation_quality_driver.py scripts/run_iteration.py \
  .github/workflows/deploy-api-cloud-run.yml \
  .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001
git commit -m "refactor(translation): 번역 클라이언트 생성을 백엔드 팩토리로 일원화

GeminiJsonClient.from_settings 8곳(notice_service:155,250,269,284,303,436,526,579)과
타입 힌트 3곳(:465,:628,:711), 스크립트 2곳을 build_json_client 로 바꾼다.
스펙 §5.1 은 드라이버 1곳만 적었지만 run_iteration.py:116 도 같은 자리다 —
둘 다 바꾸지 않으면 arm 러너가 Bedrock arm 에서 계속 Gemini 를 부른다.

배포는 여전히 TRANSLATION_BACKEND=gemini 라 런타임 동작 변화는 0이다.
다만 AWS 자격증명은 이 배포에서 미리 주입한다 — 다음 Task 가 env 한 줄만
바꾸면 되게 하려면 키가 이미 컨테이너에 있어야 한다.
키는 --set-secrets 로만 넣는다(명령줄·URL 금지).

평가 arm 에 Bedrock 3종(Haiku 4.5 / Sonnet 4.6 / 혼합)을 추가한다.
순서가 곧 정책이다 — Haiku 가 기본이고 Sonnet 은 게이트를 못 넘을 때만 승급한다.
Nova arm 은 만들지 않는다: 2026-08-27 실측에서 읽지 못한 첨부의 본문을 지어냈다.
Opus arm 도 만들지 않는다(비용).

기준선은 arm-a 가 아니라 arm-b(thinking OFF)다. 현행이 이미 그것이므로
여기서 재는 것은 순수한 모델 교체 효과다.

G6(환각 negative control)을 arm 마다 돌린다. 모델 교체는 «조금 나빠지는» 위험만
들여오는 게 아니라 «읽지 못했을 때 지어내는» 모델을 들여올 수 있다.
G6 에 실패하면 나머지를 전부 통과해도 채택하지 않는다."
```

---

## Task 12: B6 — 워커만 Bedrock 전환

**이게 진짜 반쪽 상태다.** 큐에 쌓인 공지 번역(워커 Job)은 Bedrock으로, 사용자가 화면에서 유발하는 라벨·요약 번역(API 서비스)은 Gemini로 간다. 둘이 같은 코드·같은 프롬프트를 쓰고 **롤백 단위가 서로 독립**이다.

같은 공지의 본문 번역(워커)과 소스 번역(`translation_worker.py:53` → `_translate_sources_for_locale_background`)은 **같은 워커 프로세스 안**이라 함께 Bedrock으로 간다. 공지 단위로 언어·톤이 갈릴 위험은 없다.

**Files:**
- Modify: `.github/workflows/deploy-api-cloud-run.yml:116` (워커 Job `--set-env-vars`에 `TRANSLATION_BACKEND=bedrock`)

**Interfaces:**
- Consumes: Task 11이 배선한 팩토리 + 이미 주입된 AWS 자격증명
- Produces: 워커 경로만 Bedrock. 롤백은 이 한 줄 되돌리기 + 워커 Job만 재배포.

- [ ] **Step 1: 배포 전 Bedrock 크레딧 잔액을 기록한다**

```bash
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '30 days ago' +%F),End=$(date +%F) \
  --granularity MONTHLY --metrics UnblendedCost BlendedCost \
  --filter '{"Dimensions":{"Key":"SERVICE","Values":["Amazon Bedrock"]}}' \
  --output json 2>/dev/null || echo "Cost Explorer 권한 없음 — AWS 콘솔 Billing 화면에서 크레딧 잔액을 직접 확인하고 여기 적어둘 것"
```

Expected: 숫자든 «권한 없음»이든, **배포 전 값을 기록으로 남긴다.** 전용 IAM 사용자는 모델 호출 권한만 있으므로 대체로 후자다 — 그러면 콘솔 값을 이 계획서 옆에 메모한다.

- [ ] **Step 2: 워커 Job에만 env를 넣는다**

`.github/workflows/deploy-api-cloud-run.yml`의 **워커 Job** `--set-env-vars`(116행)에 `TRANSLATION_BACKEND=bedrock`을 더한다:

```yaml
            --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=INFO,SUPABASE_URL=${{ vars.NEXT_PUBLIC_SUPABASE_URL }},VERTEX_AI_PROJECT_ID=${{ vars.VERTEX_AI_PROJECT_ID }},VERTEX_AI_LOCATION=${{ vars.VERTEX_AI_LOCATION }},GEMINI_MAX_CONCURRENCY=32,TRANSLATION_THINKING_BUDGET=0,TRANSLATION_BACKEND=bedrock" \
```

**API 서비스(77~87행)는 건드리지 않는다** — 반쪽 상태가 이 Task의 목표다.

- [ ] **Step 3: 워크플로 문법을 검사한다**

```bash
python -c "
import yaml, sys
sys.stdout.reconfigure(encoding='utf-8')
d = yaml.safe_load(open('.github/workflows/deploy-api-cloud-run.yml', encoding='utf-8'))
raw = open('.github/workflows/deploy-api-cloud-run.yml', encoding='utf-8').read()
print('TRANSLATION_BACKEND=bedrock 등장:', raw.count('TRANSLATION_BACKEND=bedrock'))
print('aws-bedrock 시크릿 등장:', raw.count('aws-bedrock-access-key-id'))
assert raw.count('TRANSLATION_BACKEND=bedrock') == 1, '워커 Job 한 곳에만 있어야 한다'
print('OK')
"
```

Expected: `TRANSLATION_BACKEND=bedrock 등장: 1`, `aws-bedrock 시크릿 등장: 2`, `OK`

- [ ] **Step 4: 커밋하고 배포한다**

```bash
git add .github/workflows/deploy-api-cloud-run.yml
git commit -m "feat(translation): 번역 워커만 Bedrock 으로 전환 (반쪽 상태)

큐에 쌓인 공지 번역(워커 Job)은 Bedrock, 사용자가 화면에서 유발하는
라벨·요약 번역(API 서비스)은 Gemini 로 간다. 같은 코드·같은 프롬프트를 쓰고
롤백 단위가 서로 독립이다.

같은 공지의 본문 번역과 소스 번역은 같은 워커 프로세스 안이라
함께 Bedrock 으로 간다 — 공지 단위로 톤이 갈리지 않는다.

되돌리기는 이 한 줄 제거 + 워커 Job 재배포다.
평가 게이트 G1~G6(환각 negative control 포함)은 이전 Task 에서 통과 확인했다.
모델은 Haiku 4.5 다 — Sonnet 승급 없이 게이트를 넘었다."
```

- [ ] **Step 5: 실제로 Bedrock 으로 가는지 로그로 확인한다**

배포 후 번역 잡이 한 번 돌기를 기다린 뒤:

```bash
gcloud logging read \
  'resource.type=cloud_run_job AND resource.labels.job_name="'"$TRANSLATION_WORKER_JOB"'"' \
  --limit=50 --format='value(textPayload)' | grep -i "translation:" | head -10
```

Expected: 백오프 경고가 났다면 `label=translation:global.anthropic.claude-haiku-4-5-…` 형태. 백오프가 안 났다면 로그에 label이 안 찍히므로, 대신 아래로 확인한다:

```bash
gcloud run jobs describe "$TRANSLATION_WORKER_JOB" --region="$REGION" \
  --format='value(spec.template.spec.template.spec.containers[0].env)' | tr ',' '\n' | grep -i "TRANSLATION_"
```

Expected: `TRANSLATION_BACKEND=bedrock`, `TRANSLATION_THINKING_BUDGET=0`

- [ ] **Step 6: 어떤 모델·라우팅을 실제로 호출했는지 확인한다**

```bash
gcloud logging read \
  'resource.type=cloud_run_job AND textPayload:"translation:"' \
  --limit=100 --format='value(textPayload)' \
  | grep -o "translation:[a-z0-9.:-]*" | sort -u
```

Expected: 나오는 값이 **전부 승자 arm의 모델**이다 — 기본 경로면 `translation:global.anthropic.claude-haiku-4-5-…`.

| 나오면 안 되는 것 | 왜 |
|---|---|
| `opus` 포함 문자열 | **금지**(비용, 사용자 지시). 하나라도 있으면 즉시 롤백하고 보고 |
| `nova` 포함 문자열 | 한국어 본문 생성 경로에서 제외. 지어낼 위험이 있다(스펙 §5.9.3) |
| `sonnet` — 승급 없이 배포했는데 나온 경우 | 설정이 계획과 어긋났다. 중단하고 보고 |

> **`global.` 접두 자체는 정상이다** — 사용자 승인됨(스펙 §16 해결됨 Q1). 다만 이 Step의 출력은 «학생 정보가 어느 경로로 나갔는가»의 **기록**이므로, 그대로 남겨둔다(스펙 §5.11 C3). 허용 범위가 바뀌면 `apac.` 계열로 되돌린다.

- [ ] **Step 7: 결제가 크레딧으로 나가는지 확인한다**

AWS 콘솔 Billing → Credits 에서 Step 1에 기록한 값과 비교한다.

Expected: Bedrock 사용량이 늘고 **현금 청구는 $0**. 크레딧 차감만 있어야 한다. 현금이 잡히면 크레딧이 소진됐거나 적용 대상이 아닌 모델이라는 뜻이므로 중단하고 보고한다.

- [ ] **Step 8: 워커 번역 산출물의 품질을 표본으로 본다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python -c "
import json,os,urllib.request,sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=id,target_language,validation,created_at&order=created_at.desc&limit=60')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=60).read().decode())
c=Counter()
for x in rows:
    v=x.get('validation') or {}
    c[('hard_fact', ((v.get('hard_fact') or {}).get('status')))] += 1
    c[('context_tone', ((v.get('context_tone') or {}).get('status')))] += 1
print(f'최근 {len(rows)}건')
for key,count in sorted(c.items()):
    print(' ', key, count)
"
```

Expected: `('hard_fact', 'passed')`가 압도적. `failed`가 배포 전 표본보다 늘었으면 롤백 후보다.

---

## Task 13: B7 — 전면 Bedrock 전환 + B9 기존 번역 155건 백필

Task 12가 7일간 무사고면 API 서비스도 넘긴다. 그 다음 기존 번역을 새 파이프라인으로 재생성한다.

**백필은 배치 추론을 쓰지 않는다.** 50% 할인이 있지만 «비용은 목표가 아니다»(결정 #2)이고, 155건 × 40초 ÷ 동시 10 ≈ **10분**이면 워커가 그냥 끝낸다. 배치 API는 «썼어야 했다»가 아니라 «쓸 이유가 없다»로 기록한다.

**Files:**
- Modify: `.github/workflows/deploy-api-cloud-run.yml` (API 서비스 `env_vars`)
- Create: `scripts/requeue_translations.py`

**Interfaces:**
- Consumes: `app_jobs` 큐 (`job_type = "notice_translation"`), `notice_ai_translations`
- Produces: 전 경로 Bedrock + 기존 번역 재생성. Gemini 호출이 문서판독·크롤러에만 남는다.

- [ ] **Step 1: Task 12 배포 후 7일 무사고를 확인한다**

```bash
gcloud logging read \
  'resource.type=cloud_run_job AND severity>=ERROR AND resource.labels.job_name="'"$TRANSLATION_WORKER_JOB"'"' \
  --freshness=7d --limit=50 --format='value(timestamp,textPayload)'
```

Expected: 출력 없음(또는 Bedrock과 무관한 기존 오류만). **번역 실패가 쌓여 있으면 전면 전환하지 말고 보고할 것.**

- [ ] **Step 2: API 서비스도 넘긴다**

`.github/workflows/deploy-api-cloud-run.yml`의 **API 서비스** `env_vars` 블록(77~87행)에 한 줄을 더한다:

```yaml
            TRANSLATION_BACKEND=bedrock
```

- [ ] **Step 3: 두 곳 다 켜졌는지 검사한다**

```bash
python -c "
import sys
sys.stdout.reconfigure(encoding='utf-8')
raw = open('.github/workflows/deploy-api-cloud-run.yml', encoding='utf-8').read()
n = raw.count('TRANSLATION_BACKEND=bedrock')
print('TRANSLATION_BACKEND=bedrock 등장:', n)
assert n == 2, 'API 서비스와 워커 Job 두 곳이어야 한다'
print('OK')
"
```

Expected: `등장: 2`, `OK`

- [ ] **Step 4: 커밋하고 배포한다**

```bash
git add .github/workflows/deploy-api-cloud-run.yml
git commit -m "feat(translation): API 서비스도 Bedrock 으로 — 전면 전환

워커만 Bedrock 으로 돌린 반쪽 상태에서 7일 무사고를 확인했다.
이제 화면에서 유발하는 라벨·요약 번역도 Bedrock 으로 간다.

이 커밋 이후 Gemini 호출은 문서판독(GeminiDocumentExtractor)과
크롤러에만 남는다. 둘 다 이 사업의 범위 밖이다.

되돌리기는 env 두 줄 제거 + 재배포다."
```

- [ ] **Step 5: Gemini 잔여 호출이 문서판독·크롤러뿐인지 확인한다**

```bash
gcloud logging read \
  'severity>=WARNING AND textPayload:"Gemini quota(429)"' \
  --freshness=2d --limit=50 --format='value(resource.labels.job_name,resource.labels.service_name,textPayload)'
```

Expected: 번역 워커에서 `label=translation:gemini-…`가 **나오지 않는다**. 문서판독·크롤러 Job에서만 Gemini 관련 로그가 남는다.

- [ ] **Step 6: 백필 스크립트를 쓴다**

`scripts/requeue_translations.py`:

```python
"""기존 번역본을 새 파이프라인으로 재생성하도록 큐에 다시 넣는다.

배치 추론(50% 할인, 목표 24시간)을 쓰지 않는다 — 비용은 목표가 아니고
155건 × 40초 ÷ 동시 10 ≈ 10분이면 워커가 그냥 끝낸다.

APPLY=1 일 때만 큐에 넣는다. 기본은 미리보기.
"""
import json
import os
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
APPLY = os.environ.get("APPLY") == "1"
JOB_TYPE = "notice_translation"


def request(method: str, path: str, body=None):
    req = urllib.request.Request(URL + path, method=method)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=120) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw.strip() else None


rows = request(
    "GET",
    "/rest/v1/notice_ai_translations?select=notice_id,target_language&limit=2000",
)

pairs = sorted({(r["notice_id"], r["target_language"]) for r in rows if r.get("target_language") != "ko"})
by_lang = Counter(lang for _, lang in pairs)

print(f"기존 번역본 {len(rows)}행 → 재생성 대상 {len(pairs)}쌍")
for lang, count in by_lang.most_common():
    print(f"  {lang:6s} {count}")

if not APPLY:
    print("\n미리보기입니다. 실제로 큐에 넣으려면 APPLY=1 을 붙여 다시 실행하세요.")
    sys.exit(0)

jobs = [
    {
        "job_type": JOB_TYPE,
        "status": "pending",
        "payload": {"notice_id": notice_id, "target_language": lang},
    }
    for notice_id, lang in pairs
]

CHUNK = 50
inserted = 0
for start in range(0, len(jobs), CHUNK):
    created = request("POST", "/rest/v1/app_jobs", jobs[start:start + CHUNK])
    inserted += len(created or [])
    print(f"  {inserted}/{len(jobs)} 큐 적재")

print(f"\n{inserted}건 큐 적재 완료. 워커가 drain 하면 재생성된다.")
```

- [ ] **Step 7: 미리보기로 규모를 확인한다**

```bash
export SUPABASE_URL="$(gh variable get NEXT_PUBLIC_SUPABASE_URL)"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python scripts/requeue_translations.py
```

Expected: `재생성 대상 155쌍` 근처. **수치가 300을 넘으면 중단하고 보고할 것** — 스펙의 155건 가정이 틀렸다는 뜻이고, 워커 예상 소요(10분)도 틀린다.

- [ ] **Step 8: 백필 전 통과율을 기록한다 (비교 기준)**

```bash
python -c "
import json,os,urllib.request,sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=validation&limit=2000')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=120).read().decode())
c=Counter(((x.get('validation') or {}).get('hard_fact') or {}).get('status') for x in rows)
print('백필 전 hard_fact 분포:', dict(c))
" | tee /tmp/backfill_before.txt
```

Expected: `{'passed': N, ...}` 형태. 이 파일을 Step 10에서 비교한다.

- [ ] **Step 9: 큐에 넣고 워커를 깨운다**

```bash
APPLY=1 python scripts/requeue_translations.py
gcloud run jobs execute "$TRANSLATION_WORKER_JOB" --region="$REGION" --wait
```

Expected: `155건 큐 적재 완료` + 워커 실행 성공. 소요 약 10분.

- [ ] **Step 10: 백필 후 통과율을 비교한다**

```bash
python -c "
import json,os,urllib.request,sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/notice_ai_translations?select=validation&limit=2000')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
rows=json.loads(urllib.request.urlopen(r,timeout=120).read().decode())
c=Counter(((x.get('validation') or {}).get('hard_fact') or {}).get('status') for x in rows)
print('백필 후 hard_fact 분포:', dict(c))
"
cat /tmp/backfill_before.txt
```

Expected: `passed` 건수가 백필 전 **이상**. 줄었으면 재생성이 품질을 깎은 것이므로 보고한다(155건 = 10분이므로 다시 돌릴 수 있다).

- [ ] **Step 11: 커밋**

```bash
git add scripts/requeue_translations.py
git commit -m "chore(translation): 기존 번역 155건 재큐잉 백필 스크립트

전면 Bedrock 전환 후 기존 번역본을 새 파이프라인으로 재생성한다.

Bedrock 배치 추론(50% 할인, 목표 24시간)을 쓰지 않는다 —
비용은 목표가 아니고(결정 #2), 155건 × 40초 ÷ 동시 10 ≈ 10분이면
워커가 그냥 끝낸다. 배치 API 는 «썼어야 했다» 가 아니라
«쓸 이유가 없다» 로 기록한다.

기본은 미리보기다. APPLY=1 일 때만 큐에 넣는다.
백필 전후 validation.hard_fact 통과율을 비교해 회귀를 잡는다."
```

---

## Task 14: B8 — 단계 병합 M1 + M2 (7라운드 → 5라운드)

thinking을 끄고 나면 남는 것은 **라운드트립 횟수**다. tb=0 기준 33.5초 중 순수 네트워크·오버헤드가 상당 부분이다.

| 안 | 대상 | 방식 | 절약 |
|---|---|---|---|
| **M1** | 원문 하드팩트(`:60`) + 식재료 매핑(`:71`→`:384`) | **동시 실행** | −3.2s |
| **M2** | 문맥·어조 검증(`:251`) + 카드 메타데이터(`:327`) | **투기적 선실행** | −1.4s (tb=0 이후) |
| M3 | 한→영 피벗 + 영→대상어 | **하지 않는다** | — |

**M1을 프롬프트 병합이 아니라 동시 실행으로 한다.** 같은 −3.2초가 나오고 프롬프트를 안 건드리므로 A/B 통제가 유지된다. 현재 `_map_ingredients_if_needed`가 `source_hard_facts["meal_and_allergy"]`에 의존하지만(`:369-372`) 그건 «식사 정보가 있나» 게이트일 뿐이라 두 콜을 동시에 띄우고 게이트를 나중에 적용하면 된다.

**M2도 프롬프트 병합이 아니라 투기적 선실행이다.** 카드 메타데이터는 최종 번역문만 필요하고 검증 결과와 무관하다. `orchestrator.py:100-112`에 **이미 있는 패턴**(`create_task` → `translation_when_back_started` 비교(`:101`, `:235`) → 바뀌었으면 `_discard_task`)을 그대로 복제한다.

**M3는 하지 않는다.** 피벗 도입 근거를 저장소에서 찾지 못했다. 근거를 모르는 설계를 −8.4초를 위해 뜯지 않는다.

> **tb=0 이후 M2의 이득은 21.8초에서 1.4초로 쪼그라든다.** 그래서 Task 7을 먼저 하고 나면 이 Task의 우선순위는 자동으로 낮아진다. 이 순서가 맞다. **M2가 게이트를 못 넘으면 M1만 적용한다.**

**Files:**
- Modify: `backend/app/translation/orchestrator.py:59-74` (M1), `:315-361` (M2)
- Test: `backend/tests/test_orchestrator_stage_merge.py`

**Interfaces:**
- Consumes: 기존 `_discard_task`(`:32-42`), `_map_ingredients_if_needed`(`:363-391`)
- Produces: 라운드 7 → 5. `run()`의 반환 구조는 **불변**이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_orchestrator_stage_merge.py`:

```python
import asyncio
import unittest

from app.translation.orchestrator import TranslationPipeline

from backend.tests.test_orchestrator_parallel_thinking import (
    _MATCHING_HARD_FACTS,
    _payload_input,
    _RecordingGemini,
)


class _OrderedGemini(_RecordingGemini):
    """호출 시작 시각을 재서 동시 실행을 판별한다."""

    def __init__(self, responses) -> None:
        super().__init__(responses)
        self.started: list[str] = []
        self.finished: list[str] = []

    async def generate_json(self, **kwargs):
        kind_probe = len(self.calls)
        result = None
        # 시작 기록은 부모 호출 전에 해야 순서가 보인다 — 부모가 kind 를 계산하므로
        # 여기서는 프롬프트로 직접 분류한다.
        from backend.tests.test_orchestrator_parallel_thinking import _classify

        kind = _classify(kwargs["prompt"])
        self.started.append(kind)
        await asyncio.sleep(0)
        result = await super().generate_json(**kwargs)
        self.finished.append(kind)
        del kind_probe
        return result


def _responses() -> dict:
    meal_facts = dict(_MATCHING_HARD_FACTS)
    meal_facts["meal_and_allergy"] = {"has_meal_info": True, "ingredients_raw": ["우유"], "menu_items_raw": ["급식"]}
    return {
        "source_hf": meal_facts,
        "ingredient": {"mapped_ingredients": [], "unmapped_ingredients": [], "critical_flags": {}},
        "pivot": {"pivot_translation_en": "Notice EN"},
        "target": {"target_translation": "Translated body"},
        "target_hf": _MATCHING_HARD_FACTS,
        "back": {"back_translation_ko": "역번역"},
        "tone": {"verdict": "PASS", "issues": []},
        "payload": {"title": "안내", "validation_status": "passed"},
    }


class StageMergeTest(unittest.TestCase):
    def test_m1_source_hard_facts_and_ingredient_map_start_together(self) -> None:
        """둘 다 source_text 만 읽는다. 순차로 돌 이유가 없다."""
        gemini = _OrderedGemini(_responses())
        asyncio.run(TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요.")))
        first_two = gemini.started[:2]
        self.assertCountEqual(first_two, ["source_hf", "ingredient"], gemini.started)

    def test_m2_card_metadata_starts_before_tone_validation_finishes(self) -> None:
        """카드 메타데이터는 최종 번역문만 필요하고 검증 결과와 무관하다."""
        gemini = _OrderedGemini(_responses())
        asyncio.run(TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요.")))
        self.assertIn("payload", gemini.started)
        self.assertIn("tone", gemini.finished)
        self.assertLess(
            gemini.started.index("payload"),
            gemini.finished.index("tone"),
            f"started={gemini.started} finished={gemini.finished}",
        )

    def test_card_metadata_is_generated_exactly_once_on_clean_pass(self) -> None:
        """투기 실행이 중복 콜을 만들면 안 된다."""
        gemini = _OrderedGemini(_responses())
        result = asyncio.run(
            TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요."))
        )
        self.assertEqual(len(gemini.calls_of("payload")), 1)
        self.assertEqual(result["metadata"]["title"], "안내")

    def test_card_metadata_is_redone_when_tone_fix_changes_the_translation(self) -> None:
        """자동수정 루프가 번역문을 바꾸면 미리 띄운 카드는 버리고 새로 돈다."""
        responses = _responses()
        responses["tone"] = [
            {"verdict": "FAIL_FIXABLE", "issues": [{"severity": "high"}]},
            {"verdict": "PASS", "issues": []},
        ]
        responses["tone_fix"] = {"corrected_target_translation": "Corrected body"}
        gemini = _OrderedGemini(responses)
        result = asyncio.run(
            TranslationPipeline(gemini).run(_payload_input(source_text="급식 안내. 6월 10일까지 신청서를 제출하세요."))
        )
        payload_calls = gemini.calls_of("payload")
        self.assertEqual(len(payload_calls), 1)
        self.assertIn("Corrected body", payload_calls[-1]["prompt"])
        self.assertEqual(result["final_translation"], "Corrected body")


if __name__ == "__main__":
    unittest.main()
```

> `_classify`(`test_orchestrator_parallel_thinking.py:12-30`)는 «식재료 매핑»과 «문맥어조 자동수정»을 따로 구분하지 않는다. 이 테스트가 쓰는 `ingredient`·`tone_fix` 두 종류를 위해 그 함수에 두 분기를 더한다:

```python
def _classify(prompt: str) -> str:
    """프롬프트 본문에서 파이프라인 단계 종류를 식별한다 (마커는 고유성 검증됨)."""
    if "Extract and normalize verifiable hard facts" in prompt:
        return "source_hf"
    if "approved_dictionary" in prompt or "mapped_ingredients" in prompt:
        return "ingredient"
    if "corrected_target_translation" in prompt and "FAIL_FIXABLE" not in prompt:
        return "hf_fix" if "mismatches" in prompt else "tone_fix"
    if "translated_hard_facts" in prompt:
        return "hf_validate"
    if "FAIL_FIXABLE" in prompt:
        return "tone"
    if '"back_translation_ko"' in prompt:
        return "back"
    if '"pivot_translation_en"' in prompt:
        return "pivot"
    if "card_sections" in prompt:
        return "payload"
    if '"target_translation"' in prompt:
        return "target"
    return "target_hf"
```

**이 분기 마커는 추측하지 말고 `prompts.py`에서 확인한다:**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
from app.translation import prompts
for name, fn, args in (
    ('ingredient', prompts.map_ingredient_identity_prompt, dict(meal_text='m', ingredients_raw=[], approved_dictionary=[])),
    ('tone_fix', prompts.fix_context_tone_prompt, dict(source_text='s', current_target_translation='t', back_translation_ko='b', issues=[], target_language='en', source_hard_facts={})),
    ('hf_fix', prompts.fix_hard_facts_prompt, dict(source_text='s', source_hard_facts={}, current_target_translation='t', mismatches=[], target_language='en', ingredient_map={}, target_dictionary=[])),
):
    body = fn(**args)
    print(name, '| approved_dictionary:', 'approved_dictionary' in body,
          '| mapped_ingredients:', 'mapped_ingredients' in body,
          '| mismatches:', 'mismatches' in body,
          '| FAIL_FIXABLE:', 'FAIL_FIXABLE' in body)
"
```

Expected: 세 프롬프트의 마커 조합이 서로 겹치지 않는다. **겹치면 `_classify` 분기를 실측에 맞게 고친다** — 마커를 추측해서 쓰면 테스트가 조용히 잘못된 것을 재게 된다.

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_orchestrator_stage_merge -v
```

Expected: `test_m1_...`과 `test_m2_...` FAIL (현재는 순차 실행)

- [ ] **Step 3: M1 — 원문 하드팩트와 식재료 매핑을 동시에 띄운다**

`backend/app/translation/orchestrator.py:59-74`를 교체:

```python
    async def run(self, payload: TranslationPipelineInput) -> dict[str, Any]:
        # ①(원문 하드팩트)과 ②(식재료 매핑)은 둘 다 source_text 만 읽는다.
        # ②가 ①의 meal_and_allergy 를 보긴 하지만 «식사 정보가 있나» 게이트일 뿐이라,
        # 둘을 동시에 띄우고 게이트는 결과가 다 온 뒤에 적용한다. 프롬프트는 그대로다.
        source_hard_facts_task = asyncio.create_task(
            self.gemini.generate_json(
                prompt=extract_source_hard_facts_prompt(payload.source_text),
                temperature=0.0,
                model=getattr(self.gemini, "source_hard_fact_model", None),
                thinking_budget=MECHANICAL_THINKING_BUDGET,
            )
        )
        ingredient_map_task = asyncio.create_task(
            self._map_ingredients_unconditional(payload=payload)
        )
        try:
            source_hard_facts = await source_hard_facts_task
        except BaseException:
            await _discard_task(ingredient_map_task)
            raise

        risk_profile = _risk_profile_from_source(
            source_text=payload.source_text,
            source_hard_facts=source_hard_facts,
        )

        if _has_meal_info(source_hard_facts):
            ingredient_map = await ingredient_map_task
        else:
            # 식사 정보가 없으면 매핑 결과를 쓰지 않는다 — 기존 게이트와 같은 판정이다.
            await _discard_task(ingredient_map_task)
            ingredient_map = _empty_ingredient_map()
```

그리고 `_map_ingredients_if_needed`(`:363-391`)를 아래 셋으로 교체한다:

```python
    async def _map_ingredients_unconditional(
        self,
        *,
        payload: TranslationPipelineInput,
    ) -> dict[str, Any]:
        """식재료 매핑을 게이트 없이 돌린다. 게이트는 호출부가 결과 폐기로 적용한다."""
        return await self.gemini.generate_json(
            prompt=map_ingredient_identity_prompt(
                meal_text=payload.source_text,
                ingredients_raw=[],
                approved_dictionary=payload.approved_ingredient_dictionary,
            ),
            temperature=0.0,
            thinking_budget=self.thinking_budget,
        )
```

모듈 하단(`_risk_profile_from_source` 앞)에 헬퍼 둘을 더한다:

```python
def _has_meal_info(source_hard_facts: dict[str, Any]) -> bool:
    meal = source_hard_facts.get("meal_and_allergy") or {}
    return bool(
        meal.get("has_meal_info")
        or list(meal.get("ingredients_raw") or [])
        or list(meal.get("menu_items_raw") or [])
    )


def _empty_ingredient_map() -> dict[str, Any]:
    return {
        "mapped_ingredients": [],
        "unmapped_ingredients": [],
        "critical_flags": {
            "contains_allergen": False,
            "contains_religious_restriction_item": False,
            "contains_unmapped_critical_item": False,
        },
    }
```

> **동작 변화 하나가 있다.** 기존 `_map_ingredients_if_needed`는 `menu_items_raw`를 `meal_text`로, `ingredients_raw`를 따로 넘겼다. 동시 실행에서는 그 값을 아직 모르므로 `source_text` 전체를 `meal_text`로 넘긴다. **프롬프트 파일은 안 바뀌지만 입력이 바뀐다** — 그래서 이 Task도 §4.6 게이트 대상이다.

- [ ] **Step 4: M2 — 카드 메타데이터를 투기적으로 선실행한다**

`backend/app/translation/orchestrator.py`의 문맥·어조 검증 직전(`:251` 앞)에 투기 실행을 띄운다:

```python
        # ⑧(카드 메타데이터)은 최종 번역문만 필요하고 검증 결과와 무관하다.
        # ⑤'(역번역)와 같은 폐기 패턴으로 검증과 병렬로 미리 띄운다.
        metadata_task: asyncio.Task[dict[str, Any]] | None = None
        translation_when_metadata_started = target_translation
        clean_validation_results = {
            "hard_fact": {"status": "passed", "attempts": hard_fact_attempts, "issues": []},
            "context_tone": {"status": "passed", "attempts": 0, "issues": []},
        }
        metadata_task = asyncio.create_task(
            self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results=clean_validation_results,
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )
        )
```

검증·자동수정 루프(`:251-300`)는 그대로 둔다. 검증 실패 조기 반환(`:302-313`)과 자동수정 루프 진입 시 투기 결과를 버려야 하므로, `:302` 앞과 `:263` 루프 본문 첫 줄에 폐기를 넣는다:

```python
        if context_tone_validation.get("verdict") != "PASS":
            await _discard_task(metadata_task)
            return await self._validation_failed_result(
                ...
            )
```

그리고 성공 경로(`:315-336`)의 메타데이터 생성을 «투기 결과 재사용 또는 재실행»으로 바꾼다:

```python
        validation_results = {
            "hard_fact": {
                "status": "passed",
                "attempts": hard_fact_attempts,
                "issues": [],
            },
            "context_tone": {
                "status": "passed",
                "attempts": context_tone_attempts,
                "issues": [],
            },
        }
        if metadata_task is not None and target_translation == translation_when_metadata_started:
            metadata = await metadata_task
        else:
            # 자동수정 루프가 번역문을 바꿨으면 미리 띄운 카드는 무효 — 버리고 새로 돈다.
            await _discard_task(metadata_task)
            metadata = await self.gemini.generate_json(
                prompt=build_supabase_payload_prompt(
                    source_text=payload.source_text,
                    final_target_translation=target_translation,
                    source_hard_facts=source_hard_facts,
                    validation_results=validation_results,
                    target_language=payload.target_language,
                ),
                temperature=0.0,
                thinking_budget=self.thinking_budget,
            )
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_orchestrator_stage_merge -v
```

Expected: 4 tests PASS

- [ ] **Step 6: 기존 회귀가 없는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. `test_orchestrator_parallel_thinking`의 `_classify` 변경이 기존 단언을 깨면, 깨진 단언이 **어떤 kind를 기대했는지** 확인해 마커를 맞춘다. `test_validation_failed_early_return_discards_pending_back_translation`이 카드 메타데이터 콜 수를 세고 있다면 투기 실행 폐기가 제대로 도는지 여기서 잡힌다.

- [ ] **Step 7: 게이트를 돌린다**

`arms.json`에 arm-f를 추가한다(현행 = arm 승자, 후보 = 병합본). 병합은 코드 변경이라 env로 가를 수 없으므로, **병합 전 커밋에서 arm-baseline을 먼저 돌리고 병합 후 arm-merged를 돌린다.**

```bash
# 병합 전 커밋(HEAD~1)에서
git stash && python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ --arm arm-c
git stash pop
# 병합 후
python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001/ --arm arm-f
python scripts/compare_arms.py \
  --iter-dir .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001 \
  --baseline arm-c --arm arm-f
```

> arm-f의 `env`는 승자 arm과 **동일**하다 — 바뀐 것은 코드뿐이다. `arms.json`에 그 사실을 `"note"`로 적어둔다.

Expected: `G1 hard_fact 하락: 0건`, `G5 wall_seconds 중앙값`이 arm-c보다 낮음, `G1/G4/G5: 통과`.

G6도 같이 돌린다. **M1이 식재료 매핑의 입력을 바꾸기 때문이다**(`menu_items_raw` → `source_text` 전체) — 입력이 바뀌면 «읽을 것이 없을 때 무엇을 하는가»도 바뀔 수 있다.

```bash
NEG=.agents/translation-quality/iterations/2026-08-27_iter-negative-control
python scripts/run_iteration.py --iter "$NEG/" --arm arm-f
python scripts/check_hallucination.py --iter-dir "$NEG" --arm arm-f
```

Expected: `G6: 통과`. 병합 전(arm-c) 결과와 같아야 한다.

> **M2가 게이트를 못 넘으면 M1만 남기고 M2를 revert한다.** M2는 검증 프롬프트에 메타 생성을 섞는 게 아니라 투기 실행이므로 판정이 흐려질 위험은 낮지만, 자동수정 루프에서 콜이 늘 수는 있다(투기 폐기 + 재실행 = 2콜).

- [ ] **Step 8: 라운드 수가 실제로 줄었는지 센다**

```bash
python -c "
import json, pathlib, sys, statistics
sys.stdout.reconfigure(encoding='utf-8')
root = pathlib.Path('.agents/translation-quality/iterations/2026-08-27_iter-bedrock-001')
for arm in ('arm-c', 'arm-f'):
    vals = []
    for p in root.glob(f'notices/*/*/pipeline-output/{arm}/*.json'):
        d = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(d.get('wall_seconds'), (int, float)):
            vals.append(d['wall_seconds'])
    if vals:
        print(f'{arm}: n={len(vals)} 중앙값 {statistics.median(vals):.1f}s 평균 {statistics.mean(vals):.1f}s')
"
```

Expected: arm-f의 중앙값이 arm-c보다 낮다. 스펙 예상 절약은 −4.6초(M1 −3.2 + M2 −1.4)다.

- [ ] **Step 9: 커밋**

```bash
git add backend/app/translation/orchestrator.py backend/tests/test_orchestrator_stage_merge.py \
  backend/tests/test_orchestrator_parallel_thinking.py \
  .agents/translation-quality/iterations/2026-08-27_iter-bedrock-001
git commit -m "perf(translation): 파이프라인 라운드 7 → 5 (원문 하드팩트∥식재료, 카드 투기 선실행)

thinking 을 끄고 나면 남는 것은 라운드트립 횟수다.

M1 — 원문 하드팩트와 식재료 매핑은 둘 다 source_text 만 읽는다.
     프롬프트 병합이 아니라 동시 실행으로 처리한다. 같은 -3.2초가 나오고
     프롬프트를 안 건드리므로 A/B 통제가 유지된다.
     식사 정보 게이트는 결과 폐기로 그대로 적용한다.

M2 — 카드 메타데이터는 최종 번역문만 필요하고 검증 결과와 무관하다.
     역번역과 같은 폐기 패턴(create_task → 번역문 비교 → _discard_task)을
     그대로 복제한다. 자동수정이 번역문을 바꾸면 버리고 새로 돈다.

M3(피벗 삭제)는 하지 않는다 — 도입 근거를 저장소에서 찾지 못했다.
근거를 모르는 설계를 -8.4초를 위해 뜯지 않는다.

M1 은 식재료 프롬프트의 입력이 바뀐다(menu_items_raw → source_text).
프롬프트 파일은 그대로지만 입력이 달라지므로 게이트 대상이다 —
G1/G4/G5 통과 확인. 입력이 바뀌면 «읽을 것이 없을 때 무엇을 하는가» 도
바뀔 수 있어 G6(환각 negative control)도 함께 돌렸다."
```

---

## 자체 검토

**1. 스펙 커버리지**

| 스펙 항목 | 담당 Task |
|---|---|
| §4 B1 arm 축 폴더 규약 | Task 3 Step 1·3 |
| §4.2(b) 블라인드 | Task 3 Step 5·6, Task 7 Step 11 |
| §4.2(c) `wall_seconds` 기록 | Task 3 Step 3 |
| §4.3 arm 구성 (Haiku 우선 → Sonnet 승급, Nova·Opus 없음) | Task 3(arm-a), Task 7(arm-b), Task 11(arm-c Haiku / arm-d Sonnet / arm-e 혼합) |
| §4.4 1차 지표 = 코드 검증 통과율 | Task 7 Step 9 (`compare_arms.py`) |
| §4.5 코퍼스 확장 12 → 30 | Task 2 |
| §4.6 게이트 G1~G6 | G1·G4·G5 = `compare_arms.py`(Task 7·11·14), G2·G3 = 평가자(Task 7 Step 11, Task 11 Step 13), **G6 = `check_hallucination.py`**(Task 7 Step 10, Task 11 Step 14, Task 14 Step 7) |
| §4.7 G6 negative control 코퍼스 | Task 2 Step 8·9 |
| §5.9.2 Nova 환각 실측 → arm 제외 | Global Constraints, Task 11 Step 10 |
| §5.10 모델 선택 정책 (Haiku 기본 / Sonnet 승급 / **Opus 금지** / Nova 용도제한) | Global Constraints, Task 9 Step 3(기본값·테스트), Task 11 Step 15, Task 12 Step 6 |
| §5.1 `JsonModelClient` 프로토콜 + 팩토리 | Task 9 |
| §5.1 호출부 교체 8+3+1곳 | Task 11 Step 2~4 |
| §5.2 세마포어·백오프·파서 재사용 | Task 10 Step 4 |
| §5.3 thinking 항상 OFF + 양수 경고 | Task 10 Step 4, 테스트 `test_thinking_is_never_sent` |
| §5.4 프리필 + 파서 복구, `toolConfig` 미사용 | Task 10 Step 4, 테스트 `test_prefill_*` |
| §5.4 `_extract_bedrock_text` | Task 10 Step 4, 테스트 `ExtractTextTest` |
| §5.5 스로틀 마커 확장 | **Task 8 (Bedrock보다 앞)** |
| §5.6 전용 `ThreadPoolExecutor` | Task 10 Step 4, 테스트 `ExecutorTest` |
| §5.7 정적 키 + Secret Manager + 전용 IAM | Task 11 Step 8 |
| §5.8 설정 4개 | Task 9 Step 3 (+ `bedrock_max_workers` 추가) |
| §5.9 모델 후보 실측 | Task 9 Step 3(기본값 = Haiku), Task 11 Step 10·15, Task 12 Step 6 |
| §5.11 C1(요청 크기 상한)·C2(판독 지연 비교) | **이 계획 밖 — 사업 C.** 번역 입력은 텍스트라 B에서는 걸리지 않는다 |
| §5.11 C3(`global.` 라우팅 기록) | Task 12 Step 6 |
| §10.4 판독 이전 가능함 확인 | **기록만.** 실제 이전은 사업 C |
| §6 B4 thinking 축소 | Task 7 |
| §6.2 검증 단계 부분 적용 예비안 | Task 7 Step 9 주석 |
| §7 B8 M1 + M2, M3 미실시 | Task 14 |
| §8.1 B3 메타데이터 플래그 | Task 6 Step 3·4 |
| §8.2(a) risk 분포 측정 선행 | **Task 1** |
| §8.2(b) dead 분기 삭제 | Task 6 Step 5 (Task 1 결과에 조건부) |
| §9.1 B2 배치 대기 제거 + 취소 전파 유지 | Task 4 |
| §9.2 #2705 keepalive / #1875 재시도 | Task 5 |
| §10.2 B6 반쪽 상태 | Task 12 |
| §10.2 B7 전면 | Task 13 Step 2 |
| §10.3 B9 백필(배치 API 미사용) | Task 13 Step 6~10 |
| §13 검증표 전 항목 | 각 Task의 Expected에 분산 |

**빠진 것 없음.**

**2. 계획을 쓰면서 발견한 스펙의 누락·모순 — 이 계획이 정정한 것**

| # | 스펙 | 이 계획 | 근거 |
|---|---|---|---|
| a | §5.2 `_parse_json("{" + _extract_bedrock_text(...))` — 무조건 프리필 재부착 | 이미 `{`로 시작하면 붙이지 않는다 | 프리필을 무시하고 완전한 JSON을 돌려주는 모델에서 `{{...}`가 되어 파서가 깨진다. `_parse_json`의 정규식 폴백도 `{{...}`를 구제하지 못한다 |
| b | §5.5 마커에 `toomanyrequests` | `too many requests`(공백 있음)와 `toomanyrequests` 둘 다 | 실제 Bedrock 메시지는 `Too many requests, please wait...` — 공백이 있다. 공백 없는 형태만 넣으면 **여전히 안 잡힌다** |
| c | §5.1 호출부 «드라이버 1곳» | `run_iteration.py:116`도 포함해 2곳 | 두 스크립트가 각자 `GeminiJsonClient.from_settings`를 부른다. `run_iteration.py`를 빼면 arm 러너가 Bedrock arm에서 계속 Gemini를 부른다 |
| d | §6.1 «호출 인자 11곳»에 상수 하드코딩 | `TRANSLATION_THINKING_BUDGET` 설정으로 주입 | arm이 환경변수로만 정의되므로 코드 분기 없이 A/B가 되고, 롤백이 env 한 줄이 된다. 기본값 `None`이라 커밋 자체의 동작 변화가 0 |
| e | §7 M1을 «프롬프트 병합 또는 동시 실행» | 동시 실행 확정. 다만 **입력이 바뀐다** | 동시 실행에서는 `menu_items_raw`를 아직 모르므로 `source_text` 전체를 `meal_text`로 넘긴다. 프롬프트 파일은 안 바뀌지만 입력이 바뀌므로 게이트 대상이다 — 스펙은 «프롬프트를 안 건드리므로 A/B 통제 유지»라고만 적었다 |
| f | §1.5(a) `_is_gemini_quota_error`와 `is_quota_exhausted_error`의 관계 미언급 | Task 8이 정렬 | `notice_service.py:1365`는 **이미** `too many requests`를 갖고 있어 Bedrock 스로틀을 잡는다. 두 함수의 마커가 어긋나 있었다 |
| g | §5.8 설정 4개 | `BEDROCK_MAX_WORKERS` 추가 (5개) | §5.6이 `max_workers = settings.gemini_max_concurrency`를 쓰라고 했는데, 그러면 «세마포어 상한»과 «스레드 수»가 한 노브에 묶여 각각 조절할 수 없다. 세마포어는 `gemini_max_concurrency` 그대로 두고 스레드만 분리한다 |
| h | §12 배포 0번 «코퍼스 확장» 방법 미기술 | Task 2가 운영 공지 기반 스크립트 제공 | 스펙 §4.5는 «운영 155건의 한국어 원문이 `notices`에 있다»까지만 적었다 |
| i | 열린 질문 Q4(검증 단계 thinking 유지 여부) | Task 7이 **전면 OFF로 진행**, 게이트 실패 시 부분 적용을 예비안으로 | 게이트를 먼저 돌려보지 않고 −20.5초를 미리 포기할 이유가 없다. G1이 못 잡는 위험(위음성)은 Task 7 Step 11에서 «Fact Preservation»·«Action Clarity» 축을 따로 봐서 보완한다 |
| j | §4.6 게이트 5개(G1~G5)가 전부 «모델이 입력을 읽었다»를 전제한다 | **G6 신설** — negative control 폴더(Task 2 Step 8) + `check_hallucination.py`(Task 7 Step 10) | 2026-08-27 실측에서 Nova가 읽지 못한 첨부의 본문을 지어냈다. 지어낸 글은 문장이 매끄러워 8축 평균을 **올린다** — 기존 게이트 다섯 개 중 어느 것도 이걸 실패로 만들지 않는다 |
| k | §5.9 초판이 «`apac.` 전용 → 최상급은 claude-3-5-sonnet» | Q1 해결(허용)로 **Haiku 4.5 기본 / Sonnet 4.6 승급**으로 교체 | 라우팅 제약이 풀리면서 모델 후보가 통째로 바뀌었다. 설정 기본값·arm 3종·시험 명령·단위 테스트의 모델 문자열을 전부 갈았다 |
| l | 금지 모델이 **문서에만** 적혀 있었다 | `test_forbidden_models_are_not_defaults`(Task 9 Step 1)로 **코드가 강제** | 기본값에 Opus·Nova가 들어가면 아무도 모르게 운영에 실린다. 문서 규칙은 리뷰를 통과하면 사라지지만 테스트는 안 사라진다 |

**아직 열려 있는 것 (이 계획이 답하지 않는다)**

- ~~**Q1 `global.` 라우팅 허용 여부**~~ — **해결됨: 허용**(사용자 승인). 그 결과로 Claude 4.x 계열이 후보가 됐고 기본값이 Haiku 4.5로, arm 구성이 Haiku/Sonnet/혼합으로 바뀌었다. 남은 의무는 «어느 프로필을 호출했는지 로그로 남긴다»뿐(Task 12 Step 6).
- **Q3 문서판독 이전 시점** — 범위 밖(**사업 C**). «옮길 수 있는가»는 더 이상 열려 있지 않다 — 2026-08-27 실측으로 Bedrock `Converse`가 PDF·이미지를 직접 받아 정확히 읽는 것이 확인됐다(스펙 §10.4). 남은 것은 시점이다. C 착수 시 **요청 크기 상한(§5.11 C1)** 과 **현행 Gemini OCR 대비 판독 지연(§5.11 C2)** 을 실측 Step으로 앞에 둬야 한다 — 둘 다 **미확인**이다. 이 계획이 끝나도 Gemini 현금 지출이 완전히 0이 되지는 않는다.
- **Q5 정적 키 → OIDC 연합** — Task 11이 정적 키로 간다. OIDC 후속 정리 일정은 이 계획에 없다.

**3. 자리표시자 점검** — "TBD"·"적절히 처리"·"비슷하게" 없음. 모든 코드 Step에 실제 코드가 들어 있다. 추측이 필요한 두 자리(Task 5의 SDK 노브, Task 14의 `_classify` 마커)는 **추측 대신 확인 Step**을 앞에 두고 «안 맞으면 중단·보고»를 명시했다.

**4. 타입 일관성**

- `JsonModelClient` 프로토콜 시그니처는 `gemini_client.py:125-132`를 그대로 복사했다. `BedrockJsonClient.generate_json`(Task 10)도 동일 — 인자 4개(`prompt`, `temperature`, `model`, `thinking_budget`), 반환 `dict[str, Any]`. 일치.
- `source_hard_fact_model: str | None` — `GeminiJsonClient.__init__`이 `model`로 폴백하고(`:97`), `BedrockJsonClient`도 동일하게 폴백한다(Task 10 Step 4). `orchestrator.py:63`의 `getattr(..., None)`은 둘 다에서 문자열을 받는다. 일치.
- `Settings.translation_thinking_budget: int | None` — Task 7 Step 3에서 정의, Step 4에서 `self.thinking_budget`으로 소비, Task 14 Step 3·4의 새 호출부도 같은 값을 쓴다. 일치.
- `Settings.bedrock_max_workers: int` — Task 9 Step 3에서 정의, Task 10 Step 4의 `from_settings`가 소비, 같은 값이 `ThreadPoolExecutor(max_workers=)`와 `Config(max_pool_connections=)` 양쪽에 들어간다. 일치.
- `arms.json`의 `{"id", "label", "env"}` — Task 3 Step 1에서 정의, Step 3의 `_apply_arm_env`가 소비, Task 7 Step 8·Task 11 Step 10이 항목을 추가. 키 이름 일치.
- `wall_seconds` — Task 3 Step 3이 결과 json에 심고, Task 7 Step 9의 `compare_arms.py`와 Task 14 Step 8이 읽는다. 일치.
- `process_jobs(...) -> int` — Task 4가 내부 구조만 바꾸고 시그니처·반환형은 유지. `run_async`(`:118-127`)와 기존 테스트 4종의 호출 형태가 그대로 통한다.
- `_best_effort_translate_notice(..., with_card_metadata: bool = True)` — Task 6이 생산, `:249` 한 곳만 `False`. `:173`·`:302`는 인자 없이 기본값. 일치.
- `_has_meal_info` / `_empty_ingredient_map` — Task 14 Step 3에서 정의·소비. 기존 `_map_ingredients_if_needed`의 게이트 조건(`:373`)과 동일한 판정식.

---

## 선행 준비물

Task 착수 전에 사람이 해둬야 하는 것:

| | 항목 | 필요한 Task |
|---|---|---|
| ✅ | 전용 IAM 사용자 `naranhi-bedrock` (모델 호출 권한만) | Task 10, 11 (생성·검증 완료) |
| ✅ | GCP Secret `aws-bedrock-access-key-id`, `aws-bedrock-secret-access-key` | Task 10, 11 (완료) |
| ✅ | Bedrock 모델 액세스 — 12종 즉시 호출 가능 (`apac.` 6종 + `global.` 계열) | Task 10, 11 (Claude Haiku 4.5·Sonnet 4.6으로 실제 첨부 PDF·이미지 판독 성공 확인) |
| ✅ | `boto3` 1.43.78 / AWS CLI 2.36.31 | Task 10 (설치 확인됨) |
| ⬜ | 운영 Supabase 읽기 권한 (`supabase-service-role-key`) | Task 1, 2, 13 |
| ✅ | **열린 질문 Q1 답 — `global.` 라우팅 허용 여부** | **해결됨 — 허용**(사용자 승인). 그 결과 기본 모델이 Haiku 4.5로 확정됐다 |
| ⬜ | 평가자 에이전트 실행 체계 (G2·G3 판정) | Task 7 Step 11, Task 11 Step 13 |
| ⬜ | `google-genai` 로컬 설치 (`pip install -r backend/requirements.txt`) | Task 5 Step 1 (SDK 노브 확인) |
| ⬜ | Task 2 Step 7의 다양성 태그 사람 검토 | Task 2 완료 조건 |

**AWS 인프라 이전은 필요 없다** — 서버는 GCP Cloud Run에 그대로 둔다(결정 #4). 이 결정이 §5.7의 «GCP에서 AWS 자격증명을 얻는» 문제를 만들지만, 그건 결정 4의 알려진 비용이지 설계 실수가 아니다.
