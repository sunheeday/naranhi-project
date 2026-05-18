# 콘텐츠 추출 Job 운영 메모

이 Job은 `notices.source='crawl'` 공지의 상세 URL에 접속해 HTML, 첨부 PDF/HWP/HWPX, 인라인 이미지를 추출하고 `notices.original_text`, `summary_oneliner`, `extracted_content`를 채운다.

이번 문서는 배포 준비용이다. 실제 Cloud Run Job 생성, Secret Manager 값 등록, Scheduler 연결은 GCP 권한자가 수행한다.

## 로컬 Docker 실행

Docker build는 반드시 repo root에서 실행한다. `cd backend` 후 build하면 `COPY backend/...` 경로가 깨진다.

```powershell
docker build -f backend\Dockerfile.extractor -t naranhi-content-extractor:local .
```

잘못된 예:

```powershell
cd backend
docker build -f Dockerfile.extractor .
```

Docker `--env-file`은 따옴표를 제거하지 않고 멀티라인 값을 지원하지 않는다. `.env.local`에 OAuth JSON, 따옴표, 멀티라인 값이 섞여 있으면 extractor 전용 env 파일을 사용한다.

```powershell
copy .env.extractor.example .env.extractor.local
```

macOS/Linux:

```bash
cp .env.extractor.example .env.extractor.local
```

필수 값을 채운 뒤 dry-run:

```powershell
docker run --rm --env-file .env.extractor.local naranhi-content-extractor:local --dry-run --max-notices 5
```

공지 1건 실제 추출:

```powershell
docker run --rm --env-file .env.extractor.local naranhi-content-extractor:local --notice-id <notice_id> --force --max-notices 1
```

디버깅 shell:

```powershell
docker run --rm -it --entrypoint bash naranhi-content-extractor:local
```

컨테이너 내부 import 검증:

```powershell
docker run --rm --entrypoint python naranhi-content-extractor:local -c "import importlib; modules = ['app.jobs.scheduled_content_extractor','extractor.extract_pipeline','extractor.extractors.hwp_extractor','extractor.extractors.hwpx_extractor','extractor.extractors.pdf_extractor','extractor.extractors.image_gemini_extractor','extractor.file_downloader','extractor.archive_security']; [importlib.import_module(m) for m in modules]; print('ok')"
```

## Artifact Registry 이미지

운영 이미지는 git SHA와 `latest`를 같이 태그한다. 롤백할 때 SHA 태그를 사용한다.

```bash
TAG="$(git rev-parse --short HEAD)"

docker build \
  -f backend/Dockerfile.extractor \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-content-extractor:${TAG}" \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-content-extractor:latest" \
  .

docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-content-extractor:${TAG}"
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-content-extractor:latest"
```

## Secret Manager

비밀값은 `--set-env-vars`로 넣지 않는다. Cloud Run Job describe, 배포 로그, shell history에 노출될 수 있다.

```bash
gcloud iam service-accounts create extractor-job-sa \
  --display-name="Naranhi Content Extractor Job"

JOB_SA="extractor-job-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud secrets create supabase-service-role-key --data-file=-
gcloud secrets create gemini-api-key --data-file=-

gcloud secrets add-iam-policy-binding supabase-service-role-key \
  --member="serviceAccount:${JOB_SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${JOB_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

## Cloud Run Job 배포 예시

Cloud Run Job retry는 v1에서 끈다. Job retry는 task 전체 재실행이고 notice 단위가 아니다. 이 extractor는 `claim_notice_extractions`, `extraction_next_run_at`, stale recovery로 notice 단위 재시도를 이미 DB에 기록한다. 컨테이너가 죽으면 `EXTRACTOR_STALE_MINUTES` 이후 다음 실행에서 다시 claim된다.

추가 args 없이 실행하면 pending 또는 retry 가능한 `source='crawl'` 공지를 `EXTRACTOR_MAX_NOTICES_PER_RUN` 개수까지 처리한다. 특정 공지 1건만 강제 처리해야 할 때만 `--notice-id`, `--force` 같은 args를 넘긴다.

```bash
gcloud run jobs deploy naranhi-content-extractor \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/naranhi-content-extractor:${TAG}" \
  --region="${REGION}" \
  --service-account="${JOB_SA}" \
  --memory=2Gi \
  --cpu=1 \
  --task-timeout=14400 \
  --max-retries=0 \
  --set-secrets="SUPABASE_SERVICE_ROLE_KEY=supabase-service-role-key:latest,GEMINI_API_KEY=gemini-api-key:latest" \
  --set-env-vars="ENVIRONMENT=production,EXTRACTOR_MAX_NOTICES_PER_RUN=20,EXTRACTOR_NOTICE_TIMEOUT_SECONDS=600,EXTRACTOR_STALE_MINUTES=180,EXTRACTOR_MAX_GEMINI_CALLS_PER_RUN=80,ENABLE_GEMINI_STRUCTURING=false,MAX_GEMINI_CALLS_PER_NOTICE=8,MAX_INLINE_IMAGES_PER_NOTICE=6,MAX_TOTAL_OCR_BYTES_PER_NOTICE=26214400,MAX_PDF_PAGES_FOR_OCR=20,OCR_INLINE_IMAGES=auto,MAX_FILE_SIZE_MB=50"
```

`--set-env-vars`는 comma-separated라 값 안에 쉼표가 있으면 깨진다. 쉼표가 들어가는 `TLS_VERIFY_INSECURE_HOSTS`는 delimiter를 바꿔 별도로 넣는다.

```bash
gcloud run jobs update naranhi-content-extractor \
  --region="${REGION}" \
  --update-env-vars="^@^TLS_VERIFY_INSECURE_HOSTS=sen.ms.kr,gen.ms.kr"
```

수동 실행:

```bash
gcloud run jobs execute naranhi-content-extractor \
  --region="${REGION}" \
  --wait
```

특정 notice만 강제 실행:

```bash
gcloud run jobs execute naranhi-content-extractor \
  --region="${REGION}" \
  --args="--notice-id=<notice_id>,--force,--max-notices=1" \
  --wait
```

Scheduler 연결은 별도 단계에서 한다. 권장 시간은 학교 크롤러가 끝난 뒤 여유를 둔 `07:00`, `19:00` KST다.
