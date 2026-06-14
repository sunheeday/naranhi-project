# Worker Queue Split

이 문서는 `크롤링/정제`와 `AI 번역`을 분리하는 1차 구조를 정리한다.

## 목표

- API 서버는 요청을 빠르게 받고 `job`만 enqueue 한다.
- 실제 무거운 작업은 별도 worker 프로세스가 수행한다.
- 이후 필요하면 이 worker들을 완전히 별도 서버/Cloud Run Job으로 분리할 수 있다.

## 현재 구조

- `Next.js`
  - 사용자 요청, 진행 상태 폴링
- `FastAPI API`
  - `/crawler/...` 요청을 `app_jobs`에 enqueue
  - `/notices/{id}/translate` 요청을 `app_jobs`에 enqueue
- `crawler_worker`
  - 학교 게시판 발견
  - pending notice 본문 추출/정제
- `translation_worker`
  - 공지 본문 번역
  - 카드 번역 저장
  - summary/source 번역 후속 처리

## 큐 테이블

- migration: [0027_app_jobs.sql](/Users/sunnykim/naranhi-project/supabase/migrations/0027_app_jobs.sql)
- table: `public.app_jobs`

주요 컬럼:
- `job_type`
- `job_key`
- `payload`
- `status`
- `attempts`
- `max_attempts`
- `available_at`
- `last_error`

`job_key`는 `queued/processing` 상태에서 unique 하므로 같은 작업의 중복 enqueue를 막는다.

## Job Types

- `school_board_discovery`
  - 학교 게시판 탐색/저장
- `school_notice_extraction`
  - 학교별 pending notice 본문 추출/정제
- `notice_translation`
  - 공지 번역 + 카드 번역 + summary/source 후속 번역

## 실행 방법

API 서버:

```bash
set -a; source .env.local; set +a
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

크롤러/정제 worker:

```bash
set -a; source .env.local; set +a
PYTHONPATH=backend python3 -m app.jobs.crawler_worker --max-jobs 20 --batch-size 3
```

번역 worker:

```bash
set -a; source .env.local; set +a
PYTHONPATH=backend python3 -m app.jobs.translation_worker --max-jobs 20 --batch-size 3
```

## 옵션 B: 항상 켜진 Worker Service

Cloud Run Service로 worker를 항상 켜두려면 `backend/app/worker_main.py`를 사용한다.

translation worker service:

```bash
set -a; source .env.local; set +a
WORKER_JOB_GROUPS=translation \
PYTHONPATH=backend backend/.venv/bin/uvicorn app.worker_main:app --host 0.0.0.0 --port 8080
```

crawler worker service:

```bash
set -a; source .env.local; set +a
WORKER_JOB_GROUPS=crawler \
PYTHONPATH=backend backend/.venv/bin/uvicorn app.worker_main:app --host 0.0.0.0 --port 8080
```

둘을 하나의 service로 합칠 수도 있다.

```bash
WORKER_JOB_GROUPS=translation,crawler
```

권장 환경변수:

- `WORKER_JOB_GROUPS=translation` 또는 `crawler`
- `WORKER_BATCH_SIZE=3`
- `WORKER_POLL_INTERVAL_SECONDS=2`
- `WORKER_RETRY_DELAY_SECONDS=120`

이 모드에서는 Scheduler 1분 주기를 기다리지 않으므로, enqueue 후 수 초 내에 worker가 job을 잡아갈 수 있다.

주의:

- Cloud Run Service에서 이 동작을 기대하려면 `min instances >= 1` 이어야 한다.
- background polling이 계속 돌 수 있게 CPU가 request 외 시간에도 유지되는 설정을 사용해야 한다.
- 그렇지 않으면 service는 떠 있어도 실제 polling loop가 항상 돌지 않아, 사실상 즉시 처리가 보장되지 않는다.

## 분리 원칙

- OCR만 `flash-lite -> flash fallback`
- 일반 번역/검증은 `flash`
- 학교 내 여러 notice 추출은 병렬
- locale별 자동 번역도 병렬
- summary/source 번역도 병렬

단, 공지 1건의 full translation pipeline 내부 단계는 의존성이 있어 대부분 직렬이다.

## 운영 모드: Cloud Run Job + 깨우기 트리거 (현행)

상시가동 Service(min-instances=1, 월 ~$120 유휴) 대신 워커를 **Cloud Run Job**으로 돌린다.

- API가 enqueue 직후 `schedule_worker_trigger(job_type)`로 해당 Job을 `run.jobs.run` 호출(깨우기).
  best-effort·인메모리 디바운스. `WORKER_TRIGGER_ENABLED=false`(기본)면 무동작.
- 워커 Job은 `--max-jobs 0`으로 큐가 빌 때까지 drain하고, 종료 직전 `--idle-grace-seconds`
  만큼 한 번 더 폴링(트리거 경합 방지) 후 종료한다.
- 시작 시 `reclaim_stale_jobs`로 오래된 좀비 `processing` 잡을 회수한다.
- 백스톱 Cloud Scheduler(10분 틱)가 트리거 실패 시 안전망이다.

배포·IAM·Scheduler·롤아웃 절차는 [worker-jobs-runbook.md](worker-jobs-runbook.md) 참고.

> 위 "옵션 B: 항상 켜진 Worker Service"(`app.worker_main:app`)는 로컬/디버그용으로 남겨둔다.
> 운영에서는 Job 모드를 쓴다.

## 다음 단계

1. `app_jobs` 상태 조회 API 추가
2. worker heartbeat/observability 추가
3. 필요 시 translation worker와 crawler worker를 완전히 별도 배포 단위로 분리
