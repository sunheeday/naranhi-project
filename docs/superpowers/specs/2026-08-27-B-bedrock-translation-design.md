# 사업 B — 번역 백엔드 Bedrock 이전 · 단건 지연 단축

기준일: 2026-08-27
상태: 설계 (구현 전)
선행: 없음 (사업 A와 독립) / 후행: 없음

---

## 1. 배경

번역 파이프라인은 **동작한다**. 문제는 두 가지다 — **느리고, 현금이 나간다.**

| 확인 사항 | 근거 |
|---|---|
| 파이프라인 1회(공지 1건 × 언어 1개) = **134.7초** | 실측(2026-08). 운영 관측치 100~155초와 일치 |
| 지연의 **75~78%가 «생각(thinking) 토큰»** | Gemini 2.5 Flash thinking ON 첫 글자까지 21.00초 / OFF **0.45초** (Artificial Analysis) |
| 실제 현금 지출은 AI 호출뿐 | Cloud Run은 무료 한도 내 $0. Gemini만 사용자 현금 |
| AWS Bedrock은 **보유 크레딧**으로 차감된다 | 2026-08 청구에 `Claude Sonnet 4.6 (Bedrock Edition)` $12.80, `Claude Haiku 4.5` $0.67 — 전액 크레딧 |

### 1.1 thinking이 어디서 켜져 있는가

`orchestrator.py`의 `generate_json` 호출은 **16곳**이다. 그중
`thinking_budget=MECHANICAL_THINKING_BUDGET`(=0, `orchestrator.py:29`)가 걸린 곳은
**5곳뿐** — `:64`(원문 하드팩트) `:110`·`:288`(역번역) `:247`(역번역 재실행) `:410`(번역본 하드팩트).

나머지 **11곳은 모델 기본값(Gemini 2.5 Flash = Auto, 최대 8,192)** 으로 돈다:

| 줄 | 단계 |
|---|---|
| `orchestrator.py:76` | 한→영 피벗 |
| `orchestrator.py:86` | 영→대상어 |
| `orchestrator.py:129` | 하드팩트 LLM 검증 |
| `orchestrator.py:143` | 하드팩트 자동수정 |
| `orchestrator.py:199` | 카드 메타데이터 (저위험 경로) |
| `orchestrator.py:251` | 문맥·어조 검증 |
| `orchestrator.py:268` | 문맥·어조 자동수정 |
| `orchestrator.py:291` | 문맥·어조 재검증 |
| `orchestrator.py:327` | 카드 메타데이터 (정상 경로) |
| `orchestrator.py:384` | 식재료 매핑 |
| `orchestrator.py:447` | 카드 메타데이터 (검증실패 경로) |

즉 **무거운 단계는 전부 thinking이 켜져 있다.**

### 1.2 단계별 실측 지연

| 라운드 | 단계 | thinking | 현재 | tb=0 |
|---|---|---|---|---|
| R1 | 원문 하드팩트 | 0 | 3.2s | 3.2s |
| R2 | 식재료 매핑 | dynamic | 22.3s | 1.8s |
| R3 | 한→영 피벗 | dynamic | 28.4s | 8.4s |
| R4 | 영→대상어 | dynamic | 29.4s | 9.6s |
| R5 | 하드팩트 ∥ 역번역 | 0 | 7.3s | 7.3s |
| R6 | 문맥·어조 검증 | dynamic | 22.3s | 1.8s |
| R7 | 카드 메타데이터 | dynamic | 21.8s | 1.4s |
| | **합계** | | **134.7s** | **33.5s** |

### 1.3 병렬화는 주력이 아니다 — 이미 분석했다

- ①(원문 하드팩트)과 ②(식재료)는 서로 독립 → 동시 실행 가능. 절약 **3.2초**
- ⑧(카드 메타데이터)은 ④의 결과만 필요하고 검증과 무관 → 투기적 선실행 가능. 절약 **21.8초**
- ⑤∥⑤'(하드팩트 추출 ∥ 역번역)는 **이미 병렬**이다 — `orchestrator.py:100-112`의 `create_task` + `:168-170`·`:237-240`의 `_discard_task`
- **①→③→④→⑤'→⑦ 다섯 개는 엄격히 순차. 90.6초. 못 쪼갠다**
- 병렬화만으로는 134.7 → **124.2초 (−8%)**. thinking을 끄고 나면 단계가 이미 짧아져서 이득이 **−10%**로 더 줄어든다

> **결론: 병렬화는 보조다. 주력은 thinking 축소와 단계 병합이다.**
> 이 스펙의 우선순위는 그 순서를 그대로 따른다.

### 1.4 동시성 설정이 죽어 있다

배포는 `GEMINI_MAX_CONCURRENCY=32`를 건다(`.github/workflows/deploy-api-cloud-run.yml:116`).
그런데 **실제 동시 in-flight 콜은 최대 10개**다.

이유: 배치 10잡(`deploy-api-cloud-run.yml:111` `--batch-size,10`)을
`asyncio.gather`로 동시에 돌리되(`translation_worker.py:113`),
각 잡은 6~7콜을 **순차 await** 한다(`orchestrator.py:60→76→86→…`).
즉 잡당 in-flight 1개 × 10잡 = 10.

리틀의 법칙: L=10, W≈25s → **λ=0.4 calls/sec**.

> **32를 올리거나 내리는 것은 아무 의미가 없다.** 세마포어(`gemini_client.py:61-71`)는
> 한 번도 포화되지 않는다. 실제 동시성을 바꾸려면 `--batch-size`(10)와
> `AUTO_TRANSLATION_LOCALE_CONCURRENCY`(`config.py:138-143`, 기본 3)를 건드려야 한다.
>
> 부수 확인: API 서비스(`deploy-api-cloud-run.yml:77-87`)에는 `GEMINI_MAX_CONCURRENCY`가
> 없어 `config.py:47-52`의 기본 12가 적용된다. 세마포어는 프로세스별이므로 이 둘은 무관하다.

### 1.5 순수 낭비 2건

**(a) 요약·본문 소스 번역이 콜을 2배 쓴다.**
`notice_service.py:247-264`(`translation_kind ∈ {notice_summary, notice_source}`)가
`_best_effort_translate_notice`(`:625`)를 부른다. 이 함수는 번역 1콜(`:638`)에 더해
**카드 메타데이터 1콜**(`:668`)을 반드시 쏜다. 그런데 호출부
`content_extraction_service.py:946-947`은 `result["translation"]`만 꺼내고
`pipeline_result`(= metadata를 담은 곳)를 **버린다**. → 이 경로 콜의 **50%가 낭비**.

메타데이터 콜이 존재하는 이유는 `notice_service.py:665-666` 주석에 적혀 있다 —
"카드가 비면 앱이 번역을 미완성으로 보고 풀 파이프라인을 무한 재요청". 이 이유는
`:173`·`:302`(공지 본체 번역의 쿼터 폴백)에는 유효하지만 `:247` 분기에는 해당 없다.

**(b) risk 게이트의 저위험 경로가 dead path다.**
`_risk_profile_from_source`(`orchestrator.py:545-603`)는
`level = "high" if reasons else "low"`(`:599`)다. reasons를 만드는 조건이
`urls`·`contacts`·`fees`·`deadlines` 존재(`:554-561`), 본문 1,600자 초과(`:577`),
그리고 텍스트 단서 "첨부/붙임/별첨/양식/서식/qr/링크/계좌/스쿨뱅킹/납부/수납/동의서/서명"(`:580-594`)이다.
학교 가정통신문이 이 중 **하나도** 걸리지 않기는 어렵다.
→ `low` 분기(`:186-231`, 역번역·문맥어조 2콜 생략)는 사실상 실행되지 않는다.

> 이것은 **추정이다.** 다만 검증 가능하다 — `risk_profile`은
> `orchestrator.py:229`·`:359`에서 `raw_steps`에 저장되므로
> `notice_ai_translations.raw_steps->'risk_profile'->>'level'` 분포를
> 코드 변경 없이 읽기 전용 쿼리로 셀 수 있다. B3 착수 전에 이 수치를 먼저 확보한다.

### 1.6 배치 대기

`translation_worker.py:113`은 `asyncio.gather`로 **배치 10잡 전원이 끝날 때까지** 기다린 뒤
다음 배치를 claim한다(`:82`). 잡 소요가 100~155초로 흩어지므로 먼저 끝난 슬롯은
가장 느린 잡을 기다리며 논다. 슬롯 유휴율 **≈23%**, 처리량 **+29% 여지**.

### 1.7 SDK 결함 3건 (전부 미해결 OPEN 이슈)

| 이슈 | 내용 | 이 워크로드에 미치는 영향 |
|---|---|---|
| googleapis/python-genai **#2705** | 기본 httpx transport가 TCP `SO_KEEPALIVE`를 설정하지 않아 20~30초 무응답 구간에 NAT가 연결을 끊는다 | **정확히 이 워크로드의 실패 모드.** 콜당 20~30초 무응답이 정상 상태다 |
| **#1875** | SDK가 429의 `RetryInfo.retryDelay`를 무시하고 고정 백오프 5회 | 앱 백오프(`gemini_client.py:24` 5/10/20/40s ×4)와 **중첩** → 최악 ~20회 시도 |
| **#2869** | ADC 토큰 갱신 중 `TransportError`가 재시도 대상에서 누락 | Vertex 경로(`gemini_client.py:150-164`)에서만 발생 |

### 1.8 갈아끼울 자리가 이미 있다

`GeminiJsonClient`는 **이미 이중 백엔드**다 — Vertex(`gemini_client.py:166-198`)와
AI Studio API 키(`:200-246`)를 `self.use_vertex`(`:136`)로 가르고,
그 값은 `config.py:208`의 `use_vertex` 프로퍼티에서 온다.

그리고 오케스트레이터가 클라이언트에서 쓰는 것은 **딱 두 개**다 —
`generate_json(...)`과 `getattr(self.gemini, "source_hard_fact_model", None)`(`orchestrator.py:63`).

**이게 이음매다. Bedrock은 세 번째 백엔드로 붙인다.**

---

## 2. 목표 / 비목표

### 목표

1. 번역 AI 호출이 **AWS Bedrock 크레딧**으로 나간다 (사용자 현금 지출 제거).
2. 파이프라인 단건 지연이 **134.7초 → 40초 이하**로 내려간다.
3. **평가 없이 모델을 바꾸지 않는다** — 모든 교체는 `.agents/translation-quality/` 장치를 통과한다.
4. 언제든 **환경변수 한 줄로 Gemini로 되돌아간다.**
5. 「번역만 Bedrock, 문서판독은 Gemini」 같은 **혼합 상태가 정상 운영 상태로 성립**한다.

### 비목표 (이 사업에서 하지 않는다)

- **인프라 이전** — 서버는 GCP Cloud Run에 그대로 둔다. 모델 교체지 이전이 아니다.
- **문서판독(멀티모달) 이전** — `GeminiDocumentExtractor`
  (`backend/extractor/extractors/gemini_document_extractor.py`)는 손대지 않는다. §10 참조.
- **크롤러 AI 이전** — `crawler/gemini_finder.py`, `crawler/unknown_post_resolver.py`는
  `gemini_client`의 헬퍼 두 개(`call_with_quota_backoff`, `_repair_invalid_json_escapes`)만
  빌려 쓴다. **그 두 헬퍼의 이름·위치를 바꾸지 않는 것**이 이 사업의 제약이다.
- **전통 NMT 하이브리드** — §11에서 «하지 않는다»로 판정.
- **컨텍스트 캐싱** — §11에서 «하지 않는다»로 판정.
- **프롬프트 품질 개선** — 프롬프트는 **고정 변수**다. 백엔드 A/B의 통제 조건이 되어야 한다.
- **사용자별 카나리 / 트래픽 분할** — 대상이 155건이다. 오프라인 A/B로 충분하다.

---

## 3. 작업 단위

| | 단위 | 크기 | 되돌리기 |
|---|---|---|---|
| B1 | 평가 하네스 A/B 확장 | 스크립트 2개 + 폴더 규약 | 스크립트 삭제 (운영 무영향) |
| B2 | 배치 대기 제거 | 워커 루프 1개 | revert |
| B3 | 낭비 제거 (메타데이터 플래그 + dead path) | 인자 1개 + 분기 삭제 | revert |
| B4 | thinking 축소 — **Gemini에서 먼저** | 호출 인자 11곳 | 인자 제거 |
| B5 | Bedrock 백엔드 (다크 코드) | 새 모듈 1개 + 팩토리 | 팩토리 미배선 → 무영향 |
| B6 | **워커만** Bedrock 전환 | env 1줄 | env 되돌리기 |
| B7 | 전면 Bedrock 전환 | env 2줄 | env 되돌리기 |
| B8 | 단계 병합 7 → 5 | orchestrator + prompts | revert |
| B9 | 기존 번역 155건 백필 | 스크립트 1개 | 재생성 안 함 |

**B4가 B5보다 먼저인 이유가 이 스펙의 핵심 판단이다.**
thinking OFF는 Gemini에서 **호출 인자 하나**로 얻어지고 예상 개선폭이 −75%다.
Bedrock으로 옮기면 이 이득은 **자동으로 딸려온다**(§5.3) — Claude의 extended thinking은
기본 OFF다. 그래서 B4를 Gemini에서 먼저 측정하면 **«thinking 효과»와 «모델 교체 효과»가
분리된다.** 순서를 뒤집으면 둘이 뭉쳐서 나중에 어느 쪽이 품질을 깎았는지 알 수 없다.

---

## 4. B1 — 평가 하네스 A/B 확장

### 4.1 이미 있는 것 (그대로 쓴다)

| 장치 | 위치 | 재사용 방식 |
|---|---|---|
| 파이프라인 드라이버 | `scripts/translation_quality_driver.py` | `:115`의 클라이언트 생성 **한 줄**만 팩토리로 교체 |
| 이터 스캐폴딩 | `scripts/scaffold_translation_quality_iteration.py` | 그대로 |
| 이터 러너 | `scripts/run_iteration.py` | arm 반복만 추가 |
| 산출물 검증 | `scripts/validate_translation_iteration.py` | 그대로 |
| 평가자 명세 (8축, 0–5) | `.agents/translation-quality/evaluator-agent.md` | 그대로 |
| 언어별 기준 | `.agents/translation-quality/language-criteria/{en,ru,ar}.md` | 그대로 |
| 점수 시계열 | `.agents/translation-quality/iterations/_history.json` | 그대로 |
| verdict 4종 + Stopping Criteria | `evaluator-agent.md:103-112`, `workflow.md:216-229` | **게이트 판정에 그대로 사용** |

드라이버가 이미 `TranslationPipeline`을 직접 돌리고(`translation_quality_driver.py:53-60`)
`orchestrator.run()`의 전체 결과 json을 저장하므로(`:146-150`),
**`validation.hard_fact` / `validation.context_tone`이 arm별로 그대로 남는다.** 이게 §4.4의 1차 지표다.

### 4.2 새로 필요한 것 세 가지

**(a) arm(백엔드 후보) 축.** 기존 이터 폴더는 «프롬프트 변경 전/후»를 비교하도록 되어 있다
(`workflow.md:31-70`, `pipeline-output/` vs `pipeline-output-after/`). 여기서는
**같은 프롬프트 × 여러 백엔드**를 비교해야 한다. 폴더 규약을 이렇게 확장한다:

```
iterations/2026-08-2X_iter-bedrock-001/
├── manifest.json
├── arms.json                      # ← 신규. 평가자는 읽지 않는다.
├── notices/<role>/<id>/
│   ├── source.ko.md
│   └── pipeline-output/
│       ├── arm-a/{en,ru,ar}.json  # ← arm별 하위 폴더
│       ├── arm-b/{en,ru,ar}.json
│       └── arm-c/{en,ru,ar}.json
└── evaluation/
    ├── feedback-report.md
    └── scores.json                # arm 축 추가
```

**(b) 블라인드.** 평가자는 어느 arm이 어느 모델인지 **몰라야 한다.**
`arms.json`이 `arm-a → gemini-2.5-flash(current)` 매핑을 갖고, 평가자 호출 프롬프트에
"`arms.json`을 읽지 않는다"를 명시한다. 기존 워크플로에는 held-out(일반화 측정)은 있어도
**블라인드 개념이 없다** — 이건 이 사업이 추가하는 것이다.

**(c) 지연 기록.** `scores.json`에 시간 필드가 없다. 드라이버가 `run()` 전후로
`time.perf_counter()`를 재 arm별 `wall_seconds`를 기록한다. 단계별 분해가 필요하면
`generate_json` 진입/종료에 `LOGGER.info` 한 줄을 넣는다(구현 시 판단).

### 4.3 arm 구성 (최소 3개, 최대 5개)

| arm | 백엔드 | 목적 |
|---|---|---|
| 기준선 | Gemini 2.5 Flash, 현행 그대로 | 비교 기준 |
| T | Gemini 2.5 Flash, **thinking 전면 0** | B4의 품질 영향 단독 측정 |
| C | Bedrock `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | Bedrock 1순위 후보 |
| N | Bedrock `apac.amazon.nova-lite-v1:0` | 저지연 후보 |
| M | Bedrock 혼합 (기계 단계 Nova Lite + 번역 단계 Claude) | `source_hard_fact_model` 분리 활용 |

M이 성립하는 이유: 클라이언트가 이미 단계별 모델 분리를 지원한다 —
`gemini_client.py:97`의 `source_hard_fact_model`, `orchestrator.py:63`에서의 사용,
`config.py:31-34`의 `GEMINI_SOURCE_HARD_FACT_MODEL`.

### 4.4 지표 — 정량 1차 / 판단 2차

> **1차 지표는 LLM 평가 점수가 아니라 코드 검증 통과율이다.**

`orchestrator.py:121-125`의 `validate_hard_facts_by_code`는 **결정적**이고 LLM을 쓰지 않는다.
그 결과는 모든 출력 json의 `validation.hard_fact.status`에 남는다.
날짜·금액·연락처·URL 보존은 이 프로젝트의 north star(`README.md:7`)에 가장 직결되는 축이고,
동시에 **판정자 편향이 0인 유일한 지표**다.

| 순위 | 지표 | 산출 | 성격 |
|---|---|---|---|
| 1 | `validation.hard_fact` 통과율 | arm × 언어 × 공지 = 36점 | 결정적 |
| 2 | `validation.context_tone` 통과율 | 동일 | LLM 판정이지만 파이프라인 내장 |
| 3 | 자동수정 재시도 횟수 합 | `validation.*.attempts` | 결정적, 지연과 직결 |
| 4 | 8축 평균 (train / held-out) | 평가자 에이전트 | **블로우업 탐지용** |
| 5 | `wall_seconds` 중앙값 | 드라이버 | 결정적 |

### 4.5 ⚠️ 코퍼스가 부족하다 — 정직하게 적는다

실측(2026-08-27):

| 항목 | 수 |
|---|---|
| `source.ko.md` 파일 | 30 |
| **내용 기준 고유 공지** | **12** (sha256 dedupe) |
| 시드 세트 | 6 (`mock-notices/seed-set-v1.json`) |
| 이터레이션 | 5 (전부 2026-06-01~02) |
| 누적 pipeline-output json | 112 |

그리고 시드 6건은 `"origin": "mock-seed-v1"` — **실제 크롤 공지가 아니라 합성 목업이다.**

arm 하나당 판정 단위는 **12공지 × 3언어 = 36건**이다. 8축 0–5 척도에서
arm 간 0.2점 차이는 잡음 구간 안이다.

> **따라서 이 평가는 «망가졌는지»는 잡아내지만 «미세하게 나빠졌는지»는 못 잡는다.**
> 게이트 문구도 그 한계에 맞춰 쓴다(§4.6) — "더 좋다"가 아니라 "더 나쁘지 않다"를 판정한다.

완화책 세 가지:
1. **코퍼스 확장 (권장, B1에 포함)** — 운영에 이미 번역본 155건이 있고 그 한국어 원문이
   `notices`에 있다. 실제 공지에서 다양성 매트릭스(`workflow.md:76-104`)를 채워
   고유 공지를 12 → 30건 이상으로 늘린다. 목업 6건보다 실제 공지가 낫다.
2. **1차 지표를 결정적 검증으로** (§4.4) — 36건에서도 통과율 차이는 8축 평균보다 오차가 작다.
3. **held-out 정책 유지** (`workflow.md:107-113`) — 확장 코퍼스에서도 held-out 비율을 유지한다.

### 4.6 게이트 — «평가 없이 교체하지 않는다»

**B4·B6·B7·B8은 다음을 모두 만족하는 서명된 이터 폴더 없이는 배포할 수 없다.**

| # | 조건 |
|---|---|
| G1 | `validation.hard_fact` 통과율이 기준선 arm 대비 **하락 0건** (36건 중 새로 실패하는 건이 없다) |
| G2 | 평가자 verdict가 `blocking_regression`이 **아니다** |
| G3 | 세 언어 각각 8축 평균이 기준선 대비 **−0.3점 이내** |
| G4 | `final_translation`에 placeholder(`{{ingredient_id}}` 등) 잔존 **0건** (`evaluator-agent.md:54`) |
| G5 | `wall_seconds` 중앙값이 기준선보다 **낮다** (지연이 목적이므로) |

G1이 «하락 0건»인 이유: 36건 표본에서 통과율 비율 차이는 의미가 없지만
**"전에 통과하던 건이 지금 실패한다"는 개별 사건**은 표본 크기와 무관하게 실재하는 회귀다.

---

## 5. B5 — Bedrock 백엔드 추상화 설계

### 5.1 이음매 — 두 멤버짜리 프로토콜

오케스트레이터가 클라이언트에서 쓰는 것은 `generate_json`과 `source_hard_fact_model`뿐이다
(`orchestrator.py:60-65`, `:63`). 그래서 프로토콜이 이만큼 작다.

```python
# backend/app/translation/json_client.py  (신규)
from typing import Any, Protocol

class JsonModelClient(Protocol):
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
    if settings.translation_backend == "bedrock":
        from app.translation.bedrock_client import BedrockJsonClient
        return BedrockJsonClient.from_settings(settings)
    from app.translation.gemini_client import GeminiJsonClient
    return GeminiJsonClient.from_settings(settings)
```

시그니처는 `gemini_client.py:125-132`를 **그대로 복사한 것**이다. 기존 클라이언트는
이미 이 프로토콜을 만족하므로 `GeminiJsonClient`는 **한 글자도 고치지 않는다**
(429 마커 확장 §5.5 제외).

호출부 교체는 기계적이다 — `GeminiJsonClient.from_settings(settings)` 8곳
(`notice_service.py:155, 250, 269, 284, 303, 436, 526, 579`)과 타입 힌트 3곳
(`notice_service.py:465, 628, 711`), 드라이버 1곳(`translation_quality_driver.py:115`).

### 5.2 Bedrock 클라이언트

```python
# backend/app/translation/bedrock_client.py  (신규)
class BedrockJsonClient:
    def __init__(
        self,
        *,
        model: str,
        source_hard_fact_model: str | None = None,
        region: str = "ap-northeast-2",
        timeout_seconds: float = 60.0,
        max_workers: int = 32,
    ) -> None: ...

    @classmethod
    def from_settings(cls, settings: "Settings") -> "BedrockJsonClient": ...

    async def generate_json(
        self, *, prompt, temperature=0.1, model=None, thinking_budget=None
    ) -> dict[str, Any]:
        async with _get_call_semaphore():          # gemini_client:64 재사용
            response = await call_with_quota_backoff(  # gemini_client:35 재사용
                lambda: self._converse_in_thread(...),
                label=f"translation:{model or self.model}",
            )
        return _parse_json("{" + _extract_bedrock_text(response))  # gemini_client:270 재사용
```

**전역 세마포어(`gemini_client.py:61-71`)와 백오프(`:35-58`)와 JSON 파서(`:270-298`)를
그대로 재사용한다.** 새로 쓰는 것은 요청 조립·응답 추출·스레드 브리지 셋뿐이다.

### 5.3 흡수해야 할 차이 ① — thinking 제어

| | Gemini (`google-genai`) | Bedrock (`boto3 bedrock-runtime`) |
|---|---|---|
| 기본값 | **Auto (최대 8,192)** — 켜져 있다 | Claude extended thinking **OFF** |
| 끄는 법 | `ThinkingConfig(thinking_budget=0)` (`gemini_client.py:182-184`) | 아무것도 안 보내면 된다 |
| 켜는 법 | 같은 필드에 N | `additionalModelRequestFields={"thinking":{"type":"enabled","budget_tokens":N}}` |
| 제약 | 없음 | thinking 켜면 **`temperature`를 1로 강제**한다 |
| Nova | — | extended thinking 노브 없음 (**미확인** — Nova 2 계열 reasoning 변종 여부) |

**이 표가 이 사업에서 가장 중요한 한 칸을 담고 있다.**
Bedrock Claude로 옮기면 §1.1의 «11곳이 기본값으로 thinking ON» 문제가
**설계 노력 없이 사라진다.** 반대로 `thinking_budget=0`이 걸린 5곳은 no-op이 된다.

그리고 thinking을 **다시 켜는 것은 이 파이프라인에서 사실상 불가능하다** —
`temperature=1` 강제가 현행 0.0/0.1 설정(`orchestrator.py:62, 82, 94, 134, 153, 207, 244, 259, 277, 299, 335, 390, 409, 458`)과 정면충돌한다.
검증·추출 단계의 결정성이 `validate_hard_facts_by_code`의 전제다.

→ **설계 결정: Bedrock 경로에서 thinking은 항상 OFF다.** `thinking_budget`은
매핑표대로 흡수하되, 양수 값은 **경고 로그 후 무시**한다(온도를 조용히 1로 바꾸지 않는다).

| 호출부가 넘긴 값 | Gemini 동작 | Bedrock 동작 |
|---|---|---|
| `None` (11곳) | Auto 8,192 | **OFF** (필드 생략) |
| `0` (5곳) | OFF | OFF (필드 생략) |
| `> 0` (현재 0곳) | 해당 예산 | **무시 + 경고 로그** |

### 5.4 흡수해야 할 차이 ② — JSON 강제 출력

| | Gemini | Bedrock Converse |
|---|---|---|
| JSON 강제 | `response_mime_type="application/json"` (`gemini_client.py:178`) / `responseMimeType` (`:213`) | **동등 기능 없음** |
| 대안 1 | — | `toolConfig` + `toolChoice`로 단일 도구 강제 |
| 대안 2 | — | assistant 턴 프리필 `"{"` |
| 대안 3 | — | 프롬프트 지시 + 파서 복구 |

**대안 1(toolConfig)을 쓰지 않는다.** 프롬프트 빌더가 13개
(`prompts.py:129, 192, 243, 301, 362, 407, 467, 542, 586, 650, 679, 745, 805`)이고
스키마는 전부 **산문으로** 프롬프트 안에 박혀 있다(`prompts.py:67` `HARD_FACT_SCHEMA`,
각 빌더 말미의 `Return JSON:`). 이걸 JSON Schema 13벌로 다시 쓰는 것은
«프롬프트를 고정 변수로 둔다»는 §2 비목표를 정면으로 깬다 — A/B의 통제가 무너진다.

**대안 2 + 3을 쓴다.**

- 프롬프트 지시는 **이미 있다** — `COMMON_SYSTEM_PROMPT`의 8번 규칙
  "Return only valid JSON matching the requested schema"(`prompts.py:36`)가
  13개 빌더 전부에 붙는다.
- 파서도 **이미 방어적이다** — `_parse_json`(`gemini_client.py:270-285`)은
  산문에 감싸인 `{...}`를 정규식으로 뽑아내고(`:274-277`),
  잘못된 백슬래시 이스케이프까지 복구한다(`:288-298`).
- 여기에 assistant 프리필 `"{"`를 얹는다. 그러면 응답 텍스트가 `{` **다음부터** 오므로
  파서에 넣기 전에 `"{"`를 되붙인다 — §5.2의 `_parse_json("{" + text)`가 그 뜻이다.
  (프리필의 Nova 지원 여부는 **미확인**. B1 평가에서 파싱 실패 건수를 세어 판단한다.)

**응답 텍스트 위치도 다르다.**

```python
def _extract_bedrock_text(response: dict) -> str:
    for block in response["output"]["message"]["content"]:
        if "text" in block:              # reasoningContent 블록은 건너뛴다
            return block["text"]
    raise RuntimeError("Bedrock 응답에서 텍스트를 찾지 못했습니다.")
```

`gemini_client.py:258-267`의 `_extract_text`와 같은 모양이다.

요청 조립:

```python
{
  "modelId": model,
  "messages": [
      {"role": "user",      "content": [{"text": prompt}]},
      {"role": "assistant", "content": [{"text": "{"}]},
  ],
  "inferenceConfig": {"temperature": temperature, "maxTokens": 8192},
  # thinking은 §5.3에 따라 필드 자체를 넣지 않는다
}
```

### 5.5 흡수해야 할 차이 ③ — 스로틀 판정 (실장 전 반드시 고칠 것)

`is_quota_exhausted_error`(`gemini_client.py:27-32`)는 메시지 소문자에
`"429" / "resource_exhausted" / "rate limit" / "rate_limit" / "quota"` 중
하나가 있는지로 판정한다.

Bedrock의 스로틀 예외는 `ThrottlingException`이고 메시지는 통상
"Too many requests, please wait before trying again." 이다 — **위 마커가 하나도 없다.**

> **그대로 두면 백오프(`gemini_client.py:35-58`)가 한 번도 동작하지 않고
> 429가 잡 실패로 곧장 전파된다.** B5에서 마커에
> `throttling`, `toomanyrequests`, `serviceunavailable`, `modelnotready`를 추가한다.
> Gemini 경로에는 무해하다(그 문자열이 나올 일이 없다).

### 5.6 흡수해야 할 차이 ④ — boto3는 동기다

`boto3`의 `bedrock-runtime.converse()`는 블로킹이다. 파이프라인 전체는 asyncio다.

`asyncio.to_thread`를 쓰되 **기본 executor에 맡기면 안 된다.**
기본 스레드풀 크기는 `min(32, cpu+4)`이고 Cloud Run 워커는 `--cpu=1`
(`deploy-api-cloud-run.yml:114`)이므로 **5**다. 세마포어는 32까지 허용하는데
(`deploy-api-cloud-run.yml:116`) 실제로는 5에서 조용히 직렬화된다.

→ 클라이언트가 **자기 executor를 소유한다**:

```python
self._executor = ThreadPoolExecutor(
    max_workers=max_workers,           # = settings.gemini_max_concurrency
    thread_name_prefix="bedrock",
)
```

botocore 클라이언트는 생성 후 호출은 스레드 안전하므로 클라이언트 1개를 공유한다.

> `aioboto3`를 쓰지 않는 이유: `aiobotocore`가 botocore 버전을 핀으로 묶어
> `requirements.txt` 해석을 어렵게 만든다. 스레드 브리지가 더 작다.

### 5.7 자격증명 — 서버는 GCP에 있다

Cloud Run에는 IAM 역할이 없다. 선택지 셋:

| # | 방식 | 장 | 단 |
|---|---|---|---|
| 1 | IAM 액세스 키를 Secret Manager에 | 즉시 된다. 기존 `--set-secrets` 패턴과 동일(`deploy-api-cloud-run.yml:117`) | 장수명 정적 자격증명 |
| 2 | AWS STS `AssumeRoleWithWebIdentity` + Cloud Run 서비스계정 OIDC 토큰 | 정적 비밀 0 | AWS 쪽 OIDC 공급자 설정 필요. Google ID 토큰의 audience/claims가 그대로 통하는지 **미확인** |
| 3 | IAM Roles Anywhere | 정적 비밀 0 | X.509 발급·회전 부담. 과하다 |

**1로 시작하고 2를 후속으로 남긴다.** 전역 원칙(열쇠는 환경변수로만, 명령줄·URL 금지)에 따라
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`를 `--set-secrets`로만 주입한다.
그리고 **AdministratorAccess를 쓰지 않는다** — `bedrock:InvokeModel` +
`bedrock:InvokeModelWithResponseStream`만 가진 전용 IAM 사용자를 새로 만든다.
(실측 확인된 `user/david`의 AdministratorAccess는 조사용이었지 배포용이 아니다.)

### 5.8 설정 추가

```python
# backend/app/core/config.py
translation_backend: str = Field(default="gemini", alias="TRANSLATION_BACKEND")   # gemini | bedrock
bedrock_region: str = Field(default="ap-northeast-2", alias="BEDROCK_REGION")
bedrock_translation_model: str = Field(
    default="apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
    alias="BEDROCK_TRANSLATION_MODEL",
)
bedrock_mechanical_model: str | None = Field(default=None, alias="BEDROCK_MECHANICAL_MODEL")
```

`use_vertex`(`config.py:208`)는 **그대로 둔다** — 문서판독 경로가 계속 쓴다(§10).
`gemini_max_concurrency`(`config.py:47-52`)도 이름 그대로 두고 Bedrock 세마포어에 재사용한다.
이름이 어색하지만 지금 바꾸면 배포 워크플로 3곳(`deploy-api-cloud-run.yml:116, 131, 148`)이
같이 흔들린다. 전면 전환(B7) 이후 정리한다.

### 5.9 모델 후보 — 실측 (2026-08-27, ap-northeast-2)

계정 `554608989606`. **액세스 신청 없이 즉시 호출 가능한 12개:**

| 추론 프로필 | 라우팅 | 초경량 요청 지연 | 한→베 번역 실측 |
|---|---|---|---|
| `apac.amazon.nova-micro-v1:0` | APAC 내 | 282ms | — |
| `apac.amazon.nova-lite-v1:0` | APAC 내 | 291ms | **778ms, 통과** |
| `apac.amazon.nova-pro-v1:0` | APAC 내 | 354ms | — |
| `apac.anthropic.claude-3-haiku-20240307-v1:0` | APAC 내 | 333ms | — |
| `global.amazon.nova-2-lite-v1:0` | 글로벌 | 463ms | **794ms, 통과** |
| `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | APAC 내 | 510ms | — |
| `apac.anthropic.claude-3-5-sonnet-20240620-v1:0` | APAC 내 | 730ms | — |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | 글로벌 | 783ms | **2,233ms, 통과** |
| `global.anthropic.claude-sonnet-4-6` | 글로벌 | 1,255ms | — |
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | 글로벌 | 1,314ms | — |
| `global.anthropic.claude-opus-4-6-v1` | 글로벌 | 1,654ms | — |
| `global.anthropic.claude-opus-4-5-20251101-v1:0` | 글로벌 | 14,897ms | — |

막힌 것(계정 미승인): `claude-sonnet-5`, `claude-opus-4-7/4-8/5`, `claude-fable-5`,
`openai.gpt-5.6-*`, `xai.grok-4.6`.

> ⚠️ **`global.` 접두는 요청이 APAC 밖으로 나갈 수 있다는 뜻이다.**
> 학교 공지에는 학생 이름·학년반·연락처가 섞인다. 데이터 거버넌스 판단이 서기 전에는
> **`apac.` 6종만 후보다.** 그러면 Claude 4.x 계열이 전부 빠지고
> 남는 최상급이 `claude-3-5-sonnet-20241022-v2:0`(510ms)이다.
> §14 열린 질문 1번이 **모델 선택을 직접 결정한다.**

기본값을 `apac.anthropic.claude-3-5-sonnet-20241022-v2:0`으로 잡은 것은
«APAC 내 라우팅 + 다국어 번역 최상급»이라는 보수적 가정이다.

---

## 6. B4 — thinking 축소

### 6.1 변경

§1.1의 11개 호출부에 `thinking_budget=0`을 넣는다. 상수는 이미 있다
(`orchestrator.py:29` `MECHANICAL_THINKING_BUDGET`). 이름이 «기계적»이라
번역 단계에 붙이면 어색하므로 상수를 하나 더 두거나 이름을 중립화한다(구현 시 판단).

### 6.2 예상 개선과 품질 리스크

| 단계 | 현재 | tb=0 | 절약 | 품질 리스크 |
|---|---|---|---|---|
| 식재료 매핑 (`:384`) | 22.3s | 1.8s | −20.5s | **낮음** — 사전 조회에 가깝다. `map_ingredient_identity_prompt`(`prompts.py:192`)는 승인 사전 대조 작업 |
| 한→영 피벗 (`:76`) | 28.4s | 8.4s | −20.0s | **높음** — 번역 품질의 1차 관문 |
| 영→대상어 (`:86`) | 29.4s | 9.6s | −19.8s | **높음** — 언어별 규칙(`prompts.py:919-996`)을 적용하는 단계 |
| 문맥·어조 검증 (`:251`) | 22.3s | 1.8s | −20.5s | **중간** — 판정이 무뎌지면 FAIL을 놓친다(위양성이 아니라 **위음성**이 문제) |
| 카드 메타데이터 (`:327`) | 21.8s | 1.4s | −20.4s | **낮음** — 요약·제목 생성 |
| **합계** | **134.7s** | **33.5s** | **−101.2s (−75%)** | |

> 검증 단계(`:251`)의 리스크가 특이하다. 나머지 단계는 나빠지면 «번역이 어색해진다»지만
> 검증 단계는 나빠지면 **«나쁜 번역을 통과시킨다»** 다. G1(`validation.hard_fact` 하락 0건)이
> 이걸 잡지 못한다 — hard_fact는 코드 검증이지만 context_tone은 이 콜 자체이기 때문이다.
> → **B4 평가에서 8축 «Fact Preservation」·«Action Clarity» 축을 별도로 본다.**
> 검증 단계만 thinking을 남기는 부분 적용도 후보다(절약 −20.5s 포기, 나머지 −80.7s 유지).

### 6.3 왜 Gemini에서 먼저 하는가

§3에 쓴 대로 변수 분리 때문이다. 부수 효과로, **Bedrock이 게이트를 통과하지 못해도
−75%는 손에 남는다.** B4는 Bedrock 이전의 성패와 독립적으로 가치가 있는 유일한 단위다.

---

## 7. B8 — 단계 병합 (7 → 5)

thinking을 끄고 나면 남는 것은 **라운드트립 횟수**다. tb=0 기준 33.5초 중
순수 네트워크·오버헤드가 상당 부분이다.

| 병합안 | 대상 | 근거 | 품질 리스크 |
|---|---|---|---|
| **M1** ① + ② | 원문 하드팩트(`:60`) + 식재료 매핑(`:384`) | 둘 다 `source_text`만 읽는다. 현재 ②가 ①의 `meal_and_allergy`에 의존하지만(`orchestrator.py:369-372`) 그건 «식사 정보가 있나» 게이트일 뿐이다. 한 프롬프트가 둘 다 내면 의존이 사라진다 | **낮음** |
| **M2** ⑦ + ⑧ | 문맥·어조 검증(`:251`) + 카드 메타데이터(`:327`) | 둘 다 최종 번역문만 읽는다. 자동수정 루프(`:263-300`)가 돌면 ⑧을 버려야 하지만, 그 폐기 패턴은 이미 코드에 있다(`_discard_task`, `:32-42`) | **중간** — 검증 프롬프트에 메타 생성이 섞이면 판정이 흐려질 수 있다 |
| **M3** ③ + ④ | 한→영 피벗(`:76`) + 영→대상어(`:86`) | 라운드 하나를 통째로 없앤다 (−8.4s) | **높음** — 피벗 구조를 삭제하는 것이다 |

**M3는 이 사업에서 하지 않는다.** 피벗이 왜 도입됐는지에 대한 기록을 저장소에서 찾지 못했다
(**미확인** — `.agents/translation-quality/iterations/*/engineering/improvement-plan.md`에
근거가 있을 수 있으나 이 스펙 작성 범위에서 확인하지 않았다). 근거를 모르는 설계를
지연 −8.4초를 위해 뜯지 않는다.

**M1 + M2만 한다: 7라운드 → 5라운드.**

### 7.1 병렬화 (보조)

M1을 프롬프트 병합 대신 **동시 실행**으로 처리해도 같은 −3.2초가 나온다.
프롬프트를 안 건드리므로 A/B 통제가 유지된다는 장점이 있다 → **M1은 병렬 실행을 우선한다.**

⑧ 투기적 선실행은 M2의 대안이다. `orchestrator.py:100-112`에 이미 있는 패턴
(`create_task` → `translation_when_back_started` 비교(`:101, :235`) → 바뀌었으면 `_discard_task`)을
카드 메타데이터에 그대로 복제한다. 절약 21.8초(현행) / 1.4초(tb=0 이후).

> **tb=0 이후에는 투기 실행의 이득이 1.4초로 쪼그라든다.**
> 그래서 B4를 먼저 하고 나면 B8의 우선순위는 자동으로 낮아진다. 이 순서가 맞다.

---

## 8. B3 — 낭비 제거

### 8.1 요약·본문 번역의 메타데이터 콜

`_best_effort_translate_notice`(`notice_service.py:625`)에 인자를 하나 추가한다:

```python
async def _best_effort_translate_notice(
    self, *, gemini, notice, target_language, source_text,
    with_card_metadata: bool = True,       # ← 신규
) -> dict[str, Any]:
```

`:667-685`의 메타데이터 블록을 `if with_card_metadata:`로 감싼다.

호출 3곳 중 **`:249`(요약·본문 소스 번역)만 `False`** 를 넘긴다.
`:173`과 `:302`는 공지 본체 번역의 쿼터 폴백이므로 `True`를 유지한다 —
`:665-666` 주석이 설명하는 «카드가 비면 무한 재요청» 문제가 거기서는 실재한다.

효과: 해당 경로 콜 **50% 감소**. 이 경로는 공지의 `summary` 1건 + `sources` N건마다
언어별로 돌므로(`content_extraction_service.py:952-966`) 다중 소스 공지에서는
본 파이프라인보다 콜이 많다.

### 8.2 risk 게이트 dead path

두 단계로 나눈다.

**(a) 측정 먼저 (코드 변경 0).**
`raw_steps.risk_profile.level` 분포를 운영 DB에서 읽는다(`orchestrator.py:229, 359`가 저장).
`low`가 0%에 가까우면 §1.5(b)의 추정이 확정된다.

**(b) 확정되면 dead 분기 삭제.**
`orchestrator.py:186-231`(46줄)을 제거한다. 동작 변화 0, 읽기 부담 −46줄.
`risk_profile` 계산 자체(`:545-603`)와 `:102`의 역번역 투기 조건은 **남긴다** —
`:102`는 `!= "low"`이므로 항상 참이 되어 투기 실행이 계속 동작한다.

> 게이트를 «실제로 저위험이 잡히도록» 재조정하는 것(콜 2개 절약)은
> **품질 동작 변경**이므로 §4.6 게이트를 통과해야 한다. B3에 넣지 않고 후보로만 남긴다.

---

## 9. B2 — 배치 대기 제거 · B5 — SDK 결함 대응

### 9.1 B2 배치 대기

`translation_worker.py:113`의 `await asyncio.gather(*(...))`가
배치 10잡 전원 완료를 기다린다. 이걸 **슬롯이 비는 즉시 다음 잡을 채우는 구조**로 바꾼다.

```
현재:  claim(10) → gather(10) → claim(10) → gather(10) → …
목표:  claim(10) → N개 소비자가 큐에서 뽑아 처리, 여유 슬롯 ≥ 5 되면 top-up claim
```

- 유휴율 ≈23% → 처리량 **+29%**
- **단건 지연은 변하지 않는다.** 이건 처리량 단위다
- `JobQueueService.claim`은 동기 호출이므로 top-up을 매 완료마다 하면 DB 왕복이 늘어난다
  → 여유 슬롯이 `batch_size/2` 이상일 때만 claim한다
- `gather`의 취소 전파(“한 잡이 취소되면 형제를 취소”, `:112` 주석)는 graceful shutdown
  동작이므로 **소비자 구조에서도 유지**해야 한다. 이게 이 단위의 유일한 함정이다

### 9.2 SDK 결함 — 옮기면 무엇이 사라지고 무엇이 남는가

| 결함 | Gemini(현행) 대응 | Bedrock으로 옮기면 |
|---|---|---|
| **#2705** TCP keepalive 미설정 | `genai.Client`(`gemini_client.py:155-163`)에 커스텀 httpx transport로 `SO_KEEPALIVE`/`TCP_KEEPIDLE` 주입. `HttpOptions`(`:159`)가 `client_args`를 받는지는 **미확인** (핀 버전 확인 필요) | **설정 한 줄로 대체된다** — `botocore.config.Config(tcp_keepalive=True)`. 몽키패치가 지원 노브가 된다 |
| **#1875** 중첩 재시도 | 앱 백오프 4회(`:24`) × SDK 내부 5회 = 최악 ~20회. SDK 내부 재시도를 0으로 끄는 것이 정답이나 `HttpOptions`의 retry 노브 존재는 **미확인** | **설정으로 사라진다** — `Config(retries={"max_attempts": 1, "mode": "standard"})`. 앱 백오프만 남는다 |
| **#2869** ADC 토큰 갱신 TransportError | Vertex 경로 전용 | **번역 경로에서는 완전히 사라진다** (ADC 미사용) |

> **그러나 셋 다 «문서판독»에는 그대로 남는다.**
> `GeminiDocumentExtractor`(`backend/extractor/extractors/gemini_document_extractor.py`)는
> 이 사업에서 손대지 않는 별도 클라이언트이고 Vertex/ADC를 계속 쓴다
> (`content_extraction_service.py:100, 178`).
> → **#2705 keepalive 주입은 Gemini 쪽에서도 반드시 해야 한다.** B5 완료가 면제해주지 않는다.

---

## 10. 단계적 이전 경로

### 10.1 혼합 상태가 기본값이다

「번역만 Bedrock, 문서판독은 Gemini」는 **설계해야 할 것이 아니라 그냥 그렇게 된다.**
두 경로가 이미 다른 클래스이기 때문이다.

| 경로 | 클라이언트 | 진입점 | 이 사업에서 |
|---|---|---|---|
| 공지 번역 파이프라인 | `GeminiJsonClient` | `notice_service.py:155, 284` | **교체 대상** |
| 라벨 번역 (식단·과목) | `GeminiJsonClient` | `notice_service.py:526, 579` | 교체 대상 |
| 폴백/요약 번역 | `GeminiJsonClient` | `notice_service.py:250, 269, 303, 436` | 교체 대상 |
| **문서판독 (멀티모달)** | `GeminiDocumentExtractor` | `content_extraction_service.py:100, 178` | **손대지 않음** |
| 크롤러 AI | 자체 httpx | `crawler/gemini_finder.py`, `crawler/unknown_post_resolver.py` | 손대지 않음 |

크롤러 두 모듈은 `gemini_client`에서 `call_with_quota_backoff`(`gemini_finder.py:44`)와
`_repair_invalid_json_escapes`(`gemini_finder.py:249`, `unknown_post_resolver.py:289`)만
빌려 쓴다. **그 두 이름을 옮기거나 바꾸면 이 사업 밖이 깨진다.**

### 10.2 되돌릴 수 있는 지점

| 단계 | 상태 | 되돌리기 |
|---|---|---|
| B5 배포 후 | Bedrock 코드는 있으나 `TRANSLATION_BACKEND=gemini` — **런타임 동작 0** | 아무것도 안 해도 됨 |
| B6 배포 후 | **워커만** Bedrock (`deploy-api-cloud-run.yml:116`의 `--set-env-vars`에 추가), API 서비스는 Gemini (`:77-87`) | 워커 Job만 재배포 |
| B7 배포 후 | 전면 Bedrock | env 2줄 되돌리고 재배포 |

**B6이 진짜 반쪽 상태다.** 큐에 쌓인 공지 번역(워커)은 Bedrock으로,
사용자가 화면에서 유발하는 라벨·요약 번역(API 서비스)은 Gemini로 간다.
둘이 같은 코드·같은 프롬프트를 쓰고 **롤백 단위가 서로 독립**이다.

한 가지 주의: 같은 공지의 본문 번역(워커, Bedrock)과 소스 번역
(`translation_worker.py:53` → `_translate_sources_for_locale_background`)은
**같은 워커 프로세스 안**이라 함께 Bedrock으로 간다. 언어·톤이 갈릴 위험은 없다.

### 10.3 백필 (B9)

기존 번역 155건을 새 백엔드로 재생성하려면:

- **Bedrock 배치 추론이 적합하다** (50% 할인, 목표 24시간). 화면에서 기다리는 번역이 아니므로
  24시간 SLA가 문제되지 않는다.
- 다만 **비용은 목표가 아니다**(결정 #2). 크레딧이 있고 시간이 우선이므로
  **그냥 워커를 돌리는 편이 단순하다** — 155건 × 40초 ÷ 동시 10 ≈ 10분.
- → **배치 API를 쓰지 않는다.** 워커 재큐잉으로 처리한다. 배치 API는 «썼어야 했다»가 아니라
  «쓸 이유가 없다»로 기록한다.

---

## 11. 하지 않는다 (판정 완료)

| 후보 | 판정 | 근거 |
|---|---|---|
| **전통 NMT 하이브리드** (Google/DeepL/Azure NMT로 번역, LLM은 검증만) | **하지 않는다** | Google NMT $0.120/공지 vs Gemini 단발 $0.011 — **LLM이 11배 싸다.** 사실 보존 검증은 그대로 LLM이 해야 해서 콜 수도 안 준다. 3사 모두 지연 SLA 미공개 |
| **컨텍스트 캐싱** | **하지 않는다** | 시스템 프롬프트가 **1,738자 ≈ 500토큰**(실측: `len(COMMON_SYSTEM_PROMPT)`, `prompts.py:20-38`)인데 캐싱 최소 요건이 2,048토큰 → **현재 발동조차 안 한다** |
| **배치 API** | **하지 않는다** | 목표 24시간. 화면에서 기다리는 번역에 부적합. 백필에는 적합하지만 §10.3 이유로 불필요 |
| **여러 모델 경주 (hedged request)** | **후보로만 기록** | 중앙값은 안 준다. 꼬리 지연만 깎는다. 우선순위 낮음 |
| **`GEMINI_MAX_CONCURRENCY` 조정** | **하지 않는다** | §1.4 — 세마포어가 포화되지 않으므로 32를 올리든 내리든 아무 일도 안 일어난다 |
| **M3 (피벗 삭제)** | **하지 않는다** | §7 — 도입 근거 미확인. −8.4초를 위해 모르는 설계를 뜯지 않는다 |
| **`toolConfig` JSON 스키마 강제** | **하지 않는다** | §5.4 — 프롬프트 13개를 다시 써야 해서 A/B 통제가 무너진다 |

---

## 12. 배포 순서

되돌리기 쉬운 것부터, 변수를 하나씩만 바꾸는 순서로.

| 배포 | 내용 | 게이트 | 확인 |
|---|---|---|---|
| **0** | risk level 분포 읽기 전용 조회 (§8.2a) + 코퍼스 확장 (§4.5) | — | `low` 비율 수치 확보, 고유 공지 ≥ 30 |
| **1** | **B1** 평가 하네스 A/B 확장 | — | 기준선 arm 1회 완주, `scores.json`에 `wall_seconds` 존재 |
| **2** | **B2** 배치 대기 제거 | — | 워커 1회 실행 처리량 비교 |
| **3** | **B3** 낭비 제거 | — | 요약 번역 1건당 콜 2 → 1 (로그) |
| **4** | **B4** thinking 축소 (Gemini) | **§4.6 G1~G5** | 단건 지연 134.7 → 33.5s 근처 |
| **5** | **B5** Bedrock 클라이언트 (다크) | — | `TRANSLATION_BACKEND=gemini`로 배포 → 런타임 동작 무변화 |
| **6** | **B6** 워커만 Bedrock | **§4.6 G1~G5** (Bedrock arm) | 워커 로그의 `label=translation:apac.…`, 크레딧 차감 확인 |
| **7** | **B7** 전면 Bedrock | 6번 무사고 7일 | Gemini 호출이 문서판독·크롤러에만 남음 |
| **8** | **B9** 155건 백필 | — | 재생성 후 `validation.hard_fact` 통과율 비교 |
| **9** | **B8** 단계 병합 M1+M2 | **§4.6 G1~G5** | 라운드 7 → 5, 지연 재측정 |

**4번이 5번보다 앞인 이유**: §3·§6.3 — 변수 분리. thinking 효과를 Gemini에서
확정해두지 않으면 6번에서 품질이 흔들렸을 때 원인이 모델인지 thinking인지 모른다.

**8번이 9번보다 앞인 이유**: 백필은 «지금 확정된 최선의 파이프라인」으로 한 번만 돌리는 게 낫다.
단계 병합까지 기다리면 백필이 늦어지고, 병합이 게이트를 못 넘으면 헛기다린 게 된다.
백필 결과가 마음에 안 들면 다시 돌리면 된다(155건 = 10분).

**#2705 keepalive 주입(§9.2)은 어디에 넣는가**: 배포 2번에 얹는다. Bedrock 이전과 무관하게
문서판독 경로에 계속 필요하고, 번역 경로에서도 B7 전까지는 유효하다.

---

## 13. 검증

| 항목 | 방법 | 통과 기준 |
|---|---|---|
| B1 하네스 | 기준선 arm으로 이터 1회 완주 | 12공지 × 3언어 × 1arm = 36 json, 전부 `status=ready_to_save` |
| B1 블라인드 | 평가자 산출물에 모델명 등장 여부 검사 | `feedback-report.md`에 `gemini`/`nova`/`claude` 문자열 0건 |
| B2 처리량 | 동일 큐 깊이(≥30잡)로 워커 1회 실행 전후 비교 | 총 소요 −20% 이상 |
| B2 회귀 | 잡 1건 취소 → graceful shutdown | 형제 잡이 `fail`로 정리되고 프로세스 정상 종료 |
| B3 콜 수 | 요약 번역 1건의 `generate_json` 호출 로그 | 2 → **1** |
| B3 회귀 | 쿼터 폴백 경로(`notice_service.py:173`)로 번역 1건 | 카드 메타데이터가 **여전히** 생성됨 |
| B4 지연 | 드라이버 `wall_seconds` 중앙값 | 134.7s → **40s 이하** |
| B4 품질 | §4.6 G1~G5 | 전부 통과 |
| B5 다크 | `TRANSLATION_BACKEND=gemini`로 배포 후 번역 1건 | 로그·결과가 배포 전과 동일 |
| B5 스로틀 | `ThrottlingException` 메시지를 `is_quota_exhausted_error`에 직접 투입 | `True` 반환 (§5.5) |
| B5 동시성 | 세마포어 32 상태에서 Bedrock 콜 32개 동시 투입 | in-flight 32 (5에서 막히지 않음, §5.6) |
| B5 JSON | 36건 arm 실행 중 `_parse_json` 실패 건수 | **0건** (프리필 + 파서 복구로 충분한지 판정) |
| B6 결제 | Bedrock 콘솔 사용량 | 크레딧 차감, 현금 $0 |
| B6 라우팅 | 호출한 추론 프로필 문자열 | 전부 `apac.` 접두 (§14 Q1 결론 전까지) |
| B7 잔여 | Gemini 호출 로그 | 문서판독·크롤러만 남음 |
| B8 | 라운드 수 + §4.6 | 7 → 5, G1~G5 통과 |
| B9 | 백필 155건 | `validation.hard_fact` 통과율이 백필 전 이상 |

---

## 14. 위험과 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| **thinking OFF가 번역 품질을 깎는다** | 이주민 학부모가 공지를 오해 — north star 정면 위반 | §4.6 게이트. 특히 검증 단계(`:251`)만 thinking을 남기는 부분 적용을 예비안으로 준비(§6.2) |
| **평가 코퍼스가 작아 미세 회귀를 못 잡는다** | 조용히 나빠진 채 배포 | §4.5 — 코퍼스 확장을 배포 0번에 선행. 1차 지표를 결정적 검증(통과율)으로 |
| **`ThrottlingException`이 백오프에 안 걸린다** | 429가 잡 실패로 직행, 번역 유실 | §5.5 마커 확장을 B5의 **필수 항목**으로. 검증 표에 단독 항목 존재 |
| **boto3 스레드풀 5개에 막힌다** | 동시성이 조용히 6배 감소, 처리량 붕괴 | §5.6 전용 executor. 검증 표에 단독 항목 존재 |
| **`global.` 라우팅으로 학생 정보가 APAC 밖으로** | 개인정보 이슈 | §14 Q1 결론 전까지 `apac.` 전용. 검증 표에서 접두 확인 |
| **AWS 자격증명 유출** | 크레딧 소진 + 계정 침해 | 전용 IAM 사용자(`bedrock:InvokeModel`만), Secret Manager 주입, AdministratorAccess 미사용(§5.7) |
| **Bedrock 크레딧 소진** | 번역 정지 | `TRANSLATION_BACKEND=gemini` env 되돌리기(1줄). 잔액을 B6 배포 전·후 확인 |
| **JSON 프리필이 Nova에서 안 먹는다** | 파싱 실패 → 잡 실패 | B1 평가 단계에서 arm N의 파싱 실패 건수로 사전 발견. Nova arm만 프리필 제외 |
| **M2 병합으로 검증 판정이 흐려진다** | 나쁜 번역을 통과시킨다 | B8은 배포 순서 마지막. 게이트 통과 실패 시 M1만 적용 |
| **B6 반쪽 상태에서 두 모델의 문체가 갈린다** | 같은 화면에 두 톤 | §10.2 — 워커 내부는 한 백엔드로 통일되므로 공지 단위로는 갈리지 않는다. 라벨(식단·과목)만 다른 백엔드 |

각 단계는 단독 롤백이 가능하다. B2·B3·B4·B8은 revert, B5는 무영향,
B6·B7은 **환경변수 되돌리기 + 해당 Cloud Run Job/Service만 재배포**.

---

## 15. 결정 기록 (2026-08-27)

| # | 질문 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | 어느 제공자로 갈 것인가 | **Bedrock 최우선.** Gemini는 사용자 현금, Bedrock은 보유 크레딧. 실제 현금이 나가는 유일한 항목이 AI 호출임이 확인됐다(Cloud Run은 무료 한도 내 $0) | §1, §5 전체 |
| 2 | 비용과 시간 중 무엇이 우선인가 | **시간이 최우선. 비용은 신경 쓰지 않는다** | §11(배치 API·NMT 하이브리드를 비용 논거가 아니라 지연 논거로 기각), §10.3 |
| 3 | Bedrock에서 Claude를 써도 되는가 | **써도 된다 — 사용자 명시 승인("Bedrock은 AWS니까").** Amazon Nova·기타와 같이 놓고 비교한다 | §4.3 arm 구성, §5.9 후보표 |
| 4 | 서버도 AWS로 옮기는가 | **옮기지 않는다.** GCP Cloud Run에 그대로 둔다. **인프라 이전이 아니라 모델 교체다** | §2 비목표, §5.7(GCP에서 AWS 자격증명을 얻는 문제가 여기서 생긴다) |

> 결정 4가 §5.7의 자격증명 설계를 강제한다. 서버가 AWS에 있었다면 IAM 역할로 끝날 일이
> OIDC 연합 또는 정적 키 관리 문제가 된다. 이건 결정 4의 **알려진 비용**이지 설계 실수가 아니다.

---

## 16. 열린 질문

| # | 질문 | 왜 지금 답이 필요한가 | 막고 있는 것 |
|---|---|---|---|
| **Q1** | **`global.` 라우팅을 허용하는가?** 학교 공지에는 학생 이름·학년반·보호자 연락처가 섞인다. `global.` 접두는 요청이 APAC 밖으로 나갈 수 있다는 뜻이다 | **모델 선택을 직접 결정한다.** APAC 전용이면 Claude 4.x 계열(Haiku 4.5·Sonnet 4.5/4.6·Opus)이 전부 빠지고 최상급이 `claude-3-5-sonnet-20241022-v2:0`(510ms)로 내려앉는다 | B6 (§5.9) |
| **Q2** | **평가 코퍼스를 실제 공지로 확장할 것인가?** 현재 고유 12건, 그중 시드 6건은 목업(`"origin": "mock-seed-v1"`) | 확장하지 않으면 §4.6 게이트가 «블로우업 탐지기»에 머문다. 미세 회귀는 못 잡는다 | 배포 0번, 그리고 B4/B6/B7의 신뢰도 전부 (§4.5) |
| **Q3** | **문서판독(멀티모달)은 언제 옮기는가?** `GeminiDocumentExtractor`는 이 사업 범위 밖이다 | 옮기지 않으면 SDK 결함 #2705·#2869가 영구히 남고(§9.2), Gemini 현금 지출도 완전히는 사라지지 않는다 | 별건. 다만 «AI 호출 현금 0» 목표의 달성 여부를 결정한다 |
| **Q4** | 검증 단계(`orchestrator.py:251`)의 thinking을 남길 것인가? | 남기면 −20.5초를 포기한다. 끄면 «나쁜 번역을 통과시키는» 위음성 위험이 생기고 이건 G1이 못 잡는다 | B4의 최종 형태 (§6.2) |
| **Q5** | AWS 자격증명을 정적 키로 갈 것인가, OIDC 연합으로 갈 것인가? | 정적 키는 즉시 되고, OIDC는 비밀 0이지만 Google ID 토큰이 AWS OIDC 공급자에 그대로 통하는지 **미확인** | B6 배포 방식 (§5.7). 정적 키로 시작해도 무방하나 후속 정리 일정이 필요 |

### 남은 판단 (이 사업의 blocker는 아님)

- `GEMINI_MAX_CONCURRENCY`·`gemini_*` 설정 이름이 Bedrock 전환 후 거짓이 된다.
  B7 이후 일괄 개명하되, 배포 워크플로 3곳(`deploy-api-cloud-run.yml:116, 131, 148`)이
  같이 바뀌므로 별도 단위로 뗀다.
- risk 게이트를 «실제로 저위험이 잡히도록» 재조정하면 콜 2개를 아낀다.
  품질 동작 변경이므로 §4.6 게이트 대상. B3에서는 dead 분기 삭제까지만 한다.

---

## 17. 다음 단계

이 스펙 승인 후 `superpowers:writing-plans`로 구현 계획을 작성한다.
배포 0번(측정 + 코퍼스 확장)은 코드 변경이 없으므로 승인 즉시 착수 가능하다.
