# 정기 학교 공지 크롤러 Job 운영 메모

이 Job은 사용자가 등록한 모든 학교를 순차적으로 크롤링해 새 공지 후보 URL을 `notices`에 저장한다.

## 로컬 실행

```powershell
$env:PYTHONPATH="backend"
python -m app.jobs.scheduled_school_crawler --dry-run
python -m app.jobs.scheduled_school_crawler --school-id "<school_id>" --force
```

운영 정기 실행에서는 `--limit`을 쓰지 않는다. `--limit`은 로컬 테스트 전용이다.

## 기본 정책

- 등록된 학교 전체를 한 번의 Job에서 전부 시도한다.
- 기본 동시성은 `CRAWLER_SCHEDULE_CONCURRENCY=1`이다.
- `unsupported_login_required`, `unsupported_forbidden`, `unsupported_external_dynamic`은 기본 7일마다 재시도한다.
- `--force`는 시간/unsupported 쿨다운만 무시한다.
- 성공률이 `CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD` 미만이면 process exit code가 `1`이 된다.

## Cloud Run Job 배포 예시

기존 API image를 재사용하고 command만 Job용으로 바꾼다.

```bash
gcloud run jobs deploy naranhi-school-crawler \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-api:latest" \
  --region="${REGION}" \
  --command="python" \
  --args="-m,app.jobs.scheduled_school_crawler" \
  --task-timeout=14400 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars="ENVIRONMENT=production,CRAWLER_SCHEDULE_CONCURRENCY=1,CRAWLER_SCHEDULE_NOTICE_COUNT=10,CRAWLER_UNSUPPORTED_RECHECK_HOURS=168,CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD=0.5"
```

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEIS_API_KEY`, `GEMINI_API_KEY` 같은 비밀값은 Secret Manager 또는 Cloud Run Job 환경변수로 별도 주입한다.

수동 실행:

```bash
gcloud run jobs execute naranhi-school-crawler \
  --region="${REGION}" \
  --wait
```

## Cloud Scheduler 예시

Cloud Scheduler는 Cloud Run Jobs API의 `jobs:run` endpoint를 OAuth service account로 호출한다.

```bash
JOB_RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/naranhi-school-crawler:run"
SCHEDULER_SA="naranhi-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud scheduler jobs create http naranhi-school-crawler-0600 \
  --location="${REGION}" \
  --schedule="0 6 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="${JOB_RUN_URI}" \
  --http-method=POST \
  --oauth-service-account-email="${SCHEDULER_SA}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --headers="Content-Type=application/json" \
  --message-body="{}"

gcloud scheduler jobs create http naranhi-school-crawler-1800 \
  --location="${REGION}" \
  --schedule="0 18 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="${JOB_RUN_URI}" \
  --http-method=POST \
  --oauth-service-account-email="${SCHEDULER_SA}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --headers="Content-Type=application/json" \
  --message-body="{}"
```

Scheduler service account에는 Cloud Run Job 실행 권한이 필요하다. 최소한 `run.jobs.run` 권한이 포함된 역할을 Job 리소스에 부여한다.
