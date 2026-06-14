# 매일 자동 크롤 + 증분수집 운영 런북 (step 3)

매일 정해진 시각에 **등록된 전체 학교**를 크롤해 새 공지를 수집하고(`scheduled_school_crawler`),
이어서 본문 추출·카드 생성(`scheduled_content_extractor`)을 돌린다. 두 Job은 큐(app_jobs)를
거치지 않고 **Cloud Scheduler가 직접** 실행한다(step 2의 enqueue-트리거 워커와는 별개).

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

## Cloud Scheduler 4개

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
