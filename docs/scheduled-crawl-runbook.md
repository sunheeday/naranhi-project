# 매일 자동 크롤 + 증분수집 운영 런북 (step 3)

매일 정해진 시각에 **등록된 전체 학교**를 크롤해 새 공지를 수집하고(`scheduled_school_crawler`),
이어서 본문 추출·카드 생성(`scheduled_content_extractor`)을 돌린다. 두 Job은 큐(app_jobs)를
거치지 않고 **Cloud Scheduler가 직접** 실행한다(step 2의 enqueue-트리거 워커와는 별개).

> **"등록된 전체 학교"는 `schools` 테이블 전체가 아니다.** `select_school_targets`는
> `children.school_id` 조인으로 **자녀가 실제 등록된 학교만** 대상으로 삼는다.
> 2026-08-27 기준 `schools` 8곳 중 실제 스케줄러 대상은 **4곳뿐**이다(2026-08-27 Task 10 확인).
> 이전 계획 문서의 "8개 학교" 가정은 낡은 값이다.

## 동작 개요

```
06:00 / 18:00  Scheduler → naranhi-school-crawler   (전체 학교 게시판 스캔 → 새 공지 notices에 pending 저장)
07:00 / 19:00  Scheduler → naranhi-content-extractor (pending 공지 본문 추출 + 카드 + (인라인)번역)
```

- 크롤러는 게시판 상위 `CRAWLER_SCHEDULE_NOTICE_COUNT`(워크플로 기본 8)개를 스캔한다.
- **증분수집(watermark)**: 게시판별 "마지막으로 본 최대 글번호"보다 큰 글만 신규 처리한다.
  글번호가 신뢰 가능한 숫자 일련번호(nttSn/boardSeq/nttId/번호/`/view/숫자`)인 경우에만 적용되고,
  해시·LLM 생성·첨부 파일번호·경로숫자·카테고리 id 등은 기존 중복제거 방식으로 폴백한다.
  → 캐시 트림(학교당 50개 상한)으로 삭제된 옛 글(고정공지 등)이 재추출되는 낭비를 막는다.
- 첫 크롤은 기준선이 없으므로 상위 N개를 모두 베이스라인으로 저장한다.

## 롤아웃 순서

1. **DB 마이그레이션 적용** (`0033_school_crawl_state_board_watermarks.sql`): 머지 후 Supabase 대시보드
   SQL Editor에서 수동 실행. (GitHub Actions는 마이그레이션 자동적용 안 함)
   ```sql
   alter table public.school_crawl_state
     add column if not exists board_watermarks jsonb not null default '{}'::jsonb;
   ```
2. **GitHub repo 변수 2개 추가** (Settings → Secrets and variables → Actions → Variables):
   ```
   CLOUD_RUN_SCHOOL_CRAWLER_JOB     예: naranhi-school-crawler
   CLOUD_RUN_CONTENT_EXTRACTOR_JOB  예: naranhi-content-extractor
   ```
3. **머지 → 배포**: `deploy-api-cloud-run.yml`이 두 Job을 생성/업데이트한다(같은 이미지, command만 변경).
4. **IAM**: 스케줄러 서비스계정에 두 Job `run.jobs.run` 부여(step 2에서 만든 `naranhiJobRunner` 역할 재사용).
5. **Cloud Scheduler 4개 생성**(아래) — 크롤 06/18, 추출 07/19.
6. **검증**: 각 Job을 수동 실행(`gcloud run jobs execute … --wait` 또는 콘솔 "실행")해 정상 종료 확인.

## IAM (스케줄러 SA에 두 Job 실행 권한)

```bash
PROJECT_ID="<gcp-project-id>"; REGION="asia-northeast3"
SCHED_SA="naranhi-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
for JOB in naranhi-school-crawler naranhi-content-extractor; do
  gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
    --member="serviceAccount:${SCHED_SA}" \
    --role="projects/${PROJECT_ID}/roles/naranhiJobRunner"
done
```

## Cloud Scheduler (실제 6개)

콘솔로 하려면: Cloud Run → 작업 → 각 Job → **트리거 탭 → 스케줄러 트리거 추가**(백스톱 만들 때와 동일).
크롤러에 `0 6 * * *`·`0 18 * * *`, 추출기에 `0 7 * * *`·`0 19 * * *`, 시간대 Asia/Seoul.

gcloud로:
```bash
T_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/naranhi-school-crawler:run"
E_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/naranhi-content-extractor:run"
COMMON="--location=${REGION} --time-zone=Asia/Seoul --http-method=POST \
  --oauth-service-account-email=${SCHED_SA} \
  --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform --message-body={}"

gcloud scheduler jobs create http naranhi-school-crawler-0600 --schedule="0 6 * * *"  --uri="$T_URI" $COMMON
gcloud scheduler jobs create http naranhi-school-crawler-1800 --schedule="0 18 * * *" --uri="$T_URI" $COMMON
gcloud scheduler jobs create http naranhi-content-extractor-0700 --schedule="0 7 * * *"  --uri="$E_URI" $COMMON
gcloud scheduler jobs create http naranhi-content-extractor-1900 --schedule="0 19 * * *" --uri="$E_URI" $COMMON
```

### 실제 배치 (2026-08-27 `gcloud scheduler jobs list --location=asia-northeast3` 실측 — 위 create 예시와 이름·상태가 다르다)

| 스케줄러 | 주기 | 2026-08-27 상태 | 비고 |
|---|---|---|---|
| `naranhi-school-crawler-0600` | `0 6 * * *` | **PAUSED** | 2026-06-15 발표 준비로 정지 |
| `naranhi-school-crawler-1900` | `0 19 * * *` | **PAUSED** | 위 create 예시의 `-1800` 은 옛 이름. 2026-06-15 발표 준비로 정지 |
| `naranhi-content-extractor-0700` | `0 7 * * *` | **PAUSED** | 2026-06-15 발표 준비로 정지 |
| `naranhi-content-extractor-2000` | `0 20 * * *` | **PAUSED** | 위 create 예시의 `-1900` 은 옛 이름. 2026-06-15 발표 준비로 정지 |
| `naranhi-crawler-backstop` | `*/10 * * * *` | **PAUSED** | 큐 경로에서 놓친 잡 회수. 2026-06-15 발표 준비로 정지 |
| `naranhi-translation-backstop` | `*/10 * * * *` | ENABLED | 5개가 정지된 동안에도 계속 돎(정지 대상이 아니었음) |

**규칙: 누군가 스케줄러를 pause/resume 하면 이 표의 상태 칸을 그 자리에서 고치고 날짜와 이유를 적는다.**
2026-06-15 발표 준비로 5개를 정지시킨 사실이 이 저장소 어디에도 기록되지 않아 72일 동안
아무도 그 사실을 몰랐다(`gcloud scheduler jobs pause|resume` 언급이 저장소에 0건이었다).
개인 메모는 저장소 문서가 아니다.

## 재가동 · 비상 정지

**순서가 중요하다: 추출기 → 크롤러 백스톱 → 크롤러.**
크롤러가 먼저 켜지면 신규 공지가 `pending` 으로 쌓이는데 추출기가 자고 있어,
「크롤→추출 연결이 끊겼다」와 구분할 수 없는 상태가 만들어진다.
추출기가 먼저 깨어 있으면 「크롤 → 다음 정시 추출」이 그대로 이어진다.
`naranhi-translation-backstop` 은 이미 `ENABLED` 이므로 이 절차에서 건드리지 않는다.

**선행 조건 — 반드시 끝나 있어야 한다.** 워터마크 시딩(`scripts/seed_watermarks.py --apply`)이
이미 적용됐는지 먼저 확인한다. 컷오프 없이 재가동하면 정지 기간 동안 쌓인 글이 전부
신규로 잡힌다. 2026-08-27 기준 운영 `school_crawl_state`:

| 학교 | school_id | 워터마크 |
|---|---|---|
| 연수중 | `39dad243` | 34062026 |
| 부천부흥중 | `8da4b348` | 1228320 |
| 동인천중 | `6406fa75` | 34065336 |
| 함박초 | `4d74020a` | 33863948 |
| 문남초 | `26a4bc3e` | 33891448 |
| (동명 부천부흥중) | `3b33ac1d` | **비어 있음** — `homepage_fetch_failed` 로 시딩 자체가 안 됨 |
| — | `55b773d0` | 비어 있음 |

`3b33ac1d` 는 홈페이지 접속 자체가 안 되는 상태라 크롤도 못 할 가능성이 높지만,
**재가동 첫 런에서 반드시 확인한다** — 아래 "첫 런 직후 확인" 참고.
비숫자 post_id·해시 생성·첨부 파일번호는 워터마크로 걸러지지 않는다. 그만큼은
재가동 즉시 들어올 수 있다(Task 10 dry-run 기준 이번 스캔에서는 0건이었으나 보장은 아니다).

```bash
REGION="asia-northeast3"

# 0. 현재 상태를 눈으로 본다
gcloud scheduler jobs list --location="$REGION" \
  --format="table(name.basename(), schedule, state)"

# 1. 추출기
gcloud scheduler jobs resume naranhi-content-extractor-0700 --location="$REGION"
gcloud scheduler jobs resume naranhi-content-extractor-2000 --location="$REGION"

# 2. 크롤러 백스톱 (큐 경로에서 놓친 잡을 10분 안에 회수한다)
gcloud scheduler jobs resume naranhi-crawler-backstop --location="$REGION"

# 3. (권장) 크롤을 수동 1회로 먼저 돌려 컷오프를 검증 — "첫 런 직후 확인" 참고
gcloud run jobs execute naranhi-school-crawler --region="$REGION" --wait

# 4. 수동 실행 로그에서 모든 학교 success_count=0 을 확인한 뒤에만 크롤러 스케줄러를 켠다
gcloud scheduler jobs resume naranhi-school-crawler-0600 --location="$REGION"
gcloud scheduler jobs resume naranhi-school-crawler-1900 --location="$REGION"

# 5. 전부 ENABLED 확인
gcloud scheduler jobs list --location="$REGION" --format="table(name.basename(), schedule, state)"
```

**비상 정지 — 쏟아지는 것을 봤을 때 즉시:**
```bash
REGION="asia-northeast3"
gcloud scheduler jobs pause naranhi-school-crawler-0600 --location="$REGION"
gcloud scheduler jobs pause naranhi-school-crawler-1900 --location="$REGION"
gcloud scheduler jobs pause naranhi-content-extractor-0700 --location="$REGION"
gcloud scheduler jobs pause naranhi-content-extractor-2000 --location="$REGION"
gcloud scheduler jobs pause naranhi-crawler-backstop --location="$REGION"
```
그리고 위 "실제 배치" 상태표를 즉시 고친다(상태 칸 + 날짜 + 이유).

**정기 크롤러에는 재시도가 없다** (`--max-retries=0`, `deploy-api-cloud-run.yml`).
실패하면 다음 스케줄까지 최대 12~13시간이다. `naranhi-crawler-backstop`(10분 주기)이
사실상의 재시도 역할을 한다. Cloud Run Job retry 는 task 전체 재실행이라 학교 단위
재시도가 아니므로 켜지 않는다.

## 첫 런 직후 확인 (이 사업이 넣은 계측을 이렇게 읽는다)

재가동 후 첫 크롤·추출 런이 끝나면 아래를 확인한다. 하나라도 「쏟아졌다」로 읽히면
바로 위 "비상 정지" 명령으로 해당 스케줄러를 멈추고 원인부터 본다 — 재추출 금지
제약상 일단 들어온 것을 되돌릴 방법은 없다(멈추는 것만 가능).

1. **크롤 결과 — 워터마크가 먹혔는지.**
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-school-crawler" AND textPayload:"scheduled school crawler result:"' \
     --limit=20 --freshness=30m --format="value(textPayload)"
   ```
   로그 형식: `scheduled school crawler result: school_id=%s status=%s success_count=%s`.
   **기대값: 모든 학교 `success_count=0`.** `3b33ac1d`(무워터마크)에서 `success_count>0` 이
   나오면 그 학교부터 의심한다. 0이 아닌 학교가 있으면 새로 들어온 글의 post_id 가 숫자
   일련번호인지 먼저 확인한다(숫자인데 들어왔으면 시딩 실패 — 즉시 정지하고 Task 10의
   백업 JSON 으로 워터마크 복원).

2. **게시판 감지 폴백 경고.**
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-school-crawler" AND textPayload:"scheduled crawler board fallback:"' \
     --limit=20 --freshness=30m --format="value(textPayload)"
   ```
   `scheduled crawler board fallback: count=%s schools=%s` — 나오면 해당 학교가 지정
   게시판이 아니라 공지사항 전체 폴백으로 스캔됐다는 뜻. 워터마크 board_key 와 어긋날
   수 있으니 이름이 나온 학교는 워터마크 값을 다시 대조한다.

3. **추출기 — 본문 사진 합성.**
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-content-extractor" AND textPayload:"body images: notice_id="' \
     --limit=20 --freshness=30m --format="value(textPayload)"
   ```
   `body images: notice_id=%s collected=%s stitched=0|1 [bytes=%s] upload=ok|fail|skip`.
   `upload=fail` 이 반복되면 Storage 업로드 경로를 본다.

4. **추출기 — 이미지 타일 OCR.**
   ```bash
   gcloud logging read \
     'resource.type="cloud_run_job" AND resource.labels.job_name="naranhi-content-extractor" AND textPayload:"image tiles: source="' \
     --limit=20 --freshness=30m --format="value(textPayload)"
   ```
   `image tiles: source=%s tiles=%s ok=%s empty=%s failed=%s`. `failed` 이 `tiles` 대비
   과반이면 롤백: 추출기 Job env `MAX_TILES_PER_IMAGE=1`.

5. **추출기 — HWP 표 뭉개짐 경고 (Cloud Logging 이 아니라 DB 조회).**
   `hwp5html_below_threshold: chars=N table_rows=M` / `hwp5html_skip_no_command` 는
   LOGGER 로 찍히지 않고 공지별 `notices.extracted_content.sources[].errors` 에
   저장된다. Supabase SQL Editor(읽기 전용)에서:
   ```sql
   select id, title,
          jsonb_path_query_array(extracted_content, '$.sources[*].errors[*]') as source_errors
   from notices
   where created_at > now() - interval '1 day'
     and extracted_content::text like '%hwp5html%';
   ```
   `hwp5html_below_threshold` 가 몰리면 표가 실제로 뭉개지는지 카드 내용을 눈으로 대조한다.
   롤백: 추출기 Job env `HWP5HTML_ACCEPT_SHORT_TABLES=0` (옛 길이 전용 규칙으로 복귀).

**개인정보:** 위 로그 어디에도 본문·첨부 내용·학생명·연락처가 없다 — 식별자·개수·
상태값·정제된 예외 메시지뿐(Task 2·4·8 계측 설계 그대로).

## 튜닝 / 비상

- **스캔 깊이**: 크롤러 Job env `CRAWLER_SCHEDULE_NOTICE_COUNT`(워크플로 기본 8). 한 게시판에서
  반나절에 (고정공지 포함) 이보다 많은 글이 올라오면 그 너머는 못 본다 → 필요 시 올린다.
- **추출량**: 추출기 Job args `--max-notices 30`. 실제 처리량은 `EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN`
  (기본 80콜)이 좌우 — 새 공지가 많으면 한 번에 다 못 하고 다음 run에 이어서 처리된다.
- **증분수집 끄기**: 크롤러 Job env `CRAWLER_WATERMARK_ENABLED=false` → 즉시 비활성(상위 N + 중복제거만).
- **재크롤(기준선 무시)**: `scheduled_school_crawler --force`는 시간/unsupported 쿨다운만 무시한다.
  CMS가 글번호를 리셋해 신규글이 누락되면 해당 학교 `board_watermarks`를 SQL로 비우거나 낮춘다.

## 한계 (정직하게)

- "글번호가 클수록 최신"은 우리 학교들이 쓰는 CMS(eGovFrame nttSn / boardCnts boardSeq 등 자동증가
  시퀀스)에서 성립한다. 게시일을 따로 저장하지 않으므로 번호로만 판단한다.
- 스캔 깊이(상위 N) 너머로 밀린 신규 글은 watermark로도 못 잡는다(페이지네이션 미구현). 현재 학교
  공지량(보통 하루 1건)에서는 N=8이면 충분(고정공지 몇 개 위에 있어도 새 글 잡힘).
