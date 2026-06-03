# Iter-001 Resume Checkpoint

## 현재 상태 (2026-06-02 시점)

### 완료된 것
- 에이전트 명세, 평가 rubric, language-criteria 전부 정비 (north star + stopping criteria 반영)
- 팀 생성: `translation-quality` (team-lead만, evaluator/engineer 미스폰)
- 6개 통신문 한국어 원문 저장 + manifest.json 생성
- 분할: training 4 (n01, n02, n05, n06) / held-out 2 (n03, n04)
- Python venv (.venv, Python 3.11) + 의존성 설치 완료
- driver / run_iteration 스크립트 작성 완료

### 파이프라인 실행 결과
- ✅ 성공 5개: `n01-bike-safety` (en/ru/ar), `n02-field-trip-consent` (en/ru)
- ❌ 실패 13개: 전부 `429 RESOURCE_EXHAUSTED — monthly spending cap` 도달
  - n02 ar
  - n03~n06 전부 (12개)

### 인증 상태
- `backend/.env`: GEMINI_API_KEY 설정됨 (cap 초과 상태), Vertex 라인 주석 처리됨
- gcloud CLI: 설치 중단됨 — 원인은 libexpat 미스매치로 homebrew Python pyexpat 로드 실패
  - Python 3.13, 3.14 둘 다 영향
  - 증상: `Symbol not found: _XML_SetAllocTrackerActivationThreshold`

## 재시작 후 진행할 길 3가지

### A. Vertex 길 계속 (libexpat 고친 후)

재부팅으로 dyld 캐시가 살아나면 그대로 될 수도 있음. 안 되면 brew 재설치:

```bash
brew reinstall expat
brew reinstall python@3.13
# 그다음 virtualenv 설치 + gcloud cask 설치
/opt/homebrew/opt/python@3.13/libexec/bin/python -m pip install virtualenv --break-system-packages
brew install --cask gcloud-cli
# 그다음 로그인
gcloud auth application-default login
# 그다음 .env에서 VERTEX_AI_PROJECT_ID 주석 해제
```

### B. AI Studio cap 올리기 (가장 빠른 길)

https://ai.studio/spend 에서 한도 상향. Flash 모델은 18회 실행에 보통 $1 미만. 즉시 검증됨.

### C. 새 API 키 발급

다른 GCP 프로젝트의 새 API 키를 받아서 `backend/.env`의 GEMINI_API_KEY 교체. 같은 결제 계정이면 한도 공유 가능성 있음.

## 재시작 후 첫 명령

선택지를 정한 후 Claude에게 다음 중 하나로 알려주세요:

- "Vertex 다시 시도" — 위 A 경로 진행
- "AI Studio cap 올렸다, 이어서 가자" — 13개만 재실행
- "새 API 키 줄게: AIza..." — 키 교체 후 13개 재실행

## 재실행 시 명령 (참고용)

성공한 5개는 건드리지 않고 실패한 13개만 다시 돌리는 명령:

```bash
.venv/bin/python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-06-01_iter-001/ \
  --only n02-field-trip-consent,n03-parent-edu-program,n04-college-info-session,n05-reporter-recruit,n06-health-class \
  --langs ar
.venv/bin/python scripts/run_iteration.py \
  --iter .agents/translation-quality/iterations/2026-06-01_iter-001/ \
  --only n03-parent-edu-program,n04-college-info-session,n05-reporter-recruit,n06-health-class \
  --langs en,ru
```

(driver는 lang 단위가 아닌 notice 단위라서 두 번 나눠 돔. n02는 ar만 재실행 필요.)

## 폴더 위치

```
.agents/translation-quality/iterations/2026-06-01_iter-001/
├── manifest.json
├── _resume.md  ← 본 문서
├── notices/
│   ├── training/
│   │   ├── n01-bike-safety/        ← 모든 lang 완료
│   │   ├── n02-field-trip-consent/ ← en, ru 완료, ar 실패
│   │   ├── n05-reporter-recruit/   ← 전부 실패
│   │   └── n06-health-class/       ← 전부 실패
│   └── held-out/
│       ├── n03-parent-edu-program/    ← 전부 실패
│       └── n04-college-info-session/  ← 전부 실패
├── evaluation/                ← 비어 있음
├── engineering/               ← 비어 있음
└── pipeline-output-after/     ← 비어 있음
```
