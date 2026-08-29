# 사업 C — 첨부 추출 파이프라인 수리 · 크롤 재가동

기준일: 2026-08-27
상태: 설계 (구현 전)
선행: 없음 (사업 A와 독립) / 후행: 사업 D(DB 정리)

---

## 1. 배경

파이프라인은 **72일째 멈춰 있다.** 2026-06-15 발표를 위해 크롤·추출 스케줄러 5개를
정지시킨 뒤 그대로다. Vertex 호출이 최근 30일 4회뿐인 것이 이를 뒷받침한다.

멈춘 동안 확인된 것은 «쉬고 있었다»가 아니라 «고장 난 채로 멈췄다»이다.
운영 DB 실측(2026-08-26, 공지 38건 / 완료 35 / 학교 8곳 / 첨부 70건)에서 네 개의
고장과 두 개의 크롤 문제가 나왔다.

| # | 고장 | 한 줄 요약 |
|---|---|---|
| ① | HWP 폴백 열화 | HWP 20건 중 6건(30%)이 표를 잃는 2순위 경로로 떨어졌다 |
| ② | 본문 사진 산출물 0건 | 합성 PNG를 만드는 코드는 있는데 운영에 결과가 없다 |
| ③ | 타일 24 vs 콜 8 | 긴 포스터를 24조각 내놓고 9조각째에 예산이 죽는다 |
| ④ | 런 예산 80 vs `--max-notices 30` | 산술상 런당 최대 10건. 구조적 백로그 |
| ⑤ | 게시판 오선택을 성공으로 집계 | `announcement_fallback`이 `success`로 계산된다 |
| ⑥ | 크롤→추출 연결 실패 | 수동 킥 폴백이 스크립트에 하드코딩되어 있다 |

**이 사업은 «수리 먼저, 재가동 나중»이다.** 순서를 뒤집으면 안 되는 이유는 하나다 —
지금 스케줄러를 켜면 72일치 신규 공지가 ①~④를 그대로 통과한다. 첨부의 45.8%가
이미지인데(png 24 + jpg 6 + jpeg 2 = 32/70), 이미지 경로가 ③으로 망가져 있다.
고장을 안고 켜면 «처리했지만 내용이 빈» 공지가 대량으로 쌓이고, 재추출하지 않기로
결정했으므로(§2 비목표) 그건 영구 손실이다.

> **크롤 재가동 자체는 이 사업에서 한다.** 다만 §11의 워터마크 컷오프로
> «밀린 것»이 아니라 «지금부터 새로 오는 것»만 받는다.

### 1.1 2026-08-27 갱신 — 판독 경로의 비용 전제가 바뀌었다

**GCP 무료 크레딧이 소진됐다(사용자 확인, 2026-08-27).** 이 사업이 다루는 판독
(OCR·문서추출) 경로는 전부 Vertex AI Gemini(`gemini-2.5-flash` /
`gemini-2.5-flash-lite`, `gemini_document_extractor.py:130, 154, 388-389`)를 부른다.
그 호출은 이제 **크레딧 차감이 아니라 사용자 현금 지출**이다.

같은 날 **AWS Bedrock `Converse` API로 판독이 가능하다는 것이 실측으로 확인**됐다(§19).
Bedrock은 보유 크레딧으로 차감된다 — 사업 B 설계서가 확인한 것과 같은 사실
(`docs/superpowers/specs/2026-08-27-B-bedrock-translation-design.md:17-18`).

> **이 사실은 «무엇을 고칠 것인가»를 바꾸지 않는다.** ①~⑥은 제공자와 무관한 고장이고,
> 제공자를 갈아도 타일 예산·런 예산·워터마크·게시판 오선택은 그대로 남는다.
> 바뀌는 것은 «고친 뒤 어디로 갈 것인가»이며, 그 판단을 **§19**에 새로 넣었다.
> 결론은 §19.7 — **수리가 본체, 이전은 그 위에 얹는 선택**이다.

---

## 2. 목표 / 비목표

### 목표

1. 이미지 첨부(45.8%)가 예산 때문에 잘려나가지 않는다.
2. HWP 표 보존율을 70%(14/20)보다 올린다.
3. 본문 사진 산출물이 0건인 **원인이 규명된다** (수정은 원인에 달렸다).
4. 추출 경로가 429를 만나도 번역 경로와 같은 수준으로 버틴다.
5. 지금 관측 불가능한 것(429율·타일 폐기·예산 소진)이 로그에 남는다.
6. 스케줄러를 다시 켜고, **재가동 첫 런에서 신규 공지가 0건**이다(컷오프가 맞았다는 뜻).

### 비목표 (이 사업에서 하지 않는다)

- **기존 첨부 재추출** — 사용자 결정 (2026-08-26): "이제부터 다시 가정통신문 받을 거다."
  70건의 기존 첨부는 손대지 않는다. 사업 A §6.3(f)와 같은 방침이다.
- **밀린 공지 소급 수집** — 2026-06-15 이후 각 학교 게시판에 올라온 글은 받지 않는다(§11).
- **비용 최적화** — 사용자 결정: "비용은 신경 쓰지 않는다. 시간이 우선."
  이 문서의 모든 트레이드오프는 시간 편으로 기운다.
  > ⚠️ **2026-08-27 단서.** GCP 크레딧이 소진되어 Gemini 호출이 현금이 됐다(§1.1).
  > 그래도 이 비목표는 **유지한다** — §19.6에서 계산한 판독 경로의 월 현금은
  > **$1 미만**이라 콜 수를 아끼는 절충안을 넣을 이유가 되지 못한다.
  > 「비용을 이유로 타일을 버리거나 예산을 조이는 안」은 여전히 채택하지 않는다.
  > 비용이 실제로 결정을 바꾸는 지점은 «제공자를 바꿀 것인가»뿐이고 그건 §19다.
- **판독 백엔드 이전(Bedrock) 자체** — 설계는 §19에 완비하되 **이 사업의 본 배포 순서에
  넣지 않는다.** 계획의 «선택 Task 13»으로 분리한다(§19.7).
- **데모 관련 작업** — 데모는 끝났다. 데모 학교 예외를 새로 만들지 않는다.
- **크롤러 페이지네이션** — 스캔 깊이 너머(상위 8개 밖)의 글은 여전히 못 본다
  (`docs/scheduled-crawl-runbook.md:78-80`이 인정하는 한계). 그대로 둔다.
- **첨부 비공개화** — 사업 A(A3)의 몫. 여기서는 `public_url` 계약을 바꾸지 않는다.
- **`hwplib` / LibreOffice 폴백 부활** — `hwp_extractor.py:56,69`에서 이미 의도적으로
  꺼둔 경로다. 되살리지 않는다.

---

## 3. 작업 단위

| | 단위 | 크기 | 되돌리기 |
|---|---|---|---|
| C1 | 타일 예산 분리 (③) | `budget.py` + `image_gemini_extractor.py` | env 한 줄로 옛 동작 복원 |
| C2 | 런 예산 정합 + 직렬화 해제 (④) | **env 한 줄** | env 되돌리기 |
| C3 | 본문 사진 0건 진단 (②) | 조사 — 코드 변경 없음 | 해당 없음 |
| C4 | HWP 2순위 폴백 개선 (①) | `hwp_extractor.py` 한 함수 | 함수 되돌리기 |
| C5 | 추출 429 백오프 보강 | `gemini_document_extractor.py` 재시도부 | 함수 되돌리기 |
| C6 | 계측 추가 | 로그 문자열 + metadata 필드 | 로그 제거 |
| C7 | Job 설정 누락 3건 + 메모리 | 워크플로 1개 | 워크플로 되돌리기 |
| C8 | 워터마크 컷오프 시딩 | 스크립트 1개 (일회성) | 워터마크 SQL 복원 |
| C9 | 스케줄러 resume + 런북 | 문서 + `gcloud` 명령 | `pause` 재실행 |
| C10 | 게시판 오선택 감지 (⑤) | 집계 함수 + 알람 조건 | 함수 되돌리기 |
| C11 | 크롤→추출 연결 (⑥) | 판단만. 구현은 C3 결과에 종속 | — |

C2는 **env 한 줄**인데 효과가 가장 크다 (§6). 순서상 가장 먼저 간다.

---

## 4. C1 — 타일 24 vs 콜 8 의 산술 모순

### 4.1 모순의 정확한 형태

```
image_gemini_extractor.py:115   tile_height, step, limit = 2200, 2000, 24
budget.py:27                    max_gemini_calls=_int_env("MAX_GEMINI_CALLS_PER_NOTICE", 8)
image_gemini_extractor.py:75-84 _ocr_image() 가 타일마다 budget.reserve_gemini_call()
```

`extract_image_text`는 초장축 이미지를 최대 24조각으로 자른 뒤
(`image_gemini_extractor.py:38-56`) 조각마다 `_ocr_image`를 부른다. `_ocr_image`는
**조각 하나당 예산 1콜을 예약한다**(`:76`). 공지당 상한이 8이므로 **9번째 조각에서
`budget_exhausted`가 되고 남은 15조각은 빈 문자열로 버려진다**(`:78-84`).

버려지는 것은 조용하다. 타일 루프가 예외를 삼키고(`:54-55`), 빈 텍스트만
스킵하므로(`:52-53`) 최종 결과는 `gemini_vision_tiled[24]`인데 내용은 앞 8조각뿐이다.
운영에 `gemini_vision_tiled[2]` 2건이 있다 — 조각이 2개뿐이라 문제가 드러나지 않은
케이스다. **24조각짜리가 실제로 어떻게 잘렸는지는 지금 데이터로 알 수 없다**(미확인).

그리고 `budget_exhausted`는 즉시 포기 코드다
(`content_extraction_service.py:19` `IMMEDIATE_GIVEUP_CODES`,
`:1115-1116` → `next_run_at = None`, `attempts = max(attempts, 3)`).
**재시도조차 없다.**

여기에 더해, 24조각을 다 돌려도 그 공지의 다른 첨부(PDF·HWP)는 예산을 한 톨도
못 쓴다. 이미지 하나가 공지 전체 예산을 먹는 구조다.

### 4.2 선택지

| | 안 | 장점 | 단점 |
|---|---|---|---|
| **A** | **타일을 예산에서 분리** — 이미지 소스 1개 = 예산 1콜. 타일 수는 별도 상한 `MAX_TILES_PER_IMAGE`로만 제한 | 코드 최소 변경(예약 지점을 `_ocr_image`에서 `extract_image_text`로 올림). 이미지와 문서가 예산을 공평히 나눔. 해상도 손실 0 | 공지당 실제 Gemini 호출수가 8을 넘음 → 비용·시간 증가 (비용은 비목표) |
| **B** | 이미지당 예산을 별도 계정으로 — `max_gemini_calls`(문서용)과 `max_image_ocr_calls`(이미지용)를 분리 | 이미지·문서 각각 상한을 조절 가능 | 예산 개념이 둘로 늘어 `metadata()`·에러코드·문서가 전부 갈라짐. 「요청한 것만 최소 코드」 원칙 위반 |
| **C** | 타일 수를 줄이되 해상도 유지 — 타일 높이 2200→4400, 상한 24→12 | 예산 손 안 댐 | 4400px 타일은 `_normalize_image`의 `thumbnail((2400,2400))`(`:138`)에 걸려 **다시 축소된다.** 해상도 유지가 안 됨 → 이 안은 실효가 없다 |
| **D** | 여러 타일을 한 콜에 묶어 전송 | 콜 수 자체가 줄어 예산 문제 소멸 | `extract_bytes`가 **단일 `inlineData`/단일 `Part`만 지원**한다(`gemini_document_extractor.py:81-95, 105-125, 230-236`). 멀티파트 지원·프롬프트 재설계·조각 순서 보장이 전부 필요 → 이 사업 범위를 넘음 |

### 4.3 권고 — 안 A

**근거:**

1. **이미지가 첨부의 45.8%다** (32/70). 가장 많이 쓰이는 경로가 가장 잘 깨지는
   구조를 그대로 둘 수 없다.
2. **비용은 비목표, 시간이 우선**이다. 안 A의 유일한 단점이 비용·시간인데,
   비용은 신경 쓰지 않기로 했고 시간은 C2의 동시성 회복(§6)으로 상쇄된다.
3. 안 C는 `_normalize_image`의 2400px 썸네일 때문에 **실효가 없다**.
   이 사실은 코드를 읽기 전에는 보이지 않았다.
4. 안 D는 API 계층 변경이라 위험 대비 이득이 나쁘다.

**설계:**

- `reserve_gemini_call` 호출을 `_ocr_image`(`:75-84`)에서 `extract_image_text`
  진입부(`:38` 직후)로 **한 단계 올린다.** 이미지 소스 하나 = 예산 1콜.
- 타일 상한은 `MAX_TILES_PER_IMAGE`(기본 24, 현재 하드코딩된 `limit`을 env화)로만
  제한한다. `MAX_TOTAL_OCR_BYTES_PER_NOTICE`(26MB)는 **그대로 둔다** — 폭주에 대한
  마지막 방어선으로 남긴다. 타일 바이트는 `ocr_bytes_used`에 계속 누적한다.
- 타일이 바이트 상한에 걸려 중단되면 **버리지 말고 로그로 남긴다**(§8).

**롤백:** `MAX_TILES_PER_IMAGE=1`로 두면 타일링이 사실상 꺼지고 옛 동작에 가까워진다.
코드 롤백은 예약 지점을 한 줄 되돌리는 것이다.

---

## 5. C1 부수 — `budget_exhausted`의 즉시 포기

③의 절반은 «잘린다»이고 나머지 절반은 «잘린 채로 확정된다»이다.

`content_extraction_service.py:19`가 `budget_exhausted`를 즉시 포기 코드로 분류하고,
`:1115-1116`이 `extraction_next_run_at = None` + `extraction_attempts = 3`으로 못 박는다.
그 결과 예산 때문에 실패한 공지는 **다음 런에서 다시 시도되지 않는다.**

C1로 이미지 경로의 예산 소진이 사라지면 이 코드가 발동할 상황 자체가 줄지만,
`MAX_TOTAL_OCR_BYTES_PER_NOTICE`·`MAX_PDF_PAGES_FOR_OCR`(`budget.py:29-30`)로 인한
소진은 남는다.

**결정: 이 사업에서는 즉시 포기를 유지한다.** 바이트·페이지 상한은 «재시도해도 같은
결과»인 결정론적 한계라 재시도가 낭비다. 다만 **왜 소진됐는지가 로그에 남지 않는 것**이
문제이므로 §8에서 그것만 고친다.

> 미확인: 운영 35건 중 `budget_exhausted`로 확정된 공지가 몇 건인지는 실측하지
> 않았다. `extraction_error_code` 분포를 §12 검증에서 센다.

---

## 6. C2 — 런 예산 vs `--max-notices` 정합

### 6.1 모순

| 값 | 위치 | 값 |
|---|---|---|
| 런당 Gemini 콜 상한 | `config.py:133-137` `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN` | 80 |
| 공지당 콜 상한 | `budget.py:27` `MAX_GEMINI_CALLS_PER_NOTICE` | 8 |
| 배포 args | `deploy-api-cloud-run.yml:158` | `--max-notices 30` |

80 ÷ 8 = **런당 최대 10건**. `--max-notices 30`은 도달할 수 없는 숫자다.
런북이 이를 인정한다 — `docs/scheduled-crawl-runbook.md:74-75`:
*"실제 처리량은 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN`이 좌우 — 새 공지가 많으면 한 번에
다 못 하고 다음 run에 이어서 처리된다."*

**실제 처리량은 10건보다 더 적다.** 런 카운터에는 OCR 콜만 들어가는 게 아니다:

```
content_extraction_service.py:341  gemini_calls_used = _gemini_calls_used(result)   # 예산이 센 OCR 콜
:346                               gemini_calls_used += refine_calls               # 본문+첨부별 정제
:359                               gemini_calls_used += summary_calls              # 요약 1회
```

정제·요약 콜은 **`ExtractionBudget`이 예약하지 않는다**(`_refine_sources`·`summarize`
어디에도 `reserve_gemini_call`이 없다). 즉 공지당 실제 콜은 8이 아니라
`OCR 최대 8 + 정제(본문 1 + 첨부 N) + 요약 1`이다. 첨부 3개짜리 공지면 13콜.
**런 예산 80은 현실적으로 6~8건이다.**

### 6.2 같은 한 줄이 직렬화도 만든다

```python
# content_extraction_service.py:107-109
batch_size = 1 if notice_id else min(settings.extractor_notice_concurrency, remaining)
if settings.extractor_max_gemini_calls_per_run > 0:
    batch_size = 1        # ← 기본값 80 > 0 이므로 항상 여기
```

`run_for_school`도 같다(`:185-187`).
`_cap_reached`는 `cap > 0 and used >= cap`(`:1467-1468`)이라 **`cap = 0`이면 상한 자체가
꺼진다.** 즉 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0` 한 줄이

- 런 상한을 없애고 (`--max-notices`가 실제 상한이 된다)
- `batch_size = min(extractor_notice_concurrency, remaining) = 3`으로 복원한다
  (`config.py:117-122` 기본 3)

**두 문제를 동시에 푼다.** 이것이 이 사업에서 비용 대비 효과가 가장 큰 변경이다.

### 6.3 어느 쪽을 바꾸는가 — 런 예산을 끈다

`--max-notices`를 10으로 낮추는 대안은 «시간이 우선»에 정면으로 어긋난다.
비용 상한을 걷어내고 **공지 건수(`--max-notices 30`)를 유일한 상한으로 삼는다.**

폭주 방어는 이미 다른 층에 있다:

| 층 | 값 | 위치 |
|---|---|---|
| 공지 건수 | `--max-notices 30` | `deploy-api-cloud-run.yml:158` |
| 공지당 OCR 콜 | 8 | `budget.py:27` |
| 공지당 OCR 바이트 | 26MB | `budget.py:29` |
| 공지 타임아웃 | 600초 | `config.py:123-127` |
| Job 타임아웃 | 14400초 | `deploy-api-cloud-run.yml:159` |
| 동시 OCR 콜 | 6 | `extract_pipeline.py:83` `EXTRACTOR_OCR_CONCURRENCY` |

**남는 직렬 구간이 하나 더 있다.** 각 공지의 번역이 `:373`
`await _auto_translate_notice_locales(notice)`로 인라인 실행된다. 공지 3건을 동시에
돌려도 각각은 «추출 → 정제 → 요약 → 번역»을 끝내야 다음으로 넘어간다.
이건 이 사업에서 건드리지 않는다 — 동시성 3이 회복되면 체감 처리량이 3배가 되고,
그 이상은 429 위험을 새로 만든다.

---

## 7. C3 — 본문 사진 산출물 0건: 진단 계획

### 7.1 이건 구현이 아니라 진단이다

먼저 **관측치를 다시 정의해야 한다.** 코드를 읽어보니 파이프라인은
`extracted_content` 최상위에 `body_image` 키를 **애초에 쓰지 않는다.**

```python
# content_extraction_service.py:765-773  (_save_success)
if body_image_url:
    extracted_content.setdefault("sources", []).append({
        "source_id": "body_images_combined",
        "source_type": "attachment_image",
        "source_role": "body_images",
        "filename": "본문 사진.png",
        "public_url": body_image_url,
        ...
    })
```

저장소 전체에서 `body_image`라는 **키**를 쓰는 곳은 0건이다(`body_image`는 함수
지역변수 이름일 뿐 — `:362, 364, 757, 765`). 산출물의 실제 흔적은
**`sources[]` 안의 `source_id == "body_images_combined"`** 이다.

> ⚠️ **따라서 «최상위 `body_image` 키가 35건 전부 없다»는 관측은 고장의 증거가 아닐 수
> 있다.** 계측 대상을 잘못 짚은 것일 가능성이 첫 번째 가설이다.
> 진단은 여기서 시작해야 한다.

### 7.2 좁혀가는 순서

각 단계는 **앞 단계가 아니라고 나와야만** 다음으로 간다.

| 순서 | 가설 | 확인 방법 | 아니라면 |
|---|---|---|---|
| **H0** | 관측 대상이 틀렸다 | 운영 35건의 `extracted_content.sources[]`에서 `source_id = 'body_images_combined'` 개수를 센다 | 1건 이상이면 **고장이 아니다.** 사업 종료 |
| **H1** | 코드가 없던 시절에 추출됐다 | 기능 도입 커밋 `61fe3e2`(2026-06-04)와 각 공지의 최종 추출 시각을 비교. 스케줄러 정지가 2026-06-15이므로 **가능한 창은 11일뿐** | 창 안에 추출된 공지가 0건이면 **원인 확정.** 이후 신규 공지에서 자연히 해결 |
| **H2** | 수집이 안 됐다 (`inline_images`가 비어 있다) | `on_attachment` 콜백(`:294-303`)이 불렸는지. 파이프라인 쪽 진입점은 `extract_pipeline.py:236-242`(OCR 스킵 경로)와 `:263-265`(OCR 경로) 두 곳 | H3으로 |
| **H2a** | 노이즈 필터가 다 걸렀다 | `_looks_like_noise_image`(`extract_pipeline.py:583-584, 603-604`)에 걸린 건 **다운로드조차 안 한다**(`:230-231`이 `noise_filter`만 제외). 운영 `inline_image` 20건 중 status가 `skipped`+`inline_image_noise_filter`인 건수를 센다 | H2b로 |
| **H2b** | 다운로드가 실패했다 | `download_attachment` 예외를 `:243-244`가 **통째로 삼킨다**(`except: pass`). 지금은 흔적이 안 남는다 → §8에서 이 지점에 로그를 심고 재현으로 확인 | H3으로 |
| **H3** | 합성이 실패했다 | `_stitch_images_vertically`(`:687-716`)가 `None`을 반환. PIL이 열지 못한 이미지는 조용히 건너뛴다(`:697-698`) → 전부 건너뛰면 `pil`이 비어 `None` | H4로 |
| **H4** | 업로드가 실패했다 | `upload_bytes`(`attachment_storage.py:80-94`)가 실패 시 `WARNING` 로그 **1줄은 남긴다**(`:93`). Cloud Logging에서 `"bytes upload failed"` 검색 | H5로 |
| **H5** | 성공 경로에 도달 못 했다 | `:362`는 `_is_successful_extraction(result)`(`:1298-1303`)가 참일 때만 실행된다. `raw_text`가 비었거나 `content_kind == empty_or_unreadable`이면 통째로 건너뛴다 — **본문이 사진뿐이고 OCR이 실패한 공지가 정확히 이 함정에 빠진다** | 원인 미상. 재현으로 |

### 7.3 재현 방법

기존 첨부를 재추출하지 않는다는 결정(§2)은 **운영 데이터**에 대한 것이다.
진단용 일회성 실행은 여기 해당하지 않되, **운영 공지에 쓰기를 하면 안 된다.**

```
1. 본문에 사진이 있는 학교 공지 detail_url 1건을 고른다
   (inline_image source 가 잡힌 20건 중에서 고른다 — 이미 사진이 있다고 확인된 URL)
2. 로컬에서 extract_case() 를 직접 호출한다 (DB 미접속)
   - on_attachment 콜백을 로컬 파일 저장으로 바꿔 «몇 장이 수집되는지» 를 직접 센다
   - 이 경로는 _save_success 를 타지 않으므로 운영 DB 를 건드리지 않는다
3. 수집 장수 > 0 이면 → _stitch_images_vertically 를 그 바이트로 직접 호출 (H3)
4. 합성 성공이면 → 문제는 업로드(H4) 또는 성공경로 미도달(H5)
```

**중간 산출물**을 남길 곳:
- 수집 단계: `on_attachment(source_id, downloaded)`의 `source_id`·바이트 길이
- 필터 단계: `_inline_image_ocr_decision`의 `reason`(`extract_pipeline.py:572-595`)
- 합성 단계: PIL이 연 장수 / 건너뛴 장수 / 최종 폭·높이

이 셋은 §8(C6)에서 **영구 로그로 승격한다.** 진단이 끝나도 다음 사고 때 다시 쓰인다.

### 7.4 결론이 나기 전에는 고치지 않는다

H0~H5 중 무엇이 참인지에 따라 수정 위치가 전혀 다르다(계측 / 무수정 /
`except: pass` 제거 / PIL 처리 / 성공 판정 완화). **진단 없이 고치면 «고쳤다고 믿는
코드»만 늘어난다.** C3의 산출물은 코드가 아니라 «어느 가설이 참인가»라는 답이다.

---

## 8. C4 — HWP 2순위 폴백 개선

### 8.1 4단계 폴백의 실제 모양

`hwp_extractor.py:21-88`:

| 순위 | 방법 | 표 보존 | 진입 조건 | 운영 실적 |
|---|---|---|---|---|
| 1 | `hwp5html` → markdownify (`_hwp_to_markdown`, `:91-130`) | **보존** | 결과가 40자 이상 (`:31`) | `hwp5html_markdown` **14건** |
| 2 | OLE BodyText 직독 (`_try_hwp_ole_bodytext`, `:310-349`) | **소실** — `PARA_TEXT` 레코드(tag 67)만 긁으므로 표 구조가 사라진다 (`:352-371`) | 1순위 실패 | `hwp_ole_bodytext_filtered` **6건** |
| 3 | `hwp5txt` CLI (`_try_hwp5txt`, `:528-552`) | 소실 | 2순위도 빈 문자열 | 0건 |
| 4 | BinData 이미지 OCR (`_ocr_hwp_bindata_images`, `:485-525`) | — | 3순위도 실패 | 0건 |

**열화율 30%(6/20)는 «1순위가 실패한 비율»이다.** 3·4순위 실적이 0이라는 것은
2순위가 항상 무언가를 뱉는다는 뜻이고, 그래서 6건이 조용히 표를 잃었다.

### 8.2 왜 1순위가 실패했는지 — 지금 데이터로는 알 수 없다

이게 이 단위의 핵심 발견이다. `_hwp_to_markdown`에는 **경고를 남기지 않는 이탈 경로가
둘** 있다.

| 이탈 지점 | 코드 | 경고 |
|---|---|---|
| `hwp5html` 실행파일 없음 | `:99-100` `if command is None: return ""` | **없음** |
| 결과가 40자 미만 | `:31` `if len(markdown.strip()) >= 40:` — 미만이면 그냥 다음 블록으로 | **없음** |
| markdownify 미설치 | `:102-105` | `hwp5html_skip_no_markdownify` |
| 서브프로세스 실패 / index.xhtml 없음 | `:113-119` | `hwp5html_failed: returncode=… stderr=…` |
| 변환 중 예외 | `:128-130` | `hwp5html_failed: {타입}: {메시지}` |

운영에서 관측된 것은 `hwp_ole_storage_used: BodyText` 6건뿐이다 —
이건 **2순위가 성공했다는 표시**(`:344`)이지 1순위가 왜 실패했는지가 아니다.
`hwp5html_failed`가 관측 목록에 없다는 사실은 두 가지 중 하나를 뜻한다:

- (a) 6건이 **경고 없는 두 경로**(실행파일 없음 / 40자 미만)로 빠졌다, 또는
- (b) `warnings`가 저장되지 않았다 (미확인 — `_source_summary`가 무엇을 담는지
  확인 필요)

(a)의 «실행파일 없음»은 배제할 수 있다. `pyhwp==0.1b15`가
`backend/extractor-requirements.txt:8`에 있고 Dockerfile이 이를 설치하며
(`backend/Dockerfile:9-11`), 14건이 실제로 `hwp5html_markdown`으로 성공했다.
**따라서 유력한 것은 «결과가 40자 미만»이다.**

### 8.3 설계 — 진단 가능하게 만든 뒤 고친다

**(a) 침묵하는 이탈에 경고를 붙인다 (필수, 선행)**

```
:31   40자 미만 → warnings.append(f"hwp5html_too_short: chars={len(markdown.strip())}")
:100  command 없음 → warnings.append("hwp5html_skip_no_command")
```

두 줄이다. 이것 없이는 다음 개선이 맞았는지 검증할 수 없다.

**(b) 40자 임계값을 재검토한다**

`>= 40`은 근거가 문서화되지 않은 상수다. 표만 있고 산문이 적은 가정통신문
(예: 일정표 한 장)이 40자를 못 넘겨 표째로 버려질 수 있다.

**권고: «40자»를 «표가 있으면 통과»로 보강한다.** 길이가 아니라 **구조**로 판정한다.

```
표 마커(줄 시작 '|' 가 2줄 이상)가 있으면 길이와 무관하게 1순위 채택
없으면 기존 40자 기준
```

근거: 1순위의 존재 이유가 표 보존이다(`:92-96` docstring). 표가 나왔는데 짧다는 이유로
표를 못 읽는 2순위로 떨어뜨리는 것은 목적에 반한다. 운영 22/35(63%)의 공지가 온전한
마크다운 표를 갖고 있고 그 표들이 이 경로에서 나온다.

**(c) 2순위 자체는 건드리지 않는다**

`_extract_para_text_records`(`:352-371`)는 HWP5 레코드 구조상 `PARA_TEXT`(tag 67)만
읽는다. 표 셀도 결국 문단이라 텍스트는 나오지만 **행·열 경계 정보가 레코드에 없다.**
여기서 표를 복원하려면 `TABLE`(tag 76)·`LIST_HEADER` 레코드 파싱이 필요한데,
그건 이 사업의 크기를 넘는다. **2순위는 «표 없는 안전망»으로 남긴다.**

**(d) 도달률 목표**

표 보존율 70%(14/20) → **85% 이상**. 다만 이 숫자는 기존 20건에 대한 것이고,
재추출하지 않으므로(§2) **검증은 신규 HWP 첨부로만 한다.** 신규 유입이 적으면
판정에 시간이 걸린다 — 이건 수용한다.

---

## 9. C5 — 추출 경로의 429 대응 보강

### 9.1 격차

| | 번역 경로 | 추출 경로 |
|---|---|---|
| 구현 | `app/translation/gemini_client.py:35-58` `call_with_quota_backoff` | `extractors/gemini_document_extractor.py:238-275`(Vertex), `:277-309`(텍스트), `:159-206`(API키) — **각자 자체 재시도** |
| 지연 | `(5, 10, 20, 40)` × `(0.5 + random())` jitter | `2 ** attempt` → 1s, 2s |
| 시도 | 5 (마지막은 지연 없이 재호출, `:58`) | 3 |
| 최대 대기 | 5+10+20+40 = 75초, jitter 최대 1.5배 → **112.5초** | 1+2 = **3초** |
| 재시도 조건 | `is_quota_exhausted_error`(`:27-32`) — `429`/`resource_exhausted`/`rate limit`/`quota` | `retryable_tokens`(`:262-269`) — `429`/`resource_exhausted`/`503`/`unavailable`/`504`/`deadline` |
| 계측 | `:50-56` `"Gemini quota(429) hit; retrying call in %.1fs"` **WARNING 1줄** | **문자열 자체가 없음** |
| 동시성 가드 | `:61-71` `GEMINI_MAX_CONCURRENCY` 전역 세마포어 | `extract_pipeline.py:88-101` `EXTRACTOR_OCR_CONCURRENCY`(기본 6) — 별개 세마포어 |

Vertex는 dynamic shared quota라 일시 혼잡이 정상이다
(`gemini_client.py:21-23` 주석이 이를 설명한다). **3초 안에 포기하는 쪽이 이상하다.**

### 9.2 `call_with_quota_backoff` 재사용 가능성

**결론: 재사용한다. 단, 임포트 방향에 주의가 필요하다.**

| 검토 항목 | 판정 |
|---|---|
| 시그니처 | `factory: Callable[[], Awaitable[Any]]` — 인자 없는 코루틴 팩토리. 추출기의 `client.aio.models.generate_content(...)` 호출을 람다로 감싸면 그대로 맞는다 |
| 의존성 | `asyncio`, `random`, `logging`뿐. `app.core.config`는 `_get_call_semaphore`(`:64-71`)에서만 쓰고 `call_with_quota_backoff` 자체는 설정에 의존하지 않는다 |
| 임포트 방향 | ⚠️ `backend/extractor/`는 현재 `backend/app/`을 **임포트하지 않는다**(단방향). `extractor → app.translation` 임포트는 이 경계를 깬다 |
| 판단 | **`call_with_quota_backoff`와 `is_quota_exhausted_error`를 `extractor/` 쪽으로 옮기고 `app/translation/gemini_client.py`가 그걸 재임포트한다.** 방향이 뒤집혀도 `extractor`는 여전히 `app`을 모른다 |

> 대안(같은 로직을 추출기에 복붙)은 **하지 않는다.** 두 벌이 되면 다음에 지연값을
> 조정할 때 한쪽만 고치는 사고가 난다 — PR #66이 translation-worker만 고치고
> crawler-worker를 빠뜨린 것과 같은 종류의 사고다(§10).

### 9.3 적용 지점

`gemini_document_extractor.py`의 세 재시도 루프를 전부 바꾸지 않는다. **Vertex 경로만
바꾼다** — 운영은 `VERTEX_AI_PROJECT_ID`가 설정되어 Vertex로 간다
(`deploy-api-cloud-run.yml:163`, `gemini_document_extractor.py:53-55`).

| 함수 | 위치 | 조치 |
|---|---|---|
| `_generate_content_vertex` | `:238-275` | 재시도 루프를 `call_with_quota_backoff`로 교체. 모델 폴백 루프(`for model in _dedupe(models)`)는 **유지** — 429가 아닌 실패에는 여전히 다음 모델로 가야 한다 |
| `_generate_text_vertex` | `:277-309` | 위와 동일 |
| `_generate_json_payload` (API키) | `:159-206` | **건드리지 않는다.** 운영 경로가 아니고, `Retry-After` 헤더 처리(`:188, 201`)라는 더 나은 로직을 이미 갖고 있다 |

**주의:** 429가 아닌 재시도 토큰(`503`/`unavailable`/`504`/`deadline`, `:262-269`)은
`is_quota_exhausted_error`가 잡지 않는다. 이들에 대한 `2 ** attempt` 재시도는
**그대로 남긴다.** 429만 긴 백오프로 승격한다.

---

## 10. C6 — 계측 추가

지금 관측 불가능한 것들과, 그것을 어디에 남길지.

| # | 관측 불가 대상 | 남길 위치 | 형태 | 왜 필요한가 |
|---|---|---|---|---|
| 1 | **추출 경로 429 발생률** | `extractor/`로 옮긴 `call_with_quota_backoff` (§9.2) | 기존 WARNING 문자열 `"Gemini quota(429) hit"` 재사용 — `label`에 `ocr:{source_id}` 전달 | 문자열이 하나로 통일되면 번역·추출을 같은 쿼리로 센다 |
| 2 | **타일 폐기** | `image_gemini_extractor.py` `extract_image_text` 종료 직전 | `INFO`: `tiles=24 ocr_ok=8 ocr_empty=1 dropped=15` | ③이 재발했는지 한 줄로 판정 |
| 3 | **예산 소진 이유** | `ExtractionBudget.metadata()`(`budget.py:57-68`)가 이미 `budget_exhausted_reasons`를 담는다 → **저장되고 있는지 확인부터** | 확인 후 필요하면 `_source_summary`에 노출 | 소진이 콜 때문인지 바이트 때문인지 구분 불가 |
| 4 | **본문 사진 수집 실패** | `extract_pipeline.py:243-244`, `:266-267` — `except: pass` 두 곳 | `LOGGER.warning("inline image collect failed: source_id=%s %s")` | §7 H2b의 유일한 확인 수단 |
| 5 | **HWP 1순위 침묵 이탈** | `hwp_extractor.py:31`, `:99-100` | `warnings.append("hwp5html_too_short: chars=N")` / `"hwp5html_skip_no_command"` | §8.2 — 30% 열화의 이유 자체를 모른다 |
| 6 | **본문 사진 합성 결과** | `_combine_and_upload_body_images`(`:723-748`) | `INFO`: `collected=N stitched=M upload=ok\|fail` | §7 H3/H4를 로그만으로 가른다 |
| 7 | **인라인 이미지 필터 사유 분포** | `_inline_image_ocr_decision`(`extract_pipeline.py:572-595`) | 이미 `reason`이 `errors[]`에 저장된다(`:250`) — **추가 불필요** | 운영에 `inline_image_no_content_signal` 7건이 이미 보이는 이유 |

**원칙:** 새 로그는 전부 `LOGGER.info` / `LOGGER.warning`이다. 새 테이블·새 필드를
만들지 않는다. Cloud Logging 검색으로 세는 것이 이 규모(공지 38건)에 맞다.

---

## 11. C7 — 설정 누락 4건

| # | 누락 | 현재 실효값 | 근거 | 조치 |
|---|---|---|---|---|
| 1 | 추출 Job에 `GEMINI_MAX_CONCURRENCY` 미설정 | 코드 기본값 **12** (`config.py:47-52`) | `deploy-api-cloud-run.yml:163`에 없음. 번역 워커만 32 (`:116`) | 추출 Job에도 `GEMINI_MAX_CONCURRENCY=32` 추가. **이 값은 추출 Job의 인라인 번역 경로(`content_extraction_service.py:373`)에 걸린다** — OCR 세마포어(`EXTRACTOR_OCR_CONCURRENCY`)와는 별개다 |
| 2 | 추출 Job에 `EXTRACTOR_*` 전부 미설정 | `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=80`, `EXTRACTOR_NOTICE_CONCURRENCY=3`, `EXTRACTOR_OCR_CONCURRENCY=6`, `MAX_GEMINI_CALLS_PER_NOTICE=8` (전부 코드 기본값) | `deploy-api-cloud-run.yml:163` vs `docs/content-extractor-job.md:114` 권고 목록 | **`EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`을 명시적으로 넣는다**(§6.3). 나머지는 기본값이 맞으므로 «기본값에 의존한다»는 사실만 문서화 |
| 3 | crawler-worker Job에 `--batch-size` 누락 | argparse 기본 **3** (`crawler_worker.py:166`) | `deploy-api-cloud-run.yml:126` args에 없음. PR #66이 translation-worker(`:111`)만 고쳤다 | `--batch-size 3`을 **명시**한다. 값을 바꾸는 게 아니라 «암묵을 명시로» 바꾸는 것이다 — 다음에 기본값이 바뀌어도 배포가 흔들리지 않는다 |
| 4 | 추출 Job 메모리 512Mi | 512Mi | `deploy-api-cloud-run.yml:161` vs `docs/content-extractor-job.md:105` **2Gi 권고** | **2Gi로 올린다.** C1이 타일 24조각을 실제로 다 처리하게 만들고, `_stitch_images_vertically`(`:687-716`)가 최대 12장을 PIL로 동시에 열며(`_MAX_BODY_IMAGES = 12`, `:720`), `Image.MAX_IMAGE_PIXELS`가 5000만 화소(`image_gemini_extractor.py:22`)다. 512Mi로는 OOM 위험이 실재한다 |

> #3에 대한 주의: 문제는 «3이 틀렸다»가 아니라 «PR #66이 두 곳 중 한 곳만 고쳤다»는
> 것이다. 같은 종류의 누락을 막으려면 두 Job의 args를 나란히 놓고 읽을 수 있어야 한다.

---

## 12. C8 · C9 — 크롤 재가동

### 12.1 워터마크가 실제로 어떻게 동작하는가

**워터마크는 시각이 아니라 «글번호»다.** 이것이 «지금부터»의 의미를 결정한다.

```
school_crawl_state.board_watermarks jsonb    (0033 마이그레이션)
  → { "boardID=32701|m=0201|s=munnam": 1218492, ... }
     ^^^ board_key (CMS별 문자열, notice_post_extractor.py:295,347)
                                        ^^^ 그 게시판에서 본 최대 글번호
```

| 동작 | 코드 |
|---|---|
| 켜짐 여부 | `config.py:85-88` `CRAWLER_WATERMARK_ENABLED` **기본 `True`** |
| 읽기 | `school_crawler_service.py:694-718` `_read_board_watermarks` |
| 필터 | `:669-691` `_apply_watermark_filter` — `value <= baseline`이면 **제외** |
| 쓰기 | `:721-727` `_write_board_watermarks` (달라졌을 때만, `:781-782`) |
| 대상 제한 | `:652-666` `_watermark_post_value` — **숫자 post_id만.** 해시 생성(`generated`)·첨부번호(`file_download`)·경로숫자·카테고리 id는 `None` → **항상 통과** |
| 기준선 없을 때 | `:687-690` `baseline is None`이면 **전부 통과** (첫 크롤 = 전량 수집) |

### 12.2 «지금부터»의 정확한 정의

세 가지를 각각 정의해야 한다.

**(a) 어느 시각 기준인가**

시각 기준은 **존재하지 않는다.** 게시일을 저장하지 않으므로 번호로만 판단한다
(`docs/scheduled-crawl-runbook.md:76-78`이 이 한계를 명시한다).

> **따라서 «지금부터» = «재가동 시점에 각 게시판의 최상단에 있는 글번호 이하는 받지
> 않는다».** 시각이 아니라 «현재 최대 글번호»가 컷오프다.

**(b) 이미 저장된 워터마크는 어떤 상태인가**

8개 학교의 `board_watermarks`는 **2026-06-15 기준값**이다
(`scripts/_state_out.txt:9` `last_checked_at: 2026-06-15T03:38:17`).
그대로 켜면 06-15 이후 올라온 글이 **전부 신규로 잡힌다.** 이게 «밀린 것 우르르»다.

다만 규모는 무한이 아니다. 스캔 깊이가 `CRAWLER_SCHEDULE_NOTICE_COUNT=8`
(`deploy-api-cloud-run.yml:148`)이므로 **학교당 한 런에 최대 8건, 8개 학교면 최대 64건**이다.
72일치 전부가 아니라 «각 게시판 상위 8개 중 06-15 이후 것»이다.

64건이라도 사용자 결정에 어긋난다. 따라서 **컷오프 시딩이 필요하다.**

**(c) 이미 pending인 공지는 어떻게 하는가**

운영에 공지 38건 중 완료 35건 → **비완료 3건**이 있다
(`scripts/_state_out.txt:19`에 `[processing]` 1건 확인). 이들은 **크롤은 됐지만 추출이
안 끝난** 상태다.

> **결정: 이 3건은 그냥 둔다.** 재가동 후 첫 추출 런이 자연히 집어간다
> (`_claim_notice` → `claim_notice_extractions` RPC가 `pending`/`error`/stale
> `processing`을 claim한다, `:1127-1154`).
> 이건 «기존 첨부 재추출»(비목표)이 아니다 — **한 번도 추출된 적 없는 공지**다.
> 재추출 금지는 이미 `done`인 35건에 대한 것이다.
> 다만 `processing` 1건은 `EXTRACTOR_STALE_MINUTES=180`(`config.py:128-132`)을
> 훨씬 넘겼으므로 stale 회수로 자동 처리된다.

**(d) 이미 크롤된 URL은 어떻게 되는가**

`notices` 테이블의 unique 제약이 막는다. 같은 글이 다시 발견되면 insert가 실패하고
`_update_existing_notice_candidate`(`:786-819`)로 **crawl_result만 갱신**된다.
새 공지로 취급되지 않으므로 추출이 다시 돌지 않는다. **조치 불필요.**

### 12.3 C8 — 컷오프 시딩 설계

목표: **재가동 첫 런에서 신규 공지 0건.**

| | 안 | 판정 |
|---|---|---|
| A | `scheduled_school_crawler --dry-run`으로 현재 최대 글번호를 얻어 SQL로 워터마크를 갱신 | **불가.** `dry_run`은 게시판 스캔 전에 반환한다(`scheduled_crawler_service.py:105-116`). 글번호를 알 수 없다 |
| B | 일회성 스크립트가 `SchoolCrawlerService`로 게시판을 스캔하되 **`notices` insert를 하지 않고** `board_watermarks`만 쓴다 | **권고** |
| C | 첫 런을 그냥 돌리고 새로 들어온 공지를 나중에 지운다 | 추출·번역 비용이 이미 발생하고, 삭제가 사용자에게 보인다. 기각 |
| D | `CRAWLER_WATERMARK_ENABLED=false`로 두고 다른 방법을 쓴다 | 반대 방향이다(필터가 아예 꺼진다). 기각 |

**안 B의 형태:**

```
scripts/seed_watermarks.py  (일회성, APPLY 플래그 필요 — dry-run 기본)
  각 학교에 대해
    1. 게시판 스캔 (기존 discovery 경로 재사용)
    2. valid_posts 에서 _watermark_post_value 로 board_key → max 값을 계산
    3. --apply 일 때만 school_crawl_state.board_watermarks 를 그 값으로 덮어쓴다
    4. notices 는 절대 건드리지 않는다
```

기존 함수를 그대로 쓴다 — `_watermark_post_value`(`:652-666`),
`_apply_watermark_filter`(`:669-691`)의 갱신 로직(`updated[board_key] = max(...)`)이
이미 «최대값 계산»을 한다. 새 로직을 쓰지 않는다.

**남는 구멍 (수용):** `_watermark_post_value`가 `None`을 주는 글
(해시 생성 id·비숫자 post_id)은 **워터마크로 막을 수 없다.** 이들은 기존 중복제거만
적용되므로, 06-15 이후 올라온 그런 글은 재가동 첫 런에 들어올 수 있다.
운영 8개 학교의 CMS가 대부분 숫자 시퀀스(eGovFrame `nttSn`, `boardCnts boardSeq`)라
실제 유입은 적을 것으로 본다 — **미확인.** §14 검증에서 실제 건수를 센다.

### 12.4 C9 — 스케줄러 resume 절차

**저장소에 `gcloud scheduler jobs pause|resume` 언급이 0건이다.**
검색 결과 스케줄러 관련 언급은 `docs/superpowers/specs/2026-08-26-prerequisites.md:13`의
`gcloud scheduler jobs list` 하나뿐이다. 정지시킨 방법이 문서에 없으니 되살리는 방법도 없다.

**현황 (2026-08-26 `gcloud` 실측):**

| 스케줄러 | 주기 | 상태 | 런북 표기 |
|---|---|---|---|
| `naranhi-school-crawler-0600` | `0 6 * * *` | PAUSED | 일치 |
| `naranhi-school-crawler-1900` | `0 19 * * *` | PAUSED | **불일치** — 런북은 `-1800`/`0 18 * * *` (`docs/scheduled-crawl-runbook.md:11, 65`) |
| `naranhi-content-extractor-0700` | `0 7 * * *` | PAUSED | 일치 |
| `naranhi-content-extractor-2000` | `0 20 * * *` | PAUSED | **불일치** — 런북은 `-1900`/`0 19 * * *` (`:12, 67`) |
| `naranhi-crawler-backstop` | `*/10 * * * *` | PAUSED | 런북에 없음 |
| `naranhi-translation-backstop` | `*/10 * * * *` | ENABLED | 런북에 없음 |

**런북을 실제와 맞추는 것이 C9의 절반이다.** 이름이 틀린 문서는 없느니만 못하다.

**resume 절차 (런북에 신설할 절):**

```bash
REGION="asia-northeast3"

# 1. 현재 상태 확인 (무엇이 멈춰 있는지 눈으로 본다)
gcloud scheduler jobs list --location="$REGION" \
  --format="table(name.basename(), schedule, state)"

# 2. 재가동 (순서 중요 — 아래 설명)
gcloud scheduler jobs resume naranhi-content-extractor-0700 --location="$REGION"
gcloud scheduler jobs resume naranhi-content-extractor-2000 --location="$REGION"
gcloud scheduler jobs resume naranhi-crawler-backstop       --location="$REGION"
gcloud scheduler jobs resume naranhi-school-crawler-0600    --location="$REGION"
gcloud scheduler jobs resume naranhi-school-crawler-1900    --location="$REGION"

# 3. 비상 정지 (되돌리기)
gcloud scheduler jobs pause <이름> --location="$REGION"
```

**순서 근거:** 추출기를 먼저 켠다. 크롤러가 먼저 켜지면 신규 공지가 `pending`으로
쌓이는데 추출기가 자고 있어 ⑥(§13)과 구분이 안 되는 상태가 만들어진다.
추출기가 먼저 깨어 있으면 «크롤 → 다음 정시 추출»이 즉시 이어진다.

**정지 재발 방지:** 다음에 누군가 다시 pause하면 같은 일이 반복된다.
런북에 «정지했으면 이 표의 상태 칸을 고치고 날짜를 적는다»를 규칙으로 넣는다.
`MEMORY.md`의 `paused_crawl_schedulers_demo.md`가 이번에 그 역할을 했지만,
그건 개인 메모지 저장소 문서가 아니다.

### 12.5 정기 크롤러에 재시도가 없다

`--max-retries=0` (`deploy-api-cloud-run.yml:145`). 실패하면 12시간 뒤 다음 스케줄이다.
반면 큐 워커는 `--max-retries=1`(`:113, 128`)에 좀비 회수까지 갖췄다
(`crawler_worker.py:109-112`).

> **결정: 이 사업에서 바꾸지 않는다.**
> `naranhi-crawler-backstop`이 10분마다 돌아 사실상의 재시도 역할을 한다.
> Cloud Run Job retry는 **task 전체 재실행**이라 학교 단위 재시도가 아니고,
> 그 위험은 `docs/content-extractor-job.md:100`이 추출기에 대해 이미 설명한 것과 같다.
> «재시도가 없다»는 사실을 런북에 적는 것으로 갈음한다.

---

## 13. C10 · C11 — 크롤 쪽 문제 둘

### 13.1 C10 — 게시판 오선택을 성공으로 집계한다 (⑤)

**증상:** 인천문남초는 `crawl_status: success`인데
`crawl_board_kind: announcement_fallback`이다
(`scripts/_state_out.txt:6-8`). 가정통신문 게시판을 못 찾아 공지사항 게시판으로
대체했고, 실제 수집물은 「제26회 산림문화작품공모전」 등 가정통신문이 아닌
일반 공지다(`:19-21`).

**성공률 계산이 이를 못 잡는다:**

```python
# scheduled_crawler_service.py:333-336
success_count = sum(1 for item in results if item.status == "success")
success_rate = success_count / processed if processed else 1.0
alarm = bool(processed and success_rate < fail_rate_threshold)
```

`ScheduledSchoolResult`(`:44-53`)에는 `status`·`success_count`·`error_message`만 있고
**`board_kind`가 없다.** 게시판을 잘못 골라도 글만 잘 긁으면 성공이다.

**신호는 이미 저장되고 있다.** 대체 결정 시점에 `needs_human_check=True`가 세팅되고
(`board_detector.py:123, 148`), `fallback_used`가 `crawl_result`에 들어간다
(`scripts/_state_out.txt:13` 키 목록에 `fallback_used` 존재).
`school_crawl_state.crawl_board_kind` 컬럼에도 값이 있다(`school_crawler_service.py:616-618`).

**설계 — 실패로 세지 않는다. 따로 센다.**

| 안 | 판정 |
|---|---|
| `announcement_fallback`을 `status = "error"`로 강등 | **기각.** 그 학교는 공지를 실제로 받고 있다. 실패로 만들면 `crawler_schedule_fail_rate_threshold=0.5`(`config.py:106-111`) 알람이 오작동하고, 학부모는 아무것도 못 받게 된다 |
| **`ScheduledCrawlerSummary`에 `fallback_count`를 추가하고 로그·요약에 노출** | **권고.** 성공률 정의를 바꾸지 않으면서 «몇 개 학교가 잘못된 게시판을 보고 있는가»가 매 런마다 보인다 |
| 별도 알람 임계 추가 | 지금 학교가 8곳이다. 숫자 하나면 눈으로 판정 가능. 임계값은 학교가 늘면 그때 |

**구현 크기:** `ScheduledSchoolResult`에 `board_kind` 필드 1개,
`_result_item`(`:307-317`)에서 `result.board_kind` 전달,
`_build_summary`(`:320-352`)에서 카운트 1줄, 요약 dataclass에 필드 1개.

**«올바른 게시판을 다시 찾는 것»은 이 사업의 범위가 아니다.** 인천문남초의 홈페이지에
가정통신문 메뉴가 실제로 없을 수도 있다(미확인). 먼저 «몇 곳인가»를 보이게 하고,
대응은 그 숫자를 보고 정한다.

### 13.2 C11 — 크롤 후 추출이 자동으로 안 걸린다 (⑥)

**증거:** `scripts/recrawl_monitor.py:78-81`에 수동 킥이 하드코딩되어 있다.

```python
if (not extract_done and el > 120 and c.get("pending", 0) > 0
        and c.get("processing", 0) == 0 and c.get("done", 0) == 0):
    st, _ = req("POST", f"{API}/crawler/schools/{SCHOOL_ID}/extract-pending", ...)
```

«경과 120초 초과 & pending>0 & processing==0 & done==0» — 이 조건이 스크립트에
박혀 있다는 것은 그 상태가 **재현 가능할 만큼 흔했다**는 뜻이다.

**코드를 읽고 나온 것: 경로가 둘인데 하나에는 연결이 아예 없다.**

| 경로 | 크롤 후 추출 연결 |
|---|---|
| **큐 경로** (`crawler_worker`) | **있다.** `_run_discovery_job`(`crawler_worker.py:31-37`)이 `status == "success" and success_count > 0`이면 `school_notice_extraction` 잡을 enqueue하고, 같은 워커의 drain 루프(`:116-129`)가 이어서 집는다 |
| **정기 경로** (`scheduled_school_crawler` → `ScheduledCrawlerService.run`) | **없다.** `scheduled_crawler_service.py` 어디에도 enqueue가 없다. 추출은 **1시간 뒤 별도 스케줄러**(`naranhi-content-extractor-0700`)가 맡는다 |

즉 정기 경로의 «즉시 연결 없음»은 고장이 아니라 **설계다**
(`docs/scheduled-crawl-runbook.md:9-12`가 06:00 크롤 / 07:00 추출로 명시).

그렇다면 `recrawl_monitor.py`의 폴백은 **큐 경로**에서 생긴 것이다. 그 경로에서
연결이 끊길 수 있는 지점:

| 지점 | 코드 | 끊기는 조건 |
|---|---|---|
| enqueue 조건 | `crawler_worker.py:31` | `success_count == 0`이면 enqueue 자체가 없다. **워터마크가 켜져 있으면 «새 글 없음» = `success_count 0`** — 재크롤 시 정상적으로 0이 된다 |
| 중복 억제 | `job_queue_service.py:52-63` | 같은 `job_key`(`school-extraction:{id}`)로 `queued`/`processing` 잡이 있으면 `already_running`으로 새로 만들지 않는다. **앞 런의 잡이 `processing`에 걸려 있으면 조용히 무시된다** |
| drain 종료 | `crawler_worker.py:122-129` | enqueue 직후 `idle_grace_seconds`(배포값 3초) 안에 claim되어야 한다. 놓치면 백스톱(10분)까지 대기 |
| 백스톱 | `naranhi-crawler-backstop` | **PAUSED다.** 이게 정지된 동안은 놓친 잡을 아무도 깨우지 않는다 |

> **판단: 폴백이 하드코딩된 근본 원인은 «크롤과 추출을 잇는 계약이 두 경로에서 다른데
> 어느 쪽도 문서에 없어서, 운영자가 관측된 증상에 스크립트로 대응했다»는 것이다.**
>
> 이 사업에서 코드를 고치지 않는다. 대신 셋을 한다:
> 1. §12.4에서 `naranhi-crawler-backstop`을 **resume한다** — 놓친 잡을 10분 안에 회수한다.
> 2. 두 경로의 차이를 런북에 표로 적는다 (위 표를 그대로).
> 3. 재가동 후 §14 검증에서 «크롤 종료 → 추출 시작»까지의 실제 지연을 잰다.
>    폴백 조건(120초)이 여전히 필요한지는 그 숫자를 보고 정한다.
>
> **하드코딩된 폴백을 지우지 않는다.** 지금은 그게 유일한 안전망이다.
> 검증에서 «필요 없다»가 나오면 그때 지운다.

---

## 14. 배포 순서

되돌리기 쉬운 것부터, 서로의 전제가 되는 순서로.
**크롤 재가동(6~7)은 수리(1~5)가 검증된 뒤다.**

| 배포 | 내용 | 확인 |
|---|---|---|
| **1** | C7 — Job env·args·메모리 (`GEMINI_MAX_CONCURRENCY=32`, `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`, `--batch-size 3`, `--memory=2Gi`) | Job 리비전에 값이 반영. **이 배포만으로 C2가 끝난다** |
| **2** | C6 — 계측 (로그만. 동작 변경 0) | 로그 문자열이 나온다 |
| **3** | C3 — 진단 실행 (배포 아님. 1·2 배포 후 로그를 보며 §7.2를 순서대로) | H0~H5 중 하나가 확정 |
| **4** | C1 — 타일 예산 분리 + C4 — HWP 폴백 | 단위 테스트 통과 |
| **5** | C5 — 429 백오프 (`call_with_quota_backoff` 이동 + Vertex 경로 교체) | 번역 경로 회귀 없음 |
| **6** | C8 — 워터마크 시딩 (dry-run → 확인 → `--apply`) | 8개 학교 `board_watermarks`가 현재 최대값 |
| **7** | C9 — 스케줄러 resume (추출기 → 백스톱 → 크롤러 순) | 첫 크롤 런에서 **신규 공지 0건** |
| **8** | C10 — `fallback_count` 집계 | 다음 런 요약에 숫자가 보인다 |

**1이 맨 앞인 이유:** env 한 줄로 처리량이 배 이상 오르고, 그 상태여야 이후 진단·검증이
현실적인 시간에 끝난다.

**3(진단)이 4(수정)보다 앞인 이유:** §7.4 — 원인을 모르고 고치면 고쳤는지 알 수 없다.

**6이 7보다 앞인 이유:** 시딩 전에 스케줄러를 켜면 그 순간 64건이 들어온다(§12.2b).
되돌릴 수 없다.

**8이 마지막인 이유:** 집계 변경은 아무것도 막지 않는다. 급할 이유가 없다.

---

## 15. 검증

| 항목 | 방법 | 통과 기준 |
|---|---|---|
| C7-1 | `gcloud run jobs describe` 로 추출 Job env 확인 | `GEMINI_MAX_CONCURRENCY=32`, `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0` 존재 |
| C7-3 | crawler-worker Job args 확인 | `--batch-size,3` 존재 |
| C7-4 | 추출 Job 메모리 | `2Gi` |
| C2 | 추출 Job 1회 수동 실행 후 로그 | `content extractor result:` 줄이 **동시에 3건씩** 나온다 (직렬화 해제 확인) |
| C2 | 같은 런의 summary JSON | `gemini_call_cap_reached: false` |
| C1 | 초장축 이미지 첨부 1건 추출 | 로그에 `tiles=N ocr_ok=N dropped=0` — **`dropped`가 0** |
| C1 회귀 | 일반 이미지(타일링 미적용) 추출 | `method: gemini_vision`, 예산 1콜 소비 |
| C4 | 신규 HWP 첨부 추출 | `extraction_method`가 `hwp5html_markdown`. 2순위로 떨어졌다면 **warnings에 이유가 있다** |
| C4 | 2순위로 떨어진 건 | `hwp5html_too_short` 또는 `hwp5html_failed` 중 하나가 반드시 기록됨 (침묵 이탈 0) |
| C5 | Cloud Logging에서 `"Gemini quota(429) hit"` 검색 | 추출 Job 로그에서도 검출된다 (지금은 0건) |
| C5 회귀 | 번역 워커 1회 실행 | 번역 성공률 변화 없음 |
| C6 | 로그 검색 7종(§10) | 각 문자열이 최소 1회 관측 가능 |
| C3 | §7.2 H0 | `sources[].source_id = 'body_images_combined'` 개수 — **0이면 H1로, 1 이상이면 고장 아님** |
| C3 | 진단 종료 | H0~H5 중 정확히 하나가 «참»으로 확정 |
| C8 | 시딩 dry-run 출력 | 8개 학교 × board_key별 현재 최대값이 기존 워터마크보다 **크거나 같다** |
| C8 | `--apply` 후 SQL 조회 | `board_watermarks`가 dry-run 값과 일치 |
| **C9** | **resume 후 첫 크롤 런 요약** | **`success_count` 합계 = 0** (= 신규 공지 0건. 컷오프 성공) |
| C9 | 첫 런에서 0이 아니라면 | 들어온 글의 `post.method`·`post.source`를 본다 — 워터마크 비대상(§12.3 «남는 구멍»)이면 **수용**, 숫자 id인데 들어왔으면 시딩 실패 → 롤백 |
| C9 | 스케줄러 상태 | `gcloud scheduler jobs list`에서 6개 전부 `ENABLED` |
| C11 | 크롤 → 추출 지연 | 큐 경로: 크롤 종료 후 추출 시작까지 걸린 시간을 기록 (판정 아님, 측정) |
| C10 | 다음 정기 크롤 요약 | `fallback_count >= 1` (인천문남초가 잡힌다) |
| 전체 | 재가동 3일 후 | `extraction_error_code` 분포에서 `budget_exhausted` **0건** |
| **환각 N1** | **negative control — 판독 불가 입력(QR 코드 전용 PNG)** | 결과가 «읽을 수 없다» 또는 빈 텍스트. **가정통신문 형태의 문장이 나오면 실패** |
| **환각 N2** | negative control — 백지/노이즈 이미지 | 위와 같다. 학교명·교장·날짜 같은 **구체 명사가 하나라도 생성되면 실패** |
| **환각 N3** | positive control — 내용이 확실한 PDF 1건 | 원본에 실제로 있는 문자열이 결과에 있다. N1·N2가 «항상 빈 결과»여서 통과한 것이 아님을 보인다 |

> **N1~N3은 왜 필요한가.** 나머지 검증은 전부 «무언가가 나왔는가»를 본다.
> 판독의 진짜 실패는 «아무것도 못 읽고 그럴듯한 것을 지어냈다»이고, 그건
> 나오는 쪽이라 기존 기준을 **전부 통과한다**. §19.2의 Nova 결과가 그 증거다.
> **현행 Gemini도 같은 위험을 갖는다 — 확인한 적이 없을 뿐이다**(§18 #10).

---

## 16. 위험과 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| **워터마크 시딩 실패로 밀린 공지가 들어온다** | 최대 64건이 처리됨. 재추출 금지 방침상 되돌리기 어렵다 | 시딩을 **dry-run 기본**으로 만들고 출력을 눈으로 확인한 뒤에만 `--apply`. 배포 6이 7보다 앞(§14). 실패 시 스케줄러를 즉시 `pause`하고 워터마크를 백업값으로 SQL 복원 |
| **`EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=0`이 폭주를 부른다** | Vertex 호출 급증, 429 다발 | 상한 6층이 남아 있다(§6.3 표). 되돌리기는 env 한 줄. 첫 런은 **수동 실행으로 지켜본다** |
| **C1로 공지당 콜이 8을 크게 넘는다** | 한 공지가 런을 오래 잡는다 | `EXTRACTOR_NOTICE_TIMEOUT_SECONDS=600`(`config.py:123-127`)이 공지 단위로 자른다. `MAX_TOTAL_OCR_BYTES_PER_NOTICE` 26MB 유지 |
| **메모리 2Gi로도 부족** | 타일 24 + PIL 합성 12장에서 OOM | C1 검증(§15)에서 초장축 이미지를 **의도적으로** 돌려 본다. 부족하면 4Gi |
| **C5의 `call_with_quota_backoff` 이동이 번역을 깬다** | 번역 파이프라인 전체 정지 | 함수 본문을 바꾸지 않고 **위치만** 옮긴다. 번역 워커 회귀 테스트가 배포 5의 통과 조건 |
| **C3 진단이 결론 없이 끝난다** | 본문 사진 문제가 미해결로 남는다 | **수용한다.** ②는 이미 72일 방치됐고 서비스가 죽지 않았다. 신규 공지가 들어오면 H1이 자연 해소될 수 있다. 결론이 안 나면 «미해결»로 기록하고 다음 사업으로 넘긴다 |
| **HWP 표 판정 완화가 쓰레기를 통과시킨다** | 짧은 깨진 markdown이 1순위로 채택 | 표 마커 2줄 이상이라는 조건은 markdownify가 실제 `<table>`을 변환했을 때만 만족한다. 그래도 불안하면 «표 마커 + 최소 20자»로 조인다 |
| **스케줄러를 켰는데 크롤이 실패한다** | 12시간 대기 (`--max-retries=0`) | `naranhi-crawler-backstop`을 함께 resume(§12.4). 첫 런은 수동 실행으로 확인한 뒤 스케줄러를 켠다 |
| **`recrawl_monitor.py` 폴백을 성급히 지운다** | 유일한 안전망 소실 | §13.2 결정 — **지우지 않는다.** 측정 결과가 나온 뒤에만 판단 |

각 단위는 단독 롤백이 가능하다. C7·C2는 env, C1·C4·C5는 함수 되돌리기,
C8은 워터마크 SQL 복원, C9는 `pause` 재실행, C6·C10은 제거해도 동작에 영향 없음.

---

## 17. 결정 기록 (2026-08-26)

| # | 질문 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | 크롤을 다시 켤 것인가 | **켠다.** 단 «밀린 것 우르르»가 아니라 «지금부터 새로 올라오는 것»만 | §12 — 워터마크 컷오프 시딩(C8) + resume(C9) |
| 2 | 기존 첨부를 재추출할 것인가 | **하지 않는다.** "이제부터 다시 가정통신문 받을 거다" | §2 비목표. §8.4 HWP 검증을 신규 첨부로만 하는 이유 |
| 3 | 비용을 고려할 것인가 | **하지 않는다. 시간이 우선** | §4.3 안 A 선택, §6.3 런 예산 해제 |
| 4 | 데모를 계속 지원할 것인가 | **끝났다** | §2 비목표 — 데모 예외 없음 |

### 결정에서 파생된 판단 (이 문서에서 정한 것)

| # | 판단 | 근거 |
|---|---|---|
| 5 | 타일 예산은 **안 A**(소스 단위 예약) | 이미지 45.8% + 비용 비목표. 안 C는 `_normalize_image`의 2400px 썸네일 때문에 실효 없음(§4.2) |
| 6 | 런 예산은 **끄고** `--max-notices`를 유일 상한으로 | 같은 env 한 줄이 강제 직렬화도 푼다(§6.2) |
| 7 | ② 는 **진단이 산출물**이다 | 최상위 `body_image` 키는 코드에 존재하지 않는다 — 관측 자체가 틀렸을 수 있다(§7.1) |
| 8 | `budget_exhausted` 즉시 포기는 **유지** | 바이트·페이지 상한은 결정론적. 재시도가 낭비(§5) |
| 9 | `announcement_fallback`은 **실패로 세지 않는다** | 그 학교는 공지를 실제로 받고 있다. 따로 센다(§13.1) |
| 10 | `recrawl_monitor.py` 폴백은 **지우지 않는다** | 유일한 안전망. 측정이 먼저(§13.2) |
| 11 | 정기 크롤러 `--max-retries=0`은 **그대로** | 백스톱이 사실상의 재시도. Job retry는 task 전체 재실행이라 학교 단위가 아니다(§12.5) |
| **12** | **Nova는 한국어 판독에서 제외** (완전 삭제가 아니라 용도 제한) | 판독 불가 입력에 대해 없는 가정통신문을 지어냈다. 검출 불가능한 실패 양상이다(§19.3) |
| **13** | **Claude Opus 계열은 금지** | 사용자 지시(2026-08-27) "절대 쓰지마 너무 비싸". 판독 기본은 Haiku 4.5, 승급만 Sonnet 4.6(§19.8) |
| **14** | 판독 이전은 **(가) 먼저, (나)는 선택 Task로 분리** | 아끼는 현금이 월 $1 미만이고 커버 범위가 70.1%다. 이전이 고치는 고장은 0개다(§19.5~19.7) |
| **15** | 판독 검증에 **환각 negative control을 추가**한다 | 지금 검증은 «표가 나오는가»만 본다. Nova 시험이 보여주듯 «못 읽었을 때 지어내는가»는 별개의 질문이고, 현행 Gemini에 대해 한 번도 확인한 적이 없다(§15, §18 #10) |

---

## 18. 열린 질문

| # | 질문 | 왜 지금 답할 수 없는가 | 언제 답이 나오나 |
|---|---|---|---|
| 1 | 본문 사진 0건의 진짜 원인은? | H0~H5 중 어느 것도 코드만으로는 판정 불가 | C3 진단 (배포 3) |
| 2 | `extracted_content.sources[].warnings`가 실제로 저장되는가? | `_source_summary`가 담는 필드를 확인하지 않았다. §8.2 (b) 가설의 전제 | C6 배포 후 운영 데이터 1건 조회 |
| 3 | 운영 35건 중 `budget_exhausted`로 확정된 공지가 몇 건인가? | `extraction_error_code` 분포를 실측하지 않았다 | §15 «재가동 3일 후» 항목 |
| 4 | 24조각짜리 이미지가 실제로 몇 조각에서 잘렸는가? | `gemini_vision_tiled[N]`의 N만 저장되고 «몇 조각이 성공했는가»는 저장 안 됨 | C6 #2 계측 후 신규 공지에서 |
| 5 | 인천문남초에 가정통신문 게시판이 실제로 있는가? | 홈페이지를 확인하지 않았다. 없다면 `announcement_fallback`은 최선의 선택이다 | C10 배포 후 `fallback_count`를 보고 개별 확인 |
| 6 | 워터마크 비대상(비숫자 post_id) 학교가 몇 곳인가? | `board_watermarks`의 현재 내용을 실측하지 않았다. §12.3 «남는 구멍»의 크기 | C8 dry-run 출력 |
| 7 | 큐 경로에서 크롤→추출 지연의 실제 분포는? | 72일간 데이터가 없다 | C11 측정 (재가동 후) |
| 8 | HWP 표 보존율 85% 목표가 신규 유입만으로 언제 판정 가능한가? | 학교 8곳 × 하루 1건 수준이면 HWP 20건 모으는 데 수 주 | 재가동 후 관측 |
| **9** | **현행 Gemini 판독의 지연이 얼마인가?** | 72일간 데이터가 없다. Bedrock PDF 14~16초(§19.2)와 비교할 상대값이 없어 «(나)가 느린가»를 지금 판정할 수 없다 | 재가동 후 첫 런 로그. 선택 Task 13 A/B의 전제 |
| **10** | **현행 Gemini 판독이 «못 읽었을 때 지어내는가»?** | 한 번도 negative control을 돌린 적이 없다. Nova 시험(§19.2)이 보여준 실패 양상을 Gemini에 대해서는 모른다 | 계획 Task 4 Step 11~13 (본 계획, 선택 아님) |
| **11** | 판독 콜당 실제 토큰 수는? | §19.6의 현금 계산이 «타일 1콜 = 입력 4,000 / 출력 1,000 토큰»이라는 **가정** 위에 있다 — 실측 아님 | 재가동 후 Vertex 사용량 콘솔 |
| **12** | Bedrock 판독의 **정확도**가 Gemini보다 나은가? | §19.2는 «Bedrock Claude가 읽는다»만 보였다. 같은 입력에 대한 Gemini 결과와 나란히 세운 적이 없다 | 선택 Task 13의 A/B 게이트 |

---

## 19. 판독 백엔드 — Gemini 유지 vs Bedrock Claude 이전 (2026-08-27 추가)

### 19.1 왜 이 절이 생겼는가

§1~§18은 전부 **판독 경로가 Gemini라는 전제** 위에 쓰였다. §1.1의 두 사실
(GCP 크레딧 소진 / Bedrock 판독 실측 성공)이 그 전제를 «주어진 것»에서 «선택»으로 바꿨다.
이 절은 그 선택을 정의하고, 계산하고, 하나를 권고한다.

### 19.2 실측 — Bedrock `Converse` (2026-08-27)

조건: IAM `naranhi-bedrock`(모델 호출 권한만), 리전 `ap-northeast-2`, `global.` 라우팅.

**PDF** — 실제 첨부 `안내문.pdf` 1,219KB
(「2026 인천농어촌유학 말랑갯티학교 2학기 장기체류형」)

| 모델 | 지연 | 한글 | 표 | 판정 |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 15,929ms | 371자 | 인식 | ✅ 정확 |
| Claude Haiku 4.5 | 14,066ms | 357자 | 인식 | ✅ 정확 |
| Nova Lite | 9,105ms | 38자 | 빈 표 | 🔴 환각 |
| Nova Pro | 11,243ms | 465자 | 없음 | 🔴 완전히 무관한 문서를 생성 |

**이미지** — `본문 사진.png` 9KB (파일명은 사진이지만 실제 내용은 **QR 코드**다)

| 모델 | 결과 |
|---|---|
| Claude Sonnet 4.6 / Haiku 4.5 | ✅ *"QR 코드라 읽을 수 없다"* 고 **정직하게** 답함 |
| Nova Lite / Nova Pro | 🔴 **없는 가정통신문을 통째로 지어냄** ("교장 김 교장입니다…") |

**확정된 기술 사실**

| # | 사실 | 근거 |
|---|---|---|
| 1 | `Converse`가 **PDF를 `document` 블록으로 직접 받는다.** 변환·분할 불필요 | 1.2MB 파일이 그대로 통과 (실측) |
| 2 | 이미지는 `image` 블록 | `format: png\|jpeg` 실측 확인 |
| 3 | **AWS Textract는 한국어를 지원하지 않는다** | 따라서 판독은 멀티모달 모델로만 가능하고, 그게 Claude로 확인됐다 |
| 4 | 자격증명은 이미 있다 | GCP Secret Manager의 `aws-bedrock-access-key-id`·`aws-bedrock-secret-access-key` (`docs/superpowers/specs/2026-08-26-prerequisites.md:229`) |
| 5 | `global.` 라우팅 **사용자 허용됨** | 사업 B 열린질문 Q1의 답과 같다 |

> **이 표의 한계 — 반드시 읽을 것.** 위 실측은 «Bedrock Claude가 읽는다»를 보였을 뿐,
> **같은 파일에 대한 현행 Gemini 결과와 나란히 세운 적이 없다.** 지연도 정확도도
> **상대 비교가 없다**(§18 #9, #12). 이전 판단의 근거로 쓰려면 A/B가 선행해야 한다.

### 19.3 🔴 Nova 배제 결정

**결정: Amazon Nova(Lite·Pro)는 한국어 판독 경로에서 제외한다.**

근거는 «품질이 낮다»가 아니라 **실패 양상이 나쁘다**는 것이다.

| 실패 양상 | 검출 가능한가 |
|---|---|
| 읽지 못하고 빈 결과를 낸다 | ✅ 가능 — 길이 0으로 잡힌다 |
| 읽지 못하고 **그럴듯한 가정통신문을 지어낸다** | 🔴 **불가능** — 문법도 형식도 정상이고, 원본과 대조하지 않으면 아무도 모른다 |

Nova는 두 번째를 했다. 가정통신문은 **학부모가 그대로 믿는 문서**이므로, 지어낸 내용이
번역되어 다국어로 배포되면 되돌릴 방법이 없다. §2 비목표의 «재추출하지 않는다» 방침과
결합하면 **영구 오염**이다.

**완전 삭제가 아니라 용도 제한이다.** Nova는 다음 조건을 **전부** 만족하는 용도에만 쓴다:

1. 출력이 제약된다 — 고정 라벨 분류·불리언·짧은 열거처럼 값 집합이 닫혀 있다
2. 환각을 **기계적으로** 검출할 수 있다 — 원본 문자열 대조·스키마 검증·교차 확인
3. 결과가 학부모에게 **본문으로 노출되지 않는다**

자유 서술을 학부모에게 그대로 보이는 판독(OCR·문서추출)은 이 셋을 하나도 만족하지 않는다.
→ **판독에는 쓰지 않는다.**

### 19.4 HWP는 어느 쪽을 골라도 지금 구조를 유지해야 한다 (확인 완료)

**확인함 — 추측 아님.** Bedrock `Converse`의 `DocumentBlock.format` 유효값은
**`pdf | csv | doc | docx | xls | xlsx | html | txt | md`** 뿐이다
(AWS API 레퍼런스 `API_runtime_DocumentBlock`, 2026-08-27 조회). **`hwp`가 없다.**

따라서:

| | 결론 |
|---|---|
| HWP 판독 | **Bedrock으로 옮길 수 없다.** `hwp5html` → markdownify 경로(`hwp_extractor.py:21-88`, `:91-130`)를 **어느 시나리오에서도 유지해야 한다** |
| 이것이 뜻하는 바 | **C4(§8)는 «이전으로 대체될 수 있는 수리»가 아니다.** 이전을 하든 안 하든 HWP 표 보존은 지금 코드로만 해결된다 |
| 부수 확인 | HWP 4순위 BinData 이미지 OCR(`hwp_extractor.py:485-525`)만이 멀티모달 경로다. 운영 실적 **0건**이므로 이전 대상으로서 무의미하다 |

**첨부 구성으로 환산하면(운영 실측 70건):**

| 포맷 | 비율 | 이전 가능 |
|---|---|---|
| 이미지 (png 24 + jpg 6 + jpeg 2) | **45.8%** (32/70) | ✅ `image` 블록 |
| HWP | **28.6%** (20/70) | 🔴 **불가** — 지금 구조 유지 |
| PDF | **24.3%** (17/70) | ✅ `document` 블록 |
| (합계 오차) | 1.4% (1/70, 기타) | — |

> **이전으로 옮겨지는 것은 최대 70.1%이고, 28.6%는 남는다.** «Bedrock으로 갈아탄다»가
> «Gemini를 끈다»를 뜻하지 않는다 — 옮겨도 HWP 경로와 정제·요약 경로는 그대로다.

### 19.5 선택지 — (가) Gemini 유지 vs (나) Bedrock 이전

| | **(가) Gemini 유지 + 고장 수리만** | **(나) 판독도 Bedrock Claude로 이전** |
|---|---|---|
| 이 스펙의 §3~§13 | 그대로 유효 | 그대로 유효 (**고장은 제공자와 무관**) |
| 추가 작업 | **없음** | Bedrock 판독 클라이언트 + A/B 실측 + 판정 게이트 + 전환 |
| 판독 현금 | 월 **$0.8** (§19.6) | **$0** (크레딧 차감) |
| 아끼는 돈 | — | **월 $1 미만** |
| 커버 범위 | 100% | **70.1%** — HWP 28.6%는 못 옮긴다(§19.4) |
| 판독 지연 | **미확인**(§18 #9) | PDF 14~16초 (§19.2). **현행보다 느릴 수 있다** |
| 환각 위험 | **미확인**(§18 #10) — 한 번도 negative control을 안 돌렸다 | Claude는 QR에 «못 읽는다»고 답했다(§19.2) — 다만 표본 1건 |
| 429 노출 | Vertex dynamic shared quota (§9) | Bedrock 스로틀로 **바뀔 뿐 사라지지 않는다** |
| 새로 생기는 위험 | 없음 | 제공자 2개 동시 운용, 프롬프트 재검증, AWS 자격증명이 추출 Job에도 필요 |
| 되돌리기 | — | env 한 줄 (사업 B와 같은 방식) |

### 19.6 비용 근거 — 판독 경로의 현금은 실제로 얼마인가

**단가(확인, 2026-08-27 모델 페이지 조회):** Gemini 2.5 Flash 입력 **$0.30**/1M,
출력 **$2.50**/1M. Flash-Lite는 $0.10 / $0.40.

**물량 가정(⚠️ 가정이다 — 실측 아님):** 재가동 후 월 60공지. 운영 실측
공지 38건 / 첨부 70건 = 공지당 1.84첨부 → 월 110첨부.

| 항목 | 콜 수 | 입력 토큰 | 출력 토큰 | 월 현금 |
|---|---|---|---|---|
| 이미지 OCR (45.8% = 50건 × 평균 3타일) | 150 | 4,000/콜 | 1,000/콜 | $0.56 |
| PDF OCR (24.3% = 27건 × 평균 2콜) | 54 | 4,000/콜 | 1,000/콜 | $0.20 |
| HWP (로컬 파싱) | 0 | — | — | $0 |
| **판독 소계** | **204** | | | **≈ $0.76** |
| 정제·요약 (공지당 4콜, 판독 경로 아님) | 240 | 3,000/콜 | 2,000/콜 | ≈ $1.42 |
| **합계** | | | | **≈ $2.2 / 월** |

> **토큰 수는 가정이다**(§18 #11). 그러나 **결론은 가정에 둔감하다** — 물량이나
> 토큰이 **10배**여도 판독 경로의 현금은 월 $8 수준이다. 이 규모에서
> **«비용이 이전을 정당화한다»는 논거는 성립하지 않는다.**

### 19.7 🔴 권고 — (가)를 먼저 하고, (나)를 선택 Task로 분리한다

**권고: (가).** (나)는 설계를 완비해 계획의 **선택 Task 13**으로 떼어 놓되,
본 배포 순서에는 넣지 않는다.

| # | 근거 |
|---|---|
| 1 | **비용 논거가 성립하지 않는다.** 아끼는 돈이 월 $1 미만이다(§19.6). 사업 B의 번역 이전은 «현금 지출의 대부분»을 옮기는 일이었지만, 판독은 그 지출의 3분의 1이고 절대액이 커피 한 잔이다 |
| 2 | **범위가 70.1%뿐이다.** HWP 28.6%는 어차피 못 옮긴다(§19.4). 제공자를 둘로 늘리고도 Gemini는 계속 돈다 |
| 3 | **비교 근거가 아직 없다.** §19.2는 «Bedrock이 읽는다»만 보였다. 현행 Gemini의 지연도 환각률도 모른다(§18 #9, #10, #12). **모르는 것을 «개선»으로 바꿀 수는 없다** |
| 4 | **지연이 나빠질 수 있다.** PDF 14~16초는 짧지 않다. 「비용은 비목표, 시간이 우선」(§17 #3)이 여기서는 **이전에 불리하게** 작용한다 |
| 5 | **사업 C의 본체는 «고장 수리»다.** ①~⑥ 중 이전이 해결하는 것은 **0개**다. 수리 전에 제공자를 갈면 «수리 효과»와 «제공자 효과»가 뭉쳐 어느 쪽이 원인인지 알 수 없게 된다 — 사업 B가 thinking OFF를 Bedrock보다 먼저 둔 것과 같은 이유(`docs/superpowers/plans/2026-08-27-B-bedrock-translation.md:76`) |

**그럼 (나)는 언제 하는가.** 이전을 실제로 정당화하는 것은 비용이 아니라 **품질**이다.
Task 4 Step 11~13의 negative control에서 **현행 Gemini가 판독 불가 입력에 대해
내용을 지어낸다면**, 그때 (나)는 «돈 아끼기»가 아니라 «안전 조치»가 되고 우선순위가
올라간다. 선택 Task 13의 착수 조건을 그 결과에 건다.

### 19.8 모델 정책 (이 사업 전체에 적용)

| 용도 | 모델 | 규칙 |
|---|---|---|
| **판독 기본** | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | **항상 여기서 시작한다.** PDF 14,066ms·357자·표 인식으로 Sonnet과 실질 동등하다(§19.2). 사업 B가 같은 사다리를 쓴다(`…-B-bedrock-translation-design.md:643`) |
| **판독 승급** | `global.anthropic.claude-sonnet-4-6` | Haiku가 판정 게이트를 **못 넘은 건에 한해서만.** 승급은 «정말 필요할 때만» 한다 |
| 🔴 **금지** | **Claude Opus 계열 전부** | **사용자 지시(2026-08-27): "절대 쓰지마 너무 비싸".** 기본·승급·폴백·A/B arm 어디에도 넣지 않는다. 예외 없다 |
| ⚠️ **용도 제한** | Amazon Nova Lite / Nova Pro | **한국어 판독 금지**(§19.3). 출력이 제약되고 환각을 기계적으로 검출할 수 있는 용도에만 |

---

## 20. 다음 단계

이 스펙 승인 후 `superpowers:writing-plans`로 구현 계획을 작성한다.
**단, 배포 3(C3 진단)은 계획이 아니라 조사다** — 그 결과가 나오기 전에는
C3에 대한 구현 계획을 쓰지 않는다.

구현은 서브에이전트로 분담하되 §14 배포 순서의 경계를 넘지 않는다.
특히 **배포 6(시딩) 이전에 배포 7(resume)을 하지 않는다.**

**§19(판독 이전)은 본 배포 순서에 넣지 않는다.** 계획의 «선택 Task 13»으로 분리하고,
착수 여부는 Task 4 Step 11~13(환각 negative control)의 결과를 보고 정한다(§19.7).
