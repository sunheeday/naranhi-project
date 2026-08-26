# 미문서화 RSS · 교육부 공식 API 얹기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NEIS 오류가 «데이터 없음»으로 둔갑하는 것을 멈추고, 학사일정을 공식 API에서 받아 캘린더에 공존시키고, 부산·충북의 가짜 홈페이지 URL을 DB에서 몰아내고, RSS가 살아 있는 교육청(경북·전북·경기·전남)에서는 HTML 목록 파싱 없이 신규 글 목록을 얻는다.

**Architecture:** 세 갈래를 순차 배포한다. ① NEIS 클라이언트 두 곳(백엔드·프론트)에 `RESULT.CODE` 판정을 넣고 홈페이지 URL 정규화를 백엔드 규칙으로 통일한다 — RSS와 무관하게 전 학교에 즉효다. ② `school_events`에 `source` 컬럼을 넣고 `notice_id`를 nullable로 풀어 NEIS 학사일정을 AI 역추출 일정과 **같은 테이블에 공존**시킨다. ③ 게시판 탐지 성공 직후 학교당 1회 RSS 프로브를 돌려 `school_crawl_state.rss_feed`에 판정을 기록하고, 그 다음 배포에서만 수집 경로를 켠다. RSS는 **절대 단독 경로가 되지 않는다** — 실패하면 항상 기존 HTML 경로로 폴백한다. 각 갈래는 단독 롤백이 가능하다.

**Tech Stack:** Python 3.12 FastAPI, `httpx`, `xml.etree.ElementTree`, `supabase-py`, Cloud Run Jobs + Cloud Scheduler, Next.js 15 App Router, Supabase(Postgres), NEIS Open API

**Spec:** [docs/superpowers/specs/2026-08-27-E-rss-official-api-design.md](../specs/2026-08-27-E-rss-official-api-design.md)

## Global Constraints

- **마이그레이션 번호**: 이 계획은 **0039**부터 쓴다. `0035`는 자녀 개인일정용으로 예약, `0036`은 사업 A(app_jobs RLS, 파일 존재), `0037`은 사업 A(첨부 비공개), `0038`은 사업 F(관리자 role 복원)가 쓸 예정이다. 번호 중복 금지.
- **기존 크롤러 판정 로직을 바꾸지 않는다**: `board_detector.py` / `cms_patterns.py`의 판정과 `notice_post_extractor.py`의 파서 패밀리 6종은 한 줄도 바꾸지 않는다. RSS는 **위에 얹는 우회로**다. 손대는 것은 «후보 목록을 어디서 얻는가» 한 구간뿐이다.
- **🔴 세 값을 재계산하지 않는다**: `cms_key`·`board_key`·`post_id`는 캐시값을 그대로 재사용한다. `post_uid = f"{cms.key}:{board_key}:{post_id}"`(`notice_post_extractor.py:832`)가 한 글자라도 달라지면 같은 글이 두 행으로 저장되고 **에러가 나지 않는다.** 이 사업의 최대 실패 모드다.
- **`item == 0`은 `ok`가 아니라 `unknown`**: 서울 AJAX의 «조용한 0건»과 같은 함정이다. 방학 중 빈 게시판과 죽은 엔드포인트를 구분할 수 없다.
- **RSS delete 규칙**: 학사일정 동기화의 `delete`에 `.eq("source", "neis")`가 없으면 **실행하지 않는다.** 공지에서 뽑은 일정을 지운다.
- **급식·시간표는 손대지 않는다**: 이미 `mealServiceDietInfo` + `meals` 캐시를 쓴다. §9의 오류코드 판정만 공유된다.
- **로그인 게시판 우회 금지**: RSS 경로도 `_validate_candidate`(`notice_post_extractor.py:651`)를 그대로 탄다. `unsupported_login_required` 판정이 유지되어야 한다.
- **열쇠 취급**: 토큰·키를 명령줄 인자나 URL 쿼리에 넣지 않는다. 값 출력 금지(길이만). 단, **NEIS API는 `KEY` 쿼리 파라미터 외의 인증 수단이 없고 기존 코드가 이미 그렇게 호출한다**(`neis_client.py:104`, `lib/neis.ts:81`) — 이 계획은 그 방식을 바꾸지 않는다. 셸에서 NEIS를 찔러 볼 때는 **일부러 무효한 문자열**(`invalid-key-probe`)이나 **키 없는 5건 모드**만 쓴다.
- **테스트 실행**:
  - 백엔드: `PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests`
  - 프론트: **테스트 러너가 없다**(`package.json`에 test 스크립트 없음). `npm run typecheck` + `npm run build`로 검증하고, 순수 함수는 Node 22의 타입 스트리핑으로 직접 호출해 확인한다:
    `node --experimental-strip-types --input-type=module -e "const m = await import('./lib/neis.ts'); …"`
    (`lib/neis.ts`의 import는 전부 `import type`이라 값 의존성이 없다 — 이 방식이 실제로 동작하는 것을 확인했다.)
- **운영 DB 읽기**: `SUPABASE_URL=https://aoihmzewthgyoxtejfwo.supabase.co`, 키는 `gcloud secrets versions access latest --secret=supabase-service-role-key`. 읽기만 한다.
- **커밋 메시지**: 한국어, `type(scope): 요약` 형식. 저장소 관례를 따른다.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `backend/app/crawler/neis_client.py` | NEIS 클라이언트 (RESULT 판정 + SchoolSchedule) | 수정 (Task 1, 5) |
| `backend/tests/test_neis_result_code.py` | RESULT.CODE 판정 테스트 | 신규 (Task 1) |
| `lib/neis.ts` | 프론트 NEIS 클라이언트 (RESULT 판정 + 홈페이지 정규화) | 수정 (Task 2, 3) |
| `supabase/migrations/0039_school_events_source.sql` | 출처 컬럼 + `notice_id` nullable + 부분 유니크 | 신규 (Task 4) |
| `backend/tests/test_school_schedule_client.py` | SchoolSchedule 파싱·페이징 테스트 | 신규 (Task 5) |
| `backend/app/services/school_schedule_sync_service.py` | 학사일정 → `school_events` 전량 교체 | 신규 (Task 6) |
| `backend/tests/test_school_schedule_sync.py` | 동기화 규칙 테스트 (delete 가드 포함) | 신규 (Task 6) |
| `backend/app/jobs/sync_school_schedules.py` | 주 1회 배치 CLI | 신규 (Task 7) |
| `.github/workflows/deploy-api-cloud-run.yml` | Cloud Run Job 배포 | 수정 (Task 7) |
| `supabase/migrations/0040_school_crawl_state_rss_feed.sql` | RSS 판정 저장 컬럼 | 신규 (Task 8) |
| `backend/app/crawler/rss_feed.py` | 피드 URL 유도 · 파싱 · link 정규화 · 4단 게이트 프로브 | 신규 (Task 9, 11) |
| `backend/tests/test_rss_feed_probe.py` | URL 유도 + 게이트 테스트 | 신규 (Task 9) |
| `backend/tests/test_rss_feed_parse.py` | 두 flavor 파싱 + link 정규화 테스트 | 신규 (Task 11) |
| `backend/app/services/school_crawler_service.py` | 프로브 호출 + `rss_feed` 읽기/쓰기 + 수집 분기 | 수정 (Task 10, 12) |
| `backend/app/core/config.py` | 프로브·수집 플래그 2개 | 수정 (Task 10, 12) |
| `backend/tests/test_rss_post_candidates.py` | RSS→`_RawPostCandidate` 값 일치 테스트 | 신규 (Task 12) |
| `backend/app/crawler/notice_post_extractor.py` | RSS 후보 주입 분기 (`_raw_candidates_from_rss`) | 수정 (Task 12) |

---

## 배포 순서

스펙 §12를 그대로 따른다. **NEIS·URL 수정이 먼저, RSS가 나중이다.** 등록 학교 8곳 중 RSS 지역이 0곳일 수 있으므로(스펙 §11.2 — 미확인), 전 학교에 즉효인 것을 앞에 둔다.

```
Task 1   NEIS RESULT 판정 — 백엔드      ┐ 배포 1 (E5)
Task 2   NEIS RESULT 판정 — 프론트      ┘
Task 3   홈페이지 URL 정규화 통일          배포 2 (E6)
Task 4   마이그레이션 0039                배포 3 (E4-a)
Task 5   SchoolSchedule 클라이언트       ┐ 배포 4 (E4-b)
Task 6   학사일정 동기화 서비스           ┘
Task 7   주 1회 배치 Job                 배포 5 (E4-c)
Task 8   마이그레이션 0040                배포 6 (E1-a)
Task 9   RSS 프로브 모듈                 ┐ 배포 7 (E1-b, 기록만)
Task 10  프로브를 크롤에 접합             ┘
Task 11  RSS 파싱 + link 정규화          ┐ 배포 8 (E2+E3, 플래그 뒤)
Task 12  수집 경로 접합 + 이중 저장 대조   ┘
```

**Task 4가 Task 6보다 앞인 이유**: 컬럼 없이 NEIS 행을 넣으면 `notice_id` not null에 걸린다. 그리고 컬럼만 먼저 넣으면 프론트 회귀를 **NEIS 데이터 없이** 확인할 수 있다.

**Task 10이 Task 12보다 앞인 이유**: 프로브를 «기록만»으로 한 주기 돌려서 게이트 4(제목 교차검증)의 오탐률을 **수집을 켜기 전에** 본다. 이게 이 사업에서 가장 값싼 안전장치다.

---

## Task 1: NEIS RESULT 코드 판정 — 백엔드

NEIS는 오류를 **HTTP 200 본문의 `RESULT.CODE`**로 돌려주는데 `neis_client.py:75-83`의 `_extract_rows`는 `row` 블록이 없으면 그냥 `[]`를 반환한다. 즉 일일 한도 초과(`ERROR-337`)와 «데이터 없음»(`INFO-200`)이 **구분되지 않는다.**

**Files:**
- Modify: `backend/app/crawler/neis_client.py` (`_extract_rows` 앞단)
- Create: `backend/tests/test_neis_result_code.py`

**Interfaces:**
- Consumes: 없음
- Produces: `NeisApiError(code, message)` · `NeisQuotaExceeded(NeisApiError)` · `check_result_code(payload, key) -> None`. Task 5의 `fetch_school_schedule`와 Task 7의 배치 중단 판정이 이 예외를 잡는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_neis_result_code.py` 생성:

```python
import unittest

from app.crawler.neis_client import (
    NeisApiError,
    NeisQuotaExceeded,
    _extract_rows,
)


class NeisResultCodeTest(unittest.TestCase):
    def test_quota_exceeded_raises(self):
        """ERROR-337(일일 한도)은 빈 배열이 아니라 예외여야 한다.

        지금은 화면에 '급식 정보 없음'으로 뜬다 — 서울 AJAX의 '조용한 0건'과 같은 구조다.
        """
        payload = {"RESULT": {"CODE": "ERROR-337", "MESSAGE": "일일 트래픽 제한을 넘었습니다."}}
        with self.assertRaises(NeisQuotaExceeded) as ctx:
            _extract_rows(payload, "mealServiceDietInfo")
        self.assertEqual(ctx.exception.code, "ERROR-337")

    def test_no_data_is_empty_not_error(self):
        """INFO-200(데이터 없음)은 정상이다. 휴일 급식이 여기 해당한다."""
        payload = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
        self.assertEqual(_extract_rows(payload, "mealServiceDietInfo"), [])

    def test_unknown_service_raises(self):
        payload = {"RESULT": {"CODE": "ERROR-310", "MESSAGE": "해당하는 서비스를 찾을 수 없습니다."}}
        with self.assertRaises(NeisApiError):
            _extract_rows(payload, "schoolNotice")

    def test_result_inside_head_block_is_checked(self):
        payload = {
            "schoolInfo": [
                {"head": [{"list_total_count": 0}, {"RESULT": {"CODE": "ERROR-336", "MESSAGE": "필수 값이 없습니다."}}]},
            ]
        }
        with self.assertRaises(NeisApiError):
            _extract_rows(payload, "schoolInfo")

    def test_normal_payload_returns_rows(self):
        payload = {
            "schoolInfo": [
                {"head": [{"list_total_count": 1}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}]},
                {"row": [{"SCHUL_NM": "가천초등학교"}]},
            ]
        }
        self.assertEqual(_extract_rows(payload, "schoolInfo"), [{"SCHUL_NM": "가천초등학교"}])

    def test_missing_result_block_is_tolerated(self):
        payload = {"schoolInfo": [{"row": [{"SCHUL_NM": "가천초등학교"}]}]}
        self.assertEqual(_extract_rows(payload, "schoolInfo"), [{"SCHUL_NM": "가천초등학교"}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_neis_result_code -v
```

Expected: FAIL — `ImportError: cannot import name 'NeisApiError'`

- [ ] **Step 3: 최소 구현 — 예외와 판정 함수를 만든다**

`backend/app/crawler/neis_client.py`의 `NEIS_BASE_URL` 정의 아래에 추가:

```python
QUOTA_EXCEEDED_CODE = "ERROR-337"
BENIGN_RESULT_CODES = {"INFO-000", "INFO-200"}


class NeisApiError(RuntimeError):
    """NEIS가 HTTP 200 본문에 담아 보낸 오류."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"NEIS {code}: {message}")
        self.code = code
        self.message = message


class NeisQuotaExceeded(NeisApiError):
    """일일 호출 한도 초과(ERROR-337). 한도 값은 공식적으로 미공개다."""


def check_result_code(payload: dict[str, Any], key: str) -> None:
    """행 추출 **앞단**에서 RESULT.CODE를 판정한다.

    NEIS는 오류를 HTTP 상태가 아니라 200 본문의 RESULT 블록으로 돌려준다.
    이 판정이 없으면 ERROR-337(한도 초과)이 빈 배열이 되어 화면에는
    '급식 정보 없음'으로 표시된다.
    """
    code, message = _result_code(payload, key)
    if not code or code in BENIGN_RESULT_CODES:
        return
    if code == QUOTA_EXCEEDED_CODE:
        raise NeisQuotaExceeded(code, message)
    raise NeisApiError(code, message)


def _result_code(payload: dict[str, Any], key: str) -> tuple[str, str]:
    top = payload.get("RESULT")
    if isinstance(top, dict):
        return str(top.get("CODE") or "").strip(), str(top.get("MESSAGE") or "")

    blocks = payload.get(key)
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            head = block.get("head")
            if not isinstance(head, list):
                continue
            for item in head:
                if isinstance(item, dict) and isinstance(item.get("RESULT"), dict):
                    result = item["RESULT"]
                    return str(result.get("CODE") or "").strip(), str(result.get("MESSAGE") or "")
    return "", ""
```

그리고 `_extract_rows`의 첫 줄에 판정을 넣는다 (호출부 2곳을 각각 고치지 않는다):

```python
def _extract_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    check_result_code(payload, key)
    blocks = payload.get(key)
    if not isinstance(blocks, list):
        return []
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_neis_result_code -v
```

Expected: PASS (6 tests)

- [ ] **Step 5: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. `_extract_rows`를 모킹 없이 쓰는 테스트가 있으면 payload에 `RESULT` 블록이 없어 그대로 통과한다(Step 1의 마지막 케이스가 그 보장이다).

- [ ] **Step 6: 실제 NEIS 응답 모양이 가정과 맞는지 확인한다**

무효한 키 문자열은 비밀이 아니므로 URL에 넣어도 된다.

```bash
curl -s "https://open.neis.go.kr/hub/mealServiceDietInfo?KEY=invalid-key-probe&Type=json&pIndex=1&pSize=5&ATPT_OFCDC_SC_CODE=B10&SD_SCHUL_CODE=7010084&MLSV_YMD=20260601" | head -c 300
echo
curl -s "https://open.neis.go.kr/hub/mealServiceDietInfo?Type=json&pIndex=1&pSize=5&ATPT_OFCDC_SC_CODE=B10&SD_SCHUL_CODE=7010084&MLSV_YMD=20260101" | head -c 300
```

Expected: 첫 줄은 최상위 `{"RESULT":{"CODE":"ERROR-…"` (인증키 오류), 둘째 줄은 `{"RESULT":{"CODE":"INFO-200"`. **`RESULT`가 최상위가 아니라 다른 곳에 있으면 중단하고 보고할 것** — `_result_code`의 가정이 틀렸다는 뜻이다.

- [ ] **Step 7: 커밋**

```bash
git add backend/app/crawler/neis_client.py backend/tests/test_neis_result_code.py
git commit -m "fix(neis): 200 본문의 RESULT.CODE 를 행 추출 앞단에서 판정한다

NEIS 는 오류를 HTTP 상태가 아니라 200 본문의 RESULT 블록으로 돌려주는데
_extract_rows 가 row 블록이 없으면 그냥 빈 배열을 반환하고 있었다.
그래서 일일 한도 초과(ERROR-337)가 '데이터 없음'과 구분되지 않고
화면에 '급식 정보 없음' 으로 표시된다.

INFO-000/INFO-200 만 정상으로 통과시키고 ERROR-337 은 NeisQuotaExceeded,
그 외는 NeisApiError 로 올린다. 판정을 _extract_rows 안에 두어
schoolInfo·급식·학사일정 호출부가 자동으로 같은 규칙을 탄다."
```

---

## Task 2: NEIS RESULT 코드 판정 — 프론트

`lib/neis.ts:87-89`가 `res.ok`만 보고, `extractRows`(`:98-105`)는 `row`가 없으면 `[]`를 반환한다. `:224,316,351`의 `INFO-200` 문자열 매칭은 **throw된 에러에만** 걸리는데 RESULT 블록은 throw하지 않으므로 실질적으로 동작하지 않는다.

**Files:**
- Modify: `lib/neis.ts` (`extractRows` 앞단, `NeisListEnvelope` 아래)

**Interfaces:**
- Consumes: 없음
- Produces: `NeisApiError` · `NeisQuotaExceededError` · `assertNeisResult(envelope, key)` (검증을 위해 export). 급식·시간표·학교검색 호출부가 자동으로 판정을 탄다.

- [ ] **Step 1: 판정 함수와 예외를 쓴다**

`lib/neis.ts`의 `extractRows` 정의 **바로 위**(즉 `NeisListEnvelope` 인터페이스 아래)에 추가:

```typescript
export class NeisApiError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(`NEIS ${code}: ${message}`)
    this.name = 'NeisApiError'
    this.code = code
  }
}

/** 일일 호출 한도 초과. 한도 값은 공식적으로 미공개다. */
export class NeisQuotaExceededError extends NeisApiError {
  constructor(message: string) {
    super('ERROR-337', message)
    this.name = 'NeisQuotaExceededError'
  }
}

const NEIS_BENIGN_CODES = new Set(['INFO-000', 'INFO-200'])

function readNeisResult(envelope: unknown, key: string): { CODE?: string; MESSAGE?: string } | null {
  if (!envelope || typeof envelope !== 'object') return null
  const top = (envelope as Record<string, unknown>).RESULT
  if (top && typeof top === 'object') return top as { CODE?: string; MESSAGE?: string }

  const blocks = (envelope as Record<string, unknown>)[key]
  if (!Array.isArray(blocks)) return null
  for (const block of blocks) {
    if (!block || typeof block !== 'object') continue
    const head = (block as Record<string, unknown>).head
    if (!Array.isArray(head)) continue
    for (const item of head) {
      const result = item && typeof item === 'object' ? (item as Record<string, unknown>).RESULT : null
      if (result && typeof result === 'object') return result as { CODE?: string; MESSAGE?: string }
    }
  }
  return null
}

/** 행 추출 앞단의 RESULT.CODE 판정. 백엔드 neis_client.check_result_code 와 같은 규칙.
 *  이 판정이 없으면 ERROR-337(한도 초과)이 빈 배열이 되어 '급식 정보 없음'으로 보인다. */
export function assertNeisResult(envelope: unknown, key: string): void {
  const result = readNeisResult(envelope, key)
  const code = (result?.CODE ?? '').trim()
  if (!code || NEIS_BENIGN_CODES.has(code)) return
  const message = result?.MESSAGE ?? ''
  if (code === 'ERROR-337') throw new NeisQuotaExceededError(message)
  throw new NeisApiError(code, message)
}
```

- [ ] **Step 2: `extractRows` 첫 줄에 판정을 넣는다**

```typescript
function extractRows<R>(envelope: NeisListEnvelope<R>, key: string): R[] {
  assertNeisResult(envelope, key)
  const arr = envelope[key]
  if (!Array.isArray(arr)) return []
  for (const block of arr) {
    if (block && 'row' in block && Array.isArray(block.row)) return block.row
  }
  return []
}
```

> `:224,316,351`의 `/INFO-200|해당 자료가 없습니다/` catch 블록은 **그대로 둔다.** 이제 `INFO-200`은 `assertNeisResult`가 조용히 통과시키므로 저 매칭은 더 이상 발화하지 않지만, 제거는 이 Task의 범위가 아니고 남아 있어도 무해하다.

- [ ] **Step 3: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공

- [ ] **Step 4: 판정 동작을 직접 호출해 확인한다 (프론트 테스트 러너 없음)**

```bash
node --experimental-strip-types --input-type=module -e "
const { assertNeisResult, NeisApiError, NeisQuotaExceededError } = await import('./lib/neis.ts')
const cases = [
  ['ERROR-337 한도초과', {RESULT:{CODE:'ERROR-337',MESSAGE:'x'}}, 'quota'],
  ['INFO-200 데이터없음', {RESULT:{CODE:'INFO-200',MESSAGE:'x'}}, 'ok'],
  ['INFO-000 정상',      {RESULT:{CODE:'INFO-000',MESSAGE:'x'}}, 'ok'],
  ['ERROR-310 서비스없음',{RESULT:{CODE:'ERROR-310',MESSAGE:'x'}}, 'error'],
  ['head 안 RESULT',     {schoolInfo:[{head:[{list_total_count:0},{RESULT:{CODE:'ERROR-336',MESSAGE:'x'}}]}]}, 'error'],
  ['RESULT 없음',        {schoolInfo:[{row:[{}]}]}, 'ok'],
]
let bad = 0
for (const [label, payload, want] of cases) {
  let got = 'ok'
  try { assertNeisResult(payload, 'schoolInfo') }
  catch (e) { got = e instanceof NeisQuotaExceededError ? 'quota' : (e instanceof NeisApiError ? 'error' : 'other') }
  const okMark = got === want ? 'OK ' : 'FAIL'
  if (got !== want) bad++
  console.log(okMark, label, '→', got)
}
process.exit(bad === 0 ? 0 : 1)
" 2>&1 | grep -v MODULE_TYPELESS
echo "종료코드: $?"
```

Expected: 6줄 전부 `OK`, 종료코드 0

- [ ] **Step 5: 커밋**

```bash
git add lib/neis.ts
git commit -m "fix(neis): 프론트도 200 본문의 RESULT.CODE 를 판정한다

extractRows 가 row 블록이 없으면 빈 배열을 반환해서, 일일 한도 초과
(ERROR-337)가 화면에 '급식 정보 없음' 으로 표시되고 있었다.
:224,316,351 의 INFO-200 문자열 매칭은 throw 된 에러에만 걸리는데
RESULT 블록은 throw 하지 않으므로 실질적으로 동작하지 않았다.

백엔드 neis_client.check_result_code 와 같은 규칙으로 맞춘다.
프론트 테스트 러너가 없으므로 assertNeisResult 를 export 해
Node 타입 스트리핑으로 직접 호출해 검증한다."
```

---

## Task 3: 홈페이지 URL 정규화 통일 (부산·충북)

`schoolInfo`의 `HMPG_ADRES`가 부산(C10)·충북(M10)은 문자열 `"http://"`로만 채워져 사실상 누락인데, 백엔드는 이를 `""`로 거르고(`neis_client.py:53-54`) **프론트는 통과시킨다**(`lib/neis.ts:137-142`가 `/^https?:\/\//` 검사만 한다). 그 값이 온보딩을 통해 `schools.homepage_url`에 저장되고(`app/onboarding/actions.ts:127`), 크롤이 다시 `None`으로 떨어뜨려 NEIS를 재조회하고, 같은 값이 돌아와 `homepage_missing`이 반복된다.

**Files:**
- Modify: `lib/neis.ts:137-142` (`normalizeHomepageUrl`)

**Interfaces:**
- Consumes: 없음
- Produces: `normalizeHomepageUrl`(export). 백엔드 `normalize_homepage_url`(`neis_client.py:45-72`)과 입력·출력이 일치한다.

- [ ] **Step 1: 백엔드와 같은 규칙으로 바꾼다**

`lib/neis.ts`의 `normalizeHomepageUrl`을 아래로 교체한다:

```typescript
/** 백엔드 neis_client.normalize_homepage_url(:45-72) 과 같은 규칙.
 *
 *  부산(C10)·충북(M10)의 HMPG_ADRES 는 "http://" 한 문자열로만 채워져 사실상 누락이다.
 *  이걸 통과시키면 온보딩이 그 값을 schools.homepage_url 에 저장하고, 크롤은 다시
 *  None 으로 떨어뜨려 NEIS 를 재조회하고, 같은 값이 돌아와 homepage_missing 이 반복된다.
 *  추정으로 채우지 않는다 — 틀린 URL 은 다른 학교의 공지를 학부모에게 보낸다.
 *  export 하는 이유: 프론트 테스트 러너가 없어 Node 타입 스트리핑으로 직접 검증한다. */
export function normalizeHomepageUrl(value: string | null | undefined): string {
  const trimmed = (value ?? '').trim()
  if (!trimmed) return ''
  if (['http:', 'https:', 'http://', 'https://'].includes(trimmed.toLowerCase())) return ''
  if (trimmed.startsWith('//')) return `https:${trimmed}`.replace(/\/+$/, '')

  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
    let host = ''
    try {
      host = new URL(trimmed).host
    } catch {
      return ''
    }
    if (!host) return ''
    return trimmed.replace(/\/+$/, '')
  }

  return `https://${trimmed}`.replace(/\/+$/, '')
}
```

- [ ] **Step 2: 타입체크·빌드**

```bash
npm run typecheck && npm run build
```

Expected: 둘 다 성공

- [ ] **Step 3: 백엔드와 값이 실제로 일치하는지 두 언어로 대조한다**

```bash
node --experimental-strip-types --input-type=module -e "
const { normalizeHomepageUrl } = await import('./lib/neis.ts')
const inputs = ['http://','https://','http:','https:','','   ','iginue.icees.kr','http://iginue.icees.kr/','https://school.gyo6.net/gacheon','//school.jbedu.kr/kacheon','mailto:a@b.kr','school.cbe.go.kr/abc/']
console.log(JSON.stringify(inputs.map(v => [v, normalizeHomepageUrl(v)])))
" 2>/dev/null > /tmp/front_norm.json

PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from app.crawler.neis_client import normalize_homepage_url
front = json.load(open('/tmp/front_norm.json', encoding='utf-8'))
bad = 0
for raw, got in front:
    want = normalize_homepage_url(raw)
    mark = 'OK  ' if got == want else 'FAIL'
    if got != want: bad += 1
    print(f'{mark} {raw!r:38} front={got!r:38} back={want!r}')
print('불일치', bad)
sys.exit(1 if bad else 0)
"
```

Expected: 모든 줄 `OK`, `불일치 0`, 종료코드 0. 특히 `'http://'` → `''` 가 양쪽 다 나와야 한다.

- [ ] **Step 4: 운영 DB에 이미 들어간 쓰레기값 규모를 확인한다 (읽기만)**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/schools?select=id,name,neis_office_code,homepage_url')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
rows = json.loads(urllib.request.urlopen(r, timeout=60).read().decode())
junk = [x for x in rows if (x.get('homepage_url') or '').strip() in ('http:', 'https:', 'http://', 'https://')]
print('학교 수', len(rows), '| 쓰레기 homepage_url', len(junk))
for x in junk:
    print(' ', x['neis_office_code'], x['name'], repr(x['homepage_url']))
"
```

Expected: 개수와 목록이 출력된다. **이 값들을 지우지 않는다** — 스펙 §10.3대로 무해하고, 되돌리기가 커밋 하나로 끝나야 한다. 숫자만 기록해 둔다.

- [ ] **Step 5: 커밋**

```bash
git add lib/neis.ts
git commit -m "fix(neis): 프론트 홈페이지 URL 정규화를 백엔드 규칙과 통일

부산(C10)·충북(M10) 의 HMPG_ADRES 는 'http://' 한 문자열로만 채워져
사실상 누락인데, 프론트는 /^https?:\\/\\// 검사만 해서 그대로 통과시켰다.
그 값이 온보딩을 통해 schools.homepage_url 에 저장되고, 크롤은 다시
None 으로 떨어뜨려 NEIS 를 재조회하고, 같은 값이 돌아와
homepage_missing 이 무한 반복된다.

도메인 규칙으로 URL 을 추정하지 않는다 — 틀린 URL 은 다른 학교의 공지를
학부모에게 보낸다. 나아지는 것은 '정직해지는 것' 하나다."
```

---

## Task 4: 마이그레이션 0039 — `school_events` 출처 구분

NEIS 학사일정은 **학교 공식 연간 일정**(개학·방학·시험)이고 AI 역추출 일정은 **개별 공지에 딸린 일정**(특정 학년 체험학습, 신청 마감)이다. 서로를 포함하지 않으므로 **공존**시킨다. 그런데 `school_events.notice_id`가 not null + FK(`0017_school_events.sql:4`)라 NEIS 일정을 그냥 넣을 수 없다.

**Files:**
- Create: `supabase/migrations/0039_school_events_source.sql`

**Interfaces:**
- Consumes: 없음
- Produces: `school_events.source text not null default 'notice_ai'`, `notice_id` nullable, `school_events_neis_uidx` 부분 유니크. Task 6의 동기화가 이 컬럼과 인덱스에 의존한다.

- [ ] **Step 1: 지금 상태를 기록으로 남긴다 (적용 전)**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/school_events?select=id&limit=1')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k); r.add_header('Prefer', 'count=exact')
x = urllib.request.urlopen(r, timeout=60)
print('school_events 전체:', x.headers.get('Content-Range'))
"
```

Expected: `0-0/N` 형태. **이 N을 적어 둔다** — Step 5에서 «변화 0»을 확인하는 기준선이다.

- [ ] **Step 2: 마이그레이션을 쓴다**

`supabase/migrations/0039_school_events_source.sql`:

```sql
-- NEIS SchoolSchedule(학교 공식 학사일정)을 공지 본문 AI 역추출 일정과 같은 테이블에
-- 공존시킨다. 둘은 서로를 포함하지 않는 다른 정보다 — 어느 한쪽을 버리면 정보가 준다.
--
-- 새 테이블로 나누지 않는 이유: 캘린더 쿼리가 하나로 남고(app/(app)/calendar/page.tsx:118-123),
-- RLS 정책이 이미 school_id 기준이며(0017), end_date·event_kinds 를 그대로 재사용한다.
--
-- 기존 행은 전부 공지에서 나왔으므로 기본값이 'notice_ai' 다 — 백필이 필요 없다.
alter table public.school_events
  add column if not exists source text not null default 'notice_ai';

-- NEIS 일정에는 이어 붙일 공지가 없다.
alter table public.school_events
  alter column notice_id drop not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'school_events_source_check'
      and conrelid = 'public.school_events'::regclass
  ) then
    alter table public.school_events
      add constraint school_events_source_check
      check (source in ('notice_ai', 'neis'));
  end if;
end;
$$;

-- notice_id 가 null 이면 unique (notice_id, event_date)(0029) 가 무력하다
-- (postgres 에서 null 은 서로 distinct). NEIS 행 전용 부분 유니크로 재실행을 막는다.
create unique index if not exists school_events_neis_uidx
on public.school_events (school_id, event_date, title)
where source = 'neis';

create index if not exists school_events_school_source_date_idx
on public.school_events (school_id, source, event_date);
```

- [ ] **Step 3: 번호가 겹치지 않는지 확인한다**

```bash
ls supabase/migrations/ | cut -c1-4 | sort | uniq -d
```

Expected: `0030` 한 줄만 (기존 역사적 중복). `0039`가 나오면 중단한다.

- [ ] **Step 4: 적용될 내용을 먼저 본다**

```bash
supabase db push --dry-run --include-all
```

Expected: 적용 대상 목록에 `0039_school_events_source.sql`이 포함된다. 사업 A가 아직 안 섰다면 `0030`·`0034`·`0036`도 함께 나온다 — **그건 사업 A의 Task 1이 할 일이므로, 그 세 개가 나오면 중단하고 보고할 것.**

- [ ] **Step 5: 적용하고 회귀를 확인한다**

```bash
supabase db push --include-all
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def count(q):
    r = urllib.request.Request(u + '/rest/v1/school_events?' + q)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k); r.add_header('Prefer', 'count=exact')
    return urllib.request.urlopen(r, timeout=60).headers.get('Content-Range')
print('전체        :', count('select=id&limit=1'))
print('notice_ai   :', count('select=id&limit=1&source=eq.notice_ai'))
print('neis        :', count('select=id&limit=1&source=eq.neis'))
"
```

Expected: 전체 = Step 1의 N (**변화 0**), `notice_ai` = N, `neis` = 0

- [ ] **Step 6: 캘린더 화면이 안 깨졌는지 확인한다**

```bash
npm run build
```

그리고 dev 서버를 띄워 로그인 상태로 `/calendar`를 연다.

Expected: 기존 일정이 그대로 보이고, 일정 → 공지 상세 링크(`notice_id` 기반, `calendar/page.tsx:147-170`)가 동작한다. 홈 화면 D-day 칩(`app/(app)/page.tsx:337-343`)도 그대로다.

- [ ] **Step 7: 커밋**

```bash
git add supabase/migrations/0039_school_events_source.sql
git commit -m "feat(calendar): school_events 에 출처 컬럼 추가, notice_id nullable 로 완화

NEIS 학사일정(학교 공식 연간 일정)과 공지 본문 AI 역추출 일정은 서로를
포함하지 않는 다른 정보다. 대체하지 않고 공존시킨다.

notice_id 가 not null + FK 라 NEIS 일정을 넣을 수 없었다. null 을 허용하되
(notice_id, event_date) 유니크가 null 에 무력하므로 source='neis' 전용
부분 유니크 인덱스를 따로 둔다.

기존 행은 전부 notice_ai 이므로 기본값으로 처리되고 백필이 없다.
notice_service._replace_school_events_from_pipeline 은 notice_id 로만
조회·삭제하므로 NEIS 행이 시야에 들어오지 않는다 — 코드 수정 0."
```

---

## Task 5: NEIS `SchoolSchedule` 클라이언트

저장소 전체에서 `SchoolSchedule` 호출은 **0건**이다. 학사일정만 공식 API를 안 쓰고 공지 본문에서 AI로 역추출하고 있다(`notice_service.py:826` → `:1125-1193`). 그 품질 보정용 일회성 스크립트가 둘 존재한다(`scripts/rebuild_school_events.py`, `scripts/sweep_footer_dates.py`).

**Files:**
- Modify: `backend/app/crawler/neis_client.py` (`SchoolScheduleEntry`, `NeisClient.fetch_school_schedule`)
- Create: `backend/tests/test_school_schedule_client.py`

**Interfaces:**
- Consumes: Task 1의 `_extract_rows` RESULT 판정 (`ERROR-337` → `NeisQuotaExceeded`)
- Produces: `SchoolScheduleEntry(event_date: str, title: str, description: str | None)`, `NeisClient.fetch_school_schedule(office_code, school_code, from_ymd, to_ymd) -> list[SchoolScheduleEntry]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_school_schedule_client.py` 생성:

```python
import unittest

from app.crawler.neis_client import SchoolScheduleEntry, _schedule_entry_from_row


class ScheduleRowMappingTest(unittest.TestCase):
    def test_maps_ymd_and_event_name(self):
        row = {"AA_YMD": "20260302", "EVENT_NM": "1학기 개학일", "EVENT_CNTNT": "전교생 등교"}
        self.assertEqual(
            _schedule_entry_from_row(row),
            SchoolScheduleEntry(event_date="2026-03-02", title="1학기 개학일", description="전교생 등교"),
        )

    def test_blank_content_becomes_none(self):
        row = {"AA_YMD": "20260715", "EVENT_NM": "여름방학", "EVENT_CNTNT": "   "}
        entry = _schedule_entry_from_row(row)
        assert entry is not None
        self.assertIsNone(entry.description)

    def test_rejects_bad_date_or_missing_title(self):
        self.assertIsNone(_schedule_entry_from_row({"AA_YMD": "2026-03-02", "EVENT_NM": "개학"}))
        self.assertIsNone(_schedule_entry_from_row({"AA_YMD": "20260302", "EVENT_NM": "  "}))
        self.assertIsNone(_schedule_entry_from_row({}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_schedule_client -v
```

Expected: FAIL — `ImportError: cannot import name 'SchoolScheduleEntry'`

- [ ] **Step 3: 최소 구현 — 엔트리 타입과 행 매핑**

`backend/app/crawler/neis_client.py`의 `School` 데이터클래스 아래에 추가:

```python
SCHOOL_SCHEDULE_PAGE_SIZE = 100
SCHOOL_SCHEDULE_MAX_PAGES = 10


@dataclass(frozen=True)
class SchoolScheduleEntry:
    """NEIS SchoolSchedule 한 행. NEIS는 기간 일정도 하루 1행으로 준다."""

    event_date: str  # ISO YYYY-MM-DD
    title: str
    description: str | None


def _schedule_entry_from_row(row: dict[str, Any]) -> SchoolScheduleEntry | None:
    ymd = str(row.get("AA_YMD") or "").strip()
    title = str(row.get("EVENT_NM") or "").strip()
    if len(ymd) != 8 or not ymd.isdigit() or not title:
        return None
    description = str(row.get("EVENT_CNTNT") or "").strip() or None
    return SchoolScheduleEntry(
        event_date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
        title=title,
        description=description,
    )
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_schedule_client -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: 페이징 호출을 붙인다**

`NeisClient` 클래스에 `search_schools` 아래로 메서드를 추가:

```python
    async def fetch_school_schedule(
        self,
        office_code: str,
        school_code: str,
        from_ymd: str,
        to_ymd: str,
    ) -> list[SchoolScheduleEntry]:
        """학사일정. 학년도 범위를 pSize=100으로 페이징한다.

        RESULT.CODE 판정은 _extract_rows가 한다 — ERROR-337은 NeisQuotaExceeded로,
        데이터 없음(INFO-200)은 빈 리스트로 올라온다.

        ⚠️ 연속 일정을 end_date로 병합하지 않는다. 0030_school_events_end_date.sql이
        '캘린더는 더 이상 근접 날짜를 추측 병합하지 않는다'고 명시했다 — 그 결정과
        충돌하는 설계를 새로 들이지 않는다.
        """
        if not self.api_key:
            raise RuntimeError("NEIS_API_KEY 환경변수가 필요합니다.")

        entries: dict[tuple[str, str], SchoolScheduleEntry] = {}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for page in range(1, SCHOOL_SCHEDULE_MAX_PAGES + 1):
                response = await client.get(
                    f"{NEIS_BASE_URL}/SchoolSchedule",
                    params={
                        "KEY": self.api_key,
                        "Type": "json",
                        "pIndex": str(page),
                        "pSize": str(SCHOOL_SCHEDULE_PAGE_SIZE),
                        "ATPT_OFCDC_SC_CODE": office_code,
                        "SD_SCHUL_CODE": school_code,
                        "AA_FROM_YMD": from_ymd,
                        "AA_TO_YMD": to_ymd,
                    },
                )
                response.raise_for_status()
                rows = _extract_rows(response.json(), "SchoolSchedule")
                for row in rows:
                    entry = _schedule_entry_from_row(row)
                    if entry:
                        entries[(entry.event_date, entry.title)] = entry
                if len(rows) < SCHOOL_SCHEDULE_PAGE_SIZE:
                    break

        return sorted(entries.values(), key=lambda item: (item.event_date, item.title))
```

- [ ] **Step 6: 전체 백엔드 테스트**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과

- [ ] **Step 7: 실제 NEIS 응답 필드명이 맞는지 키 없이 확인한다**

인증키 없이도 5건까지 반환된다.

```bash
curl -s "https://open.neis.go.kr/hub/SchoolSchedule?Type=json&pIndex=1&pSize=5&ATPT_OFCDC_SC_CODE=B10&SD_SCHUL_CODE=7010084&AA_FROM_YMD=20260301&AA_TO_YMD=20270228" | head -c 700
```

Expected: `AA_YMD`·`EVENT_NM`·`EVENT_CNTNT` 필드가 보인다. **필드명이 다르면 중단하고 보고할 것** — `_schedule_entry_from_row`의 매핑을 고쳐야 한다.

- [ ] **Step 8: 커밋**

```bash
git add backend/app/crawler/neis_client.py backend/tests/test_school_schedule_client.py
git commit -m "feat(neis): SchoolSchedule(학사일정) 조회 추가

저장소 전체에서 SchoolSchedule 호출이 0건이었다. 학사일정만 공식 API 를
안 쓰고 공지 본문에서 AI 로 역추출하고 있었고, 그 노이즈를 지우는
일회성 스크립트가 둘(rebuild_school_events, sweep_footer_dates) 존재한다.

학년도 범위를 pSize=100 으로 페이징하고 (날짜, 제목)으로 중복을 접는다.
연속 일정을 end_date 로 병합하지 않는다 — 0030 이 '캘린더는 더 이상
근접 날짜를 추측 병합하지 않는다' 고 명시한 결정과 충돌한다."
```

---

## Task 6: 학사일정 동기화 서비스

**Files:**
- Create: `backend/app/services/school_schedule_sync_service.py`
- Create: `backend/tests/test_school_schedule_sync.py`

**Interfaces:**
- Consumes: Task 4의 `school_events.source` + 부분 유니크, Task 5의 `fetch_school_schedule`
- Produces: `academic_year_range(today) -> (year, from_ymd, to_ymd)`, `SchoolScheduleSyncService.sync_school(school, today=None) -> SchoolScheduleSyncResult`, `select_schedule_sync_targets() -> list[dict]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_school_schedule_sync.py` 생성:

```python
import unittest
from datetime import date

from app.services.school_schedule_sync_service import (
    NEIS_SOURCE,
    academic_year_range,
    build_neis_event_rows,
)
from app.crawler.neis_client import SchoolScheduleEntry


class AcademicYearRangeTest(unittest.TestCase):
    def test_march_starts_new_academic_year(self):
        self.assertEqual(academic_year_range(date(2026, 3, 1)), (2026, "20260301", "20270228"))

    def test_january_belongs_to_previous_academic_year(self):
        self.assertEqual(academic_year_range(date(2026, 1, 15)), (2025, "20250301", "20260228"))

    def test_leap_february_end(self):
        # 2027-08 → 학년도 2027, 끝은 2028-02-29 (윤년)
        self.assertEqual(academic_year_range(date(2027, 8, 27)), (2027, "20270301", "20280229"))


class BuildRowsTest(unittest.TestCase):
    def test_rows_carry_source_and_null_notice(self):
        entries = [SchoolScheduleEntry(event_date="2026-03-02", title="개학일", description="전교생 등교")]
        rows = build_neis_event_rows("s-1", entries)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], NEIS_SOURCE)
        self.assertIsNone(row["notice_id"])
        self.assertIsNone(row["end_date"])
        self.assertEqual(row["event_kinds"], ["event"])
        self.assertEqual(row["school_id"], "s-1")
        self.assertEqual(row["event_date"], "2026-03-02")

    def test_empty_entries_produce_no_rows(self):
        self.assertEqual(build_neis_event_rows("s-1", []), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_schedule_sync -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.school_schedule_sync_service'`

- [ ] **Step 3: 최소 구현 — 순수 함수 두 개**

`backend/app/services/school_schedule_sync_service.py` 생성:

```python
from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import logging
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.crawler.neis_client import NeisClient, SchoolScheduleEntry

LOGGER = logging.getLogger(__name__)

NEIS_SOURCE = "neis"


def academic_year_range(today: date) -> tuple[int, str, str]:
    """학년도 범위(3/1 ~ 이듬해 2월 말). 1·2월은 직전 학년도에 속한다."""
    year = today.year if today.month >= 3 else today.year - 1
    last_day = 29 if calendar.isleap(year + 1) else 28
    return year, f"{year}0301", f"{year + 1}02{last_day}"


def build_neis_event_rows(school_id: str, entries: list[SchoolScheduleEntry]) -> list[dict[str, Any]]:
    """NEIS 일정 → school_events 행.

    notice_id 는 null 이다 — 이어 붙일 공지가 없다. 그래서 이 행들은
    notice_service._replace_school_events_from_pipeline(:1137-1191)의 시야에
    들어오지 않고, 홈 화면 D-day 칩(app/(app)/page.tsx:337-343)의
    .in('notice_id', …) 필터에도 걸리지 않는다.
    """
    return [
        {
            "school_id": school_id,
            "notice_id": None,
            "title": entry.title,
            "event_date": entry.event_date,
            "end_date": None,
            "event_kinds": ["event"],
            "location": None,
            "description": entry.description,
            "source_language": "ko",
            "source": NEIS_SOURCE,
        }
        for entry in entries
    ]
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_school_schedule_sync -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: 동기화 본체를 붙인다**

같은 파일 아래에 이어 쓴다:

```python
@dataclass(frozen=True)
class SchoolScheduleSyncResult:
    school_id: str
    school_name: str
    status: str  # "synced" | "skipped_no_codes" | "failed"
    academic_year: int
    from_date: str
    to_date: str
    fetched_count: int
    deleted_count: int
    inserted_count: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SchoolScheduleSyncService:
    def __init__(self, client: NeisClient | None = None) -> None:
        settings = get_settings()
        self._client = client or NeisClient(
            settings.neis_api_key or "",
            timeout=settings.crawler_timeout_seconds,
        )

    async def sync_school(
        self,
        school: dict[str, Any],
        *,
        today: date | None = None,
    ) -> SchoolScheduleSyncResult:
        """한 학교의 학년도 학사일정을 전량 교체한다.

        NeisQuotaExceeded 는 잡지 않는다 — 호출한 배치가 남은 학교를 건너뛰도록
        위로 올린다(재시도 폭주 금지).
        """
        school_id = str(school.get("id") or "")
        school_name = str(school.get("name") or "")
        office_code = str(school.get("neis_office_code") or "").strip()
        school_code = str(school.get("neis_school_code") or "").strip()
        year, from_ymd, to_ymd = academic_year_range(today or datetime.now(UTC).date())
        from_date = _iso(from_ymd)
        to_date = _iso(to_ymd)

        if not school_id or not office_code or not school_code:
            return SchoolScheduleSyncResult(
                school_id=school_id,
                school_name=school_name,
                status="skipped_no_codes",
                academic_year=year,
                from_date=from_date,
                to_date=to_date,
                fetched_count=0,
                deleted_count=0,
                inserted_count=0,
                error_message="neis_office_code/neis_school_code 가 없습니다.",
            )

        entries = await self._client.fetch_school_schedule(
            office_code,
            school_code,
            from_ymd,
            to_ymd,
        )
        deleted, inserted = replace_neis_events(
            school_id=school_id,
            entries=entries,
            from_date=from_date,
            to_date=to_date,
        )
        return SchoolScheduleSyncResult(
            school_id=school_id,
            school_name=school_name,
            status="synced",
            academic_year=year,
            from_date=from_date,
            to_date=to_date,
            fetched_count=len(entries),
            deleted_count=deleted,
            inserted_count=inserted,
        )


def replace_neis_events(
    *,
    school_id: str,
    entries: list[SchoolScheduleEntry],
    from_date: str,
    to_date: str,
) -> tuple[int, int]:
    """source='neis' + 같은 학년도 범위만 전량 교체한다.

    🔴 delete 에서 .eq("source", NEIS_SOURCE) 를 빼면 공지에서 뽑은 일정
    (source='notice_ai')을 지운다. 이 조건 없이 delete 를 실행하지 않는다.

    upsert 를 쓰지 않는 이유: 0039 의 유니크는 부분 인덱스(where source='neis')라
    PostgREST 의 on_conflict 대상으로 추론되지 않는다. 삭제 후 삽입으로 교체하고,
    부분 인덱스는 동시 실행 시의 중복을 막는 가드로만 쓴다.
    """
    supabase = get_supabase_client()
    deleted = (
        supabase.table("school_events")
        .delete()
        .eq("school_id", school_id)
        .eq("source", NEIS_SOURCE)
        .gte("event_date", from_date)
        .lte("event_date", to_date)
        .execute()
        .data
        or []
    )

    rows = build_neis_event_rows(school_id, entries)
    if not rows:
        return len(deleted), 0

    inserted = supabase.table("school_events").insert(rows).execute().data or []
    return len(deleted), len(inserted)


def select_schedule_sync_targets() -> list[dict[str, Any]]:
    """자녀가 등록된 학교만 대상. scheduled_crawler_service._fetch_registered_school_targets 와 같은 기준."""
    supabase = get_supabase_client()
    children = supabase.table("children").select("school_id").execute().data or []
    school_ids = sorted({str(row["school_id"]) for row in children if row.get("school_id")})
    if not school_ids:
        return []

    rows: list[dict[str, Any]] = []
    for index in range(0, len(school_ids), 100):
        chunk = school_ids[index : index + 100]
        result = (
            supabase.table("schools")
            .select("id,name,neis_office_code,neis_school_code")
            .in_("id", chunk)
            .execute()
        )
        rows.extend(result.data or [])
    return rows


def _iso(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
```

- [ ] **Step 6: import 가능 여부와 전체 테스트를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import app.services.school_schedule_sync_service as m
print('로드 OK:', [n for n in ('academic_year_range','build_neis_event_rows','replace_neis_events','select_schedule_sync_targets') if hasattr(m, n)])
"
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 네 심볼 전부 존재, 전체 테스트 통과

- [ ] **Step 7: 🔴 delete 가드가 소스에 실제로 있는지 기계적으로 확인한다**

```bash
python - <<'PY'
import re, sys, pathlib
src = pathlib.Path("backend/app/services/school_schedule_sync_service.py").read_text(encoding="utf-8")
block = src[src.index("def replace_neis_events"):]
delete_at = block.index('.delete()')
window = block[delete_at:delete_at + 400]
ok = '.eq("source", NEIS_SOURCE)' in window
print("delete 뒤 source 가드:", "있음" if ok else "없음")
print("파일 전체 delete 호출 수:", len(re.findall(r"\.delete\(\)", src)))
sys.exit(0 if ok else 1)
PY
```

Expected: `있음`, `delete 호출 수: 1`, 종료코드 0

- [ ] **Step 8: 커밋**

```bash
git add backend/app/services/school_schedule_sync_service.py backend/tests/test_school_schedule_sync.py
git commit -m "feat(calendar): NEIS 학사일정 동기화 서비스

학년도(3/1~이듬해 2월말) 단위로 source='neis' 행만 전량 교체한다.
delete 에는 반드시 .eq('source','neis') 가 붙는다 — 이 조건이 없으면
공지에서 뽑은 일정(notice_ai)을 지운다.

upsert 를 쓰지 않는다: 0039 의 유니크가 부분 인덱스라 PostgREST 의
on_conflict 대상으로 추론되지 않는다. 삭제 후 삽입으로 교체하고
부분 인덱스는 동시 실행 중복을 막는 가드로만 쓴다.

NeisQuotaExceeded 는 잡지 않고 배치로 올린다(재시도 폭주 금지)."
```

---

## Task 7: 주 1회 학사일정 배치 Job

학사일정은 거의 바뀌지 않으므로 학교당 **주 1회**로 충분하다. 등록 학교 8곳 기준 추가 호출은 **주 24회 이하**(학교당 2~3페이지)로 무시할 수준이다.

**Files:**
- Create: `backend/app/jobs/sync_school_schedules.py`
- Modify: `.github/workflows/deploy-api-cloud-run.yml` (env 1줄 + 배포 스텝 1개)

**Interfaces:**
- Consumes: Task 6의 `SchoolScheduleSyncService`, `select_schedule_sync_targets`
- Produces: `python -m app.jobs.sync_school_schedules [--school-id ID] [--limit N] [--dry-run]` → 요약 JSON을 stdout에 출력하고 종료코드로 판정

- [ ] **Step 1: 배치 CLI를 쓴다**

`backend/app/jobs/sync_school_schedules.py` 생성 (`scheduled_school_crawler.py`와 같은 모양):

```python
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.crawler.neis_client import NeisQuotaExceeded
from app.services.school_schedule_sync_service import (
    SchoolScheduleSyncService,
    select_schedule_sync_targets,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync NEIS SchoolSchedule into school_events for registered schools.",
    )
    parser.add_argument("--school-id", help="Run against one school id. Useful for manual verification.")
    parser.add_argument("--limit", type=_positive_int, help="Limit target schools for local testing.")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without calling NEIS or writing.")
    return parser


async def run_async(args: argparse.Namespace) -> int:
    targets = select_schedule_sync_targets()
    if args.school_id:
        targets = [row for row in targets if str(row.get("id")) == args.school_id]
    if args.limit is not None:
        targets = targets[: args.limit]

    if args.dry_run:
        print(json.dumps({"dry_run": True, "target_count": len(targets),
                          "targets": [{"id": r.get("id"), "name": r.get("name")} for r in targets]},
                         ensure_ascii=False))
        return 0

    service = SchoolScheduleSyncService()
    results: list[dict[str, object]] = []
    quota_exceeded = False

    for row in targets:
        if quota_exceeded:
            # 한도 초과 후에는 남은 학교를 건너뛴다. 재시도 폭주 금지 — 다음 주기에 다시 온다.
            results.append({"school_id": str(row.get("id") or ""), "status": "skipped_quota"})
            continue
        try:
            results.append((await service.sync_school(row)).to_dict())
        except NeisQuotaExceeded as exc:
            quota_exceeded = True
            LOGGER.warning("NEIS quota exceeded, skipping remaining schools: %s", exc)
            results.append({"school_id": str(row.get("id") or ""), "status": "quota_exceeded",
                            "error_message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one school must not stop the job.
            LOGGER.exception("school schedule sync failed: school_id=%s", row.get("id"))
            results.append({"school_id": str(row.get("id") or ""), "status": "failed",
                            "error_message": f"{type(exc).__name__}: {exc}"})

    synced = sum(1 for item in results if item.get("status") == "synced")
    summary = {
        "target_count": len(targets),
        "synced_count": synced,
        "quota_exceeded": quota_exceeded,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if quota_exceeded else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run_async(args))
    except Exception as exc:  # noqa: BLE001 - job should fail loudly on systemic errors.
        LOGGER.exception("school schedule sync job failed")
        print(json.dumps({"ok": False, "status": "job_failed", "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False), file=sys.stderr)
        return 1


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 컴파일과 dry-run 파서를 확인한다**

```bash
python -m compileall -q backend/app/jobs/sync_school_schedules.py && echo "컴파일 OK"
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
from app.jobs.sync_school_schedules import build_parser
args = build_parser().parse_args(['--school-id','abc','--limit','2','--dry-run'])
print(args.school_id, args.limit, args.dry_run)
"
```

Expected: `컴파일 OK`, `abc 2 True`

- [ ] **Step 3: 대상 목록만 뽑아 본다 (NEIS 호출·쓰기 없음)**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
PYTHONPATH=backend backend/venv/Scripts/python.exe -m app.jobs.sync_school_schedules --dry-run
```

Expected: `{"dry_run": true, "target_count": 8, "targets": [...]}` 근처. **target_count가 0이면 중단하고 보고할 것** — `children.school_id`가 비었다는 뜻이다.

- [ ] **Step 4: 학교 1곳만 실제로 동기화한다**

Step 3에서 나온 id 중 하나를 골라:

```bash
export NEIS_API_KEY="$(gcloud secrets versions access latest --secret=neis-api-key)"
SCHOOL_ID=<위에서 고른 id>
PYTHONPATH=backend backend/venv/Scripts/python.exe -m app.jobs.sync_school_schedules --school-id "$SCHOOL_ID"
```

Expected: `"status": "synced"`, `fetched_count > 0`, `deleted_count: 0`(첫 실행), `inserted_count == fetched_count`

- [ ] **Step 5: 🔴 AI 역추출 행이 손상되지 않았는지 대조한다**

```bash
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
def count(q):
    r = urllib.request.Request(u + '/rest/v1/school_events?select=id&limit=1&' + q)
    r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k); r.add_header('Prefer', 'count=exact')
    return urllib.request.urlopen(r, timeout=60).headers.get('Content-Range')
print('notice_ai :', count('source=eq.notice_ai'))
print('neis      :', count('source=eq.neis'))
"
```

Expected: `notice_ai`가 **Task 4 Step 5와 같은 수**(변화 0), `neis`가 Step 4의 `inserted_count`와 일치

- [ ] **Step 6: 재실행이 행을 늘리지 않는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m app.jobs.sync_school_schedules --school-id "$SCHOOL_ID"
```

Expected: `deleted_count == inserted_count`, 그리고 Step 5의 카운트를 다시 재면 `neis` 수 **증가 0**

- [ ] **Step 7: 공지 재번역이 NEIS 행을 지우지 않는지 확인한다**

동기화한 학교의 공지 1건을 골라 재추출·재번역을 태운 뒤 다시 카운트한다. (파이프라인 진입 방법은 기존 운영 절차를 따른다.)

Expected: `neis` 수 **변화 0**. `_replace_school_events_from_pipeline`은 `.eq("notice_id", …)`로만 조회·삭제하므로(`notice_service.py:1137-1191`) NEIS 행은 시야에 들어오지 않는다.

- [ ] **Step 8: 배포 워크플로에 Job을 추가한다**

`.github/workflows/deploy-api-cloud-run.yml`의 `env:` 블록에 한 줄 추가:

```yaml
  SCHEDULE_SYNC_JOB: ${{ vars.CLOUD_RUN_SCHEDULE_SYNC_JOB }}
```

그리고 «Deploy scheduled school crawler Job to Cloud Run» 스텝 **뒤에** 스텝을 추가한다:

```yaml
      # 주 1회 배치: NEIS SchoolSchedule → school_events(source='neis').
      # 학사일정은 거의 바뀌지 않으므로 주 1회면 충분하다(학교당 2~3페이지).
      - name: Deploy school schedule sync Job to Cloud Run
        if: ${{ env.SCHEDULE_SYNC_JOB != '' }}
        run: |
          gcloud run jobs deploy "$SCHEDULE_SYNC_JOB" \
            --image="$GAR_LOCATION-docker.pkg.dev/$PROJECT_ID/$GAR_REPOSITORY/$IMAGE_NAME:$GITHUB_SHA" \
            --region="$REGION" \
            --command=python \
            --args="-m,app.jobs.sync_school_schedules" \
            --task-timeout=1800 \
            --max-retries=0 \
            --memory=512Mi \
            --cpu=1 \
            --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=INFO,SUPABASE_URL=${{ vars.NEXT_PUBLIC_SUPABASE_URL }}" \
            --set-secrets="SUPABASE_SERVICE_ROLE_KEY=supabase-service-role-key:latest,NEIS_API_KEY=neis-api-key:latest"
```

- [ ] **Step 9: 워크플로 문법을 검사한다**

```bash
python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/deploy-api-cloud-run.yml', encoding='utf-8'))
names = [s.get('name') for s in d['jobs']['deploy']['steps']]
assert 'Deploy school schedule sync Job to Cloud Run' in names, names
assert 'SCHEDULE_SYNC_JOB' in d['env']
print('OK — 스텝 수', len(names))
"
```

Expected: `OK — 스텝 수 N`

- [ ] **Step 10: 주 1회 Cloud Scheduler를 건다 (사람이 1회 실행)**

> 값은 `CLOUD_RUN_SCHEDULE_SYNC_JOB`(GitHub Variable)과 같아야 한다. 매주 일요일 05:00 KST.

```bash
gcloud scheduler jobs create http school-schedule-sync-weekly \
  --location="$REGION" \
  --schedule="0 5 * * 0" \
  --time-zone="Asia/Seoul" \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$SCHEDULE_SYNC_JOB:run" \
  --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA_EMAIL"
```

Expected: 생성 성공. 기존 크롤 스케줄러와 같은 서비스 계정을 쓴다.

> ⚠️ 메모리 기록상 2026-06-15 발표용으로 크롤/추출 스케줄러 5개가 **PAUSED** 상태다. 새 스케줄러도 같은 정책을 따를지 **사용자에게 확인한 뒤** 활성화한다.

- [ ] **Step 11: 커밋**

```bash
git add backend/app/jobs/sync_school_schedules.py .github/workflows/deploy-api-cloud-run.yml
git commit -m "feat(calendar): NEIS 학사일정 주 1회 동기화 Job

학사일정은 거의 바뀌지 않으므로 학교당 주 1회면 충분하다.
등록 학교 8곳 기준 추가 호출은 주 24회 이하로 무시할 수준이다.

한도 초과(ERROR-337)를 받으면 그 실행의 남은 학교를 전부 건너뛴다.
재시도 폭주 금지 — 다음 주기에 다시 온다. 종료코드 1 로 알린다."
```

---

## Task 8: 마이그레이션 0040 — RSS 판정 저장 컬럼

RSS 유무는 학교별로 한 번 판정해 저장한다. 둘 곳은 **`school_crawl_state`**다 — 크롤 상태 전용 테이블이고 RLS 활성 + 정책 0개(`0013:72`)라 service_role 전용이 이미 보장되며, `board_watermarks`가 같은 패턴으로 이미 산다(`0033`). `schools`에는 넣지 않는다 — `schools.crawl_*`는 사업 D에서 제거 대상이다.

**Files:**
- Create: `supabase/migrations/0040_school_crawl_state_rss_feed.sql`

**Interfaces:**
- Consumes: 없음
- Produces: `school_crawl_state.rss_feed jsonb not null default '{}'::jsonb`. Task 10이 쓰고 Task 12가 읽는다.

- [ ] **Step 1: 마이그레이션을 쓴다**

`supabase/migrations/0040_school_crawl_state_rss_feed.sql`:

```sql
-- 미문서화 RSS 엔드포인트 판정 결과를 학교당 1개 기록한다.
-- board_watermarks(0033)와 같은 자리·같은 모양이다.
--
-- 값의 모양:
--   {"status":"ok|unknown|unsupported", "flavor":"gyo6_rss2|jbedu_json",
--    "url":"...", "board_key":"mi=…|bbsId=…", "item_count":15,
--    "checked_at":"2026-08-27T…+00:00", "error":null}
--
-- board_key 를 함께 저장하는 이유: 게시판이 바뀌면(재탐지·학교 리뉴얼) 저장된 피드
-- URL 이 다른 게시판을 가리키게 된다. board_key 불일치를 무효화 신호로 쓴다.
--
-- schools 에 넣지 않는 이유: schools.crawl_* 는 사업 D 에서 제거 대상이다.
alter table public.school_crawl_state
  add column if not exists rss_feed jsonb not null default '{}'::jsonb;
```

- [ ] **Step 2: 번호가 겹치지 않는지 확인한다**

```bash
ls supabase/migrations/ | cut -c1-4 | sort | uniq -d
```

Expected: `0030` 한 줄만

- [ ] **Step 3: 적용 예정을 확인하고 적용한다**

```bash
supabase db push --dry-run --include-all
supabase db push --include-all
```

Expected: `0040_school_crawl_state_rss_feed.sql`이 적용된다

- [ ] **Step 4: 기존 크롤에 무영향인지 확인한다**

```bash
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/school_crawl_state?select=school_id,crawl_status,rss_feed')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
rows = json.loads(urllib.request.urlopen(r, timeout=60).read().decode())
print('행 수', len(rows), '| rss_feed 가 {} 아닌 행', sum(1 for x in rows if x.get('rss_feed') != {}))
"
```

Expected: 행 수는 기존대로, `rss_feed 가 {} 아닌 행 0`

- [ ] **Step 5: 커밋**

```bash
git add supabase/migrations/0040_school_crawl_state_rss_feed.sql
git commit -m "feat(crawler): school_crawl_state 에 rss_feed 판정 컬럼 추가

미문서화 RSS 엔드포인트 판정을 학교당 1개 기록한다.
board_watermarks(0033)와 같은 자리·같은 모양이다.

board_key 를 값에 함께 넣는다 — 게시판이 바뀌면 저장된 피드 URL 이
다른 게시판을 가리키게 되고, board_key 불일치가 그 무효화 신호다.

schools 에 넣지 않는다: schools.crawl_* 는 사업 D 의 제거 대상이다."
```

---

## Task 9: RSS 프로브 모듈 — URL 유도 + 4단 게이트

**여기가 이 사업의 핵심이다.** 판정을 느슨하게 하면 서울 AJAX와 같은 함정에 빠진다 — 0건을 «새 글 없음»으로 오인하고 크롤이 조용히 죽는다.

**Files:**
- Create: `backend/app/crawler/rss_feed.py`
- Create: `backend/tests/test_rss_feed_probe.py`

**Interfaces:**
- Consumes: `app.crawler.http_client`의 `DEFAULT_HEADERS` · `legacy_ssl_context` · `make_async_client_for_url`
- Produces: `RssFeedState`, `derive_feed_url(board_url, parser_family, board_key) -> tuple[str, str] | None`, `should_probe(raw, board_key, now) -> bool`, `probe_rss_feed(...) -> RssFeedState`, `fetch_feed(url, timeout) -> tuple[int, bytes]`

- [ ] **Step 1: 실패하는 테스트를 쓴다 — URL 유도와 재프로브 규칙**

`backend/tests/test_rss_feed_probe.py` 생성:

```python
import unittest
from datetime import UTC, datetime, timedelta

from app.crawler.rss_feed import (
    FLAVOR_GYO6_RSS2,
    FLAVOR_JBEDU_JSON,
    derive_feed_url,
    should_probe,
)


class DeriveFeedUrlTest(unittest.TestCase):
    def test_select_ntt_builds_rss_feed_path(self):
        derived = derive_feed_url(
            board_url="https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=119615&bbsId=39051",
            parser_family="select_ntt_like",
            board_key="mi=119615|bbsId=39051",
        )
        self.assertEqual(
            derived,
            ("https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051", FLAVOR_GYO6_RSS2),
        )

    def test_jbedu_rule_is_host_pinned(self):
        """slash_view_like 는 울산·충북에서도 잡힌다. 호스트 검사 없이 적용하면
        매 크롤마다 404 를 한 번씩 때린다."""
        self.assertEqual(
            derive_feed_url(
                board_url="https://school.jbedu.kr/kacheon/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/kacheon/M010401/",
            ),
            ("https://school.jbedu.kr/rss/kacheon/M010401.do", FLAVOR_JBEDU_JSON),
        )
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.use.go.kr/abc/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/abc/M010401/",
            )
        )
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.cbe.go.kr/abc/M010401/index.do",
                parser_family="slash_view_like",
                board_key="/abc/M010401/",
            )
        )

    def test_other_families_have_no_rule(self):
        for family in ("boardcnts_like", "sen_like", "xboard_like", "generic", "gen_c2z_home_like"):
            self.assertIsNone(
                derive_feed_url(board_url="https://x.kr/list.do", parser_family=family, board_key="k")
            )

    def test_select_ntt_needs_both_params(self):
        self.assertIsNone(
            derive_feed_url(
                board_url="https://school.gyo6.net/gacheon/na/ntt/selectNttList.do?mi=1",
                parser_family="select_ntt_like",
                board_key="mi=1|bbsId=None",
            )
        )


class ShouldProbeTest(unittest.TestCase):
    NOW = datetime(2026, 8, 27, tzinfo=UTC)

    def test_empty_state_probes(self):
        self.assertTrue(should_probe({}, board_key="k", now=self.NOW))
        self.assertTrue(should_probe(None, board_key="k", now=self.NOW))

    def test_ok_does_not_reprobe(self):
        state = {"status": "ok", "board_key": "k", "checked_at": self.NOW.isoformat()}
        self.assertFalse(should_probe(state, board_key="k", now=self.NOW))

    def test_board_key_change_invalidates_ok(self):
        state = {"status": "ok", "board_key": "old", "checked_at": self.NOW.isoformat()}
        self.assertTrue(should_probe(state, board_key="new", now=self.NOW))

    def test_unsupported_is_locked_for_30_days(self):
        recent = {"status": "unsupported", "board_key": "k",
                  "checked_at": (self.NOW - timedelta(days=29)).isoformat()}
        stale = {"status": "unsupported", "board_key": "k",
                 "checked_at": (self.NOW - timedelta(days=31)).isoformat()}
        self.assertFalse(should_probe(recent, board_key="k", now=self.NOW))
        self.assertTrue(should_probe(stale, board_key="k", now=self.NOW))

    def test_unknown_reprobes_next_crawl(self):
        state = {"status": "unknown", "board_key": "k", "checked_at": self.NOW.isoformat()}
        self.assertTrue(should_probe(state, board_key="k", now=self.NOW))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_feed_probe -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.crawler.rss_feed'`

- [ ] **Step 3: 최소 구현 — 상태 타입과 URL 유도**

`backend/app/crawler/rss_feed.py` 생성:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import re
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

FLAVOR_GYO6_RSS2 = "gyo6_rss2"
FLAVOR_JBEDU_JSON = "jbedu_json"
JBEDU_RSS_HOST = "school.jbedu.kr"
UNSUPPORTED_RECHECK_DAYS = 30


@dataclass(frozen=True)
class RssItem:
    """두 flavor 를 하나로 정규화한 항목. body_html/attachments 는 저장만 하고 소비하지 않는다."""

    title: str
    link: str  # 정규화 후 절대 URL
    published_at: str | None = None
    guid: str | None = None
    body_html: str | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RssFeedState:
    status: str  # "ok" | "unknown" | "unsupported"
    flavor: str | None
    url: str | None
    board_key: str | None
    item_count: int
    checked_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "flavor": self.flavor,
            "url": self.url,
            "board_key": self.board_key,
            "item_count": self.item_count,
            "checked_at": self.checked_at,
            "error": self.error,
        }


def derive_feed_url(*, board_url: str, parser_family: str, board_key: str) -> tuple[str, str] | None:
    """(피드 URL, flavor). 규칙에 맞지 않으면 None.

    새 URL 빌더를 만들지 않는다 — notice_post_extractor 가 이미 만든 board_key 를
    그대로 쓰고 경로만 치환한다.
    """
    host = (urlparse(board_url).hostname or "").lower()

    if parser_family == "select_ntt_like":
        params = dict(
            item.split("=", 1) for item in board_key.split("|") if "=" in item
        )
        mi = (params.get("mi") or "").strip()
        bbs_id = (params.get("bbsId") or "").strip()
        if not mi or not bbs_id or "None" in (mi, bbs_id):
            return None
        feed = urlparse(_feed_path(board_url))
        return (
            urlunparse(
                (feed.scheme, feed.netloc, feed.path, "", urlencode([("mi", mi), ("bbsId", bbs_id)]), "")
            ),
            FLAVOR_GYO6_RSS2,
        )

    # ⚠️ 전북 규칙은 호스트 고정이 필수다. slash_view_like 는 울산(school.use.go.kr)·
    # 충북(school.cbe.go.kr)에서도 잡히는데(notice_post_extractor.py:239) 그 둘은 RSS 가
    # 없다. 호스트 검사 없이 적용하면 매 크롤마다 404 를 한 번씩 때린다.
    if parser_family == "slash_view_like" and host == JBEDU_RSS_HOST:
        segments = [item for item in board_key.split("/") if item]
        if len(segments) != 2:
            return None
        school_id, board_code = segments
        return (f"https://{JBEDU_RSS_HOST}/rss/{school_id}/{board_code}.do", FLAVOR_JBEDU_JSON)

    return None


def _feed_path(board_url: str) -> str:
    """notice_post_extractor._replace_path_suffix(:1340-1343) 와 같은 규칙.

    순환 import(그쪽이 이 모듈을 import 한다)를 피하려고 지역 사본을 둔다.
    """
    parsed = urlparse(board_url)
    path = (
        parsed.path.replace("selectNttList.do", "selectRssFeed.do")
        if "selectNttList.do" in parsed.path
        else parsed.path.rstrip("/") + "/selectRssFeed.do"
    )
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def should_probe(raw: dict[str, Any] | None, *, board_key: str, now: datetime) -> bool:
    """스펙 §4.1 재시도 표."""
    if not isinstance(raw, dict) or not raw.get("status"):
        return True
    if raw.get("board_key") != board_key:
        return True  # 게시판이 바뀌면 저장된 피드 URL 은 다른 게시판을 가리킨다
    status = str(raw.get("status"))
    if status == "ok":
        return False
    if status == "unsupported":
        checked_at = _parse_iso(raw.get("checked_at"))
        if checked_at is None:
            return True
        return now - checked_at >= timedelta(days=UNSUPPORTED_RECHECK_DAYS)
    return True  # unknown 은 일시적 실패로 보고 다음 크롤에서 재프로브


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_feed_probe -v
```

Expected: PASS (9 tests)

- [ ] **Step 5: 피드 GET을 붙인다 (완화 TLS 폴백 포함)**

같은 파일 상단의 import에 추가하고 아래 함수를 잇는다:

```python
import ssl

import httpx

from app.crawler.http_client import DEFAULT_HEADERS, legacy_ssl_context, make_async_client_for_url
```

```python
def relaxed_ssl_context() -> ssl.SSLContext:
    """crawler.http_client.legacy_ssl_context() + OP_LEGACY_SERVER_CONNECT.

    school.jbedu.kr / school.gyo6.net 은 기본 legacy 호스트 목록
    (http_client.DEFAULT_LEGACY_TLS_HOSTS = sen.ms.kr, gen.ms.kr)에 없는데,
    OpenSSL 3 의 unsafe-legacy-renegotiation 제한에서 연결이 끊긴다(WinError 10054).
    공용 호스트 목록·공용 컨텍스트를 바꾸지 않으려고 여기서만 옵션을 얹는다.
    """
    context = legacy_ssl_context()
    option = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if option:
        context.options |= option
    return context


async def fetch_feed(url: str, *, timeout: float) -> tuple[int, bytes]:
    """피드 1회 GET. 전송 오류일 때만 완화 컨텍스트로 한 번 더 시도한다."""
    try:
        async with make_async_client_for_url(url=url, timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code, response.content
    except httpx.TransportError:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            verify=relaxed_ssl_context(),
        ) as client:
            response = await client.get(url)
            return response.status_code, response.content
```

- [ ] **Step 6: 실제 두 엔드포인트가 이 코드로 붙는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
from app.crawler.rss_feed import fetch_feed

async def main():
    for url in (
        'https://school.jbedu.kr/rss/kacheon/M010401.do',
        'https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051',
    ):
        try:
            status, body = await asyncio.wait_for(fetch_feed(url, timeout=20.0), timeout=40)
            head = body[:60].decode('utf-8', errors='replace').replace(chr(10), ' ')
            print(f'{status} {len(body):>8}B  {url}')
            print(f'         head={head!r}')
        except Exception as exc:
            print(f'ERR  {type(exc).__name__}  {url}')

asyncio.run(main())
"
```

Expected: 두 줄 모두 `200`. 전북은 `{` 로 시작하는 JSON, 경북은 `<?xml` 또는 `<rss`. **`ERR`가 나오면 중단하고 보고할 것** — 완화 컨텍스트로도 안 붙는다는 뜻이다.

- [ ] **Step 7: 커밋 (프로브 본체는 Task 11의 파서가 있어야 완성된다)**

```bash
git add backend/app/crawler/rss_feed.py backend/tests/test_rss_feed_probe.py
git commit -m "feat(crawler): RSS 피드 URL 유도 + 재프로브 규칙 + 피드 GET

교육청 CMS 일부에 문서화되지 않은 RSS 엔드포인트가 살아 있다.
경북(selectRssFeed.do)·전북(/rss/{학교}/{보드}.do) 두 규칙만 둔다.

전북 규칙은 호스트를 school.jbedu.kr 로 고정한다 — slash_view_like 는
울산·충북에서도 잡히는데 그 둘은 RSS 가 없어서, 호스트 검사가 없으면
매 크롤마다 404 를 한 번씩 때린다.

unsupported 는 30일 잠금, unknown 은 다음 크롤 재프로브, ok 는
board_key 가 바뀌었을 때만 무효화한다.

두 호스트가 기본 legacy TLS 목록에 없고 OpenSSL 3 에서 연결이 끊기므로
전송 오류일 때만 OP_LEGACY_SERVER_CONNECT 를 얹어 한 번 더 시도한다.
공용 호스트 목록은 건드리지 않는다."
```

---

## Task 10: 프로브를 크롤 파이프라인에 접합 (기록만)

프로브는 **게시판 탐지가 성공한 직후, 학교당 1회** 돈다. 온보딩 최초 크롤과 정기 크롤이 같은 함수를 타므로 진입점이 하나다(`discover_and_save_school_board`, `school_crawler_service.py:107-128`). 그 시점에는 게이트 4에 쓸 `sample_posts` 제목이 손에 있다 — 나중에 독립적으로 프로브하면 이 대조가 불가능해진다.

**Files:**
- Modify: `backend/app/crawler/rss_feed.py` (`parse_feed` 자리표시자 없이 `probe_rss_feed` 완성은 Task 11 뒤로 미루지 않기 위해 이 Task에서 게이트만 먼저 넣는다 — 아래 Step 1 참조)
- Modify: `backend/app/services/school_crawler_service.py` (`discover_and_save_school_board`, `_fetch_school_row`, 읽기/쓰기 헬퍼 2개)
- Modify: `backend/app/core/config.py` (플래그 1개)

**Interfaces:**
- Consumes: Task 8의 `school_crawl_state.rss_feed`, Task 9의 `derive_feed_url` · `should_probe` · `fetch_feed`
- Produces: `probe_rss_feed(board_url, parser_family, board_key, sample_titles, timeout) -> RssFeedState`, `_read_rss_feed(school_id)`, `_write_rss_feed(school_id, payload)`. Task 12가 저장된 `ok` 상태를 읽는다.

- [ ] **Step 1: 4단 게이트 프로브를 쓴다**

`backend/app/crawler/rss_feed.py` 끝에 이어 쓴다. (파싱 본체 `parse_feed`는 Task 11에서 채운다 — 지금은 «파싱 실패 = unsupported» 경로만 성립하면 되므로 최소 구현을 먼저 둔다.)

```python
def parse_feed(body: bytes, *, flavor: str, feed_url: str) -> list[RssItem]:
    """flavor 별 파싱. Task 11 에서 두 flavor 를 채운다."""
    raise NotImplementedError(flavor)


async def probe_rss_feed(
    *,
    board_url: str,
    parser_family: str,
    board_key: str,
    sample_titles: list[str],
    timeout: float,
) -> RssFeedState:
    """4단 게이트를 **전부** 통과해야 ok 다(스펙 §4.3)."""
    derived = derive_feed_url(board_url=board_url, parser_family=parser_family, board_key=board_key)
    if not derived:
        return _state("unsupported", None, None, board_key, 0, "no_feed_rule")
    feed_url, flavor = derived

    try:
        status_code, body = await fetch_feed(feed_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 프로브 실패는 크롤에 영향을 주지 않는다.
        return _state("unknown", flavor, feed_url, board_key, 0, f"fetch_{type(exc).__name__}")

    # 게이트 1 — HTTP 200. 부산·제주·경남의 404/400 을 거른다.
    if status_code != 200:
        return _state("unsupported", flavor, feed_url, board_key, 0, f"http_{status_code}")

    # 게이트 2 — 파싱 성공. 세종처럼 200 에 오류 HTML 을 담는 경우를 거른다.
    # Content-Type 은 신뢰하지 않는다: 전북은 JSON 을 주고 첨부는 octet-stream 을 준다.
    try:
        items = parse_feed(body, flavor=flavor, feed_url=feed_url)
    except Exception:  # noqa: BLE001 - 파싱 실패는 '이 엔드포인트는 RSS 가 아니다' 이다.
        return _state("unsupported", flavor, feed_url, board_key, 0, "parse_failed")

    # 게이트 3 — 비어있지 않음. item 0건은 ok 가 아니라 unknown 이다.
    # 방학 중 빈 게시판과 서울 AJAX 식 '조용한 0건' 을 구분할 수 없기 때문.
    usable = [item for item in items if item.title and (item.link or item.guid)]
    if not usable:
        return _state("unknown", flavor, feed_url, board_key, len(items), "empty_feed")

    # 게이트 4 — 교차검증. 같은 크롤에서 HTML 파서가 뽑은 제목과 교집합 ≥ 1.
    # mi/bbsId 가 다른 게시판(급식·앨범)을 가리키면 여기서 걸린다.
    if sample_titles and not titles_intersect([item.title for item in usable[:5]], sample_titles):
        return _state("unknown", flavor, feed_url, board_key, len(usable), "title_mismatch")

    return _state("ok", flavor, feed_url, board_key, len(usable), None)


def titles_intersect(feed_titles: list[str], sample_titles: list[str]) -> bool:
    """HTML 목록 제목에는 '[가정통신문] … NEW 첨부' 같은 잡음이 섞이므로 포함 관계로 본다."""
    samples = [item for item in (_compact(value) for value in sample_titles) if item]
    for title in feed_titles:
        needle = _compact(title)
        if len(needle) < 4:
            continue
        if any(needle in sample or sample in needle for sample in samples):
            return True
    return False


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").replace("\xa0", " ")).lower()


def _state(
    status: str,
    flavor: str | None,
    url: str | None,
    board_key: str,
    item_count: int,
    error: str | None,
) -> RssFeedState:
    return RssFeedState(
        status=status,
        flavor=flavor,
        url=url,
        board_key=board_key,
        item_count=item_count,
        checked_at=datetime.now(UTC).isoformat(),
        error=error,
    )
```

- [ ] **Step 2: 플래그를 추가한다**

`backend/app/core/config.py`의 `crawler_watermark_enabled` 정의 아래에 추가:

```python
    # RSS 프로브: 게시판 탐지 성공 직후 학교당 1회, 결과만 school_crawl_state.rss_feed 에
    # 기록한다(수집에는 쓰지 않는다). 실패는 크롤 결과에 영향을 주지 않는 best-effort.
    crawler_rss_probe_enabled: bool = Field(
        default=True,
        alias="CRAWLER_RSS_PROBE_ENABLED",
    )
```

- [ ] **Step 3: `rss_feed`를 읽도록 select를 넓힌다**

`backend/app/services/school_crawler_service.py:341-344`의 select 문자열에 `rss_feed`를 더한다:

```python
        .select(
            "school_id,crawl_board_url,crawl_board_kind,crawl_status,"
            "crawl_error_message,crawl_result,crawl_last_checked_at,rss_feed"
        )
```

- [ ] **Step 4: 읽기·쓰기·프로브 함수를 쓴다**

같은 파일의 `_write_board_watermarks`(:721-727) 바로 아래에 추가:

```python
def _read_rss_feed(school_id: str) -> dict[str, Any]:
    try:
        rows = (
            get_supabase_client()
            .table("school_crawl_state")
            .select("rss_feed")
            .eq("school_id", school_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001 - 프로브는 best-effort.
        LOGGER.warning("Failed to read rss_feed: school_id=%s", school_id, exc_info=True)
        return {}
    raw = rows[0].get("rss_feed") if rows else None
    return raw if isinstance(raw, dict) else {}


def _write_rss_feed(school_id: str, payload: dict[str, Any]) -> None:
    try:
        get_supabase_client().table("school_crawl_state").update(
            {"rss_feed": payload}
        ).eq("school_id", school_id).execute()
    except Exception:  # noqa: BLE001 - best-effort; 다음 크롤에서 다시 기록된다.
        LOGGER.warning("Failed to write rss_feed: school_id=%s", school_id, exc_info=True)


async def _probe_and_save_rss_feed(result: SchoolBoardDiscoveryResult) -> None:
    """게시판 탐지 성공 직후 학교당 1회. best-effort — 실패해도 크롤 결과에 손대지 않는다.

    _write_board_watermarks(:721-727)와 같은 방식이다. 이 시점에 프로브하는 이유는
    게이트 4(제목 교차검증)에 쓸 sample_posts 가 손에 있기 때문이다.
    """
    settings = get_settings()
    if not settings.crawler_rss_probe_enabled:
        return
    if not result.board_url or not result.parser_family:
        return

    valid_posts = [post for post in result.sample_posts if post.status in POST_SUCCESS_STATUSES]
    if not valid_posts:
        return
    board_key = valid_posts[0].board_key

    try:
        if not should_probe(
            _read_rss_feed(result.school_id),
            board_key=board_key,
            now=datetime.now(UTC),
        ):
            return
        state = await probe_rss_feed(
            board_url=result.board_url,
            parser_family=result.parser_family,
            board_key=board_key,
            sample_titles=[post.title for post in valid_posts],
            timeout=settings.crawler_timeout_seconds,
        )
        _write_rss_feed(result.school_id, state.to_dict())
        LOGGER.info(
            "rss probe: school_id=%s status=%s flavor=%s items=%s error=%s",
            result.school_id, state.status, state.flavor, state.item_count, state.error,
        )
    except Exception:  # noqa: BLE001 - 프로브는 크롤을 절대 실패시키지 않는다.
        LOGGER.warning("Failed to probe rss feed: school_id=%s", result.school_id, exc_info=True)
```

import에 추가:

```python
from app.crawler.rss_feed import RssFeedState, probe_rss_feed, should_probe
```

- [ ] **Step 5: 호출을 한 줄 넣는다**

`discover_and_save_school_board`(:124-128):

```python
        if result.status == "school_not_found":
            return result
        _save_school_discovery_result(result)
        await _probe_and_save_rss_feed(result)
        _save_discovered_notice_candidates(result)
        return result
```

- [ ] **Step 6: 기존 백엔드 테스트가 안 깨졌는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과 (`test_school_crawler_watermark.py`, `test_scheduled_crawler_service.py` 포함)

- [ ] **Step 7: 프로브가 실제 학교에서 어떻게 판정하는지 본다 (기록만)**

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
export NEIS_API_KEY="$(gcloud secrets versions access latest --secret=neis-api-key)"
PYTHONPATH=backend backend/venv/Scripts/python.exe -m app.jobs.scheduled_school_crawler --force 2>&1 | tail -5

python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/school_crawl_state?select=school_id,crawl_board_url,crawl_status,rss_feed')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
for row in json.loads(urllib.request.urlopen(r, timeout=60).read().decode()):
    host = (row.get('crawl_board_url') or '///').split('/')[2]
    print(f\"{host:32} {row.get('crawl_status'):24} {json.dumps(row.get('rss_feed'), ensure_ascii=False)}\")
"
```

Expected 판정 기준:
- 호스트가 `school.gyo6.net` / `school.jbedu.kr` / `*-e.goe*.kr` / `*.jge.es.kr` 인데 `unsupported`면 **미탐** — §4.2 URL 유도 규칙을 의심한다.
- 그 외 호스트(`*.icees.kr`, `*.sen.es.kr`, `school.cbe.go.kr` …)는 `unsupported` + `error: "no_feed_rule"`이 정상이다.
- `status: "ok"`가 나온 학교의 `rss_feed.url`을 **손으로 열어 본다.** 그 학교의 가정통신문/공지 게시판이 아니면 **오탐** — 게이트 4가 뚫린 것이다.

- [ ] **Step 8: 프로브 도입이 크롤 결과를 바꾸지 않았는지 확인한다**

```bash
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
r = urllib.request.Request(u + '/rest/v1/school_crawl_state?select=school_id,crawl_status,crawl_result')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
for row in json.loads(urllib.request.urlopen(r, timeout=60).read().decode()):
    cr = row.get('crawl_result') or {}
    print(row['school_id'][:8], row.get('crawl_status'), 'success_count=', cr.get('success_count'))
"
```

Expected: `crawl_status`와 `success_count`가 프로브 도입 전 값과 동일. **달라지면 프로브가 best-effort 경계를 넘은 것이다 — 중단하고 보고할 것.**

- [ ] **Step 9: 커밋**

```bash
git add backend/app/crawler/rss_feed.py backend/app/services/school_crawler_service.py backend/app/core/config.py
git commit -m "feat(crawler): RSS 프로브를 게시판 탐지 직후에 1회 돌려 기록만 한다

수집에는 아직 쓰지 않는다. 한 주기 '기록만' 돌려서 게이트 4(제목 교차검증)의
오탐률을 수집을 켜기 전에 본다 — 이게 이 사업에서 가장 값싼 안전장치다.

4단 게이트를 전부 통과해야 ok 다:
  1 HTTP 200 (부산·제주·경남의 404/400 제거)
  2 파싱 성공 (Content-Type 은 신뢰하지 않는다)
  3 item >= 1 — 0건은 ok 가 아니라 unknown. 방학 중 빈 게시판과
    서울 AJAX 식 '조용한 0건' 을 구분할 수 없다
  4 RSS 제목 상위 5건과 같은 크롤의 sample_posts 제목의 교집합 >= 1

프로브 실패는 rss_feed 에만 기록하고 SchoolBoardDiscoveryResult 에는
손대지 않는다(_write_board_watermarks 와 같은 best-effort)."
```

---

## Task 11: 두 flavor 파싱 + `link` 정규화

경북 XML의 `link`는 **스킴·호스트가 없고 첫 경로 세그먼트가 두 번 반복된다**(`school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?…`) — 생성기 버그다. 전북 JSON의 `link`는 절대 URL로 정상이다.

**Files:**
- Modify: `backend/app/crawler/rss_feed.py` (`parse_feed` 본체, `normalize_rss_link`)
- Create: `backend/tests/test_rss_feed_parse.py`

**Interfaces:**
- Consumes: Task 9의 `RssItem`
- Produces: `parse_feed(body, flavor, feed_url) -> list[RssItem]`, `normalize_rss_link(raw, feed_url) -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_rss_feed_parse.py` 생성:

```python
import unittest

from app.crawler.rss_feed import (
    FLAVOR_GYO6_RSS2,
    FLAVOR_JBEDU_JSON,
    normalize_rss_link,
    parse_feed,
)

FEED_URL = "https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051"


class NormalizeRssLinkTest(unittest.TestCase):
    def test_adds_scheme_and_drops_duplicated_leading_segment(self):
        raw = "school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?nttSn=123&mi=119615"
        self.assertEqual(
            normalize_rss_link(raw, FEED_URL),
            "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=123&mi=119615",
        )

    def test_path_only_link_is_joined_to_feed_host(self):
        self.assertEqual(
            normalize_rss_link("/gacheon/na/ntt/selectNttInfo.do?nttSn=9", FEED_URL),
            "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=9",
        )

    def test_repetition_rule_is_leading_and_exactly_twice(self):
        # 중간 반복(/na/na/)과 3회 반복(/a/a/a/)은 건드리지 않는다
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/g/na/na/x.do", FEED_URL),
            "https://school.gyo6.net/g/na/na/x.do",
        )
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/a/a/a/x.do", FEED_URL),
            "https://school.gyo6.net/a/a/x.do",
        )

    def test_foreign_host_is_dropped(self):
        self.assertEqual(normalize_rss_link("https://evil.example.com/a", FEED_URL), "")
        self.assertEqual(normalize_rss_link("", FEED_URL), "")

    def test_trailing_slash_and_fragment_removed(self):
        self.assertEqual(
            normalize_rss_link("https://school.gyo6.net/gacheon/board/#top", FEED_URL),
            "https://school.gyo6.net/gacheon/board",
        )


class ParseFeedTest(unittest.TestCase):
    def test_rss2_reads_title_link_pubdate_and_file(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>\xea\xb0\x80\xec\xb2\x9c\xec\xb4\x88</title>
<item>
  <title>2\xed\x95\x99\xea\xb8\xb0 \xec\x95\x88\xeb\x82\xb4</title>
  <link>school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?nttSn=777&amp;mi=119615</link>
  <pubDate>Mon, 24 Aug 2026 06:13:47 +0900</pubDate>
  <guid>777</guid>
  <file><fileNm>\xeb\xa6\xac\xed\x94\x8c\xeb\xa6\xbf.pdf</fileNm>
  <dwldUrl>school.gyo6.net/gacheon/common/nttFileDownload.do?fileKey=e3dead</dwldUrl></file>
</item>
<item><title></title><link>school.gyo6.net/x</link></item>
</channel></rss>"""
        items = parse_feed(xml, flavor=FLAVOR_GYO6_RSS2, feed_url=FEED_URL)
        self.assertEqual(len(items), 1)  # 제목 빈 item 은 버린다
        item = items[0]
        self.assertEqual(item.link, "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?nttSn=777&mi=119615")
        self.assertEqual(item.guid, "777")
        self.assertEqual(len(item.attachments), 1)
        self.assertTrue(item.attachments[0]["url"].startswith("https://school.gyo6.net/"))

    def test_jbedu_json_reads_description_value_as_body(self):
        payload = (
            '{"items":[{"title":"\\uacf5\\uc9c0","link":'
            '"https://school.jbedu.kr/kacheon/M010401/view/6882610",'
            '"pubDate":"2026-08-24T06:13:47","guid":"6882610",'
            '"description":{"value":"<p>\\ubcf8\\ubb38</p>"}}]}'
        ).encode("utf-8")
        items = parse_feed(payload, flavor=FLAVOR_JBEDU_JSON,
                           feed_url="https://school.jbedu.kr/rss/kacheon/M010401.do")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://school.jbedu.kr/kacheon/M010401/view/6882610")
        self.assertEqual(items[0].body_html, "<p>본문</p>")
        self.assertEqual(items[0].attachments, [])

    def test_html_error_page_raises(self):
        with self.assertRaises(Exception):
            parse_feed(b"<html><body>error</body></html>", flavor=FLAVOR_GYO6_RSS2, feed_url=FEED_URL)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_feed_parse -v
```

Expected: FAIL — `ImportError: cannot import name 'normalize_rss_link'` (또는 `parse_feed`의 `NotImplementedError`)

- [ ] **Step 3: 최소 구현 — link 정규화**

`backend/app/crawler/rss_feed.py`에 추가 (import에 `import json`, `from xml.etree import ElementTree` 추가):

```python
def normalize_rss_link(raw: str, feed_url: str) -> str:
    """스펙 §5.2 규칙 1~5. 경북 생성기 버그(스킴 없음 + 선두 세그먼트 2회 반복) 대응.

    규칙 4(호스트 검사)가 외부 링크·오픈 리다이렉트를 차단한다.
    실패하면 빈 문자열을 돌려주고 그 item 만 버린다 — 크롤은 계속된다.
    """
    value = (raw or "").strip()
    if not value:
        return ""
    feed = urlparse(feed_url)

    # 규칙 1·2 — 스킴/호스트 보정
    if value.startswith("//"):
        value = f"{feed.scheme}:{value}"
    elif value.startswith("/"):
        value = urljoin(f"{feed.scheme}://{feed.netloc}", value)
    elif not urlparse(value).scheme:
        value = f"{feed.scheme}://{value}"

    parsed = urlparse(value)
    if not parsed.netloc:
        return ""

    # 규칙 4 — 피드 호스트와 다르면 버린다
    if (parsed.hostname or "").lower() != (feed.hostname or "").lower():
        return ""

    # 규칙 3 — 선두 세그먼트가 정확히 2회 연속 반복이면 하나 제거.
    # 맹목적 중복 제거가 아니다: 선두에 한정하고 중간의 /na/na/ 는 건드리지 않는다.
    segments = parsed.path.split("/")
    if len(segments) >= 3 and segments[0] == "" and segments[1] and segments[1] == segments[2]:
        segments = [segments[0], *segments[2:]]
    path = "/".join(segments)

    # 규칙 5 — fragment·params 를 떨어내고 끝 슬래시를 없앤다
    # (notice_post_extractor._normalize_url:1371-1373 과 같은 모양).
    return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", parsed.query, ""))
```

- [ ] **Step 4: 최소 구현 — 두 flavor 파싱**

`parse_feed`의 `raise NotImplementedError` 자리를 교체한다:

```python
def parse_feed(body: bytes, *, flavor: str, feed_url: str) -> list[RssItem]:
    """flavor 별 파싱. 실패하면 예외를 올린다 — 호출부(게이트 2)가 unsupported 로 접는다.

    Content-Type 은 보지 않는다: 전북은 JSON 을 주고 첨부는 octet-stream 을 준다.
    """
    if flavor == FLAVOR_JBEDU_JSON:
        return _parse_jbedu_json(body, feed_url)
    if flavor == FLAVOR_GYO6_RSS2:
        return _parse_rss2(body, feed_url)
    raise ValueError(f"unknown rss flavor: {flavor}")


def _parse_rss2(body: bytes, feed_url: str) -> list[RssItem]:
    root = ElementTree.fromstring(body)
    channel = root.find("channel")
    if channel is None:
        channel = root
    items: list[RssItem] = []
    for node in channel.findall("item"):
        title = _node_text(node, "title")
        link = normalize_rss_link(_node_text(node, "link") or _node_text(node, "guid"), feed_url)
        if not title or not link:
            continue
        attachments = []
        for file_node in node.findall("file"):
            name = _node_text(file_node, "fileNm")
            url = normalize_rss_link(_node_text(file_node, "dwldUrl"), feed_url)
            if name and url:
                attachments.append({"name": name, "url": url})
        items.append(
            RssItem(
                title=title,
                link=link,
                published_at=_node_text(node, "pubDate") or None,
                guid=_node_text(node, "guid") or None,
                body_html=_node_text(node, "description") or None,
                attachments=attachments,
            )
        )
    if not items and channel.find("item") is None and channel is root:
        raise ValueError("rss channel not found")
    return items


def _parse_jbedu_json(body: bytes, feed_url: str) -> list[RssItem]:
    payload = json.loads(body.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("jbedu rss payload is not an object")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("jbedu rss payload has no items[]")

    items: list[RssItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        link = normalize_rss_link(str(raw.get("link") or ""), feed_url)
        if not title or not link:
            continue
        description = raw.get("description")
        body_html = description.get("value") if isinstance(description, dict) else None
        items.append(
            RssItem(
                title=title,
                link=link,
                published_at=str(raw.get("pubDate") or "") or None,
                guid=str(raw.get("guid") or "") or None,
                body_html=str(body_html) if body_html else None,
                attachments=[],
            )
        )
    return items


def _node_text(node: Any, tag: str) -> str:
    child = node.find(tag)
    if child is None:
        return ""
    return " ".join((child.text or "").split())
```

- [ ] **Step 5: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_feed_parse backend.tests.test_rss_feed_probe -v
```

Expected: PASS (전부)

- [ ] **Step 6: 실물 피드 두 개로 끝까지 돌려 본다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -c "
import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
from app.crawler.rss_feed import FLAVOR_GYO6_RSS2, FLAVOR_JBEDU_JSON, fetch_feed, parse_feed

CASES = [
    ('https://school.jbedu.kr/rss/kacheon/M010401.do', FLAVOR_JBEDU_JSON),
    ('https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=119615&bbsId=39051', FLAVOR_GYO6_RSS2),
]

async def main():
    for url, flavor in CASES:
        status, body = await fetch_feed(url, timeout=20.0)
        items = parse_feed(body, flavor=flavor, feed_url=url)
        print(f'{flavor}: HTTP {status} items={len(items)}')
        for item in items[:3]:
            print('   ', item.title[:34], '|', item.link)
            if item.attachments:
                print('        첨부', item.attachments[0]['url'][:70])
        hosts = {item.link.split(\"/\")[2] for item in items}
        dup = [i.link for i in items if '/' in i.link and _dup(i.link)]
        print('   호스트', hosts, '| 선두중복 남은 링크', len(dup))

def _dup(link):
    parts = link.split('/')
    return len(parts) > 5 and parts[3] and parts[3] == parts[4]

asyncio.run(main())
"
```

Expected: 두 flavor 모두 `items > 0`, 링크가 `https://` 로 시작, 호스트가 피드 호스트와 동일, `선두중복 남은 링크 0`, 경북은 `첨부` 줄이 보인다

- [ ] **Step 7: 커밋**

```bash
git add backend/app/crawler/rss_feed.py backend/tests/test_rss_feed_parse.py
git commit -m "feat(crawler): RSS 두 flavor 파싱 + link 정규화

경북(RSS 2.0 XML)과 전북(JSON)은 실제로 다른 물건이라 RssItem 하나로 정규화한다.
본문(전북 description.value)과 첨부(경북 file/dwldUrl)는 담기만 하고
이번 사업에서는 소비하지 않는다.

경북 link 는 스킴이 없고 첫 경로 세그먼트가 두 번 반복되는 생성기 버그가 있다.
반복 제거는 선두 세그먼트가 정확히 2회 연속일 때만 적용한다 — /a/a/a/ 나
중간의 /na/na/ 는 건드리지 않는다. 호스트가 피드와 다르면 그 item 을 버린다
(외부 링크·오픈 리다이렉트 차단).

Content-Type 은 보지 않는다: 전북은 JSON 을 주고 첨부는 octet-stream 을 준다."
```

---

## Task 12: 수집 경로 접합 + 🔴 이중 저장 대조

RSS 산출물로 **새 저장 경로를 만들지 않는다.** 기존 `_RawPostCandidate` → `_validate_candidate` → `_post_ref` → `_save_discovered_notice_candidates`를 그대로 통과시킨다. 그러면 워터마크·중복방지·캐시 트림이 전부 공짜로 따라온다.

**핵심 보증**: `detail_url`은 두 경로 모두 `_validate_candidate`가 받은 **최종 응답 URL**(`notice_post_extractor.py:671,706`)이므로 자동으로 같아진다. 나머지 세 값(`cms_key`·`board_key`·`post_id`)만 문자열 단위로 맞추면 된다.

**Files:**
- Modify: `backend/app/crawler/notice_post_extractor.py` (`extract_notice_post_refs` 시그니처 + 분기, `_raw_candidates_from_rss`, `_rss_post_id`, `NoticePostRefResult.source_channel`)
- Modify: `backend/app/services/school_crawler_service.py` (`_rss_feed_from_row`, `_extract_cached_board_posts`, `SchoolBoardDiscoveryResult.source_channel`)
- Modify: `backend/app/core/config.py` (플래그 1개)
- Create: `backend/tests/test_rss_post_candidates.py`

**Interfaces:**
- Consumes: Task 10이 저장한 `rss_feed.status == "ok"`, Task 11의 `parse_feed` · `fetch_feed`
- Produces: `extract_notice_post_refs(..., rss_feed: RssFeedState | None = None)`, `NoticePostRefResult.source_channel: str = "html"`

- [ ] **Step 1: 실패하는 테스트를 쓴다 — 세 값 일치**

`backend/tests/test_rss_post_candidates.py` 생성:

```python
import unittest

from app.crawler.notice_post_extractor import _rss_post_id


class RssPostIdTest(unittest.TestCase):
    def test_select_ntt_uses_same_keys_and_source_as_html(self):
        """notice_post_extractor:306 과 같은 키·같은 순서, :315 와 같은 post_id_source."""
        link = "https://school.gyo6.net/gacheon/na/ntt/selectNttInfo.do?mi=119615&bbsId=39051&nttSn=777"
        self.assertEqual(_rss_post_id(link, "select_ntt_like"), ("777", "href query"))

    def test_select_ntt_falls_back_to_nttid_then_articleid(self):
        self.assertEqual(
            _rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do?nttId=88", "select_ntt_like"),
            ("88", "href query"),
        )
        self.assertEqual(
            _rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do?articleId=99", "select_ntt_like"),
            ("99", "href query"),
        )

    def test_slash_view_uses_same_regex_and_source_as_html(self):
        """notice_post_extractor:417,430 과 같은 정규식·같은 post_id_source."""
        self.assertEqual(
            _rss_post_id("https://school.jbedu.kr/kacheon/M010401/view/6882610", "slash_view_like"),
            ("6882610", "path /view/"),
        )

    def test_unknown_family_yields_nothing(self):
        self.assertEqual(_rss_post_id("https://x.kr/a", "boardcnts_like"), ("", ""))
        self.assertEqual(_rss_post_id("https://x.kr/a/na/ntt/selectNttInfo.do", "select_ntt_like"), ("", ""))

    def test_post_id_sources_are_watermark_eligible(self):
        """'rss' 같은 새 값을 만들면 워터마크 제외목록에는 안 걸리지만 HTML 경로와
        값이 달라져 crawl_result 진단이 갈라진다."""
        from app.services.school_crawler_service import (
            _WATERMARK_EXCLUDED_METHODS,
            _WATERMARK_EXCLUDED_SOURCES,
        )

        for source in ("href query", "path /view/"):
            self.assertNotIn(source, _WATERMARK_EXCLUDED_SOURCES)
        self.assertNotIn("href", _WATERMARK_EXCLUDED_METHODS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_post_candidates -v
```

Expected: FAIL — `ImportError: cannot import name '_rss_post_id'`

- [ ] **Step 3: 최소 구현 — RSS 항목을 기존 후보 타입으로 바꾼다**

`backend/app/crawler/notice_post_extractor.py`의 import에 추가:

```python
from app.crawler.rss_feed import RssFeedState, fetch_feed, parse_feed
```

그리고 `_raw_candidates_from_gemini`(:790) **아래에** 이어 쓴다:

```python
def _rss_post_id(link: str, parser_family: str) -> tuple[str, str]:
    """HTML 경로와 **같은 키·같은 정규식**으로만 뽑는다(:306, :417).

    여기서 다른 값을 만들면 post_uid(:832)가 갈라져 같은 글이 두 행으로 저장되고,
    에러가 나지 않으므로 아무도 모른다.
    """
    if parser_family == "select_ntt_like":
        query = parse_qs(urlparse(link).query)
        post_id = _first(query, "nttSn") or _first(query, "nttId") or _first(query, "articleId")
        return (post_id or "", "href query" if post_id else "")
    if parser_family == "slash_view_like":
        match = SLASH_VIEW_RE.search(urlparse(link).path)
        return (match.group(1), "path /view/") if match else ("", "")
    return ("", "")


async def _raw_candidates_from_rss(
    *,
    rss_feed: RssFeedState,
    parser_family: str,
    max_posts: int,
    timeout: float,
) -> list[_RawPostCandidate]:
    """RSS item[] → _RawPostCandidate.

    board_key 는 프로브가 저장한 값을 **그대로** 쓴다(재계산 금지).
    post_id_source / detail_method 도 HTML 경로의 기존 값을 재사용한다 —
    'rss' 같은 새 문자열을 만들면 워터마크 제외목록에는 안 걸리지만
    crawl_result 진단이 갈라진다.

    실패하면 빈 리스트를 돌려주고 호출부가 HTML 후보를 그대로 쓴다.
    RSS 때문에 크롤이 실패하는 일은 없어야 한다.
    """
    if not rss_feed.url or not rss_feed.flavor or not rss_feed.board_key:
        return []
    try:
        status_code, body = await fetch_feed(rss_feed.url, timeout=timeout)
        if status_code != 200:
            return []
        items = parse_feed(body, flavor=rss_feed.flavor, feed_url=rss_feed.url)
    except Exception:  # noqa: BLE001 - RSS 실패는 항상 HTML 경로로 폴백한다.
        return []

    candidates: list[_RawPostCandidate] = []
    for index, item in enumerate(items[:max_posts]):
        post_id, post_id_source = _rss_post_id(item.link, parser_family)
        if not post_id:
            continue
        candidates.append(
            _RawPostCandidate(
                row_id=f"R{index}",
                title=item.title,
                row_text=item.title,
                board_key=rss_feed.board_key,
                post_id=post_id,
                post_id_source=post_id_source,
                detail_method="href",
                url_candidates=[item.link],
            )
        )
    return _dedupe_raw_candidates(candidates)[:max_posts]
```

- [ ] **Step 4: 통과를 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest backend.tests.test_rss_post_candidates -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: 후보 목록 한 구간만 교체하는 분기를 넣는다**

`extract_notice_post_refs`의 시그니처에 인자를 더한다 (`:73-81`):

```python
async def extract_notice_post_refs(
    *,
    board_url: str,
    cms: CmsDetection,
    warmup_url: str | None,
    gemini_enabled: bool = False,
    max_posts: int = 30,
    timeout: float,
    rss_feed: RssFeedState | None = None,
) -> NoticePostRefResult:
```

`raw_candidates = _extract_raw_candidates(...)`(:146-152) **바로 아래**에 삽입:

```python
            # RSS 는 '게시판 HTML → 후보' 한 구간만 대체한다. 상세 접근 검증
            # (_validate_candidate)은 그대로 탄다 — RSS 가 링크를 준다고 그것이
            # 열린다는 보장은 없고, 로그인 게시판이면 여전히
            # unsupported_login_required 로 떨어져야 한다.
            #
            # 게시판 HTML 을 그대로 먼저 받는 이유: RSS 가 실패했을 때 폴백할
            # 후보와 referer 가 이미 손에 있어야 한다. 요청 1회가 비용이다.
            source_channel = "html"
            if rss_feed is not None:
                rss_candidates = await _raw_candidates_from_rss(
                    rss_feed=rss_feed,
                    parser_family=parser_family,
                    max_posts=max_posts,
                    timeout=timeout,
                )
                if rss_candidates:
                    raw_candidates = rss_candidates
                    source_channel = "rss"
```

그리고 `NoticePostRefResult`에 진단 필드를 더한다 (:44-56 데이터클래스 끝):

```python
    error: str | None = None
    source_channel: str = "html"
```

성공 반환(:218-230)에 한 줄 더한다:

```python
        gemini_used=gemini_used or any(item.gemini_used for item in posts),
        error=None,
        source_channel=source_channel,
    )
```

> `source_channel`은 **진단용이다.** 중복 키(`post_uid`)에도 워터마크 키(`board_key`)에도 섞지 않는다.

- [ ] **Step 6: 서비스 쪽에 플래그와 배선을 넣는다**

`backend/app/core/config.py`에 추가:

```python
    # RSS 수집 경로: rss_feed.status='ok' 인 학교의 목록만 RSS 로 대체한다.
    # 문제가 생기면 false 로 즉시 전 학교가 기존 HTML 경로로 돌아간다.
    crawler_rss_collect_enabled: bool = Field(
        default=False,
        alias="CRAWLER_RSS_COLLECT_ENABLED",
    )
```

`backend/app/services/school_crawler_service.py`의 `_read_rss_feed` 아래에 추가:

```python
def _rss_feed_from_row(row: dict[str, Any]) -> RssFeedState | None:
    """수집에 쓸 수 있는 상태(ok)일 때만 돌려준다."""
    raw = row.get("rss_feed")
    if not isinstance(raw, dict) or raw.get("status") != "ok":
        return None
    url = _optional_str(raw.get("url"))
    flavor = _optional_str(raw.get("flavor"))
    board_key = _optional_str(raw.get("board_key"))
    if not url or not flavor or not board_key:
        return None
    return RssFeedState(
        status="ok",
        flavor=flavor,
        url=url,
        board_key=board_key,
        item_count=int(raw.get("item_count") or 0),
        checked_at=str(raw.get("checked_at") or ""),
        error=None,
    )
```

`_extract_cached_board_posts`(:582-603)에 인자를 더한다:

```python
async def _extract_cached_board_posts(
    *,
    context: _SchoolContext,
    cached_board: _CachedBoard,
    gemini_enabled: bool,
    max_posts: int,
    timeout: float,
    rss_feed: RssFeedState | None = None,
) -> SchoolBoardDiscoveryResult:
    detail_result = await extract_notice_post_refs(
        board_url=cached_board.board_url,
        cms=cached_board.cms,
        warmup_url=context.homepage_url,
        gemini_enabled=gemini_enabled,
        max_posts=max_posts,
        timeout=timeout,
        rss_feed=rss_feed,
    )
```

`_discover_school_board_inner`의 캐시 게시판 호출부(:261-267):

```python
                cached_result = await _extract_cached_board_posts(
                    context=context,
                    cached_board=cached_board,
                    gemini_enabled=gemini_enabled,
                    max_posts=post_limit,
                    timeout=settings.crawler_timeout_seconds,
                    rss_feed=(
                        _rss_feed_from_row(school_row)
                        if settings.crawler_rss_collect_enabled
                        else None
                    ),
                )
```

`SchoolBoardDiscoveryResult`(:37-66)의 마지막 필드 뒤에 진단 필드를 더한다:

```python
    cached_board_failed_status: str | None = None
    source_channel: str = "html"
```

`_build_result_from_detail`의 반환(:494-497)에 한 줄:

```python
        cached_board_failed_status=board.cached_board_failed_status,
        source_channel=detail_result.source_channel,
    )
```

`_save_discovered_notice_candidates`의 `crawl_result`(:748-759)에 한 줄:

```python
            "post_rank": post_rank,
            "source_channel": result.source_channel,
            "post": asdict(post),
```

- [ ] **Step 7: 전체 백엔드 테스트가 통과하는지 확인한다**

```bash
PYTHONPATH=backend backend/venv/Scripts/python.exe -m unittest discover backend/tests
```

Expected: 전부 통과. `DiscoveredPostPreview`는 필드를 바꾸지 않았으므로 `test_school_crawler_watermark.py`가 그대로 통과해야 한다.

- [ ] **Step 8: 🔴 이중 저장 대조 — 이 사업의 단일 최대 검증 항목**

RSS `ok`인 학교 1곳을 골라 **두 경로가 만드는 `source_post_uid`가 문자열 단위로 같은지** 직접 비교한다. 실패해도 에러가 나지 않으므로 반드시 명시적으로 본다.

```bash
export SUPABASE_URL="https://aoihmzewthgyoxtejfwo.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(gcloud secrets versions access latest --secret=supabase-service-role-key)"
SCHOOL_ID=<rss_feed.status='ok' 인 학교 id>

python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
sid = os.environ['SCHOOL_ID']
r = urllib.request.Request(f'{u}/rest/v1/notices?select=source_post_uid,detail_url&school_id=eq.{sid}&order=source_post_uid')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
rows = json.loads(urllib.request.urlopen(r, timeout=60).read().decode())
json.dump(rows, open('/tmp/before.json','w',encoding='utf-8'), ensure_ascii=False)
print('RSS 켜기 전 행 수', len(rows))
" 

# RSS 수집을 켜고 같은 학교를 크롤한다
CRAWLER_RSS_COLLECT_ENABLED=true PYTHONPATH=backend \
  python -m app.jobs.scheduled_school_crawler --school-id "$SCHOOL_ID" --force 2>&1 | tail -3

python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
sid = os.environ['SCHOOL_ID']
r = urllib.request.Request(f'{u}/rest/v1/notices?select=source_post_uid,detail_url,crawl_result&school_id=eq.{sid}&order=source_post_uid')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
after = json.loads(urllib.request.urlopen(r, timeout=60).read().decode())
before = json.load(open('/tmp/before.json', encoding='utf-8'))
b = {x['source_post_uid'] for x in before}
a = {x['source_post_uid'] for x in after}
print('행 수', len(before), '→', len(after))
print('새로 생긴 uid', sorted(a - b)[:10])
print('사라진 uid  ', sorted(b - a)[:10])
ch = {(x.get('crawl_result') or {}).get('source_channel') for x in after}
print('source_channel', ch)
"
```

Expected:
- `행 수` **증가 0** (새 글이 실제로 올라오지 않았다면)
- `새로 생긴 uid` **빈 목록**
- `source_channel` 에 `'rss'` 포함

**행 수가 늘거나 새 uid가 생기면 즉시 중단하고 보고할 것.** `cms_key`·`board_key`·`post_id` 중 하나가 갈라진 것이다. 이 사업의 최대 실패 모드다.

- [ ] **Step 9: 워터마크가 그대로 동작하는지 확인한다**

```bash
CRAWLER_RSS_COLLECT_ENABLED=true PYTHONPATH=backend \
  python -m app.jobs.scheduled_school_crawler --school-id "$SCHOOL_ID" --force 2>&1 | tail -3

python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
sid = os.environ['SCHOOL_ID']
r = urllib.request.Request(f'{u}/rest/v1/school_crawl_state?select=board_watermarks,rss_feed&school_id=eq.{sid}')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
row = json.loads(urllib.request.urlopen(r, timeout=60).read().decode())[0]
print('board_watermarks', json.dumps(row['board_watermarks'], ensure_ascii=False))
print('rss_feed.board_key', (row.get('rss_feed') or {}).get('board_key'))
"
```

Expected: `board_watermarks`의 키가 `rss_feed.board_key`와 **같은 문자열**. 2회차 신규 저장 0건.

- [ ] **Step 10: 링크 정규화 결과를 육안으로 본다**

```bash
python -c "
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
u = os.environ['SUPABASE_URL'].rstrip('/'); k = os.environ['SUPABASE_SERVICE_ROLE_KEY']
sid = os.environ['SCHOOL_ID']
r = urllib.request.Request(f'{u}/rest/v1/notices?select=detail_url&school_id=eq.{sid}&limit=10')
r.add_header('apikey', k); r.add_header('Authorization', 'Bearer ' + k)
for row in json.loads(urllib.request.urlopen(r, timeout=60).read().decode()):
    url = row['detail_url']
    parts = url.split('/')
    dup = len(parts) > 5 and parts[3] and parts[3] == parts[4]
    print('DUP!' if dup else '    ', url)
"
```

Expected: 전부 `https://` 로 시작, `DUP!` 표시 0건, 호스트가 피드 호스트와 동일

- [ ] **Step 11: 로그인 게시판 판정이 우회되지 않는지 확인한다**

RSS 지역 학교 중 로그인 필요한 게시판이 있다면 그 학교를 `CRAWLER_RSS_COLLECT_ENABLED=true`로 크롤한다.

Expected: `crawl_status`가 `unsupported_login_required` 유지. RSS는 목록만 대체하고 `_validate_candidate`(`:651`)를 그대로 타므로 이 판정이 살아 있어야 한다. **`success`로 바뀌면 §1.5 법적 안전선을 넘은 것이다 — 즉시 플래그를 끄고 보고할 것.**

- [ ] **Step 12: RSS 없는 학교의 회귀를 확인한다**

```bash
CRAWLER_RSS_COLLECT_ENABLED=true PYTHONPATH=backend \
  python -m app.jobs.scheduled_school_crawler --force 2>&1 | tail -3
```

Expected: RSS 없는 학교(`rss_feed.status != 'ok'`)의 `crawl_status`·`success_count`가 플래그를 켜기 전과 동일

- [ ] **Step 13: 커밋 (프로덕션 플래그는 기본 off 로 나간다)**

```bash
git add backend/app/crawler/notice_post_extractor.py backend/app/services/school_crawler_service.py backend/app/core/config.py backend/tests/test_rss_post_candidates.py
git commit -m "feat(crawler): RSS 목록을 기존 후보 파이프라인에 주입한다 (기본 off)

새 저장 경로를 만들지 않는다. RSS 항목을 _RawPostCandidate 로 바꿔
기존 _validate_candidate → _post_ref → _save_discovered_notice_candidates 를
그대로 통과시킨다. 워터마크·중복방지·캐시 트림이 공짜로 따라온다.

🔴 cms_key·board_key·post_id 를 재계산하지 않는다:
  cms_key    캐시된 crawl_result.cms_key
  board_key  프로브가 저장한 rss_feed.board_key
  post_id    HTML 경로와 같은 키(nttSn/nttId/articleId)·같은 정규식(/view/(\\d+))
detail_url 은 두 경로 모두 _validate_candidate 가 받은 최종 응답 URL 이라
자동으로 같아진다. 하나라도 어긋나면 같은 글이 두 행으로 저장되고 에러가 없다.

post_id_source·detail_method 도 기존 값을 재사용한다 — 'rss' 같은 새 문자열은
워터마크 제외목록에 안 걸리지만 crawl_result 진단이 갈라진다.
RSS 여부는 crawl_result.source_channel 에 진단용으로만 남긴다.

게시판 HTML 은 그대로 먼저 받는다. RSS 가 실패하면 그 후보로 즉시 폴백한다 —
RSS 는 절대 단독 경로가 되지 않는다.

CRAWLER_RSS_COLLECT_ENABLED 기본값은 false 다."
```

---

## 자체 검토

### 1. 스펙 커버리지

| 스펙 항목 | 담당 Task |
|---|---|
| E1 피드 URL 유도 (§4.2, 전북 호스트 고정) | Task 9 Step 3 |
| E1 4단 게이트 (§4.3) | Task 10 Step 1 |
| E1 저장 위치·`board_key` 무효화 (§4.4) | Task 8, Task 9 `should_probe` |
| E1 실패 시 무영향 (§4.5) | Task 10 Step 4 `_probe_and_save_rss_feed` |
| E2 두 flavor 정규화 (§5.1) | Task 11 Step 4 |
| E2 `link` 정규화 규칙 1~5 (§5.2) | Task 11 Step 3 |
| E2 RSS 실패 시 HTML 폴백 (§5.3) | Task 12 Step 5 (`if rss_candidates:`) |
| E2 본문·첨부 저장만 (§5.4) | Task 11 (`RssItem.body_html` / `attachments` — 읽는 코드 없음) |
| E3 기존 저장 경로 재사용 (§6.1) | Task 12 Step 3·5 |
| E3 🔴 세 값 일치 (§6.2) | Task 12 Step 1·3, 검증 Step 8 |
| E3 워터마크 `post_id_source` 보존 (§6.3) | Task 12 Step 1 마지막 테스트, Step 9 |
| E3 갱신 경로 (§6.4) | 기존 `_update_existing_notice_candidate` 그대로 — 수정 없음 |
| E4 스키마 (§7.3) | Task 4 |
| E4 두 출처 공존 증명 (§7.4) | Task 6 `replace_neis_events` + Task 7 Step 5·7 |
| E4 동기화 설계 (§7.5) | Task 5·6·7 |
| E4 AI 역추출 유지 (§7.6) | 손대지 않음 |
| E5 RESULT 판정 (§9.2) | Task 1(백엔드) · Task 2(프론트) |
| E5 한도 초과 시 배치 중단 (§9.2) | Task 7 Step 1 (`skipped_quota`) |
| E6 프론트 정규화 통일 (§10.2 a) | Task 3 |
| 급식·시간표 변경 없음 (§8) | 계획에 없음 ✔ |
| 배포 순서 (§12) | 「배포 순서」 절 |
| 검증 표 (§13) | Task 3 Step 3·4, Task 4 Step 5·6, Task 7 Step 5·6·7, Task 10 Step 7·8, Task 12 Step 8~12 |

### 2. 자리표시자 점검

"TBD"·"적절히"·"비슷하게" 없음. 모든 코드 Step에 실제 코드가 들어 있다. 단 하나의 예외는 **의도된 것**이다 — Task 10 Step 1의 `parse_feed`가 `raise NotImplementedError`로 먼저 서고 Task 11 Step 4가 채운다. 이유: 게이트 4의 오탐률을 «기록만» 한 주기 보는 것이 배포 순서상 파싱 완성보다 앞서야 하는데, 게이트 1~2까지는 파서 없이도 판정이 성립한다. Task 10 Step 7의 검증은 파서가 없는 상태에서도 «미탐 없음»(URL 유도가 맞았는가)을 볼 수 있다. Task 11 없이 Task 12로 넘어가지 않도록 배포 순서에 명시했다.

### 3. 타입·이름 일관성

- `NeisApiError` / `NeisQuotaExceeded` — Task 1이 정의, Task 5의 `fetch_school_schedule`이 간접 발생시키고 Task 7이 잡는다.
- `SchoolScheduleEntry` — Task 5가 생산, Task 6의 `build_neis_event_rows`가 소비. 필드명 일치.
- `NEIS_SOURCE = "neis"` — Task 4의 `check (source in ('notice_ai','neis'))`와 문자열 일치.
- `RssFeedState` — Task 9가 정의, Task 10이 쓰고 Task 12가 읽는다. `to_dict()` 키 7개가 Task 8 주석의 JSON 모양과 일치.
- `FLAVOR_GYO6_RSS2` / `FLAVOR_JBEDU_JSON` — Task 9가 정의, Task 11의 `parse_feed`가 분기.
- `_rss_post_id`의 반환 `("href query", "path /view/")` — `notice_post_extractor.py:315`·`:430`의 리터럴과 문자열 일치. `_WATERMARK_EXCLUDED_SOURCES`(`school_crawler_service.py:648`)에 없음을 Task 12 Step 1이 테스트로 못박는다.
- `source_channel` — `NoticePostRefResult`·`SchoolBoardDiscoveryResult` 양쪽에 기본값 `"html"`로 추가하므로 기존 생성자 호출부(`_failure_result`, `_result_from_cached_detail_result` 등)가 안 깨진다.
- 순환 import — `rss_feed`는 `http_client`만 import하고 `notice_post_extractor`를 import하지 않는다. 방향은 `notice_post_extractor → rss_feed` 한 쪽뿐이다.

### 4. 스펙과 다르게 간 곳 (근거)

| # | 스펙 | 이 계획 | 이유 |
|---|---|---|---|
| 1 | 마이그레이션 `0037`(rss_feed)·`0038`(school_events source) | **`0039`(source)·`0040`(rss_feed)** | `0037`은 사업 A의 첨부 비공개, `0038`은 사업 F가 쓸 예정이다. 그리고 배포 순서상 `school_events`가 먼저 나가므로 번호도 뒤집었다. |
| 2 | §7.3이 부분 유니크 인덱스를 만들고 §7.5가 «전량 교체» | **`upsert`가 아니라 delete + insert** | 부분 인덱스(`where source='neis'`)는 PostgREST의 `on_conflict` 대상으로 추론되지 않는다. 인덱스는 동시 실행 중복을 막는 **가드**로만 쓴다. |
| 3 | §5.2 규칙 5 «`_normalize_url`과 같은 모양으로 맞춰 중복 방지 인덱스가 걸리게» | 규칙 5는 유지하되, **실제 보증은 다른 데서 온다** | `detail_url`은 `_normalize_url`을 거치지 않는다 — `_post_ref(detail_url=final_url)`(`:706`)로 **최종 응답 URL**이 그대로 저장된다. RSS 경로도 같은 `_validate_candidate`를 타므로 `detail_url`은 자동으로 같아진다. 규칙 5는 «같은 최종 URL로 리다이렉트되게» 하는 전처리다. |
| 4 | §6.3 «`crawl_result["post"]["source_channel"]`» | **`crawl_result["source_channel"]`** | `crawl_result["post"]`는 `asdict(DiscoveredPostPreview)`다. 거기에 필드를 넣으려면 dataclass를 바꿔야 하는데, 그러면 `_dedupe_raw_candidates`·워터마크 테스트가 쓰는 타입이 흔들린다. 한 단계 위에 두면 중복 키·워터마크 키와 확실히 분리된다. |
| 5 | 사용자 지시 «`backend/extractor/http_security.py`의 레거시 TLS를 재사용하라» | **`app/crawler/http_client.legacy_ssl_context()`를 재사용** | 두 함수는 바이트 단위로 같은 구현이다(`http_security.py:35-47` ≡ `http_client.py:57-69`). RSS 모듈이 `app/crawler/` 안에 있으므로 크롤러 쪽 사본을 쓰는 것이 패키지 경계에 맞다. 여기에 `OP_LEGACY_SERVER_CONNECT`만 얹은 `relaxed_ssl_context()`를 새로 두는데, 이는 `school.jbedu.kr`·`school.gyo6.net`이 **기본 legacy 호스트 목록에 없기 때문**이다. 공용 목록·공용 컨텍스트는 건드리지 않는다. |
| 6 | §5.3 그림이 «피드 URL → GET → item[]»으로 게시판 GET을 대체 | **게시판 HTML을 그대로 먼저 받고, 후보 목록만 교체** | RSS가 실패했을 때 폴백할 후보와 referer가 손에 있어야 «RSS 때문에 크롤이 실패하지 않는다»(§5.3, §14)가 성립한다. 요청 1회가 그 값이다. |

### 5. 스펙의 누락·모순

| # | 지점 | 문제 |
|---|---|---|
| 1 | §12 배포 표가 `0037`·`0038`을 쓴다 | §14의 위험 표는 «이 사업은 `0037`부터»라고 적었는데, 사업 A가 `0037`을 이미 쓴다(`0037_notice_attachments_private.sql`). 위 4-①로 정정. |
| 2 | §4.4 값 모양 예시에 `flavor: "gyo6_rss2"` | 그런데 §11.1은 경기·전남도 CMS A라고 한다. 세 시도가 같은 flavor를 쓰는데 이름이 «경북»에서 왔다 — 이름은 그대로 두되(스펙 용어 보존) 주석에 세 시도를 병기했다. |
| 3 | §7.5 «`pSize=100` 1회 호출로 페이징» | 「1회 호출」과 「페이징」이 모순이다. 이 계획은 **페이징**으로 읽어 `SCHOOL_SCHEDULE_MAX_PAGES=10`(최대 1,000행) 상한을 뒀다. |
| 4 | §9.2 «급식·시간표: 캐시된 값이 있으면 그것을 쓴다. 없으면 «지금 불러올 수 없음»을 명시적으로 표시» | **이 계획은 여기까지 하지 않는다.** Task 2는 오류를 «구분해서 올리는 것»까지다. 화면 표시 문구·폴백은 UI 결정이고 스펙에 화면 명세가 없다. 열린 질문으로 남긴다. |
| 5 | §4.1 표에 `unknown` 항목은 있으나 §4.4 값 모양에는 `status: "ok"`만 예시 | `unknown`·`unsupported`일 때 `url`을 남기는지 명시가 없다. 이 계획은 **남긴다**(디버깅에 필요하고, `should_probe`는 `status`만 본다). |
| 6 | §11.2 «등록 학교 8곳 중 RSS 지역이 몇 곳인가 — 미확인» | Task 10 Step 7이 이 질문에 답한다. 다만 **답이 0곳이어도 이 사업은 유효하다**(§11.3) — Task 1~7이 전 학교에 적용된다. |
| 7 | §9.4 «프론트·백엔드가 같은 `NEIS_API_KEY`를 쓰는가 — 미확인» | 이 계획도 확인하지 않는다. `deploy-api-cloud-run.yml`은 `neis-api-key:latest`를 쓰고 프론트 `deploy-cloud-run.yml`은 이 계획이 열어보지 않았다. **선행 준비물에 넣었다.** |

---

## 선행 준비물

Task 착수 전에 사람이 해둬야 하는 것:

| | 항목 | 필요한 Task |
|---|---|---|
| ⬜ | Supabase CLI 로그인 (`supabase link --project-ref aoihmzewthgyoxtejfwo`) | Task 4, 8 |
| ⬜ | 사업 A Task 1 완료 (`0030`·`0034`·`0036` 이력 정합) | Task 4 Step 4 — 안 되어 있으면 `db push`가 그 셋을 함께 적용하려 든다 |
| ⬜ | `gcloud secrets versions access` 권한 (`supabase-service-role-key`, `neis-api-key`) | Task 3~12의 검증 스텝 |
| ⬜ | GitHub Variable `CLOUD_RUN_SCHEDULE_SYNC_JOB` | Task 7 Step 8 |
| ⬜ | Cloud Scheduler 서비스 계정 (`$SCHEDULER_SA_EMAIL` — 기존 크롤 스케줄러와 동일) | Task 7 Step 10 |
| ⬜ | **프론트·백엔드가 같은 `NEIS_API_KEY`를 쓰는지 확인** (`deploy-cloud-run.yml`의 secrets 블록) | Task 1·2 배포 전 (한도가 키 단위라면 §9.3의 계산이 달라진다) |
| ⬜ | **스케줄러 재개 여부 확인** — 메모리 기록상 2026-06-15 발표용으로 크롤/추출 스케줄러 5개가 PAUSED다 | Task 7 Step 10, Task 10 Step 7 |

## 롤백

| 단위 | 롤백 |
|---|---|
| Task 1·2·3 | 커밋 되돌리기 |
| Task 4 | `alter table public.school_events alter column notice_id set not null` 은 **NEIS 행이 있으면 실패한다.** 먼저 `delete from school_events where source='neis'` |
| Task 5·6·7 | `delete from school_events where source = 'neis'` (AI 행 무영향). Cloud Scheduler 일시중지 |
| Task 8 | 컬럼은 남겨도 무해 |
| Task 9·10 | `CRAWLER_RSS_PROBE_ENABLED=false` |
| Task 11·12 | `CRAWLER_RSS_COLLECT_ENABLED=false` → 전 학교가 즉시 기존 HTML 경로 |
