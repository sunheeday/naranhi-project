# 사업 E — 미문서화 RSS · 교육부 공식 API 얹기

기준일: 2026-08-27
상태: 설계 (구현 전)
선행: 없음 (사업 A·C와 독립 배포 가능) / 후행: 없음
방침 공유: 사업 C — **«밀린 것 말고 지금부터 새로 오는 것만»**

---

## 1. 배경

### 1.1 상용 크롤링 서비스가 답이 아닌 이유

이 사업의 출발점은 «학교 12,668곳을 어떻게 긁을 것인가»에 대한 조사 결과다.
결론부터: **상용 서비스로 가면 비싸지고, 그런데도 못 긁는다.**

| 확인 사항 | 의미 |
|---|---|
| 교육청 CMS는 5개 패밀리뿐 (§1.3) | 학교 수는 12,668이지만 «형태»는 5개다 — 직접 파서가 성립한다 |
| 같은 패밀리 안에서도 배포본마다 다르다 | 경남 `*-p.gne.go.kr`은 목록 제목에 실제 href(`selectNttInfo.do?nttSn=`)를 두는데, 같은 CMS를 쓰는 제주·경북·경기는 `<a href="javascript:" data-id="…">`다 → **범용 링크 추종기로는 뚫리지 않는다** |
| 서울 `*.sen.es.kr`은 목록이 정적 HTML에 없다 | `POST /dggb/module/board/selectBoardListAjax.do` (히든폼 전체 + `X-Requested-With` + Referer). **쿠키 없이 호출하면 에러가 아니라 조용히 "0건"** → «새 글 없음»으로 오인하는 함정 |
| WCXB 벤치마크 (arXiv:2605.21097, 2,008페이지 / 1,613도메인 / 13추출기) | Article F1 **0.932**인데 Listing **0.710**. 논문이 명시한 실패 모드가 *"목록에서 카드 하나만 뽑고 나머지 버림"* — 우리가 필요한 건 정확히 목록이다 |
| 첨부의 30%가 HWP | 이를 파싱하는 상용 벤더 **0개** |
| 비용 | 상용 AI 추출 $200/1,000페이지 vs 직접 Gemini $0.70/1,000페이지 = **285배** |
| 한국 IP | 현재 Cloud Run 서울 리전이라 **공짜로 얻고 있다.** 상용으로 가면 프록시 $8/GB를 새로 낸다 |
| Bright Data 이용약관 | **정부 웹사이트를 전 네트워크에서 차단.** 학교 `.es.kr`/`.ms.kr`, 교육청 `.go.kr`이 걸리면 계약해도 못 쓴다 |

저장소는 이미 이 결론대로 만들어져 있다 — `cms_patterns.py`가 CMS 12종을 판별하고
(`backend/app/crawler/cms_patterns.py:21-35`), `notice_post_extractor.py`가 파서 패밀리
6종을 갖는다(`backend/app/crawler/notice_post_extractor.py:273-286`).
**이 분류는 정확하다. 이 사업은 이것을 바꾸지 않는다.**

### 1.2 그런데 «공짜 정문»이 있었다

조사 중 직접 HTTP 요청으로 확인한 사실 — **일부 교육청 CMS에 문서화되지 않은 RSS
엔드포인트가 살아 있다.** UI에 버튼조차 없는 곳에서도 응답한다.

**전북** `https://school.jbedu.kr/rss/{학교ID}/{보드코드}.do` — **JSON** 반환
실측(가천초 `kacheon` / `M010401`): HTTP 200, 240KB, 글 15건. item 필드:
`pubDate` · `title` · `link` · `author` · `description.value`(**본문 HTML 전체**,
`<img src="/files/2026/08/kacheon/….jpg">` 포함) · `enclosures`(빈 배열) · `guid` ·
`categories` · `content` · `uri`
예: `title="학교 구글 계정 정지 및 AIEP 계정 전환 안내"`, `pubDate=2026-08-24T06:13:47`,
`author="가천초"`, `link=".../kacheon/M010401/view/6882610"`

**경북** `https://school.gyo6.net/{학교ID}/na/ntt/selectRssFeed.do?mi={메뉴}&bbsId={보드}`
— **RSS 2.0 XML**. HTTP 200. **`<file>` 태그로 첨부 파일명 + 다운로드 URL 제공**:

```xml
<file><fileNm>경상북도교육청 학생생활과_관계개선프로그램 리플릿(학부모 안내용).pdf</fileNm>
<dwldUrl>school.gyo6.net/gacheon/common/nttFileDownload.do?fileKey=e3dead…</dwldUrl></file>
```

⚠️ `link` 값에 **스킴·호스트가 없고 경로가 중복**(`/gacheon/gacheon/`)되는 생성기 버그가
있다 → 정규화가 필수다(§6.2).

**지역별 동작 현황 (실측)**

| 시도 | RSS | 제공 정보 |
|---|---|---|
| 경북 (`school.gyo6.net`) | ✅ | 목록 + **첨부 파일명·다운로드URL** |
| 전북 (`school.jbedu.kr/rss/`) | ✅ | 목록 + **본문 HTML 전체** (JSON) |
| 경기 (`{학교}-e.goe{지원청}.kr`) | ✅ | 목록만 (`description` 항상 빔, `<file>` 없음) |
| 전남 (`gageodo.jge.es.kr`) | ✅ | 목록 |
| 세종 | ⚠️ | UI에 링크는 있으나 호출 시 오류 |
| 부산 / 제주 / 경남 | ❌ | 404 / 400 |
| 서울·인천·강원·대전·충북·울산 | ❌ | CMS 계열 자체가 RSS 미지원 |

**경북·전남은 UI에 RSS 버튼조차 없는데 엔드포인트가 살아 있다 — 미문서화다.**

RSS를 쓰면 우회되는 문제: `javascript:` 링크 / `data-id` 숨은 속성 /
첨부 `Content-Type: application/octet-stream` / HEAD 405 / 인코딩.

### 1.3 CMS 5개 패밀리 (전부 전자정부 표준프레임워크 기반)

| 패밀리 | URL 패턴 | 시도 | RSS |
|---|---|---|---|
| **A** `na/ntt` | 목록 `/{sysId}/na/ntt/selectNttList.do?mi=&bbsId=`, 상세 `selectNttInfo.do?nttSn=&mi=`, **RSS `selectRssFeed.do?mi=&bbsId=`** | 경기·부산·제주·전남·경북·세종·경남 | 일부 ○ |
| **B** `boardCnts` | `/boardCnts/list.do?boardID=&m=&s=`, 상세 `updateCnt.do?action=view&boardSeq=` | 인천·강원·대전 + 교육부 본부 | ✗ |
| **C** 서울 `/dggb/` | `/{메뉴번호}/subMenu.do` + AJAX POST | 서울 | ✗ |
| **D** `M0102xx` | `/{학교ID}/M010201/index.do`, 상세 `/view/{번호}` | 충북·울산·전북 | 전북만 ○ |
| **E** PHP | `/main/main.php`, `/xboard/board.php?tbnum=` | 광주 | ✗ |

저장소 파서 패밀리와의 대응(`notice_post_extractor.py:233-262`):
A→`select_ntt_like`, B→`boardcnts_like`, C→`sen_like`, D→`slash_view_like`,
E→`xboard_like`/`gen_c2z_home_like`.

### 1.4 NEIS 공식 API — 학사일정·급식은 무료로 존재한다

`https://open.neis.go.kr/hub/{서비스명}?Type=json&pIndex=1&pSize=100`

실재 확인된 서비스: `schoolInfo` · `classInfo` · `schoolMajorinfo` · `schulAflcoinfo` ·
**`SchoolSchedule`(학사일정)** · **`mealServiceDietInfo`(급식식단)** ·
`elsTimetable`/`misTimetable`/`hisTimetable`/`spsTimetable` · `acaInsTiInfo`

**공지사항·가정통신문 API는 없다 — 확정.** `schoolNotice`, `noticeInfo`, `notice`,
`bbsInfo`, `hmttInfo`, `prntsNoti`, `schoolBbs` 전부 `ERROR-310 해당하는 서비스를 찾을
수 없습니다`.

스펙: JSON/XML · **인증키 없이 5건까지 반환** · 인증키 무료 발급 ·
일일 한도 미공개(초과 시 `ERROR-337`).

**저장소 현재 상태 (코드 확인)**

| NEIS 서비스 | 쓰는가 | 위치 |
|---|---|---|
| `schoolInfo` | ✅ | `backend/app/crawler/neis_client.py:104`, `lib/neis.ts:122,170` |
| `mealServiceDietInfo` | ✅ | `lib/neis.ts:299,333` + `meals` 테이블 캐시 (`lib/neis.ts:357,416`) |
| `elsTimetable` 외 3종 | ✅ | `lib/neis.ts:155-164,202` |
| **`SchoolSchedule`** | ❌ | 저장소 전체 검색 결과 **호출 0건** |

즉 **학사일정만 공식 API를 안 쓰고 있다.** 지금 `school_events`는 공지 본문에서
AI로 역추출된다 — `notice_service.py:826` → `_replace_school_events_from_pipeline`
(`backend/app/services/notice_service.py:1125-1193`). 그 결과의 품질 보정을 위해
일회성 스크립트 두 개가 존재한다(`scripts/rebuild_school_events.py`,
`scripts/sweep_footer_dates.py` — 후자는 «게시일/푸터 날짜를 행사로 오인한 행»을
찾아 지우는 스크립트다). **AI 역추출이 구조적으로 노이즈를 만든다는 자백이다.**

**업계 방증**: e알리미(전국 초중고 3곳 중 1곳, 재계약율 95%)가 공식 페이지에서 방식을
그대로 공개한다 — *"일정·급식은 **NEIS 공공정보와의 연동**으로 자동 표출"*,
*"홈페이지 연동 — 원하는 게시판의 글을 알리미로 발송 · 게시판 글 수정/삭제시 자동
적용(24시간 이내)"*. **업계 표준 사업자조차 일정·급식은 공식 API, 공지만 게시판
스크래핑이다.** 우리가 가려는 구조와 정확히 같다.

### 1.5 법적 안전선

대법원 2021도1533 판결은 기술적 보호조치·명시적 이용약관 같은 **객관적으로 드러난
사정**을 기준으로 삼는다. 현재 정책 — 로그인 뒤 게시판은 건드리지 않고
`unsupported_login_required`로 남긴다(`school_crawler_service.py:912`,
`notice_post_extractor.py:213`) — 을 **그대로 유지한다.** RSS는 인증 없이 공개된
엔드포인트이므로 이 선을 넘지 않는다.

---

## 2. 목표 / 비목표

### 목표

1. RSS가 있는 학교는 **HTML 목록 파싱 없이** 신규 글 목록을 얻는다.
2. RSS 유무를 **학교별로 한 번 판정해 저장**하고, 실패하면 조용히 기존 경로로 돌아간다.
3. 학사일정을 **NEIS `SchoolSchedule`에서 받아** 캘린더에 넣는다. AI 역추출 결과와
   출처를 구분해 **공존**시킨다.
4. NEIS 응답의 오류 코드를 **«데이터 없음»과 구분**한다 (지금은 구분하지 않는다 — §9).
5. 홈페이지 URL이 `"http://"`로 채워진 학교(부산·충북)를 **«알 수 없음»으로 정직하게
   분류**한다.

### 비목표 (이 사업에서 하지 않는다)

- **기존 크롤러 교체.** `board_detector` / `notice_post_extractor` / `cms_patterns`의
  판정 로직은 한 줄도 바꾸지 않는다. RSS는 **위에 얹는 우회로**다.
- **상용 크롤링 서비스 도입.** §1.1의 결론이다. 재검토하지 않는다.
- **RSS 본문·첨부의 소비.** 전북 `description.value`(본문 HTML)와 경북 `<file>`(첨부
  URL)은 **저장만 하고 쓰지 않는다.** 추출 파이프라인은 지금처럼 `detail_url`을 다시
  받아서 처리한다(`content_extraction_service.py:278-283,318`). 소비는 다음 사업.
- **RSS 없는 지역의 개선.** 서울 AJAX·광주 PHP 등은 지금 경로 그대로다.
- **밀린 공지 재수집.** 사업 C 방침대로 «지금부터 새로 오는 것»만.
- **급식·시간표 변경.** 이미 공식 API를 쓴다(§8).

---

## 3. 작업 단위

| | 단위 | 크기 | 되돌리기 |
|---|---|---|---|
| **E1** | RSS 프로브 — 게시판 URL에서 피드 URL 유도 + 1회 판정 + 저장 | 마이그레이션 1개(컬럼 1) + 새 모듈 1개 + 호출 1줄 | 컬럼 무시 (읽는 쪽 플래그 off) |
| **E2** | RSS 수집 경로 — 두 flavor 파서 + `link` 정규화 | 새 모듈 1개 | 플래그 off → 기존 파서 |
| **E3** | 기존 파이프라인 접합 — RSS 산출물 → `DiscoveredPostPreview` | 변환 함수 1개 + 분기 1곳 | 분기 제거 |
| **E4** | NEIS 학사일정 → `school_events` | 마이그레이션 1개(컬럼 1 + 인덱스 1) + 새 서비스 1개 | 해당 출처 행 삭제 |
| **E5** | NEIS 오류코드 처리 (`ERROR-337`/`ERROR-3xx`) | 클라이언트 2곳 수정 | 되돌리기 |
| **E6** | 홈페이지 URL 결측 정규화 통일 (부산·충북) | 함수 1개 | 되돌리기 |

E1~E3은 순서 의존(E1 없으면 E2가 대상 없음). E4~E6은 서로 독립이고 E1~E3과도 독립이다.

---

## 4. E1 — RSS 프로브 설계

### 4.1 언제 도는가

**게시판 탐지가 성공한 직후, 학교당 1회.**

`SchoolCrawlerService.discover_and_save_school_board`
(`backend/app/services/school_crawler_service.py:107-128`)가 결과를 저장한 뒤
(`_save_school_discovery_result`, :606) 프로브를 실행한다. 온보딩 최초 크롤과 정기
크롤이 같은 함수를 타므로 **진입점이 하나다.**

재시도 조건:

| `rss_feed.status` | 다음 크롤에서 |
|---|---|
| 없음 (컬럼 기본값 `{}`) | 프로브한다 |
| `ok` | 프로브 안 한다. 단 `board_key`가 현재 게시판과 다르면 **무효화 후 재프로브** |
| `unsupported` | `checked_at`이 30일 이상 지났으면 재프로브 (엔드포인트가 새로 열릴 수 있다) |
| `unknown` | 다음 크롤에서 재프로브 (일시적 실패로 본다) |

### 4.2 피드 URL을 어떻게 만드는가

게시판 URL은 이미 `school_crawl_state.crawl_board_url`에 캐시되어 있다
(`0013_school_crawl_state.sql:3`, 쓰기는 `school_crawler_service.py:614-620`).
파서 패밀리별로 필요한 값은 **이미 추출하고 있다.**

| 패밀리 | 이미 뽑는 값 | 근거 | 피드 URL |
|---|---|---|---|
| `select_ntt_like` (CMS A) | `mi`, `bbsId` | `notice_post_extractor.py:292-295` (`_board_params`가 쿼리 + 히든 input 병합, :1179-1186) | `{scheme}://{host}{경로}/na/ntt/selectRssFeed.do?mi={mi}&bbsId={bbsId}` |
| `slash_view_like` (CMS D, 전북) | `board_key` = `/{학교ID}/{보드코드}/` | `notice_post_extractor.py:421,428` | `https://school.jbedu.kr/rss/{학교ID}/{보드코드}.do` |
| 그 외 | — | — | 프로브하지 않는다 (`unsupported` 즉시 기록) |

⚠️ **전북 규칙은 호스트를 `school.jbedu.kr`로 고정한다.** `slash_view_like`는 울산
(`school.use.go.kr`)·충북(`school.cbe.go.kr`)에서도 잡히는데(:239) 그 둘은 RSS가
없다. 호스트 검사 없이 규칙을 적용하면 매 크롤마다 404를 한 번씩 때린다.

경로 유도는 기존 헬퍼 `_replace_path_suffix`(`notice_post_extractor.py:1340-1343`)와
같은 방식으로 `selectNttList.do` → `selectRssFeed.do` 치환이면 충분하다. **새 URL
빌더를 만들지 않는다.**

### 4.3 «성공»의 판정 기준

여기가 이 단위의 핵심이다. **판정을 느슨하게 하면 서울 AJAX와 같은 함정에 빠진다** —
0건을 «새 글 없음»으로 오인하고 크롤이 조용히 죽는다.

4단 게이트를 **전부** 통과해야 `ok`다.

| # | 게이트 | 통과 조건 | 이걸 왜 두는가 |
|---|---|---|---|
| 1 | **HTTP** | 상태 200 | 부산·제주·경남의 404/400을 거른다 |
| 2 | **파싱** | XML이면 `<rss>`/`<channel>` 파싱 성공, JSON이면 `dict` 파싱 성공 | 세종처럼 200에 오류 HTML을 담는 경우를 거른다. **`Content-Type`은 신뢰하지 않는다** — 전북은 JSON을 주고 첨부는 `application/octet-stream`을 준다 |
| 3 | **비어있지 않음** | `item` ≥ 1 **그리고** 그중 1건 이상이 «제목 비어있지 않음 AND (`link` 또는 `guid` 존재)» | item 0건은 `ok`가 **아니라** `unknown`이다. 방학 중 빈 게시판과 «조용한 0건»을 구분할 수 없기 때문 |
| 4 | **교차검증** | RSS 제목 상위 5건과, 같은 크롤에서 HTML 파서가 뽑은 제목 집합의 **교집합 ≥ 1** | 오탐 방지의 실질. `mi`/`bbsId`가 다른 게시판을 가리키면(급식·앨범 등) 여기서 걸린다 |

게이트 4는 **프로브를 게시판 탐지 성공 직후에 두는 이유**다. 그 시점에는 HTML 경로가
방금 뽑은 `sample_posts`(`school_crawler_service.py:476-491`)가 손에 있다. 나중에
독립적으로 프로브하면 이 대조가 불가능해진다.

게이트 4가 실패하면 `status='unknown'` + `error='title_mismatch'`로 남긴다.
`unsupported`가 아니다 — 게시판이 방금 바뀌었을 수도 있으므로 다음에 다시 본다.

### 4.4 어디에 저장하는가

**`school_crawl_state`에 `rss_feed jsonb` 컬럼 하나.** `board_watermarks` 바로 옆이다
(`0033_school_crawl_state_board_watermarks.sql:4-5`와 같은 모양).

```sql
-- 0037_school_crawl_state_rss_feed.sql
alter table public.school_crawl_state
  add column if not exists rss_feed jsonb not null default '{}'::jsonb;
```

값의 모양:

```json
{
  "status": "ok",
  "flavor": "gyo6_rss2",
  "url": "https://school.gyo6.net/gacheon/na/ntt/selectRssFeed.do?mi=…&bbsId=…",
  "board_key": "mi=…|bbsId=…",
  "item_count": 15,
  "checked_at": "2026-08-27T…Z",
  "error": null
}
```

**설계 결정 — 왜 `school_crawl_state`인가**

| 후보 | 채택 | 이유 |
|---|---|---|
| `school_crawl_state.rss_feed` | ✅ | 크롤 상태 전용 테이블. RLS 활성 + 정책 0개(`0013:72`)라 service_role 전용이 이미 보장된다. `board_watermarks`가 같은 패턴으로 이미 산다 |
| `schools`에 컬럼 추가 | ✗ | `schools.crawl_*`는 사업 D에서 **죽은 컬럼으로 제거 대상**이다(사업 A §2). 거기에 새 컬럼을 얹으면 안 된다 |
| 새 테이블 `school_rss_feeds` | ✗ | 학교당 행 1개 · 컬럼 1개짜리에 테이블은 과하다 |

**`board_key`를 반드시 함께 저장한다.** 게시판이 바뀌면(재탐지·학교 리뉴얼) 저장된
피드 URL은 다른 게시판을 가리키게 된다. `board_key` 불일치를 무효화 신호로 쓴다(§4.1).

### 4.5 실패하면

**아무 일도 일어나지 않는다.** 프로브는 `try/except`로 감싸고 실패를 `rss_feed`에만
기록한다. 크롤 결과(`SchoolBoardDiscoveryResult`)에는 손대지 않는다.
`_write_board_watermarks`(`school_crawler_service.py:721-727`)와 같은 best-effort
방식이다.

---

## 5. E2 — RSS 수집 경로 설계

### 5.1 두 flavor는 실제로 다른 물건이다

| | `gyo6_rss2` (경북·경기·전남) | `jbedu_json` (전북) |
|---|---|---|
| 형식 | RSS 2.0 XML | JSON |
| 목록 | `<item>` | `item[]` |
| 제목 | `<title>` | `.title` |
| 링크 | `<link>` — **스킴·호스트 없음, 경로 중복** | `.link` — 절대 URL, 정상 |
| 날짜 | `<pubDate>` (RFC 822) | `.pubDate` (ISO 8601) |
| 본문 | 없음 (경기·전남은 `<description>`도 항상 빔) | `.description.value` — **HTML 전체** |
| 첨부 | `<file><fileNm>·<dwldUrl>` (경북만) | `.enclosures` (실측 빈 배열) |

공통 인터페이스로 정규화한다:

```python
@dataclass(frozen=True)
class RssItem:
    title: str
    link: str            # 정규화 후 절대 URL
    published_at: str | None
    guid: str | None
    body_html: str | None            # 저장만, 소비하지 않음
    attachments: list[dict[str, str]]  # [{"name":…, "url":…}] 저장만
```

### 5.2 `link` 정규화 — 경북 생성기 버그 대응

실측된 `link`는 `school.gyo6.net/gacheon/gacheon/na/ntt/selectNttInfo.do?…` 꼴이다.
스킴이 없고 첫 경로 세그먼트가 두 번 반복된다.

순서대로 적용한다:

| # | 규칙 | 예 |
|---|---|---|
| 1 | 스킴 없으면 **피드 URL의 스킴**을 붙인다 | `school.gyo6.net/…` → `https://school.gyo6.net/…` |
| 2 | 호스트 없으면(경로만) **피드 URL의 호스트**에 `urljoin` | `/gacheon/na/…` → `https://school.gyo6.net/gacheon/na/…` |
| 3 | 경로 선두 세그먼트가 **연속 2회 반복**이면 하나 제거 | `/gacheon/gacheon/na/…` → `/gacheon/na/…` |
| 4 | **호스트가 피드 URL 호스트와 다르면 그 item을 버린다** | 외부 링크·오픈 리다이렉트 차단 |
| 5 | 결과를 `_normalize_url` 규칙과 **같은 모양**으로 맞춘다 (`notice_post_extractor.py:1371-1373`) | 중복 방지 인덱스가 걸리도록 |

규칙 3은 «맹목적 중복 제거»가 아니다. **선두 세그먼트에 한정**하고, 반복이 정확히 2회
연속일 때만 적용한다. `/a/a/a/`나 중간의 `/na/na/`는 건드리지 않는다.

규칙 4·5가 이 단위의 안전장치다. 5가 빠지면 §6.2의 «조용한 이중 저장»이 난다.

### 5.3 크롤이 어떻게 달라지는가

```
현재:
  게시판 URL → GET → HTML → 파서 패밀리 → 후보 → 각 후보 상세 접근 검증 → posts

RSS 있는 학교:
  피드 URL → GET → item[] → link 정규화 → 후보 → (상세 접근 검증 그대로) → posts
             └────────────── 이 구간만 대체 ──────────────┘
```

**상세 접근 검증(`_validate_candidate`, `notice_post_extractor.py:651`)은 그대로 탄다.**
RSS가 링크를 준다고 그것이 열린다는 보장은 없다 — 로그인 게시판이면 여전히
`unsupported_login_required`로 떨어져야 한다(§1.5).

**RSS 실패 시 폴백**: 피드 GET이 실패하거나 게이트 3(§4.3)을 못 넘기면
`rss_feed.status`를 `unknown`으로 되돌리고 **그 크롤은 기존 HTML 경로로 진행한다.**
RSS 때문에 크롤이 실패하는 일은 없어야 한다.

### 5.4 본문·첨부는 저장만 한다

`crawl_result["rss"] = {"body_html": …, "attachments": [...]}` 로 넣는다.
그러면 `_fetch_context_from_notice`(`content_extraction_service.py:1306-1314`)가
`crawl_result`를 통째로 `fetch_context`에 실어 추출기에 넘긴다 — **스키마 변경 없이
다음 사업이 쓸 자리가 미리 생긴다.** 이번 사업에서 이 값을 읽는 코드는 쓰지 않는다.

---

## 6. E3 — 기존 파이프라인과의 접합

### 6.1 새 저장 경로를 만들지 않는다

RSS 산출물을 `DiscoveredPostPreview`(`school_crawler_service.py:22-35`)로 변환하고,
**기존 `_save_discovered_notice_candidates`(:730-783)를 그대로 통과시킨다.**
그러면 워터마크·중복방지·캐시 트림이 전부 공짜로 따라온다.

### 6.2 🔴 세 값을 HTML 경로와 **똑같이** 만들어야 한다

`post_uid`는 이렇게 조립된다 — `notice_post_extractor.py:832`:

```python
uid = f"{cms.key}:{candidate.board_key}:{candidate.post_id}"
```

그리고 중복 방지는 이 두 유니크 인덱스가 한다
(`0006_notices_school_only_cleanup.sql:18-24`):

```sql
notices_school_post_uid_uidx   on notices (school_id, source_post_uid) where source_post_uid is not null
notices_school_detail_url_uidx on notices (school_id, detail_url)      where detail_url is not null
```

**따라서 RSS 경로는 `cms_key` · `board_key` · `post_id` 세 값을 HTML 경로와 문자열
단위로 일치시켜야 한다.** 하나라도 어긋나면 같은 글이 두 행으로 저장되고, 두 번 추출·
두 번 번역된다. 에러가 나지 않으므로 **아무도 모른다.** 이 사업의 최대 실패 모드다.

| 값 | HTML 경로의 규칙 | RSS 경로가 맞춰야 할 것 |
|---|---|---|
| `cms_key` | `detect_cms` 결과 (`cms_patterns.py:38-102`) | **재판정하지 않고** 캐시된 `crawl_result.cms_key`를 그대로 쓴다 (`school_crawler_service.py:550-579`) |
| `board_key` (A) | `f"mi={mi}\|bbsId={bbs_id}"` (`notice_post_extractor.py:295`) | 프로브가 저장한 `rss_feed.board_key`를 그대로 |
| `board_key` (D) | `/{학교ID}/{보드코드}/` (`:421,428`) | 같은 문자열 (끝 슬래시 포함) |
| `post_id` (A) | `nttSn`/`nttId`/`articleId` 쿼리값 (`:306`) | 정규화된 `link`에서 같은 키로 추출 |
| `post_id` (D) | `SLASH_VIEW_RE` = `/view/(\d+)` (`:21,417`) | 정규화된 `link`에 같은 정규식 |
| `detail_url` | `urljoin(board_url, href)` 후 그대로 | §5.2 규칙 5로 같은 모양 |

### 6.3 워터마크는 그대로 동작한다 — 단 `post_id_source`를 조심하라

`_watermark_post_value`(`school_crawler_service.py:652-666`)는 두 제외 목록을 본다:

```python
_WATERMARK_EXCLUDED_SOURCES = {"path numeric segment", "href query id"}
_WATERMARK_EXCLUDED_METHODS = {"generated", "file_download"}
```

RSS 항목의 `post_id_source`는 **기존 값을 재사용한다** — CMS A는 `"href query"`,
CMS D는 `"path /view/"`. 둘 다 제외 목록에 없으므로 워터마크가 정상 적용된다.
`"rss"` 같은 새 문자열을 만들면 제외 목록에는 안 걸리지만 **HTML 경로와 값이 달라져
`crawl_result` 진단이 갈라진다.** 새 값을 만들지 않는다.

`detail_method`도 `"href"`를 유지한다. `"generated"`를 쓰면 워터마크가 꺼진다.

RSS인지 여부는 `crawl_result["post"]["source_channel"] = "rss"` 처럼 **진단용으로만**
따로 남긴다 — 중복 키에도 워터마크 키에도 섞지 않는다.

### 6.4 갱신 경로

유니크 위반이 나면 기존 코드가 `_update_existing_notice_candidate`(:786-838)로
제목·`detail_url`·`crawl_result`를 갱신한다. RSS가 제목을 더 깨끗하게 준다면
(HTML 목록은 «[가정통신문] 제목 NEW 첨부» 같은 잡음이 섞인다) 이 경로가 자동으로
제목을 개선한다. **이건 부작용이 아니라 이득이다.** 다만 `crawl_checked_at`은 기존
값을 보존하도록 이미 되어 있다(:828-831).

---

## 7. E4 — NEIS 학사일정 도입 설계

### 7.1 지금 `school_events`는 무엇인가

| 사실 | 근거 |
|---|---|
| `notice_id`가 **not null + FK** | `0017_school_events.sql` |
| 유니크 제약이 `(notice_id, event_date)` | `0017`, 재확인 `0029_school_events_notice_date_guard.sql` |
| 값은 **공지 본문 AI 역추출**에서만 온다 | `notice_service.py:826` → `:1125-1193` |
| 갱신 방식은 **notice 단위 전량 교체** | `:1137-1144`(조회) → `:1180-1184`(upsert) → `:1186-1191`(사라진 날짜 삭제) |
| RLS는 `school_id` 기준 | `0017` 정책 `school events select own school` |
| 프론트는 `notice_id`가 없을 수 있다고 이미 가정한다 | `app/(app)/calendar/page.tsx:147-150` (`typeof value === 'string'` 필터) |
| 홈 화면은 `notice_id`로만 조회한다 | `app/(app)/page.tsx:337-343` (`.in('notice_id', noticeIds)`) |

### 7.2 🔴 핵심 설계 논점 — 공존인가 대체인가

**공존이다. 대체가 아니다.** 이유:

- NEIS 학사일정은 **학교 공식 연간 일정**이다 (개학·방학·시험·행사).
- AI 역추출 일정은 **개별 공지에 딸린 일정**이다 (특정 학년 현장체험학습, 신청 마감).
- 둘은 겹치기도 하지만 **서로를 포함하지 않는다.** 어느 한쪽을 버리면 정보가 준다.
- 프론트 캘린더가 `notice_id`로 공지 상세·번역을 이어 붙인다
  (`calendar/page.tsx:147-170`). NEIS 행에는 이어 붙일 공지가 없다. **이 차이는
  UI에서도 유지되어야 한다** — «학교 공식 일정»과 «가정통신문에서 뽑은 일정»은
  학부모에게도 다른 물건이다.

### 7.3 스키마 — 출처 구분 컬럼이 필요한가

**필요하다.** 그리고 `notice_id`의 not null도 풀어야 한다.

```sql
-- 0038_school_events_source.sql
alter table public.school_events
  add column if not exists source text not null default 'notice_ai';

alter table public.school_events
  alter column notice_id drop not null;

alter table public.school_events
  add constraint school_events_source_check
  check (source in ('notice_ai', 'neis'));

-- NEIS 행은 notice_id가 null이라 (notice_id, event_date) 유니크가 무력하다.
-- (postgres에서 null은 서로 distinct) → 전용 부분 유니크 인덱스가 필요하다.
create unique index if not exists school_events_neis_uidx
  on public.school_events (school_id, event_date, title)
  where source = 'neis';
```

**왜 새 테이블이 아닌가**

| 후보 | 채택 | 이유 |
|---|---|---|
| `school_events.source` 컬럼 | ✅ | 캘린더 쿼리가 하나로 남는다(`calendar/page.tsx:118-123`). RLS 정책도 이미 `school_id` 기준이라 그대로 적용된다. `end_date`·`event_kinds` 같은 기존 컬럼을 재사용한다 |
| 새 테이블 `school_calendar` | ✗ | 프론트가 두 테이블을 합쳐야 하고, RLS 정책·번역 경로를 새로 만들어야 한다. 얻는 게 없다 |

**왜 `notice_ai`가 기본값인가**: 기존 행 전부가 그 출처이므로 백필이 필요 없다.
컬럼 추가 한 줄로 끝난다.

### 7.4 두 출처가 서로를 밟지 않는다 — 증명

`_replace_school_events_from_pipeline`은 **`notice_id`로만** 조회·삭제한다:

- 조회 `:1137-1144` — `.eq("notice_id", notice_id)`
- upsert `:1182` — `on_conflict="notice_id,event_date"`
- 삭제 `:1187-1191` — `existing_rows`(같은 notice) 안에서만

`notice_id`가 null인 NEIS 행은 **이 코드의 시야에 들어오지 않는다.**
즉 `notice_service.py`를 **한 줄도 고치지 않고** 공존이 성립한다.

반대 방향(NEIS 동기화가 AI 행을 지우는 것)은 새 코드이므로,
**`.eq("source", "neis")` 조건 없이는 delete를 절대 실행하지 않는다**는 규칙을
동기화 서비스에 못박는다.

### 7.5 동기화 설계

| 항목 | 값 |
|---|---|
| 서비스 | `SchoolSchedule` |
| 파라미터 | `ATPT_OFCDC_SC_CODE`, `SD_SCHUL_CODE`, `AA_FROM_YMD`, `AA_TO_YMD` |
| 필요한 값의 출처 | `schools.neis_office_code` / `neis_school_code` (`school_crawler_service.py:358-359`) |
| 범위 | 학년도 단위 (3/1 ~ 이듬해 2/28). 1회 호출로 `pSize=100` 페이징 |
| 주기 | 학교당 **주 1회**로 충분 (학사일정은 거의 안 바뀐다) |
| 매핑 | `AA_YMD`→`event_date`, `EVENT_NM`→`title`, `EVENT_CNTNT`→`description`, `end_date`=null (NEIS는 하루 1행) |
| `event_kinds` | `["event"]` 고정. NEIS 일정에 «마감»은 없다 |
| 갱신 | `source='neis'` + 같은 학년도 범위의 행을 지우고 다시 넣는다 (전량 교체) |
| 실행 위치 | 백엔드 (`neis_client.py` 확장). 프론트가 아니다 — 쓰기는 service_role 경로여야 하고, 이미 크롤 스케줄러가 있다 |

**⚠️ 연속 일정 병합은 하지 않는다.** NEIS는 «여름방학» 같은 기간을 하루 1행으로
준다. `end_date`로 접으려는 유혹이 있지만, `0030_school_events_end_date.sql`의 주석이
명시한다 — *"캘린더는 더 이상 근접 날짜를 추측 병합하지 않는다"*. 그 결정과 충돌하는
설계를 새로 들이지 않는다. 병합이 필요하면 별건으로 판단한다.

### 7.6 AI 역추출을 끄는가

**끄지 않는다.** §7.2의 이유다. 다만 NEIS 일정이 들어온 뒤에는
`scripts/sweep_footer_dates.py`류의 노이즈가 **상대적으로 더 눈에 띌** 것이다.
AI 역추출 정밀도 조정은 이 사업의 범위가 아니다 — 열린 질문(§16)에 남긴다.

---

## 8. NEIS 급식 — 변경 없음

`lib/neis.ts`를 읽어 확인했다.

| 기능 | 상태 | 근거 |
|---|---|---|
| 급식 단일일 | 공식 API 사용 중 | `lib/neis.ts:299` `mealServiceDietInfo` |
| 급식 기간 | 공식 API 사용 중 | `lib/neis.ts:333` |
| 급식 캐시 | `meals` 테이블 (`office_code, school_code, meal_date, meal_type` 유니크) | `lib/neis.ts:357-408, 416-516` |
| 알레르기 19종 | 코드→한국어 매핑 보유 | `lib/neis.ts:66-71` |
| 시간표 | 공식 API 4종 사용 중 | `lib/neis.ts:155-164` |

**결론: 급식·시간표는 변경 없음.** 이 사업에서 손대지 않는다.
(다만 §9의 오류코드 문제는 급식에도 그대로 해당된다.)

---

## 9. E5 — NEIS 키·한도 관리

### 9.1 🔴 새로 발견한 결함 — 오류가 «데이터 없음»으로 둔갑한다

NEIS는 오류를 **HTTP 200 본문 안의 `RESULT.CODE`**로 돌려준다.
그런데 양쪽 클라이언트 모두 HTTP 상태만 본다.

| 위치 | 코드 | 결과 |
|---|---|---|
| 프론트 | `lib/neis.ts:87-89` — `res.ok`만 검사 | 200이면 통과 |
| 프론트 | `lib/neis.ts:98-105` — `extractRows`가 `row` 블록 없으면 `[]` | **`ERROR-337`도 빈 배열이 된다** |
| 백엔드 | `neis_client.py:75-83` — 같은 구조 | 같은 문제 |
| 프론트 | `lib/neis.ts:224,316,351` — `INFO-200`을 문자열 매칭으로 «정상» 처리 | 그런데 그 매칭은 **throw된 에러**에만 걸린다. RESULT 블록은 throw하지 않으므로 이 코드는 실질적으로 동작하지 않는다 |

**즉 일일 한도를 넘겨도(`ERROR-337`) 화면에는 «급식 정보 없음»이 뜬다.**
서울 AJAX의 «조용한 0건»과 정확히 같은 구조의 함정이 우리 코드 안에 이미 있다.

### 9.2 조치

`extractRows` / `_extract_rows`의 **앞단**에 RESULT 판정을 넣는다.

```
head[].RESULT.CODE 를 읽는다
  INFO-000            → 정상
  INFO-200            → 데이터 없음 → []  (정상)
  ERROR-337           → 한도 초과   → NeisQuotaExceeded 예외
  ERROR-3xx / 그 외    → NeisApiError 예외 (코드·메시지 포함)
  RESULT 블록 자체가 없음 → 정상 (row가 있으면 그대로)
```

**한도 초과 시 동작** (일일 한도가 미공개이므로 방어적으로):

| 상황 | 동작 |
|---|---|
| 급식·시간표 (사용자 요청 경로) | 캐시된 값이 있으면 그것을 쓴다. 없으면 «지금 불러올 수 없음»을 **명시적으로** 표시한다. 빈 급식표를 그리지 않는다 |
| 학사일정 동기화 (배치) | 해당 실행을 중단하고 다음 주기에 재시도. **재시도 폭주 금지** — 한 실행 안에서 337을 받으면 남은 학교를 건너뛴다 |

### 9.3 호출량 — 지금 규모에서는 한도가 문제되지 않는다

| 경로 | 빈도 | 근거 |
|---|---|---|
| `schoolInfo` 검색 | 온보딩 입력당 1~3회 | `neis_client.py:127`가 질의 확장으로 최대 3회 |
| 급식 | 날짜당 학교당 1회, 이후 `meals` 캐시 | `lib/neis.ts:357-408` |
| 시간표 | 캐시 없음 — 조회마다 호출 | `lib/neis.ts:186-227` |
| **학사일정 (신규)** | 학교당 **주 1회** × 2~3페이지 | §7.5 |

등록 학교 8곳 기준 학사일정 추가 호출은 **주 24회 이하**다. 무시할 수준이다.
문제가 생긴다면 **시간표**가 먼저다(캐시 없음). 그건 이 사업의 범위가 아니지만
§9.2의 판정이 들어가면 최소한 **조용히 실패하지는 않게** 된다.

### 9.4 키

키는 이미 하나다 — 백엔드 `NEIS_API_KEY`(`backend/app/core/config.py:59`),
프론트 `process.env.NEIS_API_KEY`(`lib/neis.ts:74`).
**두 배포에 같은 키가 들어가 있는지는 «미확인»이다** (Cloud Run env 확인 필요).
한도가 키 단위라면 이건 중요한 사실이다 — 배포 전에 확인 항목에 넣는다(§13).

키를 늘리는 설계는 하지 않는다. §9.3대로 한도에 근접할 근거가 없다.

---

## 10. E6 — 부산·충북 홈페이지 URL 결측 대응

### 10.1 지금 무슨 일이 일어나는가

`schoolInfo`의 `HMPG_ADRES`가 **부산(C10)·충북(M10)은 문자열 `"http://"`로만 채워져
사실상 누락**이다. 스킴 없는 값(`iginue.icees.kr`)·경로 포함 값도 섞여 있다.

두 정규화 함수가 **다르게 동작한다**:

| 위치 | `"http://"` 입력 시 | 코드 |
|---|---|---|
| 백엔드 | `""` 반환 (명시적으로 거른다) | `neis_client.py:53-54` |
| **프론트** | **`"http://"` 그대로 통과** (`/^https?:\/\//` 검사만) | `lib/neis.ts:137-142` |

프론트 값이 그대로 온보딩을 통해 DB에 저장된다
(`app/onboarding/actions.ts:43,127` → `schools.homepage_url`).

그래서 부산·충북 학교의 실제 경로는 이렇다:

```
온보딩: schools.homepage_url = "http://"           ← 쓰레기값이 저장됨
크롤:   normalize_homepage_url("http://") → None    (school_crawler_service.py:360)
        homepage_url이 falsy → _with_neis_homepage 실행 (:364-366)
        NEIS가 같은 "http://"를 돌려줌 → 다시 ""
        → status = "homepage_missing" (:240-243)
```

**즉 NEIS로는 못 고친다. 같은 값이 돌아오기 때문이다.**

### 10.2 조치

**이 사업에서는 (a)만 한다.**

**(a) 프론트 정규화를 백엔드와 같게 만든다.** `lib/neis.ts:137-142`가 `"http:"`,
`"https:"`, `"http://"`, `"https://"`와 «호스트 없는 값»을 `""`로 만들도록 한다
(`neis_client.py:45-72`의 규칙을 그대로 옮긴다).
→ 쓰레기값이 DB에 들어가지 않는다. 학교 검색 결과에서도 «홈페이지 없음»으로 보인다.

**(b) 온보딩에서 홈페이지 주소를 직접 입력받는다** — 이 사업에서 하지 않는다.
UI 변경이고, 부산·충북 학부모에게만 보여야 하는 조건부 필드다. 열린 질문(§16).

**(c) 시도별 도메인 규칙으로 추정** (부산 `school.busanedu.net/{학교ID}`,
충북 `school.cbe.go.kr/{학교ID}`) — **채택하지 않는다.** 학교ID를 알 방법이 없고,
틀린 URL로 크롤하면 다른 학교의 공지를 학부모에게 보내게 된다. 최악의 실패다.

### 10.3 결과적으로 무엇이 나아지는가

정직해지는 것뿐이다. 부산·충북 학교는 여전히 `homepage_missing`으로 남는다.
다만 **`"http://"`라는 거짓 URL이 DB에 없어지고**, 관리자 화면(사업 F)에서
«홈페이지 주소를 받아야 하는 학교»를 셀 수 있게 된다.

---

## 11. 커버리지 — 정직하게

### 11.1 RSS는 4개 시도만이다

| | 시도 수 | 비고 |
|---|---|---|
| RSS 확인됨 | **4** (경북·전북·경기·전남) | 이 중 «목록만»이 2개(경기·전남) |
| 조건부 | 1 (세종 — 호출 오류) | 재프로브 대상 |
| 없음 | 12 | 기존 경로 그대로 |

그리고 4개 중에서도 **얻는 것이 다르다**:

| 시도 | RSS가 실제로 해결하는 문제 |
|---|---|
| 경북 | `data-id` 숨은 링크 + 첨부 URL 확보 → **가장 큰 이득** |
| 전북 | 목록 안정화 + 본문 확보(미소비) |
| 경기 | **`javascript:` / `data-id` 링크 추종 불가 문제** → 이득이 큼 (CMS A) |
| 전남 | 목록 안정화 (CMS A, 같은 이유) |

즉 «목록만»이라고 이득이 없는 게 아니다. **CMS A의 `javascript:` 링크 문제는 목록
RSS만으로 해결된다.**

### 11.2 «우리 학교 8곳 중 몇 곳인가» — 미확인

사용자 제시 기준 현재 등록 학교는 **8곳**이다. 이 중 몇 곳이 RSS 지역인지는
**DB를 조회하지 않으면 알 수 없고, 이 문서는 DB에 접근하지 않았다 — 미확인.**

판단 방법(service_role 키로 1회 실행):

```sql
select
  split_part(crawl_board_url, '/', 3) as host,
  crawl_status,
  count(*)
from public.school_crawl_state
where crawl_board_url is not null
group by 1, 2
order by 3 desc;
```

호스트 → 시도 → RSS 가부 매핑:

| 호스트 패턴 | 시도 | RSS |
|---|---|---|
| `school.gyo6.net` | 경북 | ✅ 첨부까지 |
| `school.jbedu.kr` | 전북 | ✅ 본문까지 |
| `*-e.goe*.kr` / `*-m.goe*.kr` | 경기 | ✅ 목록 |
| `*.jge.es.kr` / `*.jge.ms.kr` | 전남 | ✅ 목록 |
| `*.sen.es.kr` / `*.sen.ms.kr` | 서울 | ❌ |
| `*.icees.kr` / `*.icems.kr` | 인천 | ❌ |
| `school.cbe.go.kr` | 충북 | ❌ |
| `school.use.go.kr` | 울산 | ❌ |
| `school.busanedu.net` | 부산 | ❌ |
| `gen.ms.kr` / `gen.es.kr` | 광주 | ❌ |

**알려진 사실 하나**: 최근 데모 학교 화이트리스트는 경기(`pcbuheung-m.goebc.kr`)와
인천(`donginchon.icems.kr`, `hambak.icees.kr`)이었고
(`lib/test-entry-bypass.ts:41,50,59`), 인천문남초는 제외되었다(커밋 `776da12`).
경기 1곳은 **RSS 대상**, 인천 2곳은 **비대상**이다. 다만 사업 A에서 이 파일 자체를
제거하기로 했으므로(사업 A §5.2(d)) 실제 등록 학교 구성과는 다를 수 있다.

### 11.3 결정에 미치는 영향

**8곳 중 RSS 대상이 0곳이어도 이 사업은 유효하다.** 이유:

- E4(NEIS 학사일정)·E5(오류코드)·E6(홈페이지 URL)는 **RSS와 무관하게 전 학교에
  적용**된다. 오히려 이쪽이 즉효다.
- E1~E3은 **학교가 늘어날 때를 위한 투자**다. 경기는 학교 수가 많은 시도라 신규
  등록에서 걸릴 확률이 높다 — 다만 이건 «미확인(추정)»이다.

따라서 **§14 배포 순서는 E4~E6을 앞에 둔다.**

---

## 12. 배포 순서

되돌리기 쉬운 것부터, 즉효가 있는 것부터.

| 배포 | 내용 | 확인 |
|---|---|---|
| **1** | **E5** — NEIS RESULT 코드 판정 (프론트·백엔드) | 잘못된 키로 호출 시 «빈 배열»이 아니라 오류가 난다 |
| **2** | **E6** — 프론트 홈페이지 URL 정규화 통일 | 부산 학교 검색 결과의 `homepageUrl`이 `""` |
| **3** | **E4-a** — 마이그레이션 `0038` (`source` 컬럼 + `notice_id` nullable + 부분 유니크) | 기존 행 전부 `source='notice_ai'`, 캘린더 정상 |
| **4** | **E4-b** — `SchoolSchedule` 동기화 서비스 (1개 학교 수동 실행) | `source='neis'` 행 생성, AI 행 손상 없음 |
| **5** | **E4-c** — 주 1회 스케줄 편입 | 다음 주기에 자동 갱신 |
| **6** | **E1-a** — 마이그레이션 `0037` (`rss_feed` 컬럼) | 기존 크롤 무영향 |
| **7** | **E1-b** — 프로브 (기록만, 수집에 쓰지 않음) | RSS 지역 학교에 `status='ok'` 기록 |
| **8** | **E2 + E3** — RSS 수집 경로 + 접합 (플래그 뒤) | §13 대조 검증 통과 |

**3번이 4번보다 앞인 이유**: 컬럼 없이 NEIS 행을 넣으면 `notice_id` not null에
걸린다. 그리고 컬럼만 먼저 넣어보면 프론트 회귀를 **NEIS 데이터 없이** 확인할 수 있다.

**7번이 8번보다 앞인 이유**: 프로브를 «기록만»으로 한 주기 돌려서, 게이트 4(제목
교차검증)의 오탐률을 **수집을 켜기 전에** 볼 수 있다. 이게 이 사업에서 가장 값싼
안전장치다.

**8번이 마지막인 이유**: §6.2의 이중 저장은 조용히 일어난다. 앞의 모든 것이
안정된 뒤에 켠다.

---

## 13. 검증

| 항목 | 방법 | 통과 기준 |
|---|---|---|
| **E5** | 유효하지 않은 `KEY`로 `mealServiceDietInfo` 호출 | 빈 배열이 아니라 오류 코드가 올라온다 |
| **E5** | 정상 키 + 휴일 날짜 (`INFO-200`) | 빈 배열 (기존 동작 유지) |
| **E5 회귀** | 급식 화면 정상 날짜 | 기존과 동일하게 표시 |
| **E6** | 부산 학교를 프론트 검색 | `homepageUrl === ''` |
| **E6 회귀** | 정상 학교(스킴 없는 값 `iginue.icees.kr`) | `https://iginue.icees.kr` |
| **E4** | `0038` 적용 후 캘린더 | 기존 일정 그대로, `notice_id` 링크 동작 |
| **E4** | NEIS 동기화 1회 실행 | `source='neis'` 행 생성. **`source='notice_ai'` 행 수 변화 0** |
| **E4** | 같은 학교 동기화 재실행 | 행 수 증가 0 (부분 유니크가 잡는다) |
| **E4** | 동기화 후 공지 1건 재번역 | `_replace_school_events_from_pipeline`이 NEIS 행을 지우지 않는다 |
| **E4** | 홈 화면 D-day 칩 (`page.tsx:337-343`) | NEIS 행이 D-day로 새지 않는다 (`notice_id` 필터) |
| **E1 미탐** | RSS 지역 학교 전부에 대해 프로브 결과 확인 | 경북·전북·경기·전남 학교가 `unsupported`로 남으면 **미탐** — URL 유도 규칙(§4.2)을 의심한다 |
| **E1 오탐** | `status='ok'`인 학교의 `rss_feed.url`을 손으로 열어본다 | 그 학교의 **가정통신문/공지 게시판**이 맞아야 한다. 급식·앨범 게시판이면 **오탐** — 게이트 4가 뚫린 것 |
| **E1 오탐 2** | 프로브 결과 item 제목 vs 같은 크롤의 `sample_posts` 제목 | 교집합 0인데 `ok`면 게이트 4 버그 |
| **E1 회귀** | RSS 없는 학교 8곳 크롤 | `crawl_status`·`success_count`가 프로브 도입 전과 동일 |
| **🔴 E3 이중 저장** | RSS 켠 뒤 같은 학교를 **연속 2회** 크롤 (RSS on → off → 비교) | 두 경로가 만든 `source_post_uid`가 **문자열 단위로 동일**. `notices` 행 수 증가 0 |
| **E3 워터마크** | RSS 경로 2회 연속 크롤 | 2회차 신규 저장 0건, `board_watermarks`의 `board_key`가 1회차와 동일 |
| **E3 링크 정규화** | 경북 학교 `detail_url` 육안 확인 | `https://` 시작, `/{학교ID}/{학교ID}/` 중복 없음, 호스트가 피드 호스트와 동일 |
| **E3 로그인 게시판** | 로그인 필요한 RSS 학교(있다면) | `unsupported_login_required` 유지 (RSS가 이 판정을 우회하지 않는다) |

«E3 이중 저장» 항목이 이 사업의 **단일 최대 검증 항목**이다. 실패해도 에러가 나지
않으므로 반드시 명시적으로 대조해야 한다.

---

## 14. 위험과 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| 🔴 **미문서화 엔드포인트가 예고 없이 사라진다** | RSS 학교의 크롤이 갑자기 0건 → «새 글 없음»으로 오인 | ① 피드 실패는 **항상 기존 HTML 경로로 폴백**한다(§5.3) — RSS는 절대 단독 경로가 되지 않는다 ② `item_count == 0`은 `ok`가 아니라 `unknown`이다(§4.3 게이트 3) ③ `rss_feed.status`가 `ok`→`unknown`으로 뒤집히는 학교 수를 스케줄 요약에 남긴다. **이게 «사라짐»의 조기 신호다** |
| 🔴 **같은 글이 두 행으로 저장된다** (§6.2) | 두 번 추출·두 번 번역·중복 노출. **에러 없음** | §13의 «E3 이중 저장» 대조를 배포 8 이전 필수 게이트로. `cms_key`·`board_key`·`post_id`를 재계산하지 않고 **캐시값 재사용**(§6.2) |
| **프로브 오탐 — 다른 게시판의 RSS를 잡는다** | 급식/앨범 글이 가정통신문으로 들어온다 | 게이트 4(제목 교차검증, §4.3). 배포 7에서 **기록만** 한 주기 돌려 오탐률 확인 |
| **프로브가 매 크롤 404를 때린다** | 불필요한 부하, 로그 오염 | `unsupported`는 30일 잠금(§4.1). 전북 규칙에 **호스트 고정**(§4.2 ⚠️) |
| **경북 `link` 정규화가 과하게 동작** | 정상 URL을 망가뜨려 상세 접근 실패 | 규칙 3을 **선두 세그먼트 2회 연속**으로만 한정. 규칙 4로 호스트 검증. 실패하면 그 item만 버리고 크롤은 계속 |
| **NEIS 학사일정 동기화가 AI 행을 지운다** | 공지 연결 일정 소실 | 동기화 delete에 **`.eq("source","neis")` 없으면 실행 금지**를 코드 규칙으로. §13에서 행 수 대조 |
| **NEIS 일일 한도 초과 (`ERROR-337`)** | 급식·일정이 조용히 빈다 (**지금 이미 이렇다**) | E5가 정확히 이 문제다. 배포 1번으로 **가장 먼저** 처리 |
| **NEIS 키가 프론트·백엔드 별도일 수 있다** | 한도 계산이 틀린다 | 배포 전 Cloud Run env 확인 (§9.4, 현재 «미확인») |
| **`0037`/`0038` 번호 충돌** | 마이그레이션 이력 꼬임 | 사업 A §7.5 — `0035`는 자녀 개인일정 예약, `0036`은 사업 A(app_jobs RLS). 이 사업은 **`0037`부터**. 사업 A의 DB 자동배포가 먼저 서면 그것을 탄다 |
| **RSS가 로그인 게시판을 우회한다** | §1.5 법적 안전선 침범 | 상세 접근 검증(`_validate_candidate`)을 **그대로 통과**시킨다(§5.3). RSS는 목록만 대체한다 |

**롤백 단위**

| 단위 | 롤백 |
|---|---|
| E1 | `rss_feed`를 읽는 플래그 off. 컬럼은 남겨도 무해 |
| E2·E3 | 같은 플래그 off → 전 학교가 즉시 기존 HTML 경로 |
| E4 | `delete from school_events where source = 'neis'` (AI 행 무영향) |
| E5 | 커밋 되돌리기 |
| E6 | 커밋 되돌리기 (이미 저장된 `"http://"`는 남지만 §10.3대로 무해) |

---

## 15. 결정 기록 (2026-08-27)

| # | 질문 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | 상용 크롤링 서비스로 갈 것인가 | **가지 않는다.** 285배 비용 + Bright Data가 정부 사이트 차단 + Listing F1 0.710 + HWP 파서 0개 | §1.1, §2 비목표 |
| 2 | 기존 크롤러를 RSS로 교체할 것인가 | **교체하지 않는다.** 위에 얹고, 실패하면 항상 기존 경로로 폴백 | §2 비목표, §5.3 |
| 3 | RSS 판정 결과를 어디에 둘 것인가 | **`school_crawl_state.rss_feed jsonb`.** `schools`는 사업 D 제거 대상이라 쓰지 않는다 | §4.4 |
| 4 | `item` 0건을 «RSS 있음»으로 볼 것인가 | **보지 않는다.** `unknown`으로 남긴다 — 서울 AJAX의 «조용한 0건»과 같은 함정 | §4.3 게이트 3 |
| 5 | RSS 본문·첨부를 이번에 소비할 것인가 | **소비하지 않는다.** `crawl_result`에 저장만 하고 추출기는 지금처럼 `detail_url`을 다시 받는다 | §2 비목표, §5.4 |
| 6 | NEIS 학사일정이 AI 역추출을 대체하는가 | **대체하지 않는다. 공존한다.** 둘은 서로를 포함하지 않는 다른 정보다 | §7.2 |
| 7 | 출처 구분 컬럼이 필요한가 | **필요하다.** `school_events.source` + `notice_id` nullable + `source='neis'` 부분 유니크 인덱스 | §7.3 |
| 8 | 새 테이블로 분리할 것인가 | **분리하지 않는다.** RLS·캘린더 쿼리·`end_date`/`event_kinds`를 재사용한다 | §7.3 |
| 9 | NEIS 급식을 손댈 것인가 | **손대지 않는다.** 이미 `mealServiceDietInfo` + `meals` 캐시를 쓴다 | §8 |
| 10 | 부산·충북 홈페이지 URL을 추정할 것인가 | **추정하지 않는다.** 틀린 URL은 다른 학교 공지를 학부모에게 보낸다. 정규화만 통일해 «없음»으로 정직하게 | §10.2 |
| 11 | 밀린 공지를 재수집할 것인가 | **하지 않는다.** 사업 C 방침과 동일 — 지금부터 새로 오는 것만 | §2 비목표 |

---

## 16. 열린 질문

| # | 질문 | 왜 지금 답이 없는가 | 누가 답하는가 |
|---|---|---|---|
| 1 | 등록 학교 8곳 중 RSS 지역이 몇 곳인가 | 이 문서는 DB를 조회하지 않았다 — **미확인** | §11.2의 SQL 1회 실행 |
| 2 | 프론트·백엔드가 같은 `NEIS_API_KEY`를 쓰는가 | Cloud Run env 미확인 | 배포 설정 확인 |
| 3 | 세종 RSS는 왜 오류인가 | UI에 링크는 있으나 호출 실패 — 파라미터 문제인지 서버 문제인지 미확인 | 세종 학교가 등록되면 프로브 결과로 판단 |
| 4 | NEIS 학사일정이 들어온 뒤 AI 역추출 일정의 정밀도를 조일 것인가 | 두 출처가 같이 보이기 전에는 중복·노이즈 정도를 알 수 없다 | 배포 5 이후 실물 캘린더를 보고 |
| 5 | 캘린더 UI에서 두 출처를 구분해 보여줄 것인가 | 디자인 결정이다. 스키마는 이미 구분을 지원한다(§7.3) | 사용자 |
| 6 | 부산·충북 학부모에게 홈페이지 주소를 직접 입력받을 것인가 | 조건부 UI 필드가 필요하고, 잘못 입력하면 §10.2(c)와 같은 위험이 생긴다 | 사용자 (온보딩 개선 별건) |
| 7 | NEIS 일일 한도의 실제 값 | **공식적으로 미공개.** E5 도입 후 `ERROR-337` 발생 여부로만 관측 가능 | 운영 관측 |

---

## 17. 다음 단계

이 스펙 승인 후 `superpowers:writing-plans`로 구현 계획을 작성한다.
구현은 서브에이전트로 분담하되, 배포 순서(§12)의 경계를 넘지 않는다.

E5·E6(배포 1~2)은 다른 단위와 의존이 없고 되돌리기가 커밋 하나이므로 **먼저 떼어
진행해도 된다.**
