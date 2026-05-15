# Next.js CI/CD 구축 Phase

이 문서는 나란히 프로젝트를 Docker, GitHub Actions, Google Cloud Run 기반으로 배포하기 위한 단계별 실행 계획입니다.

## Phase 0. 기준 확정

목표는 `main` 브랜치에 merge된 코드를 자동으로 Cloud Run에 배포하는 것입니다.

- 애플리케이션: Next.js
- 컨테이너: Docker
- CI: GitHub Actions
- 이미지 저장소: Google Artifact Registry
- 런타임: Google Cloud Run
- 인증: GitHub Actions Workload Identity Federation

## Phase 1. 애플리케이션 기본 구조

구현 항목:

- Next.js 앱 기본 파일 추가
- TypeScript 설정 추가
- ESLint 설정 추가
- `/api/health` 헬스체크 엔드포인트 추가
- `next.config.mjs`에 `output: "standalone"` 설정

검증 명령:

```bash
npm run lint
npm run typecheck
npm run build
```

## Phase 2. Docker 이미지 빌드

구현 항목:

- `Dockerfile`
- `.dockerignore`
- Cloud Run 포트 `8080`
- Next.js standalone output 기반 production image

로컬 검증 명령:

```bash
docker build -t naranhi-web .
docker run --rm -p 8080:8080 naranhi-web
curl http://127.0.0.1:8080/api/health
```

## Phase 3. GitHub Actions CI

구현 항목:

- `.github/workflows/ci.yml`
- PR과 `main` push에서 lint, typecheck, build 실행

배포 전 품질 게이트:

- `npm run lint`
- `npm run typecheck`
- `npm run build`

## Phase 4. Google Cloud 리소스

필요 리소스:

- Google Cloud Project
- Artifact Registry Docker repository
- Cloud Run service
- GitHub Actions 전용 Service Account
- Workload Identity Pool / Provider

필요 API:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com
```

권장 변수:

```text
GCP_PROJECT_ID
GCP_REGION
GAR_LOCATION
GAR_REPOSITORY
CLOUD_RUN_SERVICE
```

권장 Secret:

```text
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_SERVICE_ACCOUNT
```

## Phase 5. Cloud Run 배포 자동화

구현 항목:

- `.github/workflows/deploy-cloud-run.yml`
- Google Cloud 인증
- Artifact Registry Docker auth 설정
- Docker image build / push
- Cloud Run deploy

배포 트리거:

- `main` push
- 수동 실행 `workflow_dispatch`

## Phase 6. 운영 안정화

추가할 항목:

- staging / production 환경 분리
- Cloud Run 환경 변수 관리
- GitHub Environments approval
- Sentry 또는 Google Error Reporting 연동
- uptime check
- 배포 실패 알림
