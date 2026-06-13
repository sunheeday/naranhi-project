# 워커 Cloud Run Job 운영 런북 (잠자기 + 깨우기)

큐 워커(`translation`/`crawler`)를 **상시가동 Service(min-instances=1, 월 ~$120 유휴)** 대신
**Cloud Run Job**으로 돌린다. 잡을 큐에 넣으면 API가 `run.jobs.run`으로 워커 Job을 깨우고,
워커는 큐를 비운 뒤(drain) 종료한다. 백스톱 Cloud Scheduler가 안전망이다.

## 동작 개요

```
사용자/시스템 → API enqueue(app_jobs) → schedule_worker_trigger(job_type)
                                            └─(best-effort, 인메모리 디바운스)→ run.jobs.run
워커 Job 실행 → reclaim_stale_jobs(좀비 회수) → 큐가 빌 때까지 drain(--max-jobs 0)
            → idle-grace 재폴링(트리거 경합 방지) → 종료
백스톱: Cloud Scheduler가 10분마다 두 Job을 깨워 적체분 처리(트리거 실패 대비)
```

- `notice_translation` → 번역 Job, `school_board_discovery`/`school_notice_extraction` → 크롤 Job.
- 트리거는 **best-effort**다. 실패해도 enqueue는 성공하고, 백스톱 스케줄러가 결국 처리한다.
- `WORKER_TRIGGER_ENABLED`가 false면(기본) 트리거는 아무 동작도 안 한다 → 로컬·테스트 안전.
- 동시 실행이 몇 개 생겨도 `claim`의 조건부 업데이트가 같은 행 중복처리를 막는다(안전).

## 필요한 GitHub Actions repo 변수

기존(이미 사용 중): `GCP_PROJECT_ID`, `GCP_REGION`, `GAR_LOCATION`, `GAR_REPOSITORY`,
`CLOUD_RUN_API_SERVICE`, `NEXT_PUBLIC_SUPABASE_URL`, `VERTEX_AI_PROJECT_ID`, `VERTEX_AI_LOCATION`.

**신규로 추가**(이 값이 비어 있으면 워크플로의 Job 배포 스텝은 건너뛴다):

```
CLOUD_RUN_TRANSLATION_WORKER_JOB   예: naranhi-translation-worker
CLOUD_RUN_CRAWLER_WORKER_JOB       예: naranhi-crawler-worker
```

> 참고: 기존 `CLOUD_RUN_TRANSLATION_WORKER_SERVICE` / `CLOUD_RUN_CRAWLER_WORKER_SERVICE`
> 변수는 더 이상 워크플로에서 쓰지 않는다(Service 배포 스텝 제거됨).

## 롤아웃 순서 (안전 전환)

핵심: **기존 워커 Service는 새 Job이 검증될 때까지 그대로 둔다.** 그 사이엔 Service가
계속 폴링하므로 큐 처리에 공백이 없다. 검증 후 Service를 지우면 그때 $120이 사라진다.

1. **repo 변수 추가**: `CLOUD_RUN_TRANSLATION_WORKER_JOB`, `CLOUD_RUN_CRAWLER_WORKER_JOB`.
2. **머지 → 배포**: `deploy-api-cloud-run.yml`이 두 Job을 생성/업데이트하고, API를
   `WORKER_TRIGGER_ENABLED=true`로 재배포한다. (이 시점엔 IAM이 없어 트리거가 403으로
   실패할 수 있다 — best-effort라 경고 로그만 남고, 기존 Service가 큐를 계속 처리한다.)
3. **IAM 부여**(아래 명령): API 런타임 SA에 `run.jobs.run`을 두 Job에 부여.
4. **수동 깨우기 검증**: `gcloud run jobs execute ... --wait`로 각 Job이 정상 drain·종료하는지 확인.
   API에서 번역 한 건 요청 → 로그에서 `worker job triggered`와 처리 완료 확인.
5. **백스톱 Scheduler 생성**(아래 명령): 10분 틱.
6. **기존 워커 Service 삭제**(아래 명령) → 유휴비 제거 완료.

> ⚠️ 불변식(코드로 강제되지 않음, 순서 준수 필수): **백스톱 Scheduler(5단계)와 IAM(3단계)이
> 준비되기 전에는 절대 기존 워커 Service를 삭제하지 말 것.** 그 전까지는 Service 폴링이
> 유일한 안전망이다. 또한 2→3단계 사이엔 트리거가 IAM 미부여로 403을 내며 경고 로그가
> 잠시 쌓일 수 있는데, best-effort라 무해하고 Service가 큐를 계속 처리한다.

## IAM: API 런타임 SA에 run.jobs.run 부여

```bash
PROJECT_ID="<gcp-project-id>"
REGION="<gcp-region>"                       # 예: asia-northeast3
TRANSLATION_JOB="naranhi-translation-worker"
CRAWLER_JOB="naranhi-crawler-worker"
API_SERVICE="<CLOUD_RUN_API_SERVICE 값>"

# API 서비스의 런타임 서비스계정 확인
API_SA=$(gcloud run services describe "$API_SERVICE" --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')
echo "API runtime SA = $API_SA"   # 비어 있으면 기본 Compute SA: <PROJECT_NUMBER>-compute@developer.gserviceaccount.com

# run.jobs.run(+executions.get) 만 가진 커스텀 역할
gcloud iam roles create naranhiJobRunner --project="$PROJECT_ID" \
  --title="Naranhi Job Runner" \
  --permissions=run.jobs.run,run.executions.get \
  --stage=GA

# 두 Job 리소스에 바인딩
for JOB in "$TRANSLATION_JOB" "$CRAWLER_JOB"; do
  gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
    --member="serviceAccount:$API_SA" \
    --role="projects/$PROJECT_ID/roles/naranhiJobRunner"
done
```

> 더 간단히 가려면 커스텀 역할 대신 `--role=roles/run.developer`(Job 리소스 한정)도 된다.
> 단 권한 범위가 넓다.

## 수동 실행/검증

```bash
gcloud run jobs execute "$TRANSLATION_JOB" --region="$REGION" --wait
gcloud run jobs execute "$CRAWLER_JOB" --region="$REGION" --wait
```

빈 큐면 수 초 안에 종료(`processed=0`)해야 한다.

## 백스톱 Cloud Scheduler (10분 틱)

트리거가 실패해도 적체분이 최대 10분 안에 처리되게 한다. 빈 drain은 수 초라 비용은 무시할 수준.
(step 3의 06/18시 전체 크롤 스케줄러와는 별개다.)

```bash
SCHEDULER_SA="naranhi-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
T_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${TRANSLATION_JOB}:run"
C_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${CRAWLER_JOB}:run"

# Scheduler SA에도 같은 Job 실행 권한 필요
for JOB in "$TRANSLATION_JOB" "$CRAWLER_JOB"; do
  gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
    --member="serviceAccount:${SCHEDULER_SA}" \
    --role="projects/${PROJECT_ID}/roles/naranhiJobRunner"
done

gcloud scheduler jobs create http naranhi-translation-worker-backstop \
  --location="$REGION" --schedule="*/10 * * * *" --time-zone="Asia/Seoul" \
  --uri="$T_URI" --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --message-body="{}"

gcloud scheduler jobs create http naranhi-crawler-worker-backstop \
  --location="$REGION" --schedule="*/10 * * * *" --time-zone="Asia/Seoul" \
  --uri="$C_URI" --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --message-body="{}"
```

## 기존 워커 Service 삭제 (유휴비 제거)

Job 트리거 + 백스톱이 검증된 뒤에만 실행한다.

```bash
gcloud run services delete <기존 translation worker service 이름> --region="$REGION"
gcloud run services delete <기존 crawler worker service 이름> --region="$REGION"
```

## 환경변수 요약

API Service(트리거 발신): `WORKER_TRIGGER_ENABLED=true`, `GCP_PROJECT_ID`, `GCP_REGION`,
`TRANSLATION_WORKER_JOB_NAME`, `CRAWLER_WORKER_JOB_NAME`, (선택) `WORKER_TRIGGER_DEBOUNCE_SECONDS`.

워커 Job: 워크플로가 `--max-jobs 0 --idle-grace-seconds 3`으로 실행. (선택)
`WORKER_JOB_STALE_MINUTES`(기본 180, 좀비 회수 기준).

## 롤백

문제 시: 기존 워커 Service를 삭제하지 않았다면 그대로 폴링하므로 즉시 안전.
이미 삭제했다면 git 이전 워크플로(Service 배포)로 되돌려 재배포하거나, 백스톱 Scheduler
주기를 짧게(예: `*/2 * * * *`) 낮춰 임시 대응한다.
