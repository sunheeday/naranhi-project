# 나란히

나란히는 한국어 가정통신문을 읽기 어려운 이주민 학부모가 학교 공지를 더 쉽게 이해하고 자녀의 학교생활을 놓치지 않도록 돕는 서비스입니다.

학교에서 발송하는 가정통신문을 모국어 요약, 카드뉴스, 일정 정리 형태로 제공하며, 학교 캘린더와 급식 정보까지 함께 지원하여 학부모가 필요한 준비물, 제출 기한, 행사 일정, 주의사항뿐만 아니라 매일의 식단까지 빠르게 확인할 수 있도록 합니다.

## 제품 개요

한국 학교의 가정통신문은 학사 일정, 준비물, 급식, 제출 서류, 행사 안내처럼 학부모가 꼭 알아야 하는 정보를 담고 있습니다. 하지만 한국어가 익숙하지 않은 학부모에게는 단순 번역만으로 맥락을 이해하기 어렵고, 학교 용어나 행정 표현 때문에 중요한 행동을 놓치기 쉽습니다.

나란히는 이 문제를 줄이기 위해 가정통신문을 학부모의 언어로 정리하고, 해야 할 일을 중심으로 다시 보여줍니다. 사용자는 공지 목록에서 새 가정통신문을 확인하고, 상세 화면에서 카드뉴스로 핵심 내용을 넘겨 볼 수 있습니다. 또한, 달력을 통해 학교 주요 행사와 제출 기한을 한눈에 관리하며, 자녀가 먹는 매일의 급식 식단표도 알레르기 정보와 함께 자국어로 쉽게 파악할 수 있습니다.

## 주요 사용자

- 한국어 가정통신문 이해에 어려움을 겪는 이주민 학부모
- 다문화 가정 및 국제결혼 가정의 보호자
- 외국인 근로자 자녀를 둔 보호자
- 가정통신문과 학교 소식을 더 쉽게 전달하고 싶은 학교 관계자

## 주요 기능

- **가정통신문 업로드 및 자동 분석**
- **모국어 기반 핵심 요약 제공**
- **준비물, 해야 할 일, 일정 중심의 카드뉴스 뷰어**
- **통합 캘린더 (일정 관리):** 공지에서 자동 추출된 제출 기한, 학교 행사 일정 및 개인 일정을 통합하여 캘린더 형태로 표시
- **다국어 급식 소식:** 매일 제공되는 학교 급식 식단표와 알레르기 유발 물질 정보를 학부모가 설정한 모국어로 번역하여 제공

## 화면 흐름

```text
학부모 로그인
  -> 온보딩에서 자녀 정보와 언어 설정
  -> 홈에서 새 공지 확인 및 오늘의 급식 메뉴 확인
  -> 카드뉴스로 핵심 내용 확인
  -> 학교 행사 및 서류 제출 기한은 캘린더에서 한눈에 관리
```

```text
학교 관리자 데모
  -> 가정통신문 업로드 및 월간 식단표/일정 등록
  -> 발송 대상 선택
  -> 공지 및 데이터 분석 후 학부모 화면에 맞춤형 언어로 전달
```

## 기술 정보

| 구분 | 내용 |
|---|---|
| 프론트엔드 | Next.js, React, TypeScript |
| 백엔드 | Next.js Route Handler, FastAPI |
| 데이터베이스 | Supabase Postgres |
| 인증 | Supabase Auth |
| 파일 저장 | Supabase Storage |
| AI/OCR | FastAPI에서 Gemini 기반 AI/OCR/번역 파이프라인 연동 |
| 배포 | Docker, GitHub Actions, Google Cloud Run |
| 다국어 | FastAPI 번역 파이프라인 |

## 실행 방법

```bash
npm install
npm run dev
```

로컬 개발 서버는 기본적으로 `http://localhost:3000`에서 실행됩니다.

헬스체크 엔드포인트:

```bash
curl http://localhost:3000/api/health
```

## 환경 변수

로컬 환경 변수는 `.env.local`에 작성합니다. 공개 가능한 예시는 `.env.example`을 참고합니다.

```env
NEXT_PUBLIC_APP_NAME=Naranhi
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FASTAPI_INTERNAL_URL=http://localhost:8000
SUPABASE_URL=https://your-project-ref.supabase.co
CORS_ORIGINS=http://localhost:3000
```

## Supabase

Supabase는 사용자 인증, Postgres DB, 파일 저장소, RLS 권한 정책을 담당합니다.
초기 스키마는 `supabase/migrations/0001_initial_schema.sql`에 있습니다.

```bash
supabase link --project-ref your-project-ref
supabase db push
```

자세한 내용은 [Supabase Schema](docs/supabase/schema.md)를 참고합니다.

## FastAPI

FastAPI는 공지 수집, 문서 분석, Gemini AI/OCR 호출, 번역 처리, NEIS API 연동, Google Calendar 연동처럼 Next.js 화면 서버와 분리하는 편이 좋은 서버 로직을 담당합니다.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

자세한 내용은 [FastAPI Service](docs/backend/fastapi.md)를 참고합니다.

## CI/CD

이 프로젝트는 Docker, GitHub Actions, Google Cloud Run 기반 배포를 기준으로 구성합니다.

자세한 구축 phase는 [Next.js CI/CD 구축 Phase](docs/ci-cd-phases.md)를 참고합니다.

주요 파일:

- `Dockerfile`
- `backend/Dockerfile`
- `.dockerignore`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy-cloud-run.yml`
- `.github/workflows/deploy-api-cloud-run.yml`

## 프로젝트 문서

- [Supabase Schema](docs/supabase/schema.md)
- [FastAPI Service](docs/backend/fastapi.md)
- [Agent Workflow](docs/agent-workflow.md)

## 라이선스

추후 작성 예정입니다.
