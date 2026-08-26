# 준비물 — 권한 · 자격증명 · 도구

기준일: 2026-08-26
용도: 구현 착수 전 사람이 미리 준비해야 할 것. 서브에이전트가 여기서 막히지 않도록 선행 확보한다.

---

## 0. 지금 이미 되는 것 (확인 완료)

| 항목 | 상태 | 확인 방법 |
|---|---|---|
| `gcloud` 인증 | ✅ `hyu.naranhi@gmail.com` / `project-ca37fa7b-7c0b-46da-bba` | `gcloud config list account` |
| GCP Cloud Run · Scheduler · Secret Manager 조회 | ✅ | `gcloud run services list`, `gcloud scheduler jobs list` |
| GCP Cloud Monitoring (사용량·비용 산출) | ✅ | Monitoring API v3 timeSeries |
| `gh` 인증 | ✅ `seokjoon1127`, scopes `gist, read:org, repo` | `gh auth status` |
| GitHub 저장소 변수 조회 | ✅ | `gh variable get NEXT_PUBLIC_SUPABASE_URL` |
| Supabase service_role 키 | ✅ GCP Secret Manager `supabase-service-role-key` | 운영 DB 읽기 검증 완료 |
| **AWS 자격증명** | ✅ `arn:aws:iam::554608989606:user/david` | `aws sts get-caller-identity` |
| **AWS IAM 권한** | ✅ **AdministratorAccess** | `aws iam list-attached-user-policies` |
| Node · npm · docker · python | ✅ | — |
| `supabase` CLI 설치 | ✅ v2.100.1 | `supabase --version` |

> AWS 권한이 AdministratorAccess라 **IAM 정책 때문에 막힐 일은 없다.**

---

## 1. 🔴 즉시 막히는 것 — 착수 전 반드시 해결

### 1-1. AWS CLI가 너무 낡았다 — Bedrock 명령 자체가 없다

```
현재: aws-cli/2.6.4  (2022년 빌드)
필요: 2.15 이상
```

`aws bedrock`, `aws bedrock-runtime` 서브커맨드가 **존재하지 않는다.**
사업 B(Bedrock 이전)는 이걸 고치기 전엔 한 줄도 못 나간다.

**조치**: [AWS CLI v2 최신 설치 관리자](https://awscli.amazonaws.com/AWSCLIV2.msi) 실행.
기존 설정(`~/.aws/credentials`)은 그대로 유지된다.

**확인**: `aws --version` 이 2.15 이상, `aws bedrock help` 가 동작.

### 1-2. Supabase CLI가 로그인되어 있지 않다

```
supabase projects list  →  access token 오류
```

사업 A4(DB 배포 자동화)의 이력 정합에 필요하다.

**조치**:
1. https://supabase.com/dashboard/account/tokens → **Generate new token**
2. `supabase login` 실행 후 토큰 붙여넣기

> ⚠️ 토큰 값을 대화창에 붙여넣지 말 것. 터미널에서 직접 입력한다.

---

## 2. 사업 A — 보안 · 인증 · 배포

### 2-1. GitHub 시크릿 3개 (사용자 직접 등록)

| 이름 | 종류 | 어디서 얻나 |
|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | Secret | Supabase → 계정 → Access Tokens (1-2와 같은 토큰 재사용 가능) |
| `SUPABASE_DB_PASSWORD` | Secret | Supabase → Project Settings → Database → Database password (분실 시 Reset) |
| `SUPABASE_PROJECT_REF` | **Variable** (공개값) | Project Settings → General → Reference ID |

**등록 방법 — 값이 화면에 남지 않는 방식 둘 중 하나:**

```bash
# (a) 웹 UI — 가장 간단
# GitHub → 저장소 → Settings → Secrets and variables → Actions → New repository secret

# (b) 임시 파일 경유 (명령줄 인자에 키를 넣지 않는다)
#   1. 메모장으로 토큰만 한 줄 적어 저장  →  C:\temp\t.txt
#   2. gh secret set SUPABASE_ACCESS_TOKEN < C:\temp\t.txt
#   3. del C:\temp\t.txt
```

### 2-2. 구글 로그인 설정 확인 (사용자 직접)

코드는 이미 구현되어 있다(`app/(auth)/login/actions.ts:22`). 남은 건 설정이다.

| 확인할 곳 | 봐야 할 것 |
|---|---|
| Supabase → Authentication → Providers → **Google** | 활성화되어 있는가. Client ID / Secret 이 들어 있는가 |
| Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → OAuth 2.0 클라이언트 | **승인된 리디렉션 URI**에 `https://<project-ref>.supabase.co/auth/v1/callback` 이 있는가 |
| 같은 화면 | **승인된 JavaScript 원본**에 프로덕션 웹 URL이 있는가 |

> 프로덕션 웹 URL: `https://naranhi-web-140086900496.asia-northeast3.run.app`
> 커스텀 도메인을 붙일 계획이면 그때 다시 등록해야 한다.

### 2-3. Supabase 세션 만료 — **확인만, 조치 불필요 예상**

"14일 자동 로그인"은 두 층으로 나뉜다.

| 층 | 값 | 바꾸는 곳 |
|---|---|---|
| 브라우저 쿠키 만료 | 14일 | **코드** (`@supabase/ssr` 쿠키 `maxAge`) — 구현에서 처리 |
| refresh token 수명 | 기본 무제한(회전형) | Supabase → Authentication → Sessions |

Supabase 기본값은 refresh token에 시간 제한(time-box)이 **없다.**
따라서 쿠키 만료만 14일로 잡으면 목표가 달성된다.

**확인만 해달라**: Authentication → Sessions 에 "Time-box user sessions" 같은 항목이
켜져 있고 14일보다 짧으면 알려줄 것. 꺼져 있으면 조치 불필요.

---

## 3. 사업 B — Bedrock 이전

### 3-1. 🔴 Bedrock 모델 액세스 신청 — **가장 오래 걸리는 항목**

Bedrock은 계정이 있다고 모델을 바로 못 쓴다. **모델마다 액세스를 신청**해야 하고,
일부는 사용 목적 양식을 요구하며 승인에 시간이 걸린다.

**조치**: AWS 콘솔 → Bedrock → **Model access** → Manage model access →
평가 후보를 전부 체크 후 요청.

신청할 후보 (사용자가 Claude 포함을 명시 승인함):

| 제공사 | 모델 | 용도 |
|---|---|---|
| Anthropic | Claude (최신 Sonnet 계열) | 번역 · 문서판독 |
| Amazon | Nova Lite / Nova Pro | 번역 · 문서판독 (멀티모달) |
| Meta | Llama (최신) | 번역 비교군 |
| Mistral | Large / Pixtral | 번역 · 판독 비교군 |
| Alibaba | Qwen VL 계열 (있으면) | **한국어 문서판독 유력 후보** |

> 액세스 승인 여부는 CLI 업그레이드 후 `aws bedrock list-foundation-models` 로 확인한다.

### 3-2. 리전 결정

- 서울(`ap-northeast-2`)에 모든 모델이 있지는 않다. 일부는 **크로스리전 추론 프로필**로만 도달한다.
- 크로스리전은 요청이 APAC 밖으로 갈 수 있다 → 학교 공지에 개인정보가 섞일 가능성이 있어 판단 필요.
- CLI 업그레이드 후 `aws bedrock list-inference-profiles --region ap-northeast-2` 로 실제 목록을 확인한 뒤 결정한다.

### 3-3. AWS 크레딧 잔액·만료일 (사용자 확인)

AWS 콘솔 → Billing and Cost Management → **Credits**.

| 확인할 것 | 왜 |
|---|---|
| 잔액 | 야심의 크기를 정한다 |
| 만료일 | 일정 압박이 있는지 |
| 적용 가능 서비스 | Bedrock 서드파티 모델은 Activate 약관에 **명문 예외**로 적용 가능. Amazon Nova는 네이티브라 당연히 적용 |

### 3-4. 백엔드가 쓸 AWS 자격증명

Cloud Run에서 Bedrock을 호출하려면 컨테이너 안에 AWS 자격증명이 필요하다.

- **권장**: Bedrock 호출만 가능한 **전용 IAM 사용자**를 새로 만든다
  (`bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` 만).
  지금 쓰는 AdministratorAccess 키를 서버에 넣지 않는다.
- 액세스 키/시크릿은 **GCP Secret Manager**에 넣고 Cloud Run에 `--set-secrets` 로 주입한다
  (기존 `gemini-api-key` 와 같은 방식).

> 이 IAM 사용자 생성은 제가 할 수 있다(AdministratorAccess 보유). 승인만 주면 된다.

---

## 4. 사업 C — 추출 수리 · 크롤 재가동

| 항목 | 상태 |
|---|---|
| Cloud Scheduler resume 권한 | ✅ 있음 |
| Cloud Run Job env 수정 | ✅ 있음 |
| 크롤 워터마크 컷오프 (DB 쓰기) | ✅ service_role 보유 |

**사용자 결정 필요**: 재가동 시점. 사용자 방침은 "밀린 것 말고 지금부터 새로 오는 것만"이므로
워터마크를 현재 시각으로 리셋한 뒤 켠다.

---

## 5. 사업 E — RSS · 교육부 공식 API

| 항목 | 상태 |
|---|---|
| NEIS API 키 | ✅ 있음 (`neis-api-key`). 학사일정·급식도 **같은 키**로 호출 가능 |
| NEIS 일일 호출 한도 | ⚠️ 공식 미공개. 초과 시 `ERROR-337`. 실사용에서 관측 필요 |
| 교육청 RSS | ✅ 인증 불필요. 무인증 GET으로 동작 확인 완료 (경북·전북) |

추가 준비물 없음.

---

## 6. 사업 F — 관리자 페이지

**사용자 결정 필요** (구현 착수 전):

1. 관리자가 **몇 명**인가
2. 계정을 어디에 두는가 — Supabase Auth의 별도 사용자 / 환경변수 고정 계정 / 별도 테이블
3. 접근 경로 — `/admin` 같은 하위 경로 / 별도 도메인
4. 학교 관계자에게도 권한을 주는가 (준다면 학교 범위 제한이 필요)

> `profiles.role` 컬럼과 `user_role` enum 은 `0012` 에서 삭제됐다. 되살리는 마이그레이션이 필요하다.

---

## 7. 착수 전 체크리스트

```
[ ] AWS CLI 2.15+ 로 업그레이드          → aws bedrock help 동작
[ ] supabase login                        → supabase projects list 동작
[ ] Bedrock Model access 신청 (5종)       → 승인 대기 시작 (제일 오래 걸림)
[ ] GitHub Secret 2개 + Variable 1개 등록
[ ] Supabase Google Provider 활성 확인
[ ] Google OAuth 리디렉션 URI 등록 확인
[ ] Supabase Sessions time-box 설정 확인
[ ] AWS 크레딧 잔액·만료일 확인
[ ] 관리자 계정 정책 결정 (사업 F 착수 전까지)
```

**셋만 먼저 해도 사업 A는 시작된다** — `supabase login`, GitHub 시크릿 3개, 구글 OAuth 설정 확인.
Bedrock 항목은 사업 B 착수 전까지만 되면 되지만, **모델 액세스 승인이 오래 걸릴 수 있으니 지금 신청**하는 편이 좋다.
