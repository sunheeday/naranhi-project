# 학교(선생님) 어드민 백엔드

선생님용 어드민(`/admin`)의 백엔드 계층 문서입니다. **지금은 DB 없이 인메모리로 동작**하며, 나중에 Supabase만 붙이면 되도록 데이터 접근을 추상화해 두었습니다.

## 아키텍처

```
app/admin/*  (화면)
     │  useAdminData / useAdminActions
     ▼
lib/admin/store.ts        ── 클라이언트 스토어(구독 + 낙관적 업데이트)
     │  fetch
     ▼
lib/admin/api-client.ts   ── /api/admin/* 호출
     │  HTTP
     ▼
app/api/admin/*           ── 라우트 핸들러(zod 검증)
     │  getAdminRepository()
     ▼
lib/admin/backend/index.ts ── 팩토리 (ADMIN_BACKEND 로 구현 선택)
     ├── memory-repository.ts    (기본, DB 불필요)
     └── supabase-repository.ts  (연동용 레퍼런스)
```

핵심은 **Repository 인터페이스**(`lib/admin/backend/repository.ts`)입니다. 라우트 핸들러는 이 인터페이스에만 의존하므로, 저장소 구현을 바꿔도 API·화면 코드는 그대로입니다.

## 데이터 모델

프레임워크 중립 타입: `lib/admin/types.ts`

| 도메인 | 필드 |
|---|---|
| `AdminNotice` | id, title, body, category(`letter`\|`notice`\|`meal`\|`event`), audience(`all`\|`class`), pinned, createdAt |
| `AdminEvent` | id, title, date, time, type(`event`\|`exam`\|`deadline`\|`holiday`), audience, memo, createdAt |
| `AdminMessage` | id, title, body, audience, recipient, sentAt |

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/admin/overview` | 공지·일정·메시지 전체 스냅샷 |
| GET / POST | `/api/admin/notices` | 공지 목록 / 등록 |
| PATCH / DELETE | `/api/admin/notices/:id` | 상단 고정 토글 / 삭제 |
| GET / POST | `/api/admin/events` | 일정 목록 / 등록 |
| DELETE | `/api/admin/events/:id` | 일정 삭제 |
| GET / POST | `/api/admin/messages` | 메시지 목록 / 발송 |
| DELETE | `/api/admin/messages/:id` | 메시지 삭제 |
| POST | `/api/admin/reset` | 데모 데이터 초기화(인메모리 전용) |

응답 형식은 `{ ok: true, data }` 또는 `{ ok: false, error }`. 입력 검증은 `lib/admin/backend/validation.ts`(zod).

미들웨어에서 `/admin`, `/api/admin`을 공개 경로로 열어 두었습니다(`middleware.ts`). 실서비스에서는 **교사 인증/권한**으로 대체해야 합니다(아래 참고).

## 지금 동작 방식 (인메모리)

- 데이터는 서버 프로세스 메모리(`globalThis` 싱글턴)에 저장됩니다. 새로고침해도 유지되고, **서버를 재시작하면 시드 상태로 초기화**됩니다.
- 별도 설정 없이 `npm run dev`만으로 동작합니다.

## Supabase 연동 방법 (나중에)

### 1) 테이블 생성

`supabase/migrations/`에 아래 SQL을 새 마이그레이션으로 추가하고 `supabase db push`.

```sql
-- admin_notices
create table if not exists public.admin_notices (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null,
  category text not null default 'notice',
  audience text not null default 'class',
  pinned boolean not null default false,
  created_at timestamptz not null default now()
);

-- admin_events
create table if not exists public.admin_events (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  event_date date not null,
  event_time text,
  type text not null default 'event',
  audience text not null default 'class',
  memo text not null default '',
  created_at timestamptz not null default now()
);

-- admin_messages
create table if not exists public.admin_messages (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null,
  audience text not null default 'all',
  recipient text not null,
  sent_at timestamptz not null default now()
);
```

> 참고: 선생님이 올린 공지/일정을 **학부모 앱에 그대로 노출**하고 싶다면, `admin_*` 테이블 대신
> 기존 `notices` / `school_events` 테이블에 쓰도록 `supabase-repository.ts`의 매퍼를 조정하면 됩니다.
> 그 경우 `notices.school_id`(필수), `school_events.notice_id`(필수 FK) 등 기존 제약을 함께 처리해야 합니다.

### 2) 환경변수

```env
ADMIN_BACKEND=supabase
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

### 3) (권장) 타입 재생성

```bash
supabase gen types typescript --project-id <ref> > types/database.ts
```

`supabase-repository.ts`는 타입 재생성 전에도 컴파일되도록 언타입 클라이언트를 사용합니다. 연동 후 타입을 재생성하면 타입 안전성을 높일 수 있습니다.

### 4) 서버 재시작

라우트 핸들러·화면은 수정하지 않아도 됩니다. 팩토리가 `SupabaseAdminRepository`를 선택합니다.

## 실서비스 전 체크리스트

- [ ] 교사 인증/권한: `/admin`, `/api/admin`을 공개에서 제외하고 교사 세션·학급 권한 검사 추가
- [ ] `audience: 'class'`가 실제 담당 학급을 참조하도록 교사→학급 매핑 연결
- [ ] 메시지 발송 시 기존 번역 파이프라인(Gemini) 연동으로 학부모 언어 자동 번역
- [ ] `admin_*` 테이블 RLS 정책 추가
