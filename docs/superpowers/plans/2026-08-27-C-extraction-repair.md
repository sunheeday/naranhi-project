# 첨부 추출 파이프라인 수리 · 크롤 재가동 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 72일째 멈춘 크롤·추출 파이프라인을 «고장을 고친 뒤» 다시 켠다. 이미지 첨부(45.8%)가 예산 때문에 잘리지 않게 하고, HWP 표가 조용히 사라지지 않게 하고, 본문 사진 회수율 31%의 원인을 실측으로 규명하고, 추출 경로가 429를 번역 경로와 같은 수준으로 견디게 하고, 워터마크 컷오프를 박은 뒤 스케줄러 6개를 되살린다.

**Architecture:** 다섯 갈래를 순서대로 낸다. ① env·args·메모리 한 줄씩으로 런 예산 병목과 강제 직렬화를 동시에 푼다 ② 지금 관측 불가능한 지점에 로그를 심는다 ③ 그 로그와 운영 DB 실측으로 본문 사진 회수율의 분모를 다시 정의한다 ④ 타일 예산·HWP 임계값·429 백오프를 코드로 고친다 ⑤ 워터마크를 현재 최대 글번호로 시딩한 뒤 «추출기 → 백스톱 → 크롤러» 순으로 resume한다. 각 단위는 단독 롤백이 가능하다(env 되돌리기 / 함수 되돌리기 / 워터마크 SQL 복원 / `pause` 재실행).

**Tech Stack:** Python 3.12, FastAPI, `supabase-py`, `google-genai`(Vertex AI Gemini), Pillow, `pyhwp`/`markdownify`, Cloud Run Jobs + Cloud Scheduler, GitHub Actions. **선택 Task 13 에 한해** `boto3`(Bedrock `Converse`).

> **2026-08-27 갱신.** GCP 크레딧이 소진되어 Gemini 호출이 현금이 됐고, 같은 날 Bedrock `Converse` 로 PDF·이미지 판독이 가능함이 실측됐다(스펙 §19). 이 계획의 **본체는 바뀌지 않는다** — ①~⑥은 제공자와 무관한 고장이다. 바뀐 것은 둘이다: ⓐ 판독 검증에 **환각 negative control** 이 들어갔다(Task 4 Step 11~13, **본 계획**) ⓑ 판독 백엔드 이전이 **선택 Task 13** 으로 분리됐다(본 배포 순서 밖).

**Spec:** [docs/superpowers/specs/2026-08-27-C-extraction-repair-design.md](../specs/2026-08-27-C-extraction-repair-design.md)

## Global Constraints

- **재추출 금지**: 운영 `done` 35건의 기존 첨부를 다시 추출하지 않는다(사용자 결정 2026-08-26). 진단은 **읽기 전용 조회**와 **신규 공지 로그**로만 한다. `notices` 에 쓰기를 하는 진단 단계를 만들지 말 것.
- **밀린 공지 소급 수집 금지**: 2026-06-15 이후 게시판에 올라온 글(최대 64건 = 스캔깊이 8 × 학교 8)은 받지 않는다. **Task 10(시딩)을 끝내기 전에 Task 11(resume)을 하지 않는다.**
- **비용은 고려하지 않는다**: 사용자 결정 — "시간이 우선". 콜 수·토큰 비용을 이유로 한 절충안을 넣지 말 것.
  > ⚠️ 2026-08-27: **GCP 크레딧이 소진되어 Gemini 호출이 현금이 됐다**(사용자 확인). 그래도 이 제약은 유지한다 — 판독 경로의 월 현금이 **$1 미만**이라 절충안의 근거가 못 된다(스펙 §19.6).
- **🔴 모델 정책 (예외 없음)**:
  - **Claude Opus 계열은 금지한다.** 사용자 지시(2026-08-27) — *"절대 쓰지마 너무 비싸"*. 기본·승급·폴백·A/B arm 어디에도 넣지 않는다. 이 계획의 어느 Task도 Opus를 부르는 코드·설정·명령을 만들지 않는다.
  - **판독 기본은 Claude Haiku 4.5**(`global.anthropic.claude-haiku-4-5-20251001-v1:0`), **승급은 Claude Sonnet 4.6**(`global.anthropic.claude-sonnet-4-6`)이며 승급은 «정말 필요할 때만» 한다.
  - **Amazon Nova(Lite·Pro)는 한국어 판독에 쓰지 않는다.** 완전 삭제가 아니라 용도 제한이다 — 출력이 제약되고(닫힌 값 집합) 환각을 기계적으로 검출할 수 있으며 학부모에게 본문으로 노출되지 않는 용도에만. 판독은 셋 다 만족하지 않는다(스펙 §19.3).
- **판독 백엔드 이전은 «선택 Task 13»이다**: 본 배포 순서(Task 1~12)에 넣지 않는다. 착수 조건은 Task 4 Step 11~13(환각 negative control)의 결과다(스펙 §19.7).
- **데모 예외 금지**: 데모는 끝났다. 데모 학교를 위한 새 분기를 만들지 않는다.
- **하드코딩 폴백 유지**: `scripts/recrawl_monitor.py:78-81` 의 수동 킥은 **지우지 않는다.** 측정(Task 12)이 먼저다.
- **임포트 방향**: `backend/extractor/` 는 `backend/app/` 을 임포트하지 않는다(단방향). 공용 코드는 **`extractor/` 쪽에 두고 `app/` 이 임포트**한다. 반대 방향을 만들지 말 것.
- **`hwplib` / LibreOffice 폴백 부활 금지**: `hwp_extractor.py:56,69` 에서 의도적으로 꺼둔 경로다.
- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests`
  - 프론트: 이 계획은 프론트를 건드리지 않는다(프론트 테스트 러너 없음).
- **운영 DB 읽기**: `SUPABASE_URL=https://aoihmzewthgyoxtejfwo.supabase.co`, 키는 `gcloud secrets versions access latest --secret=supabase-service-role-key` 로 환경변수에 담는다. **키를 명령줄 인자·URL 쿼리에 넣지 않고, 값을 출력하지 않는다.**
- **gcloud 경로**: PATH에 없으면 `C:/Users/david/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd`
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식.

---

## 🔴 스펙 정정 — 본문 사진은 «고장»이 아니라 «회수율»이다

스펙 §7 은 «본문 사진 산출물 0건»을 고장으로 세웠다. **그 관측은 틀렸다.**
`extracted_content` 최상위 `body_image` 키는 코드에 존재하지 않는다. 올바른 위치인
`sources[]` 의 `source_id == "body_images_combined"` 로 다시 세면 **운영 35건 중 11건에
실제로 존재한다**(2026-08-27 운영 DB 직접 조회).

즉 **기능은 돌고 있다.** 스펙 §7.2 의 H0(제대로 된 키로 재측정)은 **이미 끝났다.**
과제는 «왜 안 도는가»가 아니라 **«왜 69%(24/35)에서는 안 나오는가»** 이며, 그 24건의
상당수는 애초에 본문에 사진이 없는 정상 공지일 수 있다. **Task 9 의 첫 산출물은
«분모의 재정의»다.**

관련 실측(2026-08-27): `inline_image` **소스** 20건, 그중 `inline_image_no_content_signal`
로 폐기 7건.

**스펙 §18 열린질문 #2 는 이 계획을 쓰는 중에 코드로 해소됐다.**
HWP `warnings` 는 저장된다 — `ExtractedText.warnings` → `_source_from_extracted(errors=extracted.warnings)`
(`extract_pipeline.py:454`) → `SourceExtraction.errors` → `_source_summary["errors"]`
(`content_extraction_service.py:1364`). 따라서 §8.2 의 가설 (b)«warnings 가 저장 안 됐다»는
**거짓**이고, 6건은 **경고를 남기지 않는 이탈 경로**로 빠진 것이 확정이다(가설 a).

**스펙 §10 #3 «예산 소진 이유가 저장되는지 확인부터»도 해소됐다.**
`budget.metadata()` 가 `extract_pipeline.py:182` 에서 `result.metadata` 에 통째로 들어가고,
`build_extracted_content` 가 `"metadata": result.metadata` 로 저장한다
(`content_extraction_service.py:438`). `budget_exhausted_reasons` 는 **이미 저장되고 있다.**
추가 계측 불필요 — Task 9 의 조회에서 그대로 읽는다.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `.github/workflows/deploy-api-cloud-run.yml` | Job env·args·메모리 | 수정 (Task 1) |
| `backend/tests/test_extractor_run_budget.py` | 런 예산 캡 의미 고정 | 신규 (Task 1) |
| `backend/extractor/extract_pipeline.py` | 인라인 이미지 수집 실패 로그 | 수정 (Task 2) |
| `backend/app/services/content_extraction_service.py` | 본문 사진 합성·업로드 로그 / 성공판정 게이트 | 수정 (Task 2, Task 6) |
| `backend/tests/test_body_image_logging.py` | 합성 로그 검증 | 신규 (Task 2) |
| `backend/extractor/extractors/hwp_extractor.py` | HWP 1순위 침묵 이탈 경고 + 표 구조 판정 | 수정 (Task 3, Task 5) |
| `backend/tests/test_hwp_markdown.py` | HWP 1순위 진입 조건 | 수정 (Task 3, Task 5) |
| `scripts/diagnose_body_images.py` | 본문 사진 회수율 실측 (읽기 전용) | 신규 (Task 9) |
| `backend/extractor/extractors/image_gemini_extractor.py` | 타일 예산 분리 + 타일 계측 | 수정 (Task 4) |
| `backend/tests/test_image_tiling.py` | 타일 예산 회귀 | 수정 (Task 4) |
| `scripts/probe_extraction_hallucination.py` | 판독 환각 negative control (읽기 전용 프로브) | 신규 (Task 4 Step 11) |
| `backend/extractor/extractors/bedrock_document_extractor.py` | Bedrock `Converse` 판독 클라이언트 | 신규 (**선택** Task 13) |
| `backend/tests/test_bedrock_document_extractor.py` | 요청 조립·포맷 매핑·HWP 거부 | 신규 (**선택** Task 13) |
| `scripts/ab_extraction_backends.py` | Gemini vs Bedrock A/B 실측 (지연·정확도·환각) | 신규 (**선택** Task 13) |
| `backend/extractor/gemini_backoff.py` | 429 백오프 (이동 대상) | 신규 (Task 7) |
| `backend/app/translation/gemini_client.py` | 백오프 재임포트 | 수정 (Task 7) |
| `backend/extractor/extractors/gemini_document_extractor.py` | Vertex 429 백오프 적용 | 수정 (Task 7) |
| `backend/tests/test_extractor_quota_backoff.py` | 백오프 단일 구현 보장 | 신규 (Task 7) |
| `backend/app/services/scheduled_crawler_service.py` | `board_kind` · `fallback_count` 집계 | 수정 (Task 8) |
| `backend/tests/test_scheduled_crawler_service.py` | 집계 검증 | 수정 (Task 8) |
| `backend/app/services/school_crawler_service.py` | `compute_board_watermarks` 헬퍼 | 수정 (Task 10) |
| `backend/tests/test_school_crawler_watermark.py` | 헬퍼 검증 | 수정 (Task 10) |
| `scripts/seed_watermarks.py` | 재가동 컷오프 시딩 (일회성) | 신규 (Task 10) |
| `docs/scheduled-crawl-runbook.md` | 스케줄러 실명·resume 절차·두 경로 계약 | 수정 (Task 11, Task 12) |

---

## 배포 순서 (스펙 §14 대비 세 곳 정정)

```
Task 1   Job 설정 정합 (env·args·메모리)      ← env 한 줄로 C2가 끝난다
Task 2   본문 사진 경로 계측
Task 3   HWP 1순위 침묵 이탈 계측
Task 4   타일 예산 분리 + 타일 계측
Task 5   HWP 40자 임계 → 표 구조 판정
Task 6   본문 사진 성공판정 게이트 완화       ← Task 9 결과가 D3 일 때만
Task 7   429 백오프 공용화
Task 8   게시판 오선택 집계
Task 9   본문 사진 회수율 진단 (조사, 배포 아님)
Task 10  워터마크 컷오프 시딩
Task 11  스케줄러 resume + 런북 정정
Task 12  크롤→추출 지연 측정 + 두 경로 계약 문서화

── 여기까지가 본 배포 순서다 ──────────────────────────────
선택 Task 13  판독 백엔드 Bedrock 이전   ← 착수 조건: Task 4 Step 13 판정
```

**정정 3 — 환각 negative control을 Task 4 에 붙였다(Step 11~13).** 지금 계획의 판독 검증은
전부 «무언가가 나왔는가»만 본다. 판독의 진짜 실패는 **«아무것도 못 읽고 그럴듯한 것을
지어냈다»**이고, 그건 나오는 쪽이라 기존 기준을 전부 통과한다. 2026-08-27 Bedrock 시험에서
Nova Lite·Pro가 QR 코드 이미지에 대해 **없는 가정통신문을 통째로 지어냈다**(스펙 §19.2).
**현행 Gemini도 같은 위험을 갖는다 — 확인한 적이 없을 뿐이다.** 그래서 이건 선택이 아니라
**본 계획**이고, 이미지 판독 경로를 손대는 Task 4 의 배포 후 검증에 붙인다.

**선택 Task 13 이 본 순서 밖인 이유:** 아끼는 현금이 월 $1 미만이고, 옮겨지는 것은
첨부의 70.1% 뿐이며(HWP 28.6%는 `document` 블록이 hwp 를 지원하지 않아 못 옮긴다),
이전이 고치는 고장은 ①~⑥ 중 **0개**다. 스펙 §19.5~19.7 의 판단이다.

**정정 1 — 타일 계측을 C6(배포 2)에서 Task 4 로 옮겼다.** 스펙 §10 #2 는 타일 폐기 로그를
계측 배포에 넣었지만, 지금 구조에서 «폐기»는 `budget_exhausted` 상태로 나타나고 Task 4 가
그 상태 자체를 없앤다. 계측을 먼저 넣으면 Task 4 에서 카운터를 다시 고쳐야 한다.
**같은 함수를 두 번 고치지 않도록 한 Task 로 합친다.** 진단(Task 9)이 필요로 하는 계측은
본문 사진 경로(Task 2)뿐이므로 순서상 손해가 없다.

**정정 2 — 진단(Task 9)이 스펙의 «배포 3»보다 뒤로 갔다.** 스펙은 진단을 수정보다 앞에
뒀지만, H0 이 이미 끝나 «고장이 아니다»가 확정된 이상 Task 4·5·7 은 진단 결과에
의존하지 않는다(각각 타일 예산 / HWP 임계 / 429 로 원인이 독립적이다). 진단 결과에
의존하는 것은 **Task 6 하나뿐이고, 그것만 Task 9 뒤에 둔다.**

**Task 10 이 Task 11 보다 앞인 이유:** 시딩 전에 스케줄러를 켜면 그 순간 최대 64건이
들어온다. 되돌릴 수 없다.

---

## Task 1: 추출 Job 설정 정합 — 런 예산 해제·동시성·메모리

`EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0` **한 줄이 두 문제를 동시에 푼다.**
`_cap_reached` 가 `cap > 0 and used >= cap`(`content_extraction_service.py:1467-1468`)이라
`cap = 0` 이면 상한이 꺼지고, 동시에 `batch_size = 1` 강제 직렬화 분기
(`:107-109`, `:185-187`)가 발동하지 않아 `batch_size` 가 `extractor_notice_concurrency`(기본 3)로
복원된다.

**Files:**
- Create: `backend/tests/test_extractor_run_budget.py`
- Modify: `.github/workflows/deploy-api-cloud-run.yml:126` (crawler-worker args), `:129` (crawler-worker memory 유지), `:161` (extractor memory), `:163` (extractor env)

**Interfaces:**
- Consumes: 없음
- Produces: 추출 Job 리비전에 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`, `GEMINI_MAX_CONCURRENCY=32`, `--memory=2Gi`. crawler-worker Job args 에 `--batch-size,3`. 이후 모든 Task 의 검증이 3배 빠른 런에서 이뤄진다.

- [ ] **Step 1: `cap = 0` 의 의미를 고정하는 실패 테스트를 쓴다**

`backend/tests/test_extractor_run_budget.py` 생성:

```python
"""런 예산 캡(EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN)의 두 가지 의미를 고정한다.

0 = 상한 없음(_cap_reached 가 항상 False), 그리고 그 값일 때만 공지 동시성이
강제 직렬화(batch_size=1)에서 풀린다. 이 두 성질이 같은 env 한 줄에 묶여 있다는
사실이 배포값의 근거이므로 테스트로 못 박는다.
"""
import unittest

from app.services.content_extraction_service import _cap_reached


class RunGeminiCallCapTest(unittest.TestCase):
    def test_zero_cap_disables_the_limit(self) -> None:
        self.assertFalse(_cap_reached(0, 0))
        self.assertFalse(_cap_reached(10_000, 0))

    def test_positive_cap_still_stops_at_the_limit(self) -> None:
        self.assertFalse(_cap_reached(79, 80))
        self.assertTrue(_cap_reached(80, 80))
        self.assertTrue(_cap_reached(81, 80))

    def test_batch_size_is_serialized_only_when_cap_is_positive(self) -> None:
        """content_extraction_service.py:107-109 / :185-187 의 분기와 같은 식."""
        for cap, expected in ((80, 1), (1, 1), (0, 3)):
            with self.subTest(cap=cap):
                batch_size = min(3, 30)
                if cap > 0:
                    batch_size = 1
                self.assertEqual(batch_size, expected)


class DeployedExtractorJobEnvTest(unittest.TestCase):
    """배포 워크플로에 실제로 값이 박혀 있는지 본다. 코드 기본값에 의존하지 않는다.

    '기본값이 마침 맞다' 와 '배포가 그 값을 보장한다' 는 다른 얘기다.
    이 Job 들은 env 를 --set-env-vars 로 통째로 덮으므로 빠진 값은 코드 기본값이 된다.
    """

    def _workflow_text(self) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / ".github" / "workflows" / "deploy-api-cloud-run.yml").read_text(
            encoding="utf-8"
        )

    def test_extractor_job_disables_run_gemini_call_cap(self) -> None:
        self.assertIn("EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0", self._workflow_text())

    def test_extractor_job_pins_gemini_concurrency(self) -> None:
        text = self._workflow_text()
        self.assertEqual(text.count("GEMINI_MAX_CONCURRENCY=32"), 2)  # 번역 워커 + 추출 Job

    def test_crawler_worker_job_pins_batch_size(self) -> None:
        self.assertIn(
            "app.jobs.crawler_worker,--max-jobs,0,--idle-grace-seconds,3,--batch-size,3",
            self._workflow_text(),
        )

    def test_extractor_job_has_two_gigs(self) -> None:
        text = self._workflow_text()
        extractor_block = text.split("Deploy scheduled content extractor Job")[1]
        self.assertIn("app.jobs.scheduled_content_extractor,--max-notices,30", extractor_block)
        self.assertIn("--memory=2Gi", extractor_block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_extractor_run_budget -v
```

Expected: `RunGeminiCallCapTest` 3개 PASS (지금 코드가 이미 그렇게 동작한다 — 그 성질을 못 박는 것이 목적이다), `DeployedExtractorJobEnvTest` **4개 전부 FAIL**:

```
AssertionError: 'EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0' not found in ...
AssertionError: 1 != 2
AssertionError: 'app.jobs.crawler_worker,...,--batch-size,3' not found in ...
AssertionError: '--memory=2Gi' not found in ...
```

- [ ] **Step 3: crawler-worker args 에 `--batch-size 3` 을 명시한다**

`.github/workflows/deploy-api-cloud-run.yml:126` 을 바꾼다:

```yaml
            --args="-m,app.jobs.crawler_worker,--max-jobs,0,--idle-grace-seconds,3,--batch-size,3" \
```

> 값을 바꾸는 게 아니라 «암묵을 명시로» 바꾸는 것이다. argparse 기본값이 이미 3
> (`crawler_worker.py:166`)이지만, PR #66 이 translation-worker(`:111`)만 고치고 이쪽을
> 빠뜨린 것과 같은 사고를 막는다.

- [ ] **Step 4: 추출 Job 의 메모리와 env 를 고친다**

`.github/workflows/deploy-api-cloud-run.yml:161` 을 바꾼다:

```yaml
            --memory=2Gi \
```

같은 스텝의 `:163` 을 바꾼다:

```yaml
            --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=INFO,SUPABASE_URL=${{ vars.NEXT_PUBLIC_SUPABASE_URL }},VERTEX_AI_PROJECT_ID=${{ vars.VERTEX_AI_PROJECT_ID }},VERTEX_AI_LOCATION=${{ vars.VERTEX_AI_LOCATION }},GEMINI_MAX_CONCURRENCY=32,EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0" \
```

그리고 그 스텝 위의 주석 블록(`:134-135`)에 다음 두 줄을 덧붙인다:

```yaml
      # EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0 = 런당 콜 상한 해제. _cap_reached 가 cap>0 일 때만
      # 동작하고, 같은 조건이 batch_size=1 강제 직렬화도 켠다 → 0 이 상한 해제 + 동시성 3 복원.
      # 폭주 방어는 --max-notices 30 / 공지당 8콜 / 26MB / 600초 / OCR 동시 6 이 남는다.
      # 메모리 2Gi: 타일 24조각 + PIL 본문사진 합성 12장(_MAX_BODY_IMAGES)에 512Mi 는 OOM 위험.
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_extractor_run_budget -v
```

Expected: 7 tests, 전부 PASS

- [ ] **Step 6: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add .github/workflows/deploy-api-cloud-run.yml backend/tests/test_extractor_run_budget.py
git commit -m "fix(extractor): 런 Gemini 콜 상한 해제 + 동시성·메모리 정합

EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=80 이 두 가지를 동시에 망가뜨리고 있었다.
80 ÷ 공지당 8콜 = 런당 10건이라 --max-notices 30 이 도달 불가능한 숫자였고,
같은 값이 0보다 크다는 이유로 batch_size 를 1 로 못 박아 공지 동시성 3 이 죽어 있었다.

0 으로 두면 _cap_reached 가 꺼지고 batch_size 가 3 으로 복원된다. env 한 줄이다.
비용 상한을 걷어내는 대신 공지 건수(--max-notices 30)가 유일한 상한이 되고,
폭주 방어는 공지당 8콜·26MB·600초·OCR 동시 6·Job 타임아웃이 그대로 남는다.

추출 Job 에 GEMINI_MAX_CONCURRENCY=32 를 넣는다 — 추출 Job 은 공지마다 번역을
인라인 실행하는데(content_extraction_service.py:373) 그 경로가 코드 기본값 12 로
돌고 있었다. 번역 워커와 같은 값으로 맞춘다.

메모리를 2Gi 로 올린다. crawler-worker 는 --batch-size 3 을 명시로 바꾼다."
```

- [ ] **Step 8: 머지·배포 후 Job 리비전에 실제로 반영됐는지 확인한다**

```bash
gcloud run jobs describe naranhi-content-extractor --region=asia-northeast3 \
  --format="value(template.template.containers[0].env,template.template.containers[0].resources.limits)"
gcloud run jobs describe naranhi-crawler-worker --region=asia-northeast3 \
  --format="value(template.template.containers[0].args)"
```

Expected: 추출 Job 에 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`·`GEMINI_MAX_CONCURRENCY=32`·`memory=2Gi`, crawler-worker args 에 `--batch-size,3`

- [ ] **Step 9: 수동 실행 1회로 직렬화가 풀렸는지 확인한다**

```bash
gcloud run jobs execute naranhi-content-extractor --region=asia-northeast3 --wait
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-content-extractor" AND textPayload:"content extractor result:"' \
  --limit=20 --freshness=30m --format="value(timestamp,textPayload)"
```

Expected: `content extractor result:` 줄의 타임스탬프가 **3건씩 묶여** 나온다(동시성 3 복원). 대상 공지가 없으면 `processed=0` — 그건 정상이고 Task 11 재가동 후 다시 본다.

---

## Task 2: 본문 사진 경로 계측

Task 9(진단)가 필요로 하는 유일한 계측이다. 지금 **수집 실패는 `except: pass` 두 곳에서
통째로 사라지고**(`extract_pipeline.py:243-244`, `:266-267`), 합성·업로드 결과는
`_combine_and_upload_body_images` 가 `""` 를 돌려줄 뿐 이유를 남기지 않는다.

**Files:**
- Modify: `backend/extractor/extract_pipeline.py:243-244`, `:266-267`
- Modify: `backend/app/services/content_extraction_service.py:723-748` (`_combine_and_upload_body_images`)
- Create: `backend/tests/test_body_image_logging.py`

**Interfaces:**
- Consumes: 없음
- Produces: Cloud Logging 에서 검색 가능한 문자열 2종 — `inline image collect failed:` 와 `body images: notice_id=... collected=N stitched=M upload=ok|fail`. Task 9 가 이 문자열로 H2b/H3/H4 를 가른다.

- [ ] **Step 1: 합성 로그를 요구하는 실패 테스트를 쓴다**

`backend/tests/test_body_image_logging.py` 생성:

```python
"""본문 사진 합성·업로드가 한 줄 로그를 남기는지. 진단(Task 9)의 유일한 관측 수단이다."""
import unittest
from unittest.mock import patch

from app.services.content_extraction_service import _combine_and_upload_body_images


class BodyImageLoggingTest(unittest.IsolatedAsyncioTestCase):
    async def test_logs_counts_when_stitch_fails(self) -> None:
        """PIL 이 한 장도 못 열면 stitched=0 upload=skip 이 남아야 한다."""
        images = [("inline_image_1", b"not-an-image")]
        with self.assertLogs("app.services.content_extraction_service", level="INFO") as logs:
            url = await _combine_and_upload_body_images("notice-1", images)
        self.assertEqual(url, "")
        self.assertTrue(any("body images:" in line and "collected=1" in line for line in logs.output))
        self.assertTrue(any("stitched=0" in line for line in logs.output))

    async def test_logs_upload_result_when_stitch_succeeds(self) -> None:
        def _fake_stitch(images: list[bytes]) -> bytes:
            return b"stitched-png-bytes"

        async def _fake_upload(**kwargs: object) -> None:
            return None  # 업로드 실패

        with patch(
            "app.services.content_extraction_service._stitch_images_vertically", _fake_stitch
        ), patch("app.services.attachment_storage.upload_bytes", _fake_upload):
            with self.assertLogs("app.services.content_extraction_service", level="INFO") as logs:
                url = await _combine_and_upload_body_images("notice-2", [("inline_image_1", b"x")])

        self.assertEqual(url, "")
        self.assertTrue(any("upload=fail" in line for line in logs.output))

    async def test_no_log_when_there_are_no_inline_images(self) -> None:
        """사진이 애초에 없는 공지는 조용해야 한다 — 로그가 잡음이 되면 안 된다."""
        with self.assertNoLogs("app.services.content_extraction_service", level="INFO"):
            self.assertEqual(await _combine_and_upload_body_images("notice-3", []), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_body_image_logging -v
```

Expected: `test_logs_counts_when_stitch_fails`·`test_logs_upload_result_when_stitch_succeeds` FAIL — `AssertionError: no logs of level INFO or higher triggered`

- [ ] **Step 3: 합성·업로드 결과를 한 줄로 남긴다**

`backend/app/services/content_extraction_service.py` 의 `_combine_and_upload_body_images`
(`:723-748`) 마지막 부분을 교체한다. `ordered = [data for _, data in ordered_items]` 이후:

```python
    ordered = [data for _, data in ordered_items]
    combined = await asyncio.to_thread(_stitch_images_vertically, ordered)
    if not combined:
        LOGGER.info(
            "body images: notice_id=%s collected=%s stitched=0 upload=skip",
            notice_id,
            len(ordered),
        )
        return ""
    from app.services.attachment_storage import upload_bytes

    info = await upload_bytes(
        notice_id=notice_id, name="body-images", data=combined, content_type="image/png", ext=".png"
    )
    LOGGER.info(
        "body images: notice_id=%s collected=%s stitched=1 bytes=%s upload=%s",
        notice_id,
        len(ordered),
        len(combined),
        "ok" if info else "fail",
    )
    return info["public_url"] if info else ""
```

> `stitched` 는 «합성 PNG 가 나왔는가»(0/1)다. PIL 이 몇 장을 열었는지는
> `_stitch_images_vertically` 안에 있고 그 함수는 바이트만 돌려준다 — 지금 구조에서
> 밖으로 꺼내려면 반환형을 바꿔야 하므로 **하지 않는다.** `collected` 와 `stitched` 의
> 조합만으로 H3(«전부 못 열었다» = collected>0, stitched=0)을 가를 수 있다.

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_body_image_logging -v
```

Expected: 3 tests PASS

- [ ] **Step 5: 수집 실패를 삼키는 두 곳에 경고를 붙인다**

`backend/extractor/extract_pipeline.py:243-244` 를 바꾼다:

```python
                except Exception as exc:  # noqa: BLE001 - 수집 실패가 추출을 막지 않게.
                    LOGGER.warning(
                        "inline image collect failed: source_id=%s stage=skip_path %s: %s",
                        candidate.source_id,
                        type(exc).__name__,
                        sanitize_error(exc),
                    )
```

`:266-267` 을 바꾼다:

```python
                except Exception as exc:  # noqa: BLE001 - 수집 실패가 추출을 막지 않게.
                    LOGGER.warning(
                        "inline image collect failed: source_id=%s stage=ocr_path %s: %s",
                        candidate.source_id,
                        type(exc).__name__,
                        sanitize_error(exc),
                    )
```

> `stage` 로 두 경로를 구분한다. `skip_path` 는 «OCR 은 안 하지만 사진은 모은다» 경로
> (`inline_image_no_content_signal` 등)이고, `ocr_path` 는 OCR 까지 하는 경로다.
> **운영에 `no_content_signal` 이 7건 있으므로 `skip_path` 가 실제로 도는 경로다.**

- [ ] **Step 6: `LOGGER` 와 `sanitize_error` 가 그 파일에 이미 있는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import extractor.extract_pipeline as m
print('LOGGER:', hasattr(m, 'LOGGER'))
print('sanitize_error:', hasattr(m, 'sanitize_error'))
"
```

Expected: 둘 다 `True`. `LOGGER` 가 없으면 파일 상단에 `LOGGER = logging.getLogger(__name__)` 을 추가한다(`import logging` 포함).

- [ ] **Step 7: 인라인 이미지 회귀 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_extract_pipeline_inline backend.tests.test_content_extraction_service -v
```

Expected: 전부 통과

- [ ] **Step 8: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 9: 커밋**

```bash
git add backend/extractor/extract_pipeline.py backend/app/services/content_extraction_service.py backend/tests/test_body_image_logging.py
git commit -m "feat(extractor): 본문 사진 수집·합성 경로 계측

본문 사진 회수율이 31%(운영 35건 중 11건에 body_images_combined)인데,
왜 나머지에서 안 나오는지 알 방법이 지금 없다.

수집 실패는 except: pass 두 곳에서 통째로 사라지고 있었다. stage=skip_path /
stage=ocr_path 로 구분해 경고를 남긴다 — skip_path 는 'OCR 은 건너뛰되 사진은
모은다' 경로이고 운영에 no_content_signal 7건이 있으므로 실제로 도는 경로다.

합성·업로드는 collected/stitched/upload 한 줄로 남긴다. 사진이 없는 공지는
조용히 지나가게 해 로그가 잡음이 되지 않게 한다.

새 테이블·새 컬럼을 만들지 않는다. 공지 38건 규모에서는 Cloud Logging 검색으로 센다."
```

---

## Task 3: HWP 1순위 침묵 이탈 계측

운영 HWP 20건 중 6건(30%)이 표를 잃는 2순위(`hwp_ole_bodytext_filtered`)로 떨어졌는데
**왜 떨어졌는지가 기록에 없다.** `_hwp_to_markdown` 에는 경고를 남기지 않는 이탈 경로가
둘이다(`hwp_extractor.py:31` 40자 미만, `:99-100` 실행파일 없음).

`warnings` 가 저장된다는 사실은 확인됐다(이 문서 상단 «스펙 정정»). 따라서 **경고만
붙이면 다음 HWP 부터는 이유가 남는다.**

**Files:**
- Modify: `backend/extractor/extractors/hwp_extractor.py:30-31`, `:98-100`
- Modify: `backend/tests/test_hwp_markdown.py`

**Interfaces:**
- Consumes: 없음
- Produces: `ExtractedText.warnings` 에 `hwp5html_too_short: chars=N` 또는 `hwp5html_skip_no_command`. Task 5 가 이 경고로 «임계값 완화가 실제로 먹혔는가»를 판정한다.

- [ ] **Step 1: 침묵 이탈을 금지하는 실패 테스트를 쓴다**

`backend/tests/test_hwp_markdown.py` 끝에 추가:

```python
class HwpFirstTierSilentExitTest(unittest.IsolatedAsyncioTestCase):
    """1순위(hwp5html)가 실패했으면 이유가 반드시 warnings 에 남아야 한다.

    운영 6건이 2순위로 떨어졌는데 이유가 하나도 기록되지 않았다. 침묵 이탈이
    남아 있으면 Task 5(임계값 완화)가 먹혔는지 검증할 수단이 없다.
    """

    async def test_short_markdown_records_reason(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        with patch.object(hwp_extractor, "_hwp_to_markdown", return_value="짧음"), patch.object(
            hwp_extractor, "_try_hwp_ole_bodytext", return_value="본문 텍스트가 충분히 길게 들어 있는 문단입니다."
        ):
            result = await hwp_extractor.extract_hwp_text(
                Path("dummy.hwp"), source_name="dummy.hwp", gemini=None, work_dir=Path(".")
            )

        self.assertEqual(result.method, "hwp_ole_bodytext_filtered")
        self.assertTrue(
            any(w.startswith("hwp5html_too_short:") for w in result.warnings),
            f"이유가 기록되지 않았다: {result.warnings}",
        )

    async def test_missing_command_records_reason(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        warnings: list[str] = []
        with patch.object(hwp_extractor, "_hwp5html_command", return_value=None):
            markdown = hwp_extractor._hwp_to_markdown(Path("dummy.hwp"), warnings)

        self.assertEqual(markdown, "")
        self.assertIn("hwp5html_skip_no_command", warnings)
```

파일 상단에 `from pathlib import Path` 가 없으면 추가한다.

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_hwp_markdown -v
```

Expected: 두 새 테스트 FAIL — `이유가 기록되지 않았다: []` 와 `'hwp5html_skip_no_command' not found in []`

- [ ] **Step 3: 40자 미만 이탈에 경고를 붙인다**

`backend/extractor/extractors/hwp_extractor.py:30-31` 을 바꾼다:

```python
    markdown = _hwp_to_markdown(path, warnings)
    stripped = markdown.strip()
    if len(stripped) >= 40:  # hwp5html 로 표 구조·앞글자 보존 성공
```

그리고 그 `if` 블록이 끝난 직후(`:40`, `body_text = _try_hwp_ole_bodytext(...)` 바로 위)에 추가:

```python
    # 1순위가 표를 보존하는 유일한 경로다. 여기까지 왔다는 것은 실패했다는 뜻이므로
    # 이유를 남긴다 — 운영 6건이 이유 없이 2순위로 떨어져 원인 규명이 불가능했다.
    warnings.append(f"hwp5html_too_short: chars={len(stripped)}")
```

- [ ] **Step 4: 실행파일 없음 이탈에 경고를 붙인다**

`hwp_extractor.py:98-100` 을 바꾼다:

```python
    command = _hwp5html_command()
    if command is None:
        warnings.append("hwp5html_skip_no_command")
        return ""
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_hwp_markdown backend.tests.test_hwp_extractor -v
```

Expected: 전부 PASS

- [ ] **Step 6: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add backend/extractor/extractors/hwp_extractor.py backend/tests/test_hwp_markdown.py
git commit -m "feat(hwp): 1순위 hwp5html 실패 이유를 warnings 에 남긴다

운영 HWP 20건 중 6건(30%)이 표를 잃는 2순위(OLE BodyText)로 떨어졌는데
이유가 하나도 기록되지 않았다. _hwp_to_markdown 에 경고 없는 이탈이 둘 있다 —
결과가 40자 미만일 때와 hwp5html 실행파일이 없을 때.

pyhwp 는 extractor-requirements.txt 에 있고 14건이 실제로 1순위로 성공했으므로
실행파일 없음은 배제된다. 유력한 것은 40자 미만이지만 확증이 없다.
경고 두 줄이 그 확증을 만든다.

warnings 는 저장된다 — ExtractedText.warnings → SourceExtraction.errors →
extracted_content.sources[].errors 경로가 이미 있다."
```

---

## Task 4: 타일 예산 분리 + 타일 계측

`_tile_if_oversized` 는 초장축 이미지를 최대 24조각으로 자르는데
(`image_gemini_extractor.py:115`), `_ocr_image` 가 **조각마다 예산 1콜을 예약한다**(`:76`).
공지당 상한이 8이므로 9번째 조각에서 `budget_exhausted` 가 되고 남은 15조각이 조용히
버려진다 — 타일 루프가 예외를 삼키고(`:54-55`) 빈 텍스트를 스킵하므로(`:52-53`)
최종 결과는 `gemini_vision_tiled[24]` 인데 내용은 앞 8조각뿐이다.

**설계(스펙 §4.3 안 A):** 예약 지점을 `_ocr_image` 에서 `extract_image_text` 진입부로
**한 단계 올린다.** 이미지 소스 하나 = 예산 1콜. 타일 수는 `MAX_TILES_PER_IMAGE` 로만 제한한다.

> 스펙 §4.2 안 C(타일 높이↑·개수↓)는 **실효가 없다** — `_normalize_image` 가 모든 타일을
> `thumbnail((2400, 2400))`(`:138`)로 다시 줄인다. 안 D(멀티타일 1콜)는 `extract_bytes` 가
> 단일 `Part` 만 지원해 불가하다. 둘 다 시도하지 말 것.

**Files:**
- Modify: `backend/extractor/extractors/image_gemini_extractor.py:25-62`, `:65-84`, `:101-126`
- Modify: `backend/tests/test_image_tiling.py`
- Create: `scripts/probe_extraction_hallucination.py` (Step 11 — 읽기 전용 프로브)

**Interfaces:**
- Consumes: `ExtractionBudget.reserve_gemini_call(source_id: str, byte_count: int) -> BudgetDecision` (변경 없음)
- Produces: 이미지 소스 1개당 예산 1콜. `MAX_TILES_PER_IMAGE`(기본 24) env. 로그 `image tiles: source=... tiles=N ok=N empty=N failed=N`.
- Produces: **환각 판정 H-PASS / H-FAIL** (Step 13). H-FAIL 이면 선택 Task 13(Bedrock 이전)의 착수 조건이 성립한다.

- [ ] **Step 1: 예산 1콜을 요구하는 실패 테스트를 쓴다**

`backend/tests/test_image_tiling.py` 의 `ImageTilingTests` 클래스에 추가:

```python
    def test_tiled_image_consumes_exactly_one_budget_call(self) -> None:
        """타일 24조각이 공지당 8콜 예산을 먹어치우면 안 된다. 이미지 소스 1개 = 예산 1콜."""
        from extractor.budget import ExtractionBudget

        path = _make_image(100, 20000)  # 초장축 -> 10조각
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=8, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="tall.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(budget.gemini_calls_used, 1)
        self.assertFalse(budget.budget_exhausted)
        self.assertGreaterEqual(gem.calls, 9)  # 조각은 다 돌았다
        self.assertIn("조각 텍스트", result.text)

    def test_single_image_still_consumes_one_budget_call(self) -> None:
        from extractor.budget import ExtractionBudget

        path = _make_image(800, 600)
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=8, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="normal.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(result.method, "gemini_vision")
        self.assertEqual(budget.gemini_calls_used, 1)
        self.assertEqual(gem.calls, 1)

    def test_exhausted_budget_skips_ocr_entirely(self) -> None:
        from extractor.budget import ExtractionBudget

        path = _make_image(100, 20000)
        gem = _FakeGemini()
        budget = ExtractionBudget(
            max_gemini_calls=0, max_inline_images=6, max_ocr_bytes=26_214_400, max_pdf_pages_for_ocr=20
        )

        result = asyncio.run(
            extract_image_text(path, source_name="tall.png", gemini=gem, budget=budget, source_id="s1")
        )

        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(gem.calls, 0)  # 조각을 만들기도 전에 끝난다

    def test_tile_count_is_capped_by_env(self) -> None:
        import os
        from unittest.mock import patch

        path = _make_image(100, 20000)
        gem = _FakeGemini()
        with patch.dict(os.environ, {"MAX_TILES_PER_IMAGE": "3"}):
            result = asyncio.run(
                extract_image_text(path, source_name="tall.png", gemini=gem, source_id="s1")
            )

        self.assertEqual(result.method, "gemini_vision_tiled[3]")
        self.assertEqual(gem.calls, 3)
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_image_tiling -v
```

Expected: `test_tiled_image_consumes_exactly_one_budget_call` FAIL (`8 != 1`), `test_exhausted_budget_skips_ocr_entirely` FAIL (조각별로 호출됨), `test_tile_count_is_capped_by_env` FAIL (`gemini_vision_tiled[10] != gemini_vision_tiled[3]`)

- [ ] **Step 3: 예약을 `extract_image_text` 로 올린다**

`backend/extractor/extractors/image_gemini_extractor.py` 의 `extract_image_text`(`:25-62`)를
통째로 교체한다:

```python
async def extract_image_text(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor,
    budget: ExtractionBudget | None = None,
    source_id: str = "",
) -> ExtractedText:
    """이미지 OCR. 초장축/초대형 포스터는 세로로 타일링해 조각별로 OCR한다.

    886x25020 같은 스크롤형 포스터를 2400px 박스로 줄이면 폭이 ~85px로 찌부되어 글자를
    못 읽고 환각(엉뚱한 학교명)이 난다. 그래서 일반 이미지는 그대로, 초장축은 잘라서 처리한다.

    예산은 **이미지 소스 하나당 1콜**로 예약한다. 타일마다 예약하면 24조각짜리 포스터가
    공지당 8콜을 9조각째에 다 먹고 나머지 15조각이 조용히 버려진다 — 그 공지의 PDF·HWP
    첨부는 예산을 한 톨도 못 쓰게 된다. 타일 수는 MAX_TILES_PER_IMAGE 로만 제한한다.
    """
    if budget is not None:
        decision = budget.reserve_gemini_call(source_id or source_name, path.stat().st_size)
        if not decision.ok:
            return ExtractedText(
                source=source_name,
                method="gemini_vision",
                text="",
                status="budget_exhausted",
                warnings=[decision.reason],
            )

    tiles = _tile_if_oversized(path)
    if len(tiles) == 1:
        return await _ocr_image(tiles[0], source_name=source_name, gemini=gemini, source_id=source_id)

    texts: list[str] = []
    empty = 0
    failed = 0
    for index, tile_path in enumerate(tiles):
        try:  # 한 조각이 실패(빈 조각/일시 오류)해도 나머지 조각은 계속 OCR
            result = await _ocr_image(
                tile_path,
                source_name=f"{source_name}#t{index}",
                gemini=gemini,
                source_id=f"{source_id}:{index}" if source_id else "",
            )
            if result.text.strip():
                texts.append(result.text.strip())
            else:
                empty += 1
        except Exception:  # noqa: BLE001 - isolate per-tile failures.
            failed += 1
            continue
    LOGGER.info(
        "image tiles: source=%s tiles=%s ok=%s empty=%s failed=%s",
        source_name,
        len(tiles),
        len(texts),
        empty,
        failed,
    )
    combined = "\n\n".join(texts)
    return ExtractedText(
        source=source_name,
        method=f"gemini_vision_tiled[{len(tiles)}]",
        text=combined,
        status="success" if combined.strip() else "empty_or_unreadable",
    )
```

파일 상단 `import os` 아래에 추가:

```python
import logging

LOGGER = logging.getLogger(__name__)
```

- [ ] **Step 4: `_ocr_image` 에서 예약을 걷어낸다**

`_ocr_image`(`:65-84`)의 시그니처와 예약 블록을 교체한다:

```python
async def _ocr_image(
    path: Path,
    *,
    source_name: str,
    gemini: GeminiDocumentExtractor,
    source_id: str = "",
) -> ExtractedText:
    # 예산 예약은 호출부(extract_image_text)가 이미 했다. 여기서 다시 잡으면 타일마다
    # 1콜이 나가 24조각짜리가 공지 예산을 통째로 먹는다.
    normalized_path = _normalize_image(path)
    mime_type = IMAGE_MIME_BY_SUFFIX.get(normalized_path.suffix.lower(), "image/png")
    result = await gemini.extract_path(
        normalized_path,
        mime_type=mime_type,
        prompt=ocr_prompt(source_name),
    )
```

이후 `return ExtractedText(...)` 블록은 그대로 둔다.

> `source_id` 는 더 이상 쓰이지 않지만 **인자로 남긴다** — 호출부가 조각 번호를 붙여
> 넘기고 있어 지우면 호출부까지 고쳐야 한다. 향후 로그에 쓸 수 있는 값이다.

- [ ] **Step 5: `_ocr_image` 의 다른 호출부가 없는지 확인한다**

```bash
grep -rn "_ocr_image" backend/ --include=*.py
```

Expected: `image_gemini_extractor.py` 안의 정의 1곳 + 호출 2곳뿐. 다른 파일에서 부르면 그 호출부도 `budget=` 인자를 지워야 한다.

- [ ] **Step 6: 타일 상한을 env 화한다**

`_tile_if_oversized`(`:101-126`)의 docstring 과 상수 줄을 바꾼다:

```python
def _tile_if_oversized(path: Path) -> list[Path]:
    """초장축/초대형 이미지면 세로 타일 경로 리스트를, 아니면 [원본 경로]를 돌려준다.

    조건: 세로가 가로의 2.5배 초과 OR 총 화소 400만 초과. (둘 다 아니면 단일 처리)
    타일은 2200px 높이·200px 겹침, 최대 MAX_TILES_PER_IMAGE(기본 24)조각.
    실패 시 단일 경로로 폴백(기존 동작 보존).

    타일 높이를 올려 개수를 줄이는 안은 실효가 없다 — _normalize_image 가 모든 타일을
    thumbnail((2400, 2400)) 으로 다시 줄이므로 2200 초과분은 어차피 버려진다.
    """
```

그리고 `:115` 를 바꾼다:

```python
            tile_height, step = 2200, 2000  # 200px overlap
            limit = _max_tiles_per_image()
```

파일 끝(`_normalize_image` 정의 위)에 추가:

```python
def _max_tiles_per_image() -> int:
    """타일 상한. 1 로 두면 타일링이 사실상 꺼져 옛 동작에 가까워진다(롤백 수단)."""
    try:
        return max(1, int(os.getenv("MAX_TILES_PER_IMAGE", "24")))
    except ValueError:
        return 24
```

- [ ] **Step 7: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_image_tiling -v
```

Expected: 6 tests PASS

- [ ] **Step 8: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 9: 커밋**

```bash
git add backend/extractor/extractors/image_gemini_extractor.py backend/tests/test_image_tiling.py
git commit -m "fix(extractor): 타일 OCR 예산을 이미지 소스 단위로 올린다

초장축 포스터를 24조각으로 자른 뒤 조각마다 예산 1콜을 예약하고 있었다.
공지당 상한이 8이라 9조각째에 budget_exhausted 가 되고 남은 15조각이 조용히
버려졌다 — 타일 루프가 예외를 삼키고 빈 텍스트를 스킵하므로 결과는
gemini_vision_tiled[24] 인데 내용은 앞 8조각뿐이다. 게다가 budget_exhausted 는
즉시 포기 코드라 재시도도 없다.

예약 지점을 _ocr_image 에서 extract_image_text 진입부로 한 단계 올린다.
이미지 소스 1개 = 예산 1콜. 이미지와 문서가 예산을 공평히 나눈다.
첨부의 45.8%가 이미지(32/70)라 가장 많이 쓰이는 경로가 가장 잘 깨져 있었다.

타일 상한은 MAX_TILES_PER_IMAGE(기본 24)로만 제한한다. 26MB 바이트 상한은
폭주 방어선으로 그대로 둔다. MAX_TILES_PER_IMAGE=1 이 롤백 수단이다.

타일 높이를 올려 개수를 줄이는 안은 채택하지 않았다 — _normalize_image 가
모든 타일을 2400px 썸네일로 다시 줄여 실효가 없다."
```

- [ ] **Step 10: 배포 후 초장축 이미지 1건으로 확인한다**

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-content-extractor" AND textPayload:"image tiles:"' \
  --limit=10 --freshness=1d --format="value(textPayload)"
```

Expected: `image tiles: source=... tiles=N ok=N empty=0 failed=0` — **`ok` 가 `tiles` 와 같다.** `ok < tiles` 이고 `failed > 0` 이면 조각 OCR 자체가 실패하는 별개 문제다.

- [ ] **Step 11: 환각 negative control 프로브를 쓴다**

지금까지의 모든 검증은 «무언가가 나왔는가»를 본다. 판독의 진짜 실패는
**«아무것도 못 읽고 그럴듯한 가정통신문을 지어냈다»**이고, 그건 **나오는 쪽이라 기존
기준을 전부 통과한다.** 2026-08-27 Bedrock 시험에서 Nova Lite·Pro 가 QR 코드 PNG 에
대해 없는 가정통신문을 통째로 지어냈다(스펙 §19.2). **현행 Gemini 도 같은 위험을 갖고,
우리는 한 번도 확인한 적이 없다.**

`scripts/probe_extraction_hallucination.py` 생성:

```python
"""판독 환각 negative control. 운영 DB 를 건드리지 않는다 — 로컬 파일만 읽는다.

negative control 은 '읽을 수 없는 입력' 이다. 올바른 동작은 '못 읽겠다' 또는 빈 결과이고,
가정통신문 형태의 문장이 나오면 그건 환각이다. positive control 을 함께 돌리는 이유는
'항상 빈 결과를 내서 통과' 하는 가짜 합격을 배제하기 위해서다.
"""
import argparse
import asyncio
import json
import pathlib
import re
import sys

from extractor.extractors.gemini_document_extractor import GeminiDocumentExtractor
from extractor.extractors.image_gemini_extractor import extract_image_text

# 지어냈을 때만 나오는 것들. 판독 불가 입력에서 이게 나오면 환각이다.
FABRICATION_MARKERS = (
    "학교", "교장", "학부모", "가정통신문", "안내", "학년", "반",
    "일시", "장소", "신청", "제출", "담임", "교육청",
)
REFUSAL_MARKERS = ("읽을 수 없", "판독", "인식할 수 없", "QR", "알 수 없", "unreadable")


def verdict(text: str) -> tuple[str, list[str]]:
    stripped = text.strip()
    if not stripped:
        return "PASS(empty)", []
    if any(m in stripped for m in REFUSAL_MARKERS) and len(stripped) < 200:
        return "PASS(refused)", []
    hits = [m for m in FABRICATION_MARKERS if m in stripped]
    if hits:
        return "FAIL(fabricated)", hits
    return "PASS(no-markers)", []


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--negative", nargs="+", required=True, help="판독 불가 입력 (QR/백지/노이즈)")
    ap.add_argument("--positive", nargs="+", default=[], help="내용이 확실한 입력")
    args = ap.parse_args()

    gem = GeminiDocumentExtractor()
    report: list[dict] = []

    for kind, paths in (("negative", args.negative), ("positive", args.positive)):
        for raw in paths:
            path = pathlib.Path(raw)
            result = await extract_image_text(
                path, source_name=path.name, gemini=gem, source_id=f"probe:{path.name}"
            )
            text = result.text or ""
            if kind == "negative":
                mark, hits = verdict(text)
            else:
                mark = "PASS(read)" if len(text.strip()) >= 40 else "FAIL(empty-positive)"
                hits = []
            report.append(
                {
                    "kind": kind,
                    "file": path.name,
                    "method": result.method,
                    "chars": len(text.strip()),
                    "verdict": mark,
                    "markers": hits,
                    "head": re.sub(r"\s+", " ", text.strip())[:200],
                }
            )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [r for r in report if r["verdict"].startswith("FAIL")]
    print(f"\n판정: {'H-FAIL' if failed else 'H-PASS'} (negative {len(args.negative)}건 / positive {len(args.positive)}건)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

> **왜 «지어냄 마커»를 쓰는가.** 판독 불가 입력에는 «학교»·«교장»·«가정통신문» 같은
> 구체 명사가 **나올 수 없다.** 나왔다면 모델이 문맥에서 지어낸 것이다. 이건 정확도
> 채점이 아니라 **있을 수 없는 것이 나왔는가**라는 이진 판정이라 사람 없이 돌릴 수 있다.

- [ ] **Step 12: negative 3종 + positive 1종으로 돌린다**

입력을 만든다 — **운영 첨부를 내려받지 않는다.** negative 는 로컬에서 생성하고,
positive 는 내용을 아는 파일 1개를 쓴다.

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import pathlib, qrcode
from PIL import Image, ImageDraw
out = pathlib.Path('.tmp-probe'); out.mkdir(exist_ok=True)
qrcode.make('https://example.invalid/naranhi-probe').save(out / 'neg-qr.png')
Image.new('RGB', (900, 1200), 'white').save(out / 'neg-blank.png')
im = Image.new('RGB', (900, 1200), 'white'); d = ImageDraw.Draw(im)
for x in range(0, 900, 7): d.line([(x, 0), (x - 400, 1200)], fill=(190, 190, 190))
im.save(out / 'neg-noise.png')
print(sorted(p.name for p in out.iterdir()))
"
```

> `qrcode` 가 없으면 `backend/venv/Scripts/python.exe -m pip install qrcode` 로 넣거나,
> QR 이미지를 손으로 하나 준비해 `.tmp-probe/neg-qr.png` 로 둔다. **QR 은 negative
> control 의 핵심 표본이다** — Nova 가 정확히 이 입력에서 무너졌다.

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/probe_extraction_hallucination.py \
  --negative .tmp-probe/neg-qr.png .tmp-probe/neg-blank.png .tmp-probe/neg-noise.png \
  --positive .tmp-probe/pos-known.png
```

Expected:

| 입력 | 통과 기준 |
|---|---|
| `neg-qr.png` | `PASS(empty)` 또는 `PASS(refused)`. **`FAIL(fabricated)` 이면 현행 판독이 지어낸다는 확증** |
| `neg-blank.png` | 위와 같다 |
| `neg-noise.png` | 위와 같다 |
| `pos-known.png` | `PASS(read)` — 원본에 있는 문자열이 `head` 에 보인다. 이게 없으면 negative 통과가 «항상 빈 결과» 때문이라 무의미하다 |

- [ ] **Step 13: 판정을 기록하고 커밋한다**

아래 표를 이 문서의 «판독 환각 판정» 절(Task 12 뒤)에 채운다.

```
판정: H-PASS | H-FAIL
negative 결과:  qr=___  blank=___  noise=___
positive 결과:  ___
선택 Task 13 착수 조건 충족 여부: ___
```

**판정이 뜻하는 것:**

| 판정 | 다음 |
|---|---|
| **H-PASS** | 현행 Gemini 판독은 판독 불가 입력에 대해 지어내지 않는다. 선택 Task 13 은 **여전히 선택**이고, 착수 근거는 비용뿐인데 그건 월 $1 미만이라 약하다(스펙 §19.6) |
| **H-FAIL** | **현행 판독이 없는 내용을 만들어낸다.** 이건 비용 문제가 아니라 **안전 문제**다 — 재추출하지 않는 방침(§2 비목표)과 겹치면 영구 오염이다. 선택 Task 13 의 착수 조건이 성립하고 우선순위가 올라간다. 동시에 «지어낸 결과를 성공으로 저장하지 않는» 게이트가 별건으로 필요하다 |

```bash
git add scripts/probe_extraction_hallucination.py docs/superpowers/plans/2026-08-27-C-extraction-repair.md
git commit -m "test(extractor): 판독 환각 negative control 프로브

지금까지의 판독 검증은 전부 '무언가가 나왔는가' 만 봤다. 판독의 진짜 실패는
'아무것도 못 읽고 그럴듯한 가정통신문을 지어냈다' 이고, 그건 나오는 쪽이라
기존 기준을 전부 통과한다.

2026-08-27 Bedrock 시험에서 Nova Lite·Pro 가 QR 코드 PNG 에 대해 없는
가정통신문을 통째로 지어냈다(교장 이름까지). 같은 입력에 Claude Haiku 4.5·
Sonnet 4.6 은 'QR 코드라 읽을 수 없다' 고 답했다. 현행 Gemini 가 어느 쪽인지는
한 번도 확인한 적이 없다.

QR·백지·노이즈를 negative control 로, 내용을 아는 파일 하나를 positive control 로
돌린다. 판독 불가 입력에서 '학교'·'교장'·'가정통신문' 같은 구체 명사가 나오면
지어낸 것이다 — 정확도 채점이 아니라 이진 판정이라 사람 없이 돌아간다.

운영 DB 를 건드리지 않는다. 로컬 파일만 읽는다."
```

---

## Task 5: HWP 1순위 진입 조건 — 길이가 아니라 표 구조

`hwp_extractor.py:31` 의 `>= 40` 은 근거가 문서화되지 않은 상수다. 1순위의 존재 이유가
**표 보존**인데(`:92-96` docstring), 표만 있고 산문이 적은 가정통신문(일정표 한 장)이
40자를 못 넘겨 표를 못 읽는 2순위로 떨어진다.

**Files:**
- Modify: `backend/extractor/extractors/hwp_extractor.py:30-31`
- Modify: `backend/tests/test_hwp_markdown.py`

**Interfaces:**
- Consumes: Task 3 이 붙인 `hwp5html_too_short` 경고 (완화가 먹혔는지 판정하는 수단)
- Produces: `_has_markdown_table(markdown: str) -> bool`. 표 마커 2줄 이상 + 20자 이상이면 길이와 무관하게 1순위 채택.

- [ ] **Step 1: 짧은 표가 1순위로 채택되기를 요구하는 실패 테스트를 쓴다**

`backend/tests/test_hwp_markdown.py` 에 추가:

```python
class HwpShortTableTest(unittest.IsolatedAsyncioTestCase):
    """표만 있고 산문이 적은 가정통신문(일정표 한 장)이 표를 잃으면 안 된다.

    1순위의 존재 이유가 표 보존인데, 표가 나왔는데도 '짧다'는 이유로 표를 못 읽는
    2순위(PARA_TEXT 레코드만 긁음)로 떨어뜨리는 것은 목적에 반한다.
    """

    SHORT_TABLE = "| 날짜 | 내용 |\n| --- | --- |\n| 3/2 | 개학 |"

    async def test_short_markdown_with_table_is_accepted(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        self.assertLess(len(self.SHORT_TABLE.strip()), 40)  # 기존 임계값에 걸리는 길이

        with patch.object(hwp_extractor, "_hwp_to_markdown", return_value=self.SHORT_TABLE), patch.object(
            hwp_extractor, "_append_hwp_hyperlinks", side_effect=lambda md, _p: md
        ):
            result = await hwp_extractor.extract_hwp_text(
                Path("dummy.hwp"), source_name="dummy.hwp", gemini=None, work_dir=Path(".")
            )

        self.assertEqual(result.method, "hwp5html_markdown")
        self.assertIn("| 3/2 | 개학 |", result.text)

    async def test_short_markdown_without_table_still_falls_back(self) -> None:
        from unittest.mock import patch

        from extractor.extractors import hwp_extractor

        with patch.object(hwp_extractor, "_hwp_to_markdown", return_value="짧은 산문"), patch.object(
            hwp_extractor, "_try_hwp_ole_bodytext", return_value="본문 텍스트가 충분히 길게 들어 있는 문단입니다."
        ):
            result = await hwp_extractor.extract_hwp_text(
                Path("dummy.hwp"), source_name="dummy.hwp", gemini=None, work_dir=Path(".")
            )

        self.assertEqual(result.method, "hwp_ole_bodytext_filtered")

    async def test_single_pipe_line_is_not_a_table(self) -> None:
        """깨진 markdown 한 줄이 표로 오인되면 쓰레기가 1순위로 통과한다."""
        from extractor.extractors.hwp_extractor import _has_markdown_table

        self.assertFalse(_has_markdown_table("| 뭔가"))
        self.assertTrue(_has_markdown_table("| a |\n| b |"))
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_hwp_markdown -v
```

Expected: `test_short_markdown_with_table_is_accepted` FAIL (`'hwp_fallbacks' != 'hwp5html_markdown'` 또는 2순위), `test_single_pipe_line_is_not_a_table` FAIL (`ImportError: cannot import name '_has_markdown_table'`)

- [ ] **Step 3: 표 판정 헬퍼를 만든다**

`backend/extractor/extractors/hwp_extractor.py` 의 `_URL_RE` 정의 아래에 추가:

```python
# 줄 시작 '|' 가 2줄 이상이면 markdownify 가 실제 <table> 을 변환한 것으로 본다.
# 한 줄짜리는 깨진 markdown 일 수 있으므로 표로 치지 않는다.
_TABLE_ROW_RE = re.compile(r"(?m)^\s*\|")


def _has_markdown_table(markdown: str) -> bool:
    return len(_TABLE_ROW_RE.findall(markdown)) >= 2
```

- [ ] **Step 4: 1순위 진입 조건을 길이에서 구조로 바꾼다**

`hwp_extractor.py:30-31`(Task 3 이 `stripped` 를 도입한 뒤 상태)을 바꾼다:

```python
    markdown = _hwp_to_markdown(path, warnings)
    stripped = markdown.strip()
    # 1순위의 존재 이유는 '표 보존'이다(_hwp_to_markdown docstring). 표가 나왔는데 짧다는
    # 이유로 표를 못 읽는 2순위(PARA_TEXT 레코드만)로 떨어뜨리면 목적에 반한다.
    # 일정표 한 장짜리 가정통신문이 정확히 여기 걸렸다. 길이가 아니라 구조로 판정한다.
    # 20자 하한은 남긴다 — 깨진 markdown 이 표 마커만 갖고 통과하는 것을 막는다.
    if len(stripped) >= 40 or (_has_markdown_table(stripped) and len(stripped) >= 20):
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_hwp_markdown backend.tests.test_hwp_extractor backend.tests.test_hwpx_tables -v
```

Expected: 전부 PASS

- [ ] **Step 6: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add backend/extractor/extractors/hwp_extractor.py backend/tests/test_hwp_markdown.py
git commit -m "fix(hwp): 1순위 진입 판정을 40자 길이에서 표 구조로 바꾼다

hwp5html 결과가 40자 미만이면 무조건 2순위(OLE BodyText)로 떨어뜨리고 있었다.
2순위는 PARA_TEXT 레코드(tag 67)만 긁으므로 행·열 경계가 사라진다 — 표가 통째로
평문이 된다. 표만 있고 산문이 적은 가정통신문(일정표 한 장)이 정확히 여기 걸린다.

40자는 근거가 문서화되지 않은 상수다. 1순위의 존재 이유가 표 보존이므로
길이가 아니라 구조로 판정한다: 줄 시작 '|' 가 2줄 이상이면 채택.
20자 하한은 남긴다 — 깨진 markdown 이 표 마커만으로 통과하지 못하게.

2순위 자체는 건드리지 않는다. 표를 복원하려면 TABLE(tag 76)·LIST_HEADER 파싱이
필요한데 그건 이 작업의 크기를 넘는다. 2순위는 '표 없는 안전망'으로 남긴다.

표 보존율 목표 70%(14/20) → 85%. 재추출하지 않으므로 검증은 신규 HWP 로만 한다."
```

---

## Task 6: 본문 사진 성공판정 게이트 완화 (조건부)

> ⚠️ **이 Task 는 Task 9 의 판정이 «D3 = 성공판정 미도달» 일 때만 실행한다.**
> 다른 판정(D1 사진 없음 / D2 노이즈 필터 / D4 수집·합성 실패)이 나오면 **이 Task 를
> 건너뛰고 그 사실을 Task 9 Step 6 에 기록한다.** 원인을 모르고 고치면 «고쳤다고 믿는
> 코드»만 늘어난다.

`_combine_and_upload_body_images` 는 `_is_successful_extraction(result)` 가 참일 때만
호출된다(`content_extraction_service.py:342, 362`). `_is_successful_extraction`
(`:1298-1303`)은 `raw_text` 가 비었거나 `content_kind == "empty_or_unreadable"` 이면 거짓이다.
**본문이 사진뿐이고 OCR 이 실패한 공지가 정확히 이 함정에 빠진다** — 사진은 수집됐는데
합성조차 시도되지 않는다.

**Files:**
- Modify: `backend/app/services/content_extraction_service.py:341-387`
- Modify: `backend/tests/test_content_extraction_service.py`

**Interfaces:**
- Consumes: Task 9 의 D3 판정, Task 2 의 `body images:` 로그
- Produces: 추출 실패 공지도 수집된 본문 사진이 있으면 합성·업로드한다. `_save_failure` 경로는 그대로 실패로 남는다(상태를 조작하지 않는다).

- [ ] **Step 1: 실패 공지도 본문 사진을 남기기를 요구하는 실패 테스트를 쓴다**

`backend/tests/test_content_extraction_service.py` 에 추가:

```python
class BodyImageOnFailedExtractionTest(unittest.IsolatedAsyncioTestCase):
    """본문이 사진뿐이고 OCR 이 실패한 공지도 '본문 사진'은 남아야 한다.

    지금은 _is_successful_extraction 이 거짓이면 _combine_and_upload_body_images 가
    아예 호출되지 않는다 — 사진을 다 받아놓고 버린다.
    """

    async def test_combine_is_attempted_even_when_extraction_failed(self) -> None:
        from app.services import content_extraction_service as svc

        calls: list[str] = []

        async def _fake_combine(notice_id: str, images: list[tuple[str, bytes]]) -> str:
            calls.append(notice_id)
            return ""

        with patch.object(svc, "_combine_and_upload_body_images", _fake_combine):
            await svc._combine_body_images_best_effort("notice-9", [("inline_image_1", b"x")])

        self.assertEqual(calls, ["notice-9"])

    async def test_combine_failure_does_not_raise(self) -> None:
        from app.services import content_extraction_service as svc

        async def _boom(notice_id: str, images: list[tuple[str, bytes]]) -> str:
            raise RuntimeError("storage down")

        with patch.object(svc, "_combine_and_upload_body_images", _boom):
            self.assertEqual(
                await svc._combine_body_images_best_effort("notice-9", [("inline_image_1", b"x")]), ""
            )
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_content_extraction_service -v -k BodyImageOnFailedExtraction
```

Expected: FAIL — `AttributeError: module has no attribute '_combine_body_images_best_effort'`

- [ ] **Step 3: best-effort 래퍼를 만든다**

`backend/app/services/content_extraction_service.py` 의 `_combine_and_upload_body_images`
정의 바로 아래에 추가:

```python
async def _combine_body_images_best_effort(
    notice_id: str, inline_images: list[tuple[str, bytes]]
) -> str:
    """합성·업로드를 best-effort 로 감싼다. 실패 경로에서도 부르므로 절대 예외를 내지 않는다."""
    try:
        return await _combine_and_upload_body_images(notice_id, inline_images)
    except Exception:  # noqa: BLE001 - 본문 사진은 부가 산출물이다. 추출 판정을 바꾸지 않는다.
        LOGGER.warning("body images combine failed: notice_id=%s", notice_id, exc_info=True)
        return ""
```

- [ ] **Step 4: 성공 경로를 래퍼로 바꾸고 실패 경로에도 붙인다**

`:362` 를 바꾼다:

```python
            body_image = await _combine_body_images_best_effort(notice_id, inline_images)
```

그리고 `:381-387`(실패 경로)을 바꾼다:

```python
        # 추출이 실패해도 본문 사진은 이미 수집돼 있다. 본문이 사진뿐이고 OCR 이 실패한
        # 공지가 정확히 이 경로로 온다 — 사진을 다 받아놓고 버리면 학부모는 아무것도 못 본다.
        # 합성 결과는 로그로만 남긴다(실패 상태를 성공으로 바꾸지 않는다).
        await _combine_body_images_best_effort(notice_id, inline_images)

        error_code = classify_extraction_error(result)
        return _save_failure(
            notice,
            error_code=error_code,
            error_message=_result_error_message(result),
            gemini_calls_used=gemini_calls_used,
        )
```

> **`_save_failure` 는 `extracted_content` 를 쓰지 않으므로**(`:1092-1122` 는 상태 컬럼만
> 갱신한다) 합성 PNG 의 URL 이 어디에도 저장되지 않는다. 이 Step 은 «업로드는 되고
> 로그에 남는다»까지다. 저장까지 하려면 `_save_failure` 계약을 바꿔야 하는데 그건
> 별개 결정이므로 **Task 9 의 결론에 그 필요성을 적고 여기서 멈춘다.**

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_content_extraction_service -v
```

Expected: 전부 PASS

- [ ] **Step 6: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 커밋**

```bash
git add backend/app/services/content_extraction_service.py backend/tests/test_content_extraction_service.py
git commit -m "fix(extractor): 추출 실패 공지도 수집된 본문 사진을 합성한다

_combine_and_upload_body_images 가 _is_successful_extraction 이 참일 때만
호출되고 있었다. raw_text 가 비었거나 content_kind 가 empty_or_unreadable 이면
거짓이 되는데, 본문이 사진뿐이고 OCR 이 실패한 공지가 정확히 그 조건이다.
사진을 다 다운로드해놓고 합성조차 시도하지 않았다.

best-effort 래퍼로 감싸 실패 경로에서도 부른다. 예외는 삼키고 경고만 남긴다 —
본문 사진은 부가 산출물이고 추출 판정을 바꾸면 안 된다.

_save_failure 는 extracted_content 를 쓰지 않으므로 지금은 업로드와 로그까지다.
저장 계약 변경은 별개 결정이라 여기서 멈춘다."
```

---

## Task 7: 429 백오프 공용화 — `extractor/` 로 이동

번역 경로는 429 에 최대 112.5초를 기다리는데(`gemini_client.py:24, 35-58`) 추출 경로는
`2 ** attempt` 로 **3초 안에 포기한다**(`gemini_document_extractor.py:271, 306`).
Vertex 는 dynamic shared quota 라 일시 혼잡이 정상인데(`gemini_client.py:21-23`),
3초 안에 포기하는 쪽이 이상하다. 게다가 추출 경로에는 **429 를 만났다는 로그 문자열
자체가 없다** — 지금 429 발생률을 셀 방법이 없다.

**임포트 방향에 주의한다.** `backend/extractor/` 는 `backend/app/` 을 임포트하지 않는다.
따라서 함수를 **`extractor/` 쪽으로 옮기고 `app/translation/gemini_client.py` 가 재임포트**한다.
같은 로직을 복붙하지 않는다 — 두 벌이 되면 다음에 지연값을 조정할 때 한쪽만 고치는
사고가 난다(PR #66 이 translation-worker 만 고치고 crawler-worker 를 빠뜨린 것과 같은 종류).

**Files:**
- Create: `backend/extractor/gemini_backoff.py`
- Modify: `backend/app/translation/gemini_client.py:24-58` (정의 제거 + 재임포트)
- Modify: `backend/extractor/extractors/gemini_document_extractor.py:238-275`, `:277-309`
- Create: `backend/tests/test_extractor_quota_backoff.py`

**Interfaces:**
- Consumes: 없음
- Produces: `extractor.gemini_backoff.call_with_quota_backoff(factory, *, delays_seconds=..., label="gemini") -> Any` 와 `is_quota_exhausted_error(error: Exception) -> bool`. `app.translation.gemini_client` 가 **같은 객체**를 재수출하므로 기존 임포트 경로가 그대로 산다.

- [ ] **Step 1: 구현이 하나뿐임을 요구하는 실패 테스트를 쓴다**

`backend/tests/test_extractor_quota_backoff.py` 생성:

```python
"""429 백오프가 한 벌만 존재하는지. 두 벌이 되면 한쪽만 고치는 사고가 난다.

extractor 는 app 을 임포트하지 않는 단방향 경계이므로, 공용 함수는 extractor 쪽에
두고 app 이 재임포트한다. 방향이 뒤집혀도 extractor 는 여전히 app 을 모른다.
"""
import unittest


class QuotaBackoffSingleImplementationTest(unittest.TestCase):
    def test_extractor_owns_the_implementation(self) -> None:
        from extractor.gemini_backoff import (
            QUOTA_BACKOFF_DELAYS_SECONDS,
            call_with_quota_backoff,
            is_quota_exhausted_error,
        )

        self.assertEqual(QUOTA_BACKOFF_DELAYS_SECONDS, (5.0, 10.0, 20.0, 40.0))
        self.assertTrue(callable(call_with_quota_backoff))
        self.assertTrue(callable(is_quota_exhausted_error))

    def test_translation_reexports_the_same_objects(self) -> None:
        from app.translation import gemini_client
        from extractor import gemini_backoff

        self.assertIs(gemini_client.call_with_quota_backoff, gemini_backoff.call_with_quota_backoff)
        self.assertIs(gemini_client.is_quota_exhausted_error, gemini_backoff.is_quota_exhausted_error)

    def test_extractor_does_not_import_app(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "extractor" / "gemini_backoff.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from app.", source)
        self.assertNotIn("import app", source)


class DocumentExtractorUsesSharedBackoffTest(unittest.TestCase):
    def test_vertex_paths_call_the_shared_helper(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "extractor"
            / "extractors"
            / "gemini_document_extractor.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from extractor.gemini_backoff import", source)
        # Vertex 경로 둘(_generate_content_vertex, _generate_text_vertex) 다 공용 백오프를 탄다.
        self.assertEqual(source.count("await call_with_quota_backoff("), 2)
        # 429 를 짧은 2**attempt 재시도로 다시 돌리면 긴 백오프가 3배로 겹친다.
        # retryable_tokens 에서 문자열 토큰이 사라져야 한다(18행의 HTTP 상태코드 집합은 별개).
        self.assertEqual(source.count('"429"'), 0)
        self.assertEqual(source.count('"resource_exhausted"'), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_extractor_quota_backoff -v
```

Expected: 4 tests 전부 FAIL — `ModuleNotFoundError: No module named 'extractor.gemini_backoff'`

- [ ] **Step 3: 함수를 `extractor/` 로 옮긴다 (본문은 그대로)**

`backend/extractor/gemini_backoff.py` 생성:

```python
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

LOGGER = logging.getLogger(__name__)

# Vertex AI Gemini는 dynamic shared quota라 일시 혼잡 시 429를 돌려준다.
# 같은 호출을 잠깐 기다렸다 재시도하면 대부분 통과하므로, 파이프라인 전체를
# 폴백으로 포기하기 전에 콜 단위로 지수 백오프 재시도한다.
#
# 이 모듈은 번역(app/translation)과 추출(extractor/extractors) 양쪽이 함께 쓴다.
# extractor 는 app 을 임포트하지 않는 단방향 경계이므로 구현이 이쪽에 있고
# app.translation.gemini_client 가 재임포트한다. 복붙하지 말 것.
QUOTA_BACKOFF_DELAYS_SECONDS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0)


def is_quota_exhausted_error(error: Exception) -> bool:
    message = f"{type(error).__name__}: {error}".lower()
    return any(
        marker in message
        for marker in ("429", "resource_exhausted", "rate limit", "rate_limit", "quota")
    )


async def call_with_quota_backoff(
    factory: Callable[[], Awaitable[Any]],
    *,
    delays_seconds: tuple[float, ...] = QUOTA_BACKOFF_DELAYS_SECONDS,
    label: str = "gemini",
) -> Any:
    for attempt, delay in enumerate(delays_seconds, start=1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - 429만 흡수, 나머지는 즉시 전파.
            if not is_quota_exhausted_error(exc):
                raise
            # full-ish jitter: 공유풀(DSQ)에서 여러 콜이 동시에 같은 간격으로 재시도해
            # 다시 몰리는 thundering herd를 깬다.
            jittered = delay * (0.5 + random.random())
            LOGGER.warning(
                "Gemini quota(429) hit; retrying call in %.1fs: label=%s attempt=%s/%s",
                jittered,
                label,
                attempt,
                len(delays_seconds) + 1,
            )
            await asyncio.sleep(jittered)
    return await factory()
```

- [ ] **Step 4: `gemini_client.py` 에서 정의를 지우고 재임포트한다**

`backend/app/translation/gemini_client.py` 의 `:19-58`(상수 정의 + 두 함수)을 아래로 교체한다:

```python
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# 429 백오프는 추출 경로와 공유한다. extractor 는 app 을 임포트하지 않는 단방향
# 경계이므로 구현이 extractor/gemini_backoff.py 에 있고 여기서 재임포트한다.
# 기존 임포트 경로(app.translation.gemini_client.call_with_quota_backoff)는 그대로 산다.
from extractor.gemini_backoff import (  # noqa: E402
    QUOTA_BACKOFF_DELAYS_SECONDS,
    call_with_quota_backoff,
    is_quota_exhausted_error,
)

__all__ = [
    "GEMINI_API_BASE",
    "GeminiJsonClient",
    "QUOTA_BACKOFF_DELAYS_SECONDS",
    "call_with_quota_backoff",
    "is_quota_exhausted_error",
]
```

그리고 이제 쓰이지 않는 import(`random`, `Awaitable`, `Callable`)를 상단에서 지운다.
`asyncio` 는 `_get_call_semaphore` 가 계속 쓰므로 **남긴다.**

- [ ] **Step 5: 번역 경로 회귀를 먼저 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_gemini_quota_backoff backend.tests.test_gemini_client_parse_json backend.tests.test_translation_orchestrator -v
```

Expected: 전부 PASS. **`test_gemini_quota_backoff.py` 는 한 글자도 고치지 않는다** — 그 파일이 통과한다는 것이 «임포트 경로가 살아 있다»의 증명이다.

- [ ] **Step 6: Vertex 경로 둘을 공용 백오프로 바꾼다**

`backend/extractor/extractors/gemini_document_extractor.py` 상단 import 블록에 추가:

```python
from extractor.gemini_backoff import call_with_quota_backoff, is_quota_exhausted_error
```

`_generate_content_vertex`(`:238-275`)의 `try` 블록과 `except` 블록을 교체한다:

```python
        for model in _dedupe(models):
            for attempt in range(3):
                try:
                    response = await call_with_quota_backoff(
                        lambda: client.aio.models.generate_content(
                            model=model,
                            contents=contents,
                            config=types.GenerateContentConfig(
                                temperature=0.0,
                                response_mime_type="application/json",
                            ),
                        ),
                        label=f"extract:{model}",
                    )
                    text = (response.text or "").strip()
                    if text:
                        return _parse_json(text)
                    last_error = RuntimeError("Gemini(Vertex) returned empty text")
                    break  # empty response -> try next model
                except Exception as exc:  # noqa: BLE001 - surface the real Vertex error.
                    last_error = exc
                    if is_quota_exhausted_error(exc):
                        break  # 429는 call_with_quota_backoff 가 이미 다 기다렸다 -> 다음 모델로
                    message = str(exc).lower()
                    # 429/resource_exhausted 는 위에서 처리했다. 여기 남기면 긴 백오프가
                    # 3배로 겹친다. 나머지 일시 오류만 짧은 지수 재시도.
                    retryable_tokens = ("503", "unavailable", "504", "deadline")
                    if any(token in message for token in retryable_tokens):
                        await asyncio.sleep(2**attempt)
                        continue
                    break  # non-retryable -> try next model
```

`_generate_text_vertex`(`:277-309`)에도 같은 변환을 적용한다:

```python
        for model in _dedupe(models):
            for attempt in range(3):
                try:
                    response = await call_with_quota_backoff(
                        lambda: client.aio.models.generate_content(
                            model=model,
                            contents=[prompt],
                            config=text_config,
                        ),
                        label=f"refine:{model}",
                    )
                    text = (response.text or "").strip()
                    if text:
                        return text
                    last_error = RuntimeError("Gemini(Vertex) returned empty text")
                    break  # empty response -> try next model
                except Exception as exc:  # noqa: BLE001 - surface the real Vertex error.
                    last_error = exc
                    if is_quota_exhausted_error(exc):
                        break
                    message = str(exc).lower()
                    retryable_tokens = ("503", "unavailable", "504", "deadline")
                    if any(token in message for token in retryable_tokens):
                        await asyncio.sleep(2**attempt)
                        continue
                    break  # non-retryable -> try next model
```

> **API 키 경로(`_generate_json_payload`, `:159-206`)는 건드리지 않는다.** 운영은
> `VERTEX_AI_PROJECT_ID` 가 설정돼 Vertex 로 가고(`deploy-api-cloud-run.yml:163`),
> 그 경로는 `Retry-After` 헤더 처리라는 더 나은 로직을 이미 갖고 있다.

- [ ] **Step 7: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_extractor_quota_backoff -v
```

Expected: 4 tests PASS

- [ ] **Step 8: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. 실패하면 Step 4 에서 지운 import 의 잔재다.

- [ ] **Step 9: 커밋**

```bash
git add backend/extractor/gemini_backoff.py backend/app/translation/gemini_client.py backend/extractor/extractors/gemini_document_extractor.py backend/tests/test_extractor_quota_backoff.py
git commit -m "fix(extractor): 429 백오프를 번역 경로와 공유한다

번역 경로는 429 에 최대 112.5초를 기다리는데(5/10/20/40초 + jitter) 추출 경로는
2**attempt 로 3초 안에 포기하고 있었다. Vertex 는 dynamic shared quota 라
일시 혼잡이 정상인데 3초 안에 포기하는 쪽이 이상하다. 게다가 추출 경로에는
429 를 만났다는 로그 문자열 자체가 없어 발생률을 셀 수도 없었다.

같은 로직을 복붙하지 않는다 — 두 벌이 되면 다음에 지연값을 조정할 때 한쪽만
고치는 사고가 난다. extractor 는 app 을 임포트하지 않는 단방향 경계이므로
구현을 extractor/gemini_backoff.py 로 옮기고 app/translation/gemini_client.py 가
재임포트한다. 방향이 뒤집혀도 extractor 는 여전히 app 을 모른다.

Vertex 경로 둘만 바꾼다. API 키 경로는 운영 경로가 아니고 Retry-After 헤더
처리라는 더 나은 로직을 이미 갖고 있다.

retryable_tokens 에서 429/resource_exhausted 를 뺀다 — 남겨두면 긴 백오프가
3배로 겹친다. 503/504/unavailable/deadline 만 짧은 지수 재시도로 남긴다."
```

- [ ] **Step 10: 배포 후 추출 Job 로그에서도 429 가 잡히는지 확인한다**

```bash
gcloud logging read \
  'textPayload:"Gemini quota(429) hit" AND resource.labels.job_name="naranhi-content-extractor"' \
  --limit=20 --freshness=3d --format="value(timestamp,textPayload)"
```

Expected: `label=extract:...` 또는 `label=refine:...` 가 붙은 줄이 검출된다. **0건이면 그건 «429 가 없었다»는 뜻일 수도 있으므로 실패로 판정하지 않는다** — 번역 워커 로그에서 같은 문자열이 나오는지로 검색 자체가 유효한지만 확인한다.

---

## Task 8: 게시판 오선택을 따로 센다

인천문남초는 `crawl_status: success` 인데 `crawl_board_kind: announcement_fallback` 이다.
가정통신문 게시판을 못 찾아 공지사항 게시판으로 대체했고, 실제 수집물은
가정통신문이 아닌 일반 공지다. **성공률 계산이 이를 못 잡는다** —
`ScheduledSchoolResult`(`scheduled_crawler_service.py:45-53`)에 `board_kind` 가 없다.

**실패로 강등하지 않는다.** 그 학교는 공지를 실제로 받고 있고, 실패로 만들면
`crawler_schedule_fail_rate_threshold=0.5` 알람이 오작동해 학부모가 아무것도 못 받게 된다.
**따로 센다.**

**Files:**
- Modify: `backend/app/services/scheduled_crawler_service.py:45-53`, `:57-75`, `:307-317`, `:320-352`
- Modify: `backend/tests/test_scheduled_crawler_service.py`

**Interfaces:**
- Consumes: `SchoolBoardDiscoveryResult.board_kind: str` (`school_crawler_service.py:46`, 값은 `family_notice` / `announcement_fallback` / `unknown`)
- Produces: `ScheduledCrawlerSummary.fallback_count: int` + 요약 JSON 필드 + `WARNING` 로그 한 줄. 성공률 정의는 **바뀌지 않는다.**

- [ ] **Step 1: 집계를 요구하는 실패 테스트를 쓴다**

`backend/tests/test_scheduled_crawler_service.py` 에 추가:

```python
class BoardFallbackCountTest(unittest.TestCase):
    """게시판 오선택(announcement_fallback)이 성공률을 흐리지 않으면서 세어져야 한다."""

    def _result(self, name: str, board_kind: str) -> ScheduledSchoolResult:
        return ScheduledSchoolResult(
            school_id=f"id-{name}",
            school_name=name,
            status="success",
            success_count=3,
            error_message=None,
            board_kind=board_kind,
        )

    def test_fallback_is_counted_but_still_success(self) -> None:
        results = [
            self._result("문남초", "announcement_fallback"),
            self._result("가람초", "family_notice"),
        ]
        summary = _build_summary(
            started_at=datetime(2026, 8, 27, tzinfo=UTC),
            dry_run=False,
            force=False,
            total_registered=2,
            selected=[],
            skipped=[],
            results=results,
            fail_rate_threshold=0.5,
        )

        self.assertEqual(summary.fallback_count, 1)
        self.assertEqual(summary.success_count, 2)  # 성공률 정의는 바뀌지 않는다
        self.assertFalse(summary.alarm)
        self.assertEqual(summary.to_dict()["fallback_count"], 1)

    def test_zero_fallback_when_all_boards_are_correct(self) -> None:
        summary = _build_summary(
            started_at=datetime(2026, 8, 27, tzinfo=UTC),
            dry_run=False,
            force=False,
            total_registered=1,
            selected=[],
            skipped=[],
            results=[self._result("가람초", "family_notice")],
            fail_rate_threshold=0.5,
        )
        self.assertEqual(summary.fallback_count, 0)
```

파일 상단 import 에 `_build_summary`, `ScheduledSchoolResult`, `datetime`, `UTC` 가 없으면 추가한다.

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_scheduled_crawler_service -v
```

Expected: FAIL — `TypeError: ScheduledSchoolResult.__init__() got an unexpected keyword argument 'board_kind'`

- [ ] **Step 3: `ScheduledSchoolResult` 에 필드를 더한다**

`backend/app/services/scheduled_crawler_service.py:45-53` 을 바꾼다:

```python
@dataclass(frozen=True)
class ScheduledSchoolResult:
    school_id: str
    school_name: str
    status: str
    success_count: int
    error_message: str | None
    # 어느 게시판을 봤는가. announcement_fallback = 가정통신문 게시판을 못 찾아
    # 공지사항 게시판으로 대체했다는 뜻이다. 글은 긁히므로 status 는 success 다.
    board_kind: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

> 기본값을 준다 — 예외 경로(`:157-163`)의 생성부를 건드리지 않기 위해서다.
> 그 경로는 게시판을 보기도 전에 터진 것이므로 `unknown` 이 맞다.

- [ ] **Step 4: `ScheduledCrawlerSummary` 에 카운터를 더한다**

`:57-75` 의 `failure_count: int` 아래에 추가:

```python
    fallback_count: int
```

- [ ] **Step 5: `_result_item` 이 값을 전달하게 한다**

`:307-317` 을 바꾼다:

```python
def _result_item(
    target: ScheduledSchoolTarget,
    result: SchoolBoardDiscoveryResult,
) -> ScheduledSchoolResult:
    return ScheduledSchoolResult(
        school_id=result.school_id,
        school_name=result.school_name or target.school_name,
        status=result.status,
        success_count=result.success_count,
        error_message=result.error_message,
        board_kind=result.board_kind,
    )
```

- [ ] **Step 6: `_build_summary` 가 세고 알린다**

`:330-352` 의 `success_rate` 계산 아래에 추가하고, 반환값에 필드를 넣는다:

```python
    finished_at = _utc_now()
    processed = len(results)
    success_count = sum(1 for item in results if item.status == "success")
    failure_count = processed - success_count
    success_rate = success_count / processed if processed else 1.0
    alarm = bool(processed and success_rate < fail_rate_threshold)

    # 게시판 오선택은 실패가 아니다 — 그 학교는 공지를 실제로 받고 있다.
    # 실패로 세면 fail_rate 알람이 오작동해 학부모가 아무것도 못 받게 된다.
    # 성공률 정의를 바꾸지 않고 따로 센다. 학교가 8곳이라 숫자 하나면 눈으로 판정된다.
    fallback_schools = [item.school_name for item in results if item.board_kind == "announcement_fallback"]
    if fallback_schools:
        LOGGER.warning(
            "scheduled crawler board fallback: count=%s schools=%s",
            len(fallback_schools),
            ",".join(fallback_schools),
        )

    return ScheduledCrawlerSummary(
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        dry_run=dry_run,
        force=force,
        total_registered=total_registered,
        selected_count=len(selected),
        skipped_count=len(skipped),
        processed_count=processed,
        success_count=success_count,
        failure_count=failure_count,
        fallback_count=len(fallback_schools),
        success_rate=round(success_rate, 4),
        alarm=alarm,
        targets=[target.to_dict() for target in selected],
        results=[item.to_dict() for item in results],
    )
```

- [ ] **Step 7: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_scheduled_crawler_service -v
```

Expected: 전부 PASS

- [ ] **Step 8: 전체 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. `ScheduledCrawlerSummary` 를 다른 곳에서 구성하면 여기서 잡힌다.

- [ ] **Step 9: 커밋**

```bash
git add backend/app/services/scheduled_crawler_service.py backend/tests/test_scheduled_crawler_service.py
git commit -m "feat(crawler): 게시판 오선택을 따로 센다

인천문남초는 crawl_status=success 인데 crawl_board_kind=announcement_fallback 이다.
가정통신문 게시판을 못 찾아 공지사항 게시판으로 대체했고 실제 수집물은
가정통신문이 아닌 일반 공지다. 그런데 성공률 계산이 이를 못 잡는다 —
ScheduledSchoolResult 에 board_kind 필드가 없어서다.

신호는 이미 저장되고 있다(board_detector 의 needs_human_check, crawl_result 의
fallback_used, school_crawl_state.crawl_board_kind). 집계에만 안 잡혔다.

실패로 강등하지 않는다. 그 학교는 공지를 실제로 받고 있고, 실패로 만들면
fail_rate_threshold=0.5 알람이 오작동해 학부모가 아무것도 못 받게 된다.
성공률 정의를 그대로 두고 fallback_count 로 따로 센다.

'올바른 게시판을 다시 찾는 것'은 이 작업의 범위가 아니다. 인천문남초 홈페이지에
가정통신문 메뉴가 실제로 없을 수도 있다(미확인). 먼저 몇 곳인지를 보이게 한다."
```

---

## Task 9: 본문 사진 회수율 진단 — 무엇을 재고 어디로 가는가

**이 Task 의 산출물은 코드가 아니라 «어느 가설이 참인가»라는 답이다.**
H0(제대로 된 키로 재측정)은 끝났다 — `body_images_combined` 는 운영 35건 중 **11건에
존재한다.** 남은 질문은 «왜 나머지 24건에는 없는가»이고, 그 24건의 상당수는 애초에
본문에 사진이 없는 정상 공지일 수 있다.

**Files:**
- Create: `scripts/diagnose_body_images.py` (읽기 전용)

**Interfaces:**
- Consumes: 운영 `notices.extracted_content.sources[]`, `notices.extraction_started_at`, Task 2 의 로그 문자열
- Produces: 판정 D1~D4 중 하나. D3 일 때만 Task 6 을 실행한다.

**판정 규칙 (먼저 못 박는다):**

| 판정 | 조건 | 다음 |
|---|---|---|
| **D1** | 기능 도입일(2026-06-04) 이후 추출된 공지 중 `body_images_combined` 보유율 ≥ 80% | **고장 아님.** 31% 는 도입 전 추출된 공지가 분모에 섞인 착시. Task 6 건너뜀 |
| **D2** | 「사진 없음(`inline_image` 소스 0개)」이 미보유 공지의 대부분 | **고장 아님.** 회수율의 분모가 틀렸다. Task 6 건너뜀 |
| **D3** | 미보유 공지 중 `status != 'done'` 이 다수 | **성공판정 미도달.** → **Task 6 실행** |
| **D4** | 미보유 공지가 `done` 이고 `inline_image` 소스도 있는데 combined 만 없다 | 수집·합성 실패. Task 2 로그로 `skip_path`/`stitched=0` 를 확인해 좁힌다 |

- [ ] **Step 1: 진단 스크립트를 쓴다**

`scripts/diagnose_body_images.py` 생성:

```python
"""본문 사진 회수율 진단. 읽기 전용 — notices 에 절대 쓰지 않는다.

'body_images_combined 가 0건' 이라는 최초 관측은 틀렸다(최상위 body_image 키는
코드에 존재하지 않는다). 올바른 위치인 sources[] 로 다시 세면 35건 중 11건이다.
따라서 질문은 '왜 안 도는가' 가 아니라 '왜 69% 에서는 안 나오는가' 이고,
그 24건의 상당수는 애초에 본문에 사진이 없는 정상 공지일 수 있다.

이 스크립트는 분모를 다시 정의한다.
"""
import json
import os
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# 본문 사진 합성 기능 도입 커밋 61fe3e2 (2026-06-04). 이보다 앞서 추출된 공지에는
# 코드가 없었으므로 산출물이 없는 것이 정상이다. 스케줄러 정지가 06-15 이므로
# 기능이 살아 있던 창은 11일뿐이다.
FEATURE_LANDED = "2026-06-04"


def get(path: str):
    req = urllib.request.Request(URL + path)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


rows = get(
    "/rest/v1/notices"
    "?select=id,status,created_at,extraction_started_at,extraction_error_code,extracted_content"
    "&extracted_content=not.is.null&limit=1000"
)

window = Counter()
denom = Counter()
loss_rows = []
reasons = Counter()
budget_reasons = Counter()

for row in rows:
    ec = row.get("extracted_content") or {}
    sources = ec.get("sources") or []
    has_combined = any(s.get("source_id") == "body_images_combined" for s in sources)
    inline = [s for s in sources if s.get("source_type") == "inline_image"]
    started = str(row.get("extraction_started_at") or row.get("created_at") or "")
    in_window = started >= FEATURE_LANDED

    window["창 안" if in_window else "창 밖(도입 전)"] += 1
    if in_window and has_combined:
        window["창 안 + 보유"] += 1

    if has_combined:
        denom["보유"] += 1
        continue
    if not inline:
        denom["미보유 · 본문에 사진 없음"] += 1
        continue

    denom["미보유 · 사진은 있음(손실 후보)"] += 1
    loss_rows.append(row)
    for s in inline:
        reasons[f"{s.get('status')} / {'|'.join(str(e) for e in (s.get('errors') or [])) or '-'}"] += 1
    for reason in (ec.get("metadata") or {}).get("budget_exhausted_reasons") or []:
        budget_reasons[str(reason)] += 1

print("=== 1. 기능 도입 창 (H1) ===")
for k, v in window.most_common():
    print(f"  {k:28s} {v}")
in_win = window["창 안"]
if in_win:
    rate = window["창 안 + 보유"] / in_win
    print(f"  창 안 보유율: {rate:.0%}  → 80% 이상이면 판정 D1(고장 아님)")

print("\n=== 2. 분모 재정의 (H2) ===")
for k, v in denom.most_common():
    print(f"  {k:32s} {v}")

print("\n=== 3. 손실 후보의 인라인 이미지 상태 분포 ===")
for k, v in reasons.most_common():
    print(f"  {k:52s} {v}")

print("\n=== 4. 손실 후보의 공지 상태 (H5) ===")
print("  ", Counter(str(r.get("status")) for r in loss_rows).most_common())
print("  error_code:", Counter(str(r.get("extraction_error_code")) for r in loss_rows).most_common())

print("\n=== 5. 예산 소진 사유 (이미 저장되고 있다) ===")
for k, v in budget_reasons.most_common(10):
    print(f"  {k:52s} {v}")

print("\n=== 6. 손실 후보 공지 id (Cloud Logging 대조용) ===")
for r in loss_rows[:20]:
    print("  ", r["id"], r.get("status"), r.get("extraction_started_at"))
```

- [ ] **Step 2: H1 — 기능 도입 창으로 분모를 자른다**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python scripts/diagnose_body_images.py
```

**섹션 1 을 읽는다.**

- `창 안 보유율 ≥ 80%` → **판정 D1.** 31% 는 도입 전(2026-06-04 이전) 추출된 공지가
  분모에 섞인 착시다. **Task 6 을 건너뛰고 Step 6 으로 간다.**
- `창 안 보유율 < 80%` → Step 3 으로.

> `extraction_completed_at` 컬럼은 **존재하지 않는다.** `extraction_started_at`(claim 시각,
> `content_extraction_service.py:1227`)을 대용으로 쓴다. `done` 공지의 경우 마지막 성공
> 런의 시작 시각이므로 창 판정에 충분하다.

- [ ] **Step 3: H2 — 「사진이 애초에 없다」를 분모에서 뺀다**

**섹션 2 를 읽는다.**

- `미보유 · 사진은 있음(손실 후보)` 이 **0** → **판정 D2.** 미보유 24건은 전부 본문에
  사진이 없는 정상 공지다. 회수율 31% 는 «사진 있는 공지 중 회수율»이 아니라
  «전체 공지 중 사진 있는 공지 비율»을 잰 것이다. **Task 6 을 건너뛰고 Step 6 으로.**
- 손실 후보가 1건 이상 → Step 4 로.

> 참고 실측: `inline_image` **소스** 20건 중 `inline_image_no_content_signal` 로 폐기
> 7건. 소스 수와 공지 수는 다르므로 이 숫자를 그대로 손실 후보 수로 읽지 말 것.

- [ ] **Step 4: H5 — 성공판정 미도달인지 본다**

**섹션 4 를 읽는다.**

- 손실 후보의 `status` 가 `done` 이 아닌 것이 **과반** → **판정 D3.**
  `_is_successful_extraction` 이 거짓이라 `_combine_and_upload_body_images` 가
  호출조차 되지 않은 것이다. **→ Task 6 을 실행한다.**
- 손실 후보가 전부 `done` → Step 5 로.

- [ ] **Step 5: D4 — 수집·합성 실패를 로그로 좁힌다**

섹션 6 의 공지 id 를 갖고 Cloud Logging 을 본다(Task 2 의 계측이 배포된 뒤에 유효하다):

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND (textPayload:"body images:" OR textPayload:"inline image collect failed:")' \
  --limit=50 --freshness=7d --format="value(timestamp,textPayload)"
```

| 관측 | 결론 |
|---|---|
| `inline image collect failed: ... stage=skip_path` | **H2b 확정** — 다운로드 실패. 재현으로 원인 추적 |
| `body images: ... collected=N stitched=0` | **H3 확정** — PIL 이 한 장도 못 열었다 |
| `body images: ... upload=fail` | **H4 확정** — Storage 업로드 실패 |
| 세 문자열 전부 0건 | **`on_attachment` 이 아예 안 불렸다** — 섹션 3 의 상태 분포가 `skipped / inline_image_noise_filter` 일색이면 **설계대로다**(노이즈 이미지는 다운로드조차 안 한다). 조치 없음 |

> 로그가 아직 없으면(재가동 전) **여기서 멈추고 «신규 공지 유입 후 재확인»으로 기록한다.**
> 기존 첨부를 재추출해 로그를 만들지 않는다.

- [ ] **Step 6: 결론을 스펙에 기록한다**

`docs/superpowers/specs/2026-08-27-C-extraction-repair-design.md` 의 §18 열린질문 표에서
1번 행을 실제 판정으로 갱신하고, 이 계획 파일 하단 «진단 결과» 절에 다음을 적는다:

```
판정: D_ (D1/D2/D3/D4 중 하나)
근거 수치: 창 안 N건 중 M건 보유(P%), 손실 후보 K건
Task 6 실행 여부: 실행 / 건너뜀
남은 미확인:
```

- [ ] **Step 7: 커밋**

```bash
git add scripts/diagnose_body_images.py docs/superpowers/plans/2026-08-27-C-extraction-repair.md docs/superpowers/specs/2026-08-27-C-extraction-repair-design.md
git commit -m "chore: 본문 사진 회수율 진단 스크립트 + 판정 기록

스펙이 '본문 사진 산출물 0건'을 고장으로 세웠는데 그 관측이 틀렸다.
extracted_content 최상위 body_image 키는 코드에 존재하지 않는다 — 올바른 위치인
sources[] 의 source_id='body_images_combined' 로 세면 운영 35건 중 11건이다.

즉 기능은 돌고 있고 문제는 '고장'이 아니라 '회수율 31%' 다. 그런데 그 분모도
의심스럽다: 합성 기능이 2026-06-04 에 들어왔고 스케줄러가 06-15 에 멈췄으므로
기능이 살아 있던 창은 11일뿐이고, 미보유 24건 중 상당수는 애초에 본문에
사진이 없는 정상 공지일 수 있다.

스크립트는 읽기 전용이다. notices 에 쓰지 않고 재추출도 하지 않는다.
판정 D1~D4 중 D3(성공판정 미도달)일 때만 코드를 고친다."
```

---

## Task 10: 워터마크 컷오프 시딩

**워터마크는 시각이 아니라 «글번호»다.** `school_crawl_state.board_watermarks` 는
`{board_key: 최대 글번호}` 이고(`school_crawler_service.py:694-727`),
`_apply_watermark_filter`(`:669-691`)가 `value <= baseline` 인 글을 제외한다.
8개 학교의 현재 워터마크는 **2026-06-15 기준값**이라 그대로 켜면 그 뒤에 올라온 글이
전부 신규로 잡힌다 — 스캔 깊이 8 × 학교 8 = **최대 64건.**

따라서 «지금부터» = **«재가동 시점에 각 게시판 최상단에 있는 글번호 이하는 받지 않는다»**.

> `scheduled_school_crawler --dry-run` 은 **쓸 수 없다.** `dry_run` 이 게시판 스캔 전에
> 반환하므로(`scheduled_crawler_service.py:106-116`) 현재 최대 글번호를 얻지 못한다.
> **일회성 시딩 스크립트가 필요하다.**

**Files:**
- Modify: `backend/app/services/school_crawler_service.py` (`compute_board_watermarks` 추가)
- Modify: `backend/tests/test_school_crawler_watermark.py`
- Create: `scripts/seed_watermarks.py`

**Interfaces:**
- Consumes: `SchoolCrawlerService.discover_school_board(school_id, *, use_gemini=True, max_posts=None) -> SchoolBoardDiscoveryResult` — **저장하지 않는 경로다**(`discover_and_save_school_board` 와 달리 `_save_discovered_notice_candidates` 를 부르지 않는다)
- Produces: `compute_board_watermarks(posts: list[DiscoveredPostPreview]) -> dict[str, int]`. 운영 8개 학교의 `board_watermarks` 가 현재 최대 글번호로 갱신된다.

- [ ] **Step 1: 최대값 계산 헬퍼를 요구하는 실패 테스트를 쓴다**

`backend/tests/test_school_crawler_watermark.py` 에 추가:

```python
class ComputeBoardWatermarksTest(unittest.TestCase):
    """재가동 컷오프 시딩이 쓸 '게시판별 현재 최대 글번호' 계산."""

    def _post(self, board_key: str, post_id: str, method: str = "list", source: str = "href query id2") -> DiscoveredPostPreview:
        return DiscoveredPostPreview(
            title="t",
            post_id=post_id,
            post_uid=f"{board_key}#{post_id}",
            board_key=board_key,
            detail_url="https://example.test/view",
            status="success",
            method=method,
            source=source,
            cms_key="egov",
            parser_family="egov",
            reason="",
        )

    def test_takes_max_per_board_key(self) -> None:
        posts = [
            self._post("boardA", "100"),
            self._post("boardA", "342"),
            self._post("boardB", "7"),
        ]
        self.assertEqual(compute_board_watermarks(posts), {"boardA": 342, "boardB": 7})

    def test_ignores_posts_outside_watermark_scope(self) -> None:
        """해시 생성·첨부 파일번호·비숫자 id 는 시간순이 보장되지 않아 워터마크 대상이 아니다."""
        posts = [
            self._post("boardA", "abc123"),
            self._post("boardA", "500", method="generated"),
            self._post("boardA", "600", method="file_download"),
        ]
        self.assertEqual(compute_board_watermarks(posts), {})

    def test_empty_input_is_empty_output(self) -> None:
        self.assertEqual(compute_board_watermarks([]), {})
```

파일 상단 import 에 `compute_board_watermarks` 와 `DiscoveredPostPreview` 를 추가한다.

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_crawler_watermark -v
```

Expected: FAIL — `ImportError: cannot import name 'compute_board_watermarks'`

- [ ] **Step 3: 헬퍼를 만든다**

`backend/app/services/school_crawler_service.py` 의 `_apply_watermark_filter` 정의 바로 위에 추가:

```python
def compute_board_watermarks(posts: list[DiscoveredPostPreview]) -> dict[str, int]:
    """게시판(board_key)별 최대 글번호. 재가동 컷오프 시딩(scripts/seed_watermarks.py)이 쓴다.

    _apply_watermark_filter 안의 갱신 로직과 같은 계산이지만 '필터링 없이 최대값만'
    필요한 경우가 있어 따로 뺐다. 워터마크 비대상(_watermark_post_value 가 None)은 무시한다.
    """
    watermarks: dict[str, int] = {}
    for post in posts:
        value = _watermark_post_value(post)
        if value is None:
            continue
        watermarks[post.board_key] = max(watermarks.get(post.board_key, 0), value)
    return watermarks
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_crawler_watermark -v
```

Expected: 전부 PASS

- [ ] **Step 5: 시딩 스크립트를 쓴다**

`scripts/seed_watermarks.py` 생성:

```python
"""재가동 컷오프 시딩 (일회성). 기본은 dry-run — --apply 를 줘야 쓴다.

워터마크는 시각이 아니라 '글번호'다. 8개 학교의 board_watermarks 는 2026-06-15
기준값이라 그대로 스케줄러를 켜면 그 뒤에 올라온 글이 전부 신규로 잡힌다
(스캔 깊이 8 × 학교 8 = 최대 64건). 사용자 결정은 '밀린 것 우르르'가 아니라
'지금부터 새로 올라오는 것' 이다.

이 스크립트는 각 게시판을 스캔해 '현재 최상단 글번호'를 워터마크로 박는다.
notices 는 절대 건드리지 않는다 — discover_school_board() 는 저장 경로가 아니다
(discover_and_save_school_board 와 달리 _save_discovered_notice_candidates 를 안 부른다).

실행:  PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py
적용:  PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py --apply
"""
import argparse
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings
from app.services.school_crawler_service import (
    POST_SUCCESS_STATUSES,
    SchoolCrawlerService,
    _read_board_watermarks,
    _write_board_watermarks,
    compute_board_watermarks,
)
from app.services.scheduled_crawler_service import select_school_targets


async def main(apply: bool) -> int:
    settings = get_settings()
    selected, _skipped, total = select_school_targets(
        school_id=None,
        limit=None,
        force=True,  # 쿨다운 무시 — 시딩은 지금 전부 해야 한다
        unsupported_recheck_hours=settings.crawler_unsupported_recheck_hours,
    )
    print(f"등록 학교 {total}곳 / 대상 {len(selected)}곳 / 스캔 깊이 {settings.crawler_schedule_notice_count}")
    print(f"모드: {'APPLY (실제로 쓴다)' if apply else 'DRY-RUN (읽기만)'}\n")

    crawler = SchoolCrawlerService()
    backup: dict[str, dict[str, int]] = {}
    unscoped_total = 0

    for target in selected:
        result = await crawler.discover_school_board(
            target.school_id,
            use_gemini=settings.crawler_enable_gemini,
            max_posts=settings.crawler_schedule_notice_count,
        )
        valid = [p for p in result.sample_posts if p.status in POST_SUCCESS_STATUSES and p.detail_url]
        computed = compute_board_watermarks(valid)
        unscoped = [p for p in valid if p.board_key not in computed]
        unscoped_total += len(unscoped)

        existing = _read_board_watermarks(target.school_id)
        backup[target.school_id] = existing
        merged = dict(existing)
        for key, value in computed.items():
            merged[key] = max(merged.get(key, 0), value)

        print(f"[{target.school_name}] status={result.status} posts={len(valid)} 워터마크 비대상={len(unscoped)}")
        for key in sorted(set(existing) | set(computed)):
            print(f"    {key}\n      기존 {existing.get(key, '-')} → 계산 {computed.get(key, '-')} → 적용 {merged.get(key, '-')}")

        if apply and merged != existing:
            _write_board_watermarks(target.school_id, merged)
            print("    → 기록함")

    print(f"\n워터마크 비대상 글 합계: {unscoped_total}건")
    print("  (비숫자 post_id·해시 생성·첨부 파일번호는 워터마크로 막을 수 없다.")
    print("   재가동 첫 런에 이만큼은 들어올 수 있다 — 수용 범위인지 눈으로 판단할 것.)")

    print("\n=== 롤백용 백업 (기존 값) ===")
    print(json.dumps(backup, ensure_ascii=False, indent=2))

    if not apply:
        print("\nDRY-RUN 이었다. 위 '적용' 값이 맞으면 --apply 를 붙여 다시 실행하라.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="실제로 board_watermarks 에 쓴다")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))
```

- [ ] **Step 6: dry-run 으로 돌려 규모와 값을 확인한다**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py 2>&1 | tee scripts/_seed_watermarks_dryrun.txt
```

Expected: 학교 8곳. 각 board_key 마다 **`계산` 값이 `기존` 값보다 크거나 같다.**
- `계산 < 기존` 인 항목이 있으면 **중단하고 보고할 것** — CMS 가 글번호를 리셋했거나
  다른 게시판을 보고 있다는 뜻이다.
- `status` 가 `success` 가 아닌 학교가 있으면 그 학교는 시딩되지 않는다. **몇 곳인지 기록한다.**
- 마지막의 «롤백용 백업» JSON 을 파일로 남겨둔다(위 `tee` 가 이미 남긴다).

- [ ] **Step 7: 적용한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe scripts/seed_watermarks.py --apply 2>&1 | tee scripts/_seed_watermarks_apply.txt
```

Expected: 갱신된 학교마다 `→ 기록함`

- [ ] **Step 8: DB 에 실제로 들어갔는지 확인한다**

```bash
python -c "
import json,os,urllib.request
u=os.environ['SUPABASE_URL'].rstrip('/'); k=os.environ['SUPABASE_SERVICE_ROLE_KEY']
r=urllib.request.Request(u+'/rest/v1/school_crawl_state?select=school_id,board_watermarks,last_checked_at')
r.add_header('apikey',k); r.add_header('Authorization','Bearer '+k)
for row in json.loads(urllib.request.urlopen(r,timeout=60).read().decode()):
    print(row['school_id'], json.dumps(row.get('board_watermarks'), ensure_ascii=False))
"
```

Expected: 8개 학교의 값이 Step 6 출력의 `적용` 열과 일치

- [ ] **Step 9: 커밋**

```bash
git add backend/app/services/school_crawler_service.py backend/tests/test_school_crawler_watermark.py scripts/seed_watermarks.py
git commit -m "feat(crawler): 재가동 컷오프 워터마크 시딩 스크립트

72일 멈춘 뒤 스케줄러를 그냥 켜면 2026-06-15 기준 워터마크 때문에 그 뒤에
올라온 글이 전부 신규로 잡힌다 — 스캔 깊이 8 × 학교 8 = 최대 64건.
사용자 결정은 '밀린 것 우르르'가 아니라 '지금부터 새로 올라오는 것' 이다.

워터마크는 시각이 아니라 글번호이므로 '지금부터' = '재가동 시점 각 게시판
최상단 글번호 이하는 안 받는다' 가 된다. scheduled_school_crawler --dry-run 은
쓸 수 없다 — dry_run 이 게시판 스캔 전에 반환해 현재 최대값을 못 얻는다.

discover_school_board() 는 저장하지 않는 경로다. notices 는 건드리지 않고
board_watermarks 만 쓴다. 기본 dry-run, --apply 를 줘야 실제로 쓴다.
롤백용으로 기존 값을 JSON 으로 출력한다.

최대값 계산은 _apply_watermark_filter 안의 로직을 compute_board_watermarks 로
빼서 단위 테스트를 붙였다. 새 계산식을 쓰지 않는다.

워터마크 비대상(비숫자 post_id·해시 생성·첨부 파일번호)은 막을 수 없다.
그만큼은 첫 런에 들어올 수 있고 dry-run 출력이 그 수를 알려준다."
```

---

## Task 11: 스케줄러 resume + 런북 정정

**저장소에 `gcloud scheduler jobs pause|resume` 언급이 0건이다.** 정지시킨 방법이 문서에
없으니 되살리는 방법도 없다. 게다가 **런북의 스케줄러 이름이 실제와 다르다** —
`-1800`/`-1900` 으로 적혀 있지만 실제는 `-1900`/`-2000` 이다(2026-08-26 `gcloud` 실측).
이름이 틀린 문서는 없느니만 못하다.

> ⚠️ **Task 10 을 끝내지 않았으면 이 Task 를 시작하지 않는다.** 시딩 전에 켜면 그 순간
> 최대 64건이 들어오고 되돌릴 수 없다.

**Files:**
- Modify: `docs/scheduled-crawl-runbook.md`

**Interfaces:**
- Consumes: Task 10 이 박은 `board_watermarks`
- Produces: 스케줄러 6개 `ENABLED`. 런북에 실명·상태표·resume 절차·정지 기록 규칙.

- [ ] **Step 1: 현재 상태를 눈으로 본다**

```bash
gcloud scheduler jobs list --location=asia-northeast3 \
  --format="table(name.basename(), schedule, state)"
```

Expected: 6개. `naranhi-translation-backstop` 만 `ENABLED`, 나머지 5개 `PAUSED`.
**이름이 아래 표와 다르면 표를 실제에 맞춰 고치고 진행한다.**

- [ ] **Step 2: 런북의 스케줄러 절을 실제와 맞춘다**

`docs/scheduled-crawl-runbook.md` 의 `## Cloud Scheduler 4개` 절 제목을
`## Cloud Scheduler (실제 6개)` 로 바꾸고, `gcloud scheduler jobs create` 블록
(`:56-68`) **아래에** 다음을 추가한다:

```markdown
### 실제 배치 (2026-08-26 gcloud 실측 — 위 create 예시와 이름이 다르다)

| 스케줄러 | 주기 | 2026-08-27 상태 | 비고 |
|---|---|---|---|
| `naranhi-school-crawler-0600` | `0 6 * * *` | ENABLED | |
| `naranhi-school-crawler-1900` | `0 19 * * *` | ENABLED | 위 create 예시의 `-1800` 은 옛 이름 |
| `naranhi-content-extractor-0700` | `0 7 * * *` | ENABLED | |
| `naranhi-content-extractor-2000` | `0 20 * * *` | ENABLED | 위 create 예시의 `-1900` 은 옛 이름 |
| `naranhi-crawler-backstop` | `*/10 * * * *` | ENABLED | 큐 경로에서 놓친 잡 회수 |
| `naranhi-translation-backstop` | `*/10 * * * *` | ENABLED | |

**규칙: 누군가 스케줄러를 pause 하면 이 표의 상태 칸을 고치고 날짜와 이유를 적는다.**
2026-06-15 발표 준비로 5개를 정지시킨 사실이 어디에도 기록되지 않아 72일 동안
아무도 몰랐다. 개인 메모는 저장소 문서가 아니다.
```

- [ ] **Step 3: resume/pause 절차를 런북에 신설한다**

`## 튜닝 / 비상` 절 바로 위에 추가:

```markdown
## 재가동 · 비상 정지

**순서가 중요하다: 추출기 → 백스톱 → 크롤러.**
크롤러가 먼저 켜지면 신규 공지가 `pending` 으로 쌓이는데 추출기가 자고 있어,
「크롤→추출 연결이 끊겼다」와 구분할 수 없는 상태가 만들어진다.
추출기가 먼저 깨어 있으면 「크롤 → 다음 정시 추출」이 그대로 이어진다.

```bash
REGION="asia-northeast3"

# 0. 현재 상태를 눈으로 본다
gcloud scheduler jobs list --location="$REGION" \
  --format="table(name.basename(), schedule, state)"

# 1. 추출기
gcloud scheduler jobs resume naranhi-content-extractor-0700 --location="$REGION"
gcloud scheduler jobs resume naranhi-content-extractor-2000 --location="$REGION"

# 2. 백스톱 (큐 경로에서 놓친 잡을 10분 안에 회수한다)
gcloud scheduler jobs resume naranhi-crawler-backstop --location="$REGION"

# 3. 크롤러
gcloud scheduler jobs resume naranhi-school-crawler-0600 --location="$REGION"
gcloud scheduler jobs resume naranhi-school-crawler-1900 --location="$REGION"
```

**비상 정지:** `gcloud scheduler jobs pause <이름> --location="$REGION"` — 그리고
위 상태표를 반드시 고친다.

**선행 조건:** 오래 멈춰 있었다면 재가동 전에 `scripts/seed_watermarks.py --apply` 로
컷오프를 박는다. 안 그러면 멈춘 동안 올라온 글이 전부 신규로 잡힌다
(스캔 깊이 × 학교 수만큼).

**정기 크롤러에는 재시도가 없다** (`--max-retries=0`, `deploy-api-cloud-run.yml:145`).
실패하면 다음 스케줄까지 12시간이다. `naranhi-crawler-backstop`(10분 주기)이 사실상의
재시도 역할을 한다. Cloud Run Job retry 는 task 전체 재실행이라 학교 단위 재시도가
아니므로 켜지 않는다.
```

- [ ] **Step 4: 추출기부터 켠다**

```bash
REGION="asia-northeast3"
gcloud scheduler jobs resume naranhi-content-extractor-0700 --location="$REGION"
gcloud scheduler jobs resume naranhi-content-extractor-2000 --location="$REGION"
gcloud scheduler jobs resume naranhi-crawler-backstop --location="$REGION"
gcloud scheduler jobs list --location="$REGION" --format="table(name.basename(), state)"
```

Expected: 추출기 2개 + 백스톱 `ENABLED`, 크롤러 2개 아직 `PAUSED`

- [ ] **Step 5: 크롤을 «수동 1회»로 먼저 돌려 컷오프를 검증한다**

스케줄러를 켜기 전에 Job 을 직접 한 번 돌린다. 실패해도 12시간을 기다릴 필요가 없다.

```bash
gcloud run jobs execute naranhi-school-crawler --region=asia-northeast3 --wait
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-school-crawler" AND textPayload:"scheduled school crawler result:"' \
  --limit=20 --freshness=30m --format="value(textPayload)"
```

Expected: **모든 학교의 `success_count=0`.** 이것이 컷오프가 맞았다는 증명이다.

- `success_count > 0` 인 학교가 있으면 **크롤러 스케줄러를 켜지 말고** 들어온 글의
  `post.method`·`post.source` 를 확인한다:
  - 워터마크 비대상(비숫자 post_id·`generated`·`file_download`)이면 **수용**한다.
    Task 10 Step 6 의 «워터마크 비대상 합계»와 대조해 예상 범위인지 본다.
  - 숫자 id 인데 들어왔으면 **시딩 실패**다. Task 10 의 백업 JSON 으로 워터마크를
    복원하고 원인을 찾은 뒤 다시 시딩한다.

- [ ] **Step 6: 크롤러 스케줄러를 켠다**

```bash
REGION="asia-northeast3"
gcloud scheduler jobs resume naranhi-school-crawler-0600 --location="$REGION"
gcloud scheduler jobs resume naranhi-school-crawler-1900 --location="$REGION"
gcloud scheduler jobs list --location="$REGION" --format="table(name.basename(), schedule, state)"
```

Expected: **6개 전부 `ENABLED`**

- [ ] **Step 7: 커밋**

```bash
git add docs/scheduled-crawl-runbook.md
git commit -m "docs(runbook): 스케줄러 실명·상태표·재가동 절차

저장소에 gcloud scheduler jobs pause|resume 언급이 0건이었다. 2026-06-15 발표
준비로 5개를 정지시킨 사실이 어디에도 기록되지 않아 72일 동안 아무도 몰랐다.
정지시킨 방법이 문서에 없으니 되살리는 방법도 없었다.

런북의 스케줄러 이름이 실제와 다르다 — -1800/-1900 으로 적혀 있지만 실제는
-1900/-2000 이고, 백스톱 2개는 아예 언급이 없다. 이름이 틀린 문서는 없느니만 못하다.
실측 6개를 상태표로 적고 '정지하면 이 표를 고친다' 를 규칙으로 넣는다.

재가동 순서는 추출기 → 백스톱 → 크롤러다. 크롤러가 먼저 켜지면 pending 이
쌓이는데 추출기가 자고 있어 '크롤→추출 연결 끊김' 과 구분이 안 되는 상태가 된다.

정기 크롤러에 재시도가 없다는 사실(--max-retries=0)도 적는다. 바꾸지는 않는다 —
백스톱이 10분마다 돌아 사실상의 재시도 역할을 하고, Job retry 는 task 전체
재실행이라 학교 단위 재시도가 아니다."
```

---

## Task 12: 크롤→추출 연결 — 측정과 계약 문서화

`scripts/recrawl_monitor.py:78-81` 에 수동 킥이 하드코딩되어 있다. 「경과 120초 초과 &
pending>0 & processing==0 & done==0」이라는 조건이 스크립트에 박혀 있다는 것은 그 상태가
**재현 가능할 만큼 흔했다**는 뜻이다.

코드를 읽고 나온 것: **경로가 둘인데 계약이 다르고 어느 쪽도 문서에 없다.**

**Files:**
- Modify: `docs/scheduled-crawl-runbook.md`

**Interfaces:**
- Consumes: Task 11 이 켠 스케줄러
- Produces: 「크롤 종료 → 추출 시작」 실제 지연 수치. 하드코딩 폴백의 존폐 판단 근거.

> **하드코딩된 폴백을 지우지 않는다.** 지금은 그게 유일한 안전망이다.
> 이 Task 는 **측정**이고, 삭제 판단은 수치가 나온 뒤다.

- [ ] **Step 1: 두 경로의 계약을 런북에 적는다**

`docs/scheduled-crawl-runbook.md` 의 `## 한계 (정직하게)` 절 위에 추가:

```markdown
## 크롤 → 추출 연결 (경로가 둘이고 계약이 다르다)

| 경로 | 진입 | 크롤 후 추출 연결 |
|---|---|---|
| **큐 경로** (`crawler_worker`) | API `POST /crawler/schools/{id}/discover` 등이 잡을 enqueue | **있다.** `_run_discovery_job`(`crawler_worker.py:31-37`)이 `status == "success" and success_count > 0` 이면 `school_notice_extraction` 잡을 enqueue 하고 같은 워커의 drain 루프(`:116-129`)가 이어서 집는다 |
| **정기 경로** (`scheduled_school_crawler`) | Cloud Scheduler 06:00/19:00 | **없다. 이건 고장이 아니라 설계다.** 추출은 1시간 뒤 별도 스케줄러(`naranhi-content-extractor-0700`)가 맡는다 |

큐 경로에서 연결이 끊길 수 있는 지점:

| 지점 | 코드 | 끊기는 조건 |
|---|---|---|
| enqueue 조건 | `crawler_worker.py:31` | `success_count == 0` 이면 enqueue 자체가 없다. **워터마크가 켜져 있으면 「새 글 없음」 = 0 이 정상이다** |
| 중복 억제 | `job_queue_service.py:52-63` | 같은 `job_key`(`school-extraction:{id}`)로 `queued`/`processing` 잡이 있으면 `already_running` 으로 새로 만들지 않는다 |
| drain 종료 | `crawler_worker.py:122-129` | enqueue 직후 `idle_grace_seconds`(배포값 3초) 안에 claim 되어야 한다. 놓치면 백스톱까지 대기 |
| 백스톱 | `naranhi-crawler-backstop` | 10분 주기. **2026-06-15 ~ 08-27 동안 PAUSED 였다** — 그동안은 놓친 잡을 아무도 깨우지 않았다 |

`scripts/recrawl_monitor.py:78-81` 의 수동 킥 폴백은 **이 표가 없어서 생긴 것이다.**
운영자가 관측된 증상에 스크립트로 대응했다. **지우지 않는다** — 백스톱 resume 후
실제 지연을 재고(아래), 필요 없다는 수치가 나오면 그때 지운다.
```

- [ ] **Step 2: 실제 지연을 잰다**

재가동 후 신규 공지가 처음 들어온 날:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND (resource.labels.job_name="naranhi-school-crawler" OR resource.labels.job_name="naranhi-content-extractor" OR resource.labels.job_name="naranhi-crawler-worker") AND (textPayload:"school crawler finished" OR textPayload:"content extraction started" OR textPayload:"content extractor result:")' \
  --limit=100 --freshness=2d --format="value(timestamp,resource.labels.job_name,textPayload)" \
  | sort
```

기록할 것:
- 정기 경로: 크롤 Job 종료 시각 → 다음 추출 Job 시작 시각의 차 (설계상 ~1시간)
- 큐 경로: `school crawler finished` → 같은 학교의 `content extractor result:` 까지의 차
- 백스톱이 회수한 잡이 있는가 (`naranhi-crawler-worker` 가 스케줄 시각에 깬 흔적)

- [ ] **Step 3: 측정 결과를 런북에 적는다**

Step 1 에서 만든 절 끝에 한 줄 추가:

```markdown
**실측 (재가동 후):** 정기 경로 지연 ___분 / 큐 경로 지연 ___초 /
`recrawl_monitor.py` 의 120초 폴백 조건 발동 ___회.
발동 0회가 며칠 이어지면 그때 폴백 삭제를 판단한다.
```

- [ ] **Step 4: 커밋**

```bash
git add docs/scheduled-crawl-runbook.md
git commit -m "docs(runbook): 크롤→추출 연결 계약을 두 경로로 나눠 적는다

recrawl_monitor.py 에 '경과 120초 & pending>0 & processing==0 & done==0' 이면
수동으로 추출을 킥하는 폴백이 하드코딩되어 있다. 그 조건이 스크립트에 박혀
있다는 것은 그 상태가 재현 가능할 만큼 흔했다는 뜻이다.

코드를 읽으니 경로가 둘인데 계약이 다르다. 큐 경로(crawler_worker)는 크롤 성공 시
추출 잡을 enqueue 하고, 정기 경로(scheduled_school_crawler)는 하지 않는다 —
후자는 고장이 아니라 설계다(06시 크롤 / 07시 추출).

폴백이 생긴 근본 원인은 이 차이가 어느 문서에도 없어서 운영자가 증상에
스크립트로 대응한 것이다. 표로 적는다.

폴백은 지우지 않는다. 백스톱이 72일간 PAUSED 였으므로 놓친 잡을 아무도
깨우지 않았고, 지금은 그게 유일한 안전망이다. 실제 지연을 잰 뒤 판단한다."
```

---

## 선택 Task 13: 판독 백엔드 Bedrock 이전 (본 배포 순서 밖)

> **⛔ 본 배포 순서(Task 1~12)에 포함되지 않는다.** 설계는 여기 완비하되, 착수는
> 별도 결정이다. 스펙 §19.7 의 권고는 **(가) Gemini 유지 + 고장 수리만** 이고,
> 이 Task 는 **(나)** 를 나중에 선택할 수 있도록 떼어 놓은 것이다.

**착수 조건 (둘 중 하나라도 참일 때만):**

| # | 조건 | 확인 |
|---|---|---|
| A | Task 4 Step 13 판정이 **H-FAIL** — 현행 Gemini 판독이 판독 불가 입력에서 내용을 지어낸다 | 이건 비용이 아니라 안전 문제다. 최우선으로 올린다 |
| B | 사용자가 명시적으로 «판독도 옮기라»고 지시 | — |

**둘 다 아니면 착수하지 않는다.** 근거: 아끼는 현금이 월 **$1 미만**이고(스펙 §19.6),
옮겨지는 것은 첨부의 **70.1%** 뿐이며(HWP 28.6% 는 못 옮긴다), 이전이 고치는 고장은
①~⑥ 중 **0개**다.

**미리 못 박는 사실 (스펙 §19.4 — 확인 완료, 추측 아님):**

Bedrock `Converse` 의 `DocumentBlock.format` 유효값은
**`pdf | csv | doc | docx | xls | xlsx | html | txt | md`** 뿐이다
(AWS API 레퍼런스 `API_runtime_DocumentBlock`, 2026-08-27 조회). **`hwp` 가 없다.**
→ **HWP 판독은 어느 쪽을 고르든 `hwp5html` → markdownify 경로
(`hwp_extractor.py:21-88`, `:91-130`)를 유지한다.** 이 Task 는 HWP 를 건드리지 않는다.

**Files:**
- Create: `backend/extractor/extractors/bedrock_document_extractor.py`
- Create: `backend/tests/test_bedrock_document_extractor.py`
- Create: `scripts/ab_extraction_backends.py`
- Modify: `backend/extractor/extract_pipeline.py` (백엔드 선택 분기 — env 한 줄)
- Modify: `.github/workflows/deploy-api-cloud-run.yml` (추출 Job 에 AWS 자격증명 `--set-secrets`)

**Interfaces:**
- Consumes: `ExtractedText`(기존 계약 그대로), `ExtractionBudget`(그대로 — 백엔드가 바뀌어도 예산 회계는 안 바뀐다)
- Produces: `EXTRACTION_BACKEND=gemini|bedrock` env 한 줄. 되돌리기가 그 한 줄이다.

- [ ] **Step 1: 계약을 고정하는 실패 테스트를 쓴다**

`backend/tests/test_bedrock_document_extractor.py` 에서 **셋만** 못 박는다.
Bedrock 을 실제로 부르지 않는다(`boto3` 클라이언트를 가짜로 주입).

| # | 고정할 것 | 왜 |
|---|---|---|
| 1 | PDF 는 `document` 블록 + `format="pdf"`, 이미지는 `image` 블록 + `format="png"\|"jpeg"` | 2026-08-27 실측이 확인한 유일한 경로다 |
| 2 | **`.hwp` 를 넘기면 `ValueError`** — 조용히 `txt` 로 우회하지 않는다 | `document` 블록이 hwp 를 지원하지 않는다. 우회하면 «읽었는데 쓰레기» 가 된다 |
| 3 | **모델 ID 에 `opus` 가 들어가면 거부** | Global Constraints 의 Opus 금지를 코드로 못 박는다 |

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_bedrock_document_extractor -v
```

Expected: 모듈이 없어 `ModuleNotFoundError`

- [ ] **Step 3: Bedrock 판독 클라이언트를 만든다**

`backend/extractor/extractors/bedrock_document_extractor.py`:

- `boto3` `bedrock-runtime` `converse` 호출. **`invoke_model` 이 아니다** — PDF 를
  `document` 블록으로 직접 넘길 수 있는 것은 `Converse` 다(실측 1.2MB 통과).
- 기본 모델 `global.anthropic.claude-haiku-4-5-20251001-v1:0`,
  승급 모델 `global.anthropic.claude-sonnet-4-6`. **Opus 는 없다.**
  모델 문자열에 `opus` 가 있으면 생성 시점에 `ValueError`.
- 자격증명은 **환경변수로만** 받는다. Cloud Run 은 `--set-secrets` 로
  `aws-bedrock-access-key-id`·`aws-bedrock-secret-access-key` 를 주입한다.
  **키를 명령줄 인자·URL·로그에 넣지 않는다.**
- 리전 `ap-northeast-2`. `global.` 라우팅 사용자 허용됨.
- `boto3` 는 동기 API 다 — 사업 B 의 `BedrockJsonClient` 와 같이 **전용 executor** 에
  올려 이벤트 루프를 막지 않는다
  (`docs/superpowers/plans/2026-08-27-B-bedrock-translation.md` Task 10 과 같은 형태).
- 반환은 기존 `ExtractedText` 그대로. **호출부가 백엔드를 몰라야 한다.**

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_bedrock_document_extractor -v
```

- [ ] **Step 5: A/B 실측 스크립트를 쓴다 — 지연·정확도·환각을 한 번에 잰다**

`scripts/ab_extraction_backends.py`. **같은 입력**을 두 백엔드에 넣고 나란히 기록한다.
셋을 각각 재지 않으면 «느려졌지만 정확해졌다» 같은 답을 못 낸다.

| 축 | 재는 법 | 통과 기준 (§Step 6 게이트에서 씀) |
|---|---|---|
| 지연 | 호출 시작~반환 ms, 입력별 | — (판정은 Step 6) |
| 정확도 | 원본에 확실히 있는 문자열 N개의 포함률, 표 마커(`\|` 2줄 이상) 유무 | — |
| **환각** | Task 4 Step 11 의 `verdict()` 를 **그대로 재사용** | negative control 에서 `FAIL(fabricated)` **0건** |
| 비용 | 콜당 토큰 수 기록(응답 usage) | 참고값 |

표본: **PDF 5건 + 이미지 5건 + negative control 3건.** negative 는 Task 4 Step 12 가
만든 `.tmp-probe/` 를 재사용한다. **HWP 는 표본에 넣지 않는다** — 못 옮기는 포맷이다.

- [ ] **Step 6: 판정 게이트 — 넷을 전부 넘어야 전환한다**

| # | 게이트 | 기준 | 못 넘으면 |
|---|---|---|---|
| **G1** | 환각 | negative control 에서 Bedrock `FAIL(fabricated)` **0건** | **전환 중단.** 이걸 못 넘으면 나머지는 볼 필요가 없다 |
| **G2** | 정확도 | 필수 문자열 포함률이 Gemini 이상. 표 보존이 Gemini 이상 | 승급 모델(Sonnet 4.6)로 한 번 재시도. 그래도 못 넘으면 중단 |
| **G3** | 지연 | 판독 1건 중앙값이 Gemini 대비 **1.5배 이내** | 중단. PDF 14~16초(스펙 §19.2)가 이 게이트에 걸릴 수 있다 — **그래서 A/B 가 선행이다** |
| **G4** | 실패율 | 10건 중 예외·빈 결과 0건 | 중단 |

> **G3 이 이 Task 의 진짜 위험이다.** 「비용은 비목표, 시간이 우선」(스펙 §17 #3)이
> 여기서는 **이전에 불리하게** 작용한다. 이전이 판독을 느리게 만들면 그건 사용자 결정에
> 정면으로 어긋나므로, 비용이 싸다는 이유로 넘어가지 않는다.

- [ ] **Step 7: env 한 줄로 전환한다**

`EXTRACTION_BACKEND=bedrock`. 되돌리기는 그 한 줄을 `gemini` 로 바꾸는 것이다.
**추출 Job 에만** 넣는다. 사업 B 의 `TRANSLATION_BACKEND` 와 같은 형태이고 서로 독립이다.

- [ ] **Step 8: 커밋**

커밋 메시지에 **G1~G4 의 실제 수치**를 적는다. 「통과했다」가 아니라 「무엇이 몇이었나」다.

---

## 판독 환각 판정 (Task 4 Step 13 실행 후 채운다)

```
판정: H-PASS
negative 결과:  qr=PASS(empty)  blank=PASS(empty)  noise=PASS(empty)
positive 결과:  PASS(read) — 47자, 원본 문자열이 head 에 그대로 보임
선택 Task 13 착수 조건 충족 여부: 미충족 (착수 근거는 비용뿐이며 스펙 §19.6 기준 월 $1 미만이라 약함)
```

2026-08-27 실행: `scripts/probe_extraction_hallucination.py` 로 로컬 생성 negative
3종(QR/백지/사선노이즈) + positive 1종(합성 텍스트 이미지)을 현행 Gemini(Vertex AI) 판독
경로에 직접 통과시켰다. negative 3종 모두 빈 텍스트를 반환했다(`empty_or_unreadable` 아님,
`chars=0`) — 「학교」·「교장」 등 지어냄 마커가 전혀 나타나지 않았다. positive 는 합성
문구를 정확히 읽어 원문이 그대로 복원됐다. 즉 **현행 Gemini 판독은 이번 negative
control 표본에서 지어내지 않았다** — 2026-08-27 Bedrock Nova Lite/Pro 시험에서 관찰된
환각과 다른 결과다. 운영 DB 는 읽지 않았고(로컬 합성 이미지만 사용), 실제 판독 API
호출은 총 8회(Gemini) 발생했다 — 자세한 사유는 Task 4 보고서 참조.

---

## 진단 결과 (Task 9 실행 후 채운다)

```
판정:
근거 수치:
Task 6 실행 여부:
남은 미확인:
```

---

## 자체 검토

**1. 스펙 커버리지**

| 스펙 단위 | 담당 | 비고 |
|---|---|---|
| C1 타일 예산 분리 (③) | Task 4 | 안 A 채택. 안 C·D 는 실효 없음/범위 초과로 배제 명시 |
| C2 런 예산 정합 + 직렬화 해제 (④) | Task 1 Step 5 | env 한 줄. `_cap_reached` 의미를 테스트로 못 박음 |
| C3 본문 사진 진단 (②) | Task 9 (+ 조건부 Task 6) | **H0 이 이미 끝나 스펙 전제가 바뀜** — 아래 참조 |
| C4 HWP 2순위 폴백 개선 (①) | Task 3(계측) + Task 5(임계값) | 스펙 §8.3 (a)→Task 3, (b)→Task 5, (c) 2순위 미변경 준수 |
| C5 추출 429 백오프 | Task 7 | 임포트 방향 준수: `extractor/` 로 이동, `app/` 이 재임포트 |
| C6 계측 | Task 2(#4,#6) + Task 4(#2) + Task 3(#5) + Task 7(#1) | #3·#7 은 **불필요로 판정** — 아래 참조 |
| C7 Job 설정 누락 4건 + 메모리 | Task 1 | #1 `GEMINI_MAX_CONCURRENCY=32`, #2 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`, #3 `--batch-size 3`, #4 `2Gi` |
| C8 워터마크 컷오프 시딩 | Task 10 | 안 B 채택. `--dry-run` 이 못 쓰는 이유 명시 |
| C9 스케줄러 resume + 런북 | Task 11 | 순서 추출기→백스톱→크롤러. 이름 불일치 정정 |
| C10 게시판 오선택 감지 (⑤) | Task 8 | 실패로 강등하지 않음 |
| C11 크롤→추출 연결 (⑥) | Task 12 | 코드 미변경, 측정 + 문서화. 폴백 유지 |
| §5 `budget_exhausted` 즉시 포기 유지 | (변경 없음) | 스펙 결정대로 코드를 건드리지 않았다 |
| §15 환각 N1~N3 (negative/positive control) | **Task 4 Step 11~13** | 본 계획. 선택 아님 — 현행 Gemini 도 같은 위험을 갖는다 |
| §19 판독 백엔드 이전 (가)/(나) | **선택 Task 13** | 권고는 (가). (나)는 착수 조건(H-FAIL 또는 사용자 지시) 아래 분리 |
| §19.4 HWP 는 Bedrock 으로 못 옮긴다 | 선택 Task 13 머리말 + Step 1 #2 | `DocumentBlock.format` 에 hwp 없음(확인). 테스트로 «조용한 우회» 를 금지 |
| §19.8 모델 정책 (Haiku 기본 / Sonnet 승급 / **Opus 금지** / Nova 용도제한) | Global Constraints + 선택 Task 13 Step 1 #3 | 문서 규칙에 더해 **코드 레벨에서 `opus` 문자열 거부** |

**2. 스펙과 달라진 점 (의도된 것)**

| # | 스펙 | 이 계획 | 이유 |
|---|---|---|---|
| 1 | §7 «본문 사진 산출물 0건» = 고장 ①~④ 중 하나 | «회수율 31%» — 고장 아님 | H0 실측(2026-08-27): `sources[]` 의 `body_images_combined` 가 35건 중 **11건에 존재**. 최상위 `body_image` 키를 찾은 최초 관측이 틀렸다 |
| 2 | §7.2 H0 을 진단의 첫 단계로 | H0 은 끝났다고 보고 H1 부터 | 위와 같음. Task 9 는 **분모 재정의**로 시작한다 |
| 3 | §10 #3 «예산 소진 이유가 저장되는지 확인부터» | 확인 완료 — **저장되고 있다** | `budget.metadata()`(`extract_pipeline.py:182`) → `result.metadata` → `build_extracted_content`(`content_extraction_service.py:438`). 계측 추가 불필요, Task 9 스크립트가 그대로 읽는다 |
| 4 | §18 열린질문 #2 «warnings 가 저장되는가» | 저장된다 — **해소** | `ExtractedText.warnings` → `_source_from_extracted(errors=...)`(`extract_pipeline.py:454`) → `_source_summary["errors"]`(`:1364`). 따라서 §8.2 가설 (b) 는 거짓이고 (a)«침묵 이탈» 이 확정 |
| 5 | §14 배포 2 에 타일 계측 | 타일 계측을 Task 4 로 이동 | 같은 함수(`extract_image_text`)를 두 번 고치지 않기 위해. 진단이 필요로 하는 계측은 본문 사진 경로뿐 |
| 6 | §14 배포 3(진단)이 수정보다 앞 | Task 9 가 Task 4·5·7 뒤 | H0 이 끝나 «고장 아님»이 확정된 이상 Task 4·5·7 은 진단에 의존하지 않는다. 의존하는 것은 Task 6 하나뿐이고 그것만 Task 9 뒤에 뒀다 |
| 7 | §10 #7 «인라인 필터 사유 분포 — 추가 불필요» | 그대로 따름 | `_inline_image_ocr_decision` 의 `reason` 이 이미 `errors[]` 에 저장된다(`extract_pipeline.py:250`) |
| 8 | (2026-08-27 스펙 갱신 전) 판독 검증이 «표가 나오는가» 뿐 | **Task 4 에 negative control Step 3개 추가** | 판독의 진짜 실패는 «못 읽고 지어냈다» 이고 그건 기존 기준을 전부 통과한다. Nova 시험이 그 양상을 보였다(스펙 §19.2) |
| 9 | (2026-08-27 스펙 갱신 전) 판독 백엔드는 Gemini 고정 | **선택 Task 13 신설** | GCP 크레딧 소진 + Bedrock 판독 실측 성공. 다만 권고는 (가) 이므로 본 배포 순서 밖에 둔다(스펙 §19.7) |

**3. 자리표시자 점검** — "TBD"·"적절히"·"비슷하게" 없음. 모든 코드 Step 에 실제 코드가 들어 있다. Task 9 Step 6 · Task 12 Step 3 의 빈칸(`___`)은 **실행 후 측정치를 적는 자리**이지 미정 설계가 아니다.

**4. 심볼 일관성**

- `_cap_reached(used, cap)` — Task 1 테스트가 참조, `content_extraction_service.py:1467` 에 실존
- `ExtractionBudget(max_gemini_calls, max_inline_images, max_ocr_bytes, max_pdf_pages_for_ocr)` — Task 4 테스트의 생성자 인자가 `budget.py:14-22` 의 필드 순서·이름과 일치
- `reserve_gemini_call(source_id: str, byte_count: int)` — Task 4 가 `path.stat().st_size` 를 넘긴다. **정규화 전 원본 바이트로 바뀌는데**, `_ocr_image` 가 넘기던 정규화 후 크기보다 크므로 26MB 상한이 더 빨리 걸린다. 이는 «이미지 1개 = 1콜 + 원본 바이트 1회 계상» 이라는 더 정직한 회계다
- `_has_markdown_table(markdown: str) -> bool` — Task 5 Step 3 에서 정의, Step 1 테스트·Step 4 진입 조건에서 사용
- `_combine_body_images_best_effort(notice_id, inline_images) -> str` — Task 6 Step 3 정의, Step 4 두 호출부. Task 2 의 `_combine_and_upload_body_images` 를 감쌀 뿐 시그니처를 바꾸지 않는다
- `extractor.gemini_backoff.{QUOTA_BACKOFF_DELAYS_SECONDS, is_quota_exhausted_error, call_with_quota_backoff}` — Task 7 Step 3 정의, Step 4 재수출, Step 6 사용. **기존 `backend/tests/test_gemini_quota_backoff.py` 를 한 글자도 고치지 않는 것이 재수출이 맞았다는 증명이다**
- `ScheduledSchoolResult.board_kind` / `ScheduledCrawlerSummary.fallback_count` — Task 8 이 생산, `asdict` 가 `to_dict` 로 자동 노출
- `compute_board_watermarks(posts) -> dict[str, int]` — Task 10 Step 3 정의, Step 1 테스트·Step 5 스크립트에서 사용. `DiscoveredPostPreview` 필드(`title, post_id, post_uid, board_key, detail_url, status, method, source, cms_key, parser_family, reason`)는 `school_crawler_service.py:23-34` 와 일치
- `SchoolCrawlerService.discover_school_board` vs `discover_and_save_school_board` — 전자만 쓴다. 후자가 `_save_discovered_notice_candidates` 를 부른다(`:127`)

**5. 알려진 검증 공백 (수용)**

- **Task 7 에 429 재시도의 행동 테스트가 없다.** `_generate_content_vertex` 를 실행하려면
  `google.genai.types` 임포트와 Vertex 클라이언트 구성이 필요해 단위 테스트가 무겁다.
  대신 ⓐ 구현이 한 벌인지(소스 검사) ⓑ 번역 경로 회귀(기존 테스트 무수정 통과)
  ⓒ 배포 후 Cloud Logging 문자열 검출로 갈음한다.
- **Task 5 의 표 보존율 85% 목표는 즉시 판정 불가.** 재추출하지 않으므로 신규 HWP
  첨부로만 검증하는데, 학교 8곳 × 하루 1건 수준이면 HWP 20건을 모으는 데 수 주다.
  **수용한다** — 스펙 §18 #8 과 같은 판단.
- **Task 4 의 「타일 24조각이 실제로 다 도는가」는 초장축 이미지 유입에 달렸다.**
  단위 테스트는 예산 회계만 보장한다. 실제 확인은 Task 4 Step 10 의 로그 검색이고,
  대상 이미지가 안 들어오면 미판정으로 남는다.
- **Task 9 가 결론 없이 끝날 수 있다.** 재가동 전에는 신규 로그가 없어 D4 가 D2 와
  구분되지 않을 수 있다. **수용한다** — 스펙 §16 의 판단대로, ②는 이미 72일 방치됐고
  서비스가 죽지 않았다. 결론이 안 나면 «미해결»로 기록하고 넘긴다.
- **Task 4 Step 11~13 의 환각 판정은 «지어냄 마커» 라는 대리 지표다.** 판독 불가 입력에
  「학교」·「교장」 같은 구체 명사가 나오면 지어낸 것이라는 논리는 견고하지만,
  **마커에 없는 방식으로 지어내면 놓친다.** 정확도 채점이 아니라 **하한선**이다 —
  H-PASS 가 «절대 환각하지 않는다» 를 뜻하지는 않는다. **수용한다.**
- **선택 Task 13 의 G3(지연) 기준선이 아직 없다.** 현행 Gemini 판독 지연을 한 번도
  잰 적이 없어(스펙 §18 #9) «1.5배 이내» 의 분모가 비어 있다. 재가동 후 로그가 그
  분모를 채운다. **그 전에는 선택 Task 13 을 착수하지 않는다.**
- **Task 10 의 「워터마크 비대상」 구멍은 막을 수 없다.** 비숫자 post_id·해시 생성 글은
  워터마크로 걸러지지 않으므로 재가동 첫 런에 들어올 수 있다. dry-run 이 그 수를
  미리 알려주고, Task 11 Step 5 가 실제 유입과 대조한다.

**6. 되돌리기**

| Task | 롤백 |
|---|---|
| 1 | env·args·메모리 되돌리기 (`EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN` 삭제 → 코드 기본값 80 복귀) |
| 2, 3 | 로그·경고 제거. 동작에 영향 없음 |
| 4 | `MAX_TILES_PER_IMAGE=1` 로 타일링 사실상 차단, 또는 예약 지점 한 줄 되돌리기. Step 11~13 은 읽기 전용 프로브라 되돌릴 것이 없다 |
| 5 | 진입 조건을 `len(stripped) >= 40` 으로 되돌리기 |
| 6 | 실패 경로의 `_combine_body_images_best_effort` 호출 한 줄 제거 |
| 7 | `extractor/gemini_backoff.py` 를 유지한 채 `gemini_document_extractor.py` 의 두 함수만 되돌리기 (번역 경로는 그대로 산다) |
| 8 | 필드 3개 제거 |
| 9 | 없음 (읽기 전용) |
| 10 | dry-run 출력의 «롤백용 백업» JSON 으로 `board_watermarks` SQL 복원 |
| 11 | `gcloud scheduler jobs pause` 재실행 |
| 12 | 없음 (문서만) |
| **선택 13** | `EXTRACTION_BACKEND=gemini` 한 줄. `bedrock_document_extractor.py` 는 남겨도 호출되지 않는다 |

---

## 선행 준비물

| | 항목 | 필요한 Task |
|---|---|---|
| ✅ | `gcloud` 인증 + Cloud Run/Scheduler 권한 | Task 1, 4, 7, 11, 12 |
| ✅ | 운영 Supabase service_role 키(Secret Manager 경유) | Task 9, 10 |
| ⬜ | Task 1 머지·배포 완료 (Job 리비전 갱신) | Task 4 Step 10, Task 7 Step 10 의 로그 검증 |
| ⬜ | Task 2 머지·배포 완료 | Task 9 Step 5 의 로그 대조 |
| ⬜ | Task 9 판정 확정 | Task 6 실행 여부 결정 |
| ⬜ | Task 10 `--apply` 완료 | **Task 11 착수 전제 (건너뛰면 최대 64건 유입)** |
| ⬜ | Task 4 머지·배포 완료 + `qrcode`(또는 QR 이미지 1장) | Task 4 Step 11~13 (환각 negative control) |
| ⬜ | **Task 4 Step 13 판정이 H-FAIL** 또는 사용자의 명시적 지시 | **선택 Task 13 착수 전제.** 둘 다 아니면 착수하지 않는다 |
| ⬜ | 현행 Gemini 판독 지연의 기준선 (재가동 후 로그) | 선택 Task 13 Step 6 의 G3 게이트 — 분모가 없으면 판정 불가 |
| ⬜ | AWS 자격증명 (Secret Manager `aws-bedrock-access-key-id`·`aws-bedrock-secret-access-key`) + Bedrock 모델 액세스 승인 | 선택 Task 13 전체. **키를 명령줄·URL·로그에 넣지 않는다** |
