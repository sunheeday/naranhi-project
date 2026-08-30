# 사업 G — 시간표 시각화 · 방과후 일정 · 알림 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 학부모가 자녀의 하루 전체(학교 수업 + 방과후)를 시각과 함께 한 화면에서 보고, 하교·방과후·마감 알림을 자기 언어로 받게 한다.

**Architecture:** 학교별 교시 시각표를 새 테이블에 두고(홈페이지 자동 수집 + 표준값 2경로, 관리자 승인 필수), NEIS 가 주는 «그날 마지막 교시»와 결합해 하교 시각을 계산한다. 방과후는 부모가 요일 기반으로 등록한다. 알림은 매일 새벽 계획을 outbox 에 적재하고 5분마다 웹 푸시로 발송하는 2단 구조다.

**Tech Stack:** Next.js 16 App Router · Supabase(Postgres/RLS) · Python 3.12 FastAPI · Cloud Run Jobs + Cloud Scheduler · Vertex AI Gemini 2.5 Flash · Web Push(VAPID) · `pywebpush`

**Spec:** [docs/superpowers/specs/2026-08-30-G-timetable-notifications-design.md](../specs/2026-08-30-G-timetable-notifications-design.md)

## Global Constraints

- **마이그레이션 번호는 0048 부터.** 현재 최대는 `0047_low_risk_hygiene.sql`.
  (기존 `기능명세서-자녀-개인일정.md` 가 0035 라고 적은 것은 문서 작성 시점 기준이며 **무효**다.)
- **`SUPABASE_DB_PASSWORD` 를 저장소·GitHub 환경 어디에도 추가하지 않는다.** 추가하면 이미 수동 적용된 0038–0047 이 재적용된다.
- **번역 API 를 알림에 쓰지 않는다.** 알림 문구는 `messages/*.json` 9개 언어 고정 문구 + 파라미터 치환이다.
- **지원 언어 9개**: `ko en zh vi ru ar fr id th`. 키를 하나라도 빠뜨리면 그 언어에서 `undefined` 가 렌더된다.
- **시간대는 KST 고정.** `time` 타입은 timezone 을 갖지 않는다. 앱 전체 관례와 같다.
- **부모는 `school_bell_schedules` 를 수정할 수 없다.** 학교 공용 데이터다. 부모 보정은 `children.bell_offset_minutes` 로만 한다.
- **`confirmed_at is null` 인 일과표는 화면·알림 어디에서도 쓰지 않는다.**
- **하교 시각은 항상 «쯤» 을 붙인다.** 추정값이다.
- 서버 액션(`'use server'`) + `revalidatePath` 가 프로젝트 표준이다. 새 API route 를 만들지 않는다(관리자 API 는 예외 — 기존 `/admin/*` 패턴을 따른다).
- Python 잡은 `backend/app/jobs/` 아래, 기존 `translation_worker.py` 의 인자·로깅·종료코드 관례를 따른다.
- 검증은 프로젝트 CLAUDE.md 의 2-에이전트 워크플로를 따른다(개발 → 독립 검증).

---

# Phase 1 — 교시 시각 (알림 없이도 값어치가 있다)

### Task 1: 교시 시각 테이블 + 자녀 보정 컬럼

**Files:**
- Create: `supabase/migrations/0048_school_bell_schedules.sql`
- Modify: `types/database.ts`

**Interfaces:**
- Produces: 테이블 `public.school_bell_schedules`, 컬럼 `public.children.bell_offset_minutes`

- [ ] **Step 1: 마이그레이션 작성**

```sql
-- 학교별 교시 시각표. 한 교시가 한 행.
-- 파라미터(시작+길이+휴식)로 계산하지 않는 이유: 실측 일과표가 규칙적이지 않다.
-- 부천부흥중은 점심 직후 5교시가 쉬는 시간 0분으로 이어지고, 5→6→7 은 10분씩 쉰다.
create table if not exists public.school_bell_schedules (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id) on delete cascade,
  period smallint not null check (period between 1 and 12),
  start_time time not null,
  end_time time not null,
  -- 'default' = 학교급 표준값, 'homepage' = 홈페이지 일과표에서 수집, 'manual' = 관리자 입력
  source text not null default 'default' check (source in ('default', 'homepage', 'manual')),
  source_url text,
  -- 관리자 승인 시각. null 이면 화면·알림 어디에서도 쓰지 않는다.
  confirmed_at timestamptz,
  confirmed_by uuid references public.admin_users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (start_time < end_time),
  unique (school_id, period)
);

create index if not exists school_bell_schedules_school_idx
  on public.school_bell_schedules (school_id, period);

drop trigger if exists school_bell_schedules_set_updated_at on public.school_bell_schedules;
create trigger school_bell_schedules_set_updated_at
before update on public.school_bell_schedules
for each row execute function public.set_updated_at();

-- 부모는 읽기만. 쓰기는 service_role 만(관리자 콘솔 경유).
alter table public.school_bell_schedules enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'school_bell_schedules'
      and policyname = 'bell schedules select own school'
  ) then
    create policy "bell schedules select own school"
    on public.school_bell_schedules for select
    using (
      exists (
        select 1 from public.children
        where children.school_id = school_bell_schedules.school_id
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;

-- 자녀별 시각 보정(분). 부모가 «우리 학교는 8시 50분에 시작해요» 하면 -10.
-- 학교 공용 데이터를 건드리지 않고 그 자녀에게만 적용된다.
alter table public.children
  add column if not exists bell_offset_minutes smallint not null default 0;

alter table public.children
  drop constraint if exists children_bell_offset_range;
alter table public.children
  add constraint children_bell_offset_range
  check (bell_offset_minutes between -120 and 120);
```

- [ ] **Step 2: 로컬 적용 후 재실행해 멱등성 확인**

Run: 같은 파일을 두 번 실행.
Expected: 두 번째도 오류 없이 통과.

- [ ] **Step 3: `types/database.ts` 에 타입 추가**

`school_bell_schedules` 의 Row/Insert/Update 와 `children.bell_offset_minutes: number` 를 추가한다.

- [ ] **Step 4: 커밋**

```bash
git add supabase/migrations/0048_school_bell_schedules.sql types/database.ts
git commit -m "feat(G1): 학교별 교시 시각표 테이블 + 자녀 시각 보정 컬럼"
```

---

### Task 2: 표준값과 하교 시각 계산

**Files:**
- Create: `lib/bell-schedule.ts`
- Create: `__tests__/bell-schedule.test.ts` (없으면 프로젝트의 테스트 관례를 먼저 확인)

**Interfaces:**
- Produces:
  - `defaultBellSchedule(schoolName: string): BellPeriod[]`
  - `resolveDismissal(periods: BellPeriod[], lastPeriod: number, offsetMinutes: number): string | null`
  - `applyOffset(periods: BellPeriod[], offsetMinutes: number): BellPeriod[]`
  - `interface BellPeriod { period: number; startTime: string; endTime: string }` — `"HH:MM"`

- [ ] **Step 1: 실패하는 테스트 먼저 작성**

```ts
// 부천부흥중 실측 일과표(2026학년도)로 검증한다.
const PCBUHEUNG: BellPeriod[] = [
  { period: 1, startTime: '09:10', endTime: '09:55' },
  { period: 2, startTime: '10:05', endTime: '10:50' },
  { period: 3, startTime: '11:00', endTime: '11:45' },
  { period: 4, startTime: '11:55', endTime: '12:40' },
  { period: 5, startTime: '13:30', endTime: '14:15' },
  { period: 6, startTime: '14:25', endTime: '15:10' },
  { period: 7, startTime: '15:20', endTime: '16:05' },
]

test('6교시 날 하교는 종례 10분 뒤', () => {
  expect(resolveDismissal(PCBUHEUNG, 6, 0)).toBe('15:20')
})

test('7교시 날 하교', () => {
  expect(resolveDismissal(PCBUHEUNG, 7, 0)).toBe('16:15')
})

test('보정 -10분이 반영된다', () => {
  expect(resolveDismissal(PCBUHEUNG, 6, -10)).toBe('15:10')
})

test('해당 교시가 표에 없으면 null', () => {
  expect(resolveDismissal(PCBUHEUNG, 9, 0)).toBeNull()
})

test('초등 표준값은 1교시 09:00, 40분 수업', () => {
  const p = defaultBellSchedule('인천문남초등학교')
  expect(p[0]).toEqual({ period: 1, startTime: '09:00', endTime: '09:40' })
  expect(p[1].startTime).toBe('09:50')
})

test('초등 표준값은 4교시 뒤 점심 50분', () => {
  const p = defaultBellSchedule('인천문남초등학교')
  expect(p[3].endTime).toBe('12:20')   // 4교시 끝
  expect(p[4].startTime).toBe('13:10') // 5교시 = 점심 50분 뒤
})
```

- [ ] **Step 2: 실패 확인**

Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현**

```ts
export interface BellPeriod {
  period: number
  startTime: string   // "HH:MM"
  endTime: string     // "HH:MM"
}

/** 종례에 걸리는 시간. 학교마다 다르므로 상수로 두고 표시할 때 "쯤"을 붙인다. */
const HOMEROOM_MINUTES = 10

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function toHHMM(total: number): string {
  const wrapped = ((total % 1440) + 1440) % 1440
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** 학교급 표준값. lib/neis.ts 가 학교명으로 학교급을 가르는 것과 같은 규칙을 쓴다. */
export function defaultBellSchedule(schoolName: string): BellPeriod[] {
  const name = schoolName ?? ''
  const spec = name.includes('고등')
    ? { start: '08:50', lesson: 50, brk: 10, lunchAfter: 4, lunch: 60, count: 7 }
    : name.includes('중학')
      ? { start: '09:10', lesson: 45, brk: 10, lunchAfter: 4, lunch: 50, count: 7 }
      : { start: '09:00', lesson: 40, brk: 10, lunchAfter: 4, lunch: 50, count: 6 }

  const periods: BellPeriod[] = []
  let cursor = toMinutes(spec.start)
  for (let p = 1; p <= spec.count; p++) {
    const startTime = toHHMM(cursor)
    cursor += spec.lesson
    periods.push({ period: p, startTime, endTime: toHHMM(cursor) })
    cursor += p === spec.lunchAfter ? spec.lunch : spec.brk
  }
  return periods
}

export function applyOffset(periods: BellPeriod[], offsetMinutes: number): BellPeriod[] {
  if (!offsetMinutes) return periods
  return periods.map(p => ({
    period: p.period,
    startTime: toHHMM(toMinutes(p.startTime) + offsetMinutes),
    endTime: toHHMM(toMinutes(p.endTime) + offsetMinutes),
  }))
}

/** 하교 시각(추정) = 그날 마지막 교시의 끝 + 종례. 표에 없으면 null. */
export function resolveDismissal(
  periods: BellPeriod[],
  lastPeriod: number,
  offsetMinutes: number,
): string | null {
  const found = periods.find(p => p.period === lastPeriod)
  if (!found) return null
  return toHHMM(toMinutes(found.endTime) + offsetMinutes + HOMEROOM_MINUTES)
}
```

- [ ] **Step 4: 테스트 통과 확인**

- [ ] **Step 5: 커밋**

```bash
git add lib/bell-schedule.ts __tests__/bell-schedule.test.ts
git commit -m "feat(G1): 학교급 표준 교시 시각 + 하교 시각 계산"
```

---

### Task 3: 학교 등록 시 표준값 자동 삽입

**Files:**
- Modify: `lib/schedule-backfill.ts` 또는 학교가 처음 쓰이는 지점 (구현 전 실제 위치 확인)
- Create: `lib/bell-schedule-store.ts`

**Interfaces:**
- Consumes: Task 2 의 `defaultBellSchedule`
- Produces: `ensureBellSchedule(serviceClient, schoolId, schoolName): Promise<BellPeriod[]>`

- [ ] **Step 1: 조회 + 없으면 표준값 시딩하는 헬퍼 작성**

```ts
/** 승인된 일과표가 있으면 그것을, 없으면 표준값을 돌려준다.
 *  표준값은 이 학교에 행이 아예 없을 때만 심는다(source='default', confirmed_at=now()).
 *  표준값은 «추정이지만 즉시 쓸 수 있는» 값이므로 승인 상태로 넣는다.
 *  홈페이지 수집분(source='homepage')만 사람 승인을 기다린다. */
export async function ensureBellSchedule(
  service: SupabaseClient<Database>,
  schoolId: string,
  schoolName: string,
): Promise<BellPeriod[]> {
  const { data, error } = await service
    .from('school_bell_schedules')
    .select('period, start_time, end_time')
    .eq('school_id', schoolId)
    .not('confirmed_at', 'is', null)
    .order('period')
  if (error) throw error

  if ((data ?? []).length > 0) {
    return (data ?? []).map(r => ({
      period: r.period,
      startTime: r.start_time.slice(0, 5),
      endTime: r.end_time.slice(0, 5),
    }))
  }

  const periods = defaultBellSchedule(schoolName)
  // 경쟁 삽입에 대비해 충돌은 무시한다 — 먼저 넣은 쪽이 이긴다.
  await service.from('school_bell_schedules').upsert(
    periods.map(p => ({
      school_id: schoolId,
      period: p.period,
      start_time: p.startTime,
      end_time: p.endTime,
      source: 'default' as const,
      confirmed_at: new Date().toISOString(),
    })),
    { onConflict: 'school_id,period', ignoreDuplicates: true },
  )
  return periods
}
```

- [ ] **Step 2: 테스트 — 두 번 호출해도 행이 중복되지 않음**

- [ ] **Step 3: 커밋**

---

### Task 4: 시간표 화면에 시각과 하교 표시

**Files:**
- Modify: `app/(app)/calendar/page.tsx`
- Modify: `app/(app)/calendar/TimetableWeekView.tsx`
- Modify: `app/(app)/calendar/CalendarTabs.tsx`
- Modify: `messages/*.json` (9개)

**Interfaces:**
- Consumes: Task 2/3
- Produces: `TimetableDayEntry` 에 `dismissalTime?: string | null` 추가, `TimetablePeriod` 표시에 시각 병기

- [ ] **Step 1: `page.tsx` 에서 일과표 조회 후 각 요일의 하교 시각 계산**

```ts
// child 확보 후, NEIS 시간표 조회 성공 분기 안에서
const bellPeriods = applyOffset(
  await ensureBellSchedule(createSupabaseServiceClient(), child.school_id, child.school_name),
  child.bell_offset_minutes ?? 0,
)

// buildTimetableDays 결과에 붙인다
function attachTimes(days: TimetableDayEntry[], bell: BellPeriod[], offset: number) {
  const byPeriod = new Map(bell.map(p => [p.period, p]))
  return days.map(day => {
    const last = day.periods.length
      ? Math.max(...day.periods.map(p => p.period))
      : 0
    return {
      ...day,
      periods: day.periods.map(p => ({
        ...p,
        startTime: byPeriod.get(p.period)?.startTime ?? null,
        endTime: byPeriod.get(p.period)?.endTime ?? null,
      })),
      dismissalTime: last ? resolveDismissal(bell, last, 0) : null,
    }
  })
}
```

> `applyOffset` 을 이미 적용했으므로 `resolveDismissal` 의 offset 인자는 0 이다.
> 두 번 더하지 않도록 주의한다.

- [ ] **Step 2: `TimetableWeekView` 의 교시 줄에 시각 병기**

```tsx
<span className="text-xs font-bold text-muted pt-0.5">
  {period.startTime
    ? `${period.startTime}`
    : labels.periodSuffix.replace('{period}', String(period.period))}
</span>
```

시각을 모르면 기존 `N교시` 로 자연스럽게 되돌아간다(하위 호환).

- [ ] **Step 3: 요일 카드 하단에 하교 표시**

```tsx
{day.dismissalTime && (
  <p className="mt-3 pt-3 border-t border-hairline-soft text-sm font-semibold text-text-secondary">
    {labels.dismissal.replace('{time}', day.dismissalTime)}
  </p>
)}
```

- [ ] **Step 4: i18n 9개 언어에 `calendar.dismissal` 추가**

```json
"dismissal": "하교 {time}쯤"
```
(en: `"Home around {time}"`, vi: `"Tan học khoảng {time}"`, …)

- [ ] **Step 5: `npm run build && npm run typecheck` 통과 확인**

> 순서 주의: `typecheck` 가 `build` 가 만드는 `.next/types/validator.ts` 에 의존한다.

- [ ] **Step 6: 커밋**

---

### Task 5: 부모가 1교시 시작 시각을 고치는 화면

**Files:**
- Modify: `app/(app)/settings/page.tsx`
- Create: `app/(app)/settings/BellOffsetForm.tsx`
- Modify: `app/(app)/settings/actions.ts` (없으면 생성)
- Modify: `messages/*.json` (9개)

**Interfaces:**
- Produces: 서버 액션 `updateBellOffset({ childId, firstPeriodStart }): Promise<void>`

- [ ] **Step 1: 서버 액션**

```ts
'use server'

/** 부모는 «1교시 시작 시각» 하나만 고친다. 표 전체를 채우게 하면 아무도 안 한다.
 *  받은 값과 학교 기준 1교시 시작의 차이를 분으로 환산해 children 에 저장한다. */
export async function updateBellOffset(input: { childId: string; firstPeriodStart: string }) {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error('로그인이 필요해요.')

  if (!/^\d{2}:\d{2}$/.test(input.firstPeriodStart)) throw new Error('시간 형식이 올바르지 않아요.')

  const { data: child } = await supabase
    .from('children').select('id, school_id, school_name')
    .eq('id', input.childId).eq('user_id', user.id).maybeSingle()
  if (!child?.school_id) throw new Error('권한이 없어요.')

  const base = await ensureBellSchedule(
    createSupabaseServiceClient(), child.school_id, child.school_name,
  )
  const baseStart = base[0]?.startTime
  if (!baseStart) throw new Error('학교 시간표가 아직 없어요.')

  const offset = toMinutes(input.firstPeriodStart) - toMinutes(baseStart)
  if (offset < -120 || offset > 120) throw new Error('시간이 너무 많이 차이나요.')

  const { error } = await supabase
    .from('children').update({ bell_offset_minutes: offset })
    .eq('id', input.childId).eq('user_id', user.id)
  if (error) throw new Error('저장에 실패했어요.')
  revalidatePath('/calendar')
  revalidatePath('/settings')
}
```

- [ ] **Step 2: 설정 화면에 `<input type="time">` 한 칸 + 안내 문구**

문구: "우리 학교 1교시가 몇 시에 시작하나요? 나머지 시간은 자동으로 맞춰집니다."

- [ ] **Step 3: i18n 9개 언어**

- [ ] **Step 4: 실제 로그인으로 저장 → 캘린더 반영 확인**

- [ ] **Step 5: 커밋**

---

# Phase 2 — 방과후 개인 일정

> [기능명세서-자녀-개인일정.md](../../기능명세서-자녀-개인일정.md) 를 **그대로 따른다.**
> 그 문서의 §5~§13 이 이 Phase 의 상세 명세다. 아래는 그 문서와 달라진 점만 적는다.

### Task 6: 개인 일정 테이블

**Files:**
- Create: `supabase/migrations/0049_child_personal_schedules.sql`
- Modify: `types/database.ts`

**변경점:** 명세서가 `0035` 라고 적었으나 **`0049` 로 한다.** 그 외 DDL·RLS·인덱스·트리거는 명세서 §5.1 을 그대로 쓴다.

- [ ] **Step 1:** 명세서 §5.1 의 SQL 을 `0049_child_personal_schedules.sql` 로 작성
- [ ] **Step 2:** 두 번 실행해 멱등성 확인
- [ ] **Step 3:** `types/database.ts` 에 명세서 §5.2 의 타입 추가
- [ ] **Step 4:** 커밋

---

### Task 7: 개인 일정 조회 + 주간 배치

**Files:**
- Create: `lib/child-personal-schedules.ts`
- Modify: `app/(app)/calendar/page.tsx`

명세서 §6 을 그대로 따른다. 핵심 두 가지를 반드시 지킨다.

- **시간표 미지원 학교에서도 조회한다.** NEIS 분기 «바깥»에서 한 번 조회해 두 분기 모두에 주입한다.
- **개인 일정 제목은 번역하지 않는다.** `translateTimetableDays` **뒤에** `attachPersonalItems` 를 호출한다.

- [ ] **Step 1:** `fetchPersonalSchedulesForChild` + `attachPersonalItems` 작성 (명세서 §6.2/§6.3)
- [ ] **Step 2:** `page.tsx` 배선
- [ ] **Step 3:** 테스트 바이패스 모드에서 목 데이터 표시 확인 (명세서 §11)
- [ ] **Step 4:** 커밋

---

### Task 8: 개인 일정 CRUD 서버 액션

**Files:**
- Create: `app/(app)/calendar/actions.ts`

명세서 §7 을 그대로 따른다. `create` 는 `child_id` 를 직접 받으므로 RLS 에 더해
`assertOwnsChild` 로 명시 교차검증까지 한다.

- [ ] **Step 1:** `createPersonalSchedule` + 검증 3중화
- [ ] **Step 2:** `updatePersonalSchedule` / `deletePersonalSchedule`
- [ ] **Step 3:** 타 자녀 `child_id` 위조가 차단되는지 테스트
- [ ] **Step 4:** 커밋

---

### Task 9: 개인 일정 입력 시트 + 카드 렌더

**Files:**
- Create: `app/(app)/calendar/PersonalScheduleSheet.tsx`
- Modify: `app/(app)/calendar/TimetableWeekView.tsx`
- Modify: `app/(app)/calendar/CalendarTabs.tsx`
- Modify: `messages/*.json` (9개)

명세서 §9(A안 = 카드 뷰 확장) + §10(i18n 키 목록) 을 그대로 따른다.

**빈 상태 조건을 반드시 함께 고친다:**
`periods.length === 0 && personalItems.length === 0` 일 때만 "수업 정보 없음".

- [ ] **Step 1:** `TimetableDayEntry` 에 `personalItems?` 추가 + 카드 하단 구획 렌더
- [ ] **Step 2:** 바텀시트 폼 (제목/요일/시작·종료/장소/메모/색상)
- [ ] **Step 3:** 명세서 §10 의 `personal_*` 키를 9개 언어 전부에 추가
- [ ] **Step 4:** 9개 파일 키 셋 diff 로 누락 0 확인
- [ ] **Step 5:** `npm run build && npm run typecheck`
- [ ] **Step 6:** 커밋

---

# Phase 3 — 홈페이지 일과표 수집

### Task 10: 일과표 페이지 탐색 + 그림 판독

**Files:**
- Create: `backend/app/crawler/bell_schedule_finder.py`
- Modify: `backend/app/crawler/gemini_finder.py`
- Create: `backend/tests/test_bell_schedule_finder.py`

**Interfaces:**
- Consumes: `HomepageClient.fetch`, `link_extractor.extract_links` (둘 다 기존)
- Produces:
  - `GeminiFinder.choose_bell_schedule_page(...) -> GeminiDecision`
  - `async def discover_bell_schedule(school_id, school_name, homepage_url) -> BellScheduleResult`
  - `@dataclass BellScheduleResult: periods: list[dict], source_url: str | None, confidence: float, note: str`

- [ ] **Step 1: 실패하는 테스트 먼저 — 부천부흥중 일과표 그림에서 7교시가 나와야 한다**

```python
def test_parses_pcbuheung_bell_image(monkeypatch):
    """실측 고정 응답으로 파싱만 검증한다(네트워크 없음)."""
    fake = {
        "periods": [
            {"period": 1, "start_time": "09:10", "end_time": "09:55"},
            {"period": 2, "start_time": "10:05", "end_time": "10:50"},
            {"period": 3, "start_time": "11:00", "end_time": "11:45"},
            {"period": 4, "start_time": "11:55", "end_time": "12:40"},
            {"period": 5, "start_time": "13:30", "end_time": "14:15"},
            {"period": 6, "start_time": "14:25", "end_time": "15:10"},
            {"period": 7, "start_time": "15:20", "end_time": "16:05"},
        ]
    }
    result = normalize_bell_periods(fake)
    assert len(result) == 7
    assert result[0]["start_time"] == "09:10"
    assert result[6]["end_time"] == "16:05"


def test_rejects_out_of_order_periods():
    """교시가 뒤죽박죽이면 통째로 버린다 — 반쯤 맞는 표가 제일 위험하다."""
    bad = {"periods": [
        {"period": 1, "start_time": "09:10", "end_time": "09:55"},
        {"period": 2, "start_time": "08:00", "end_time": "08:45"},
    ]}
    with pytest.raises(ValueError):
        normalize_bell_periods(bad)


def test_rejects_when_start_after_end():
    bad = {"periods": [{"period": 1, "start_time": "10:00", "end_time": "09:00"}]}
    with pytest.raises(ValueError):
        normalize_bell_periods(bad)
```

- [ ] **Step 2: 실패 확인**

- [ ] **Step 3: `GeminiFinder` 에 일과표 페이지 선택 메서드 추가**

`choose_notice_board` 와 같은 구조. 프롬프트만 바꾼다.

```python
PROMPT = """
너는 한국 학교 홈페이지에서 '일과표(시정표)' 페이지를 찾는 분류기다.

절대 규칙:
- 찾는 것은 «교시별 시작·종료 시각»이 적힌 페이지다.
  메뉴 이름은 보통 일과표 / 시정표 / 일과운영 / 등하교 시간 이다.
- '학사일정'(월별 행사)은 일과표가 아니다. 고르지 마라.
- '시간표'(과목 배치)도 일과표가 아니다. 고르지 마라.
- 캐러셀 제어 버튼('일시정지')은 링크가 아니다. 무시해라.
- 확실하지 않으면 best_url 을 null 로 두고 needs_human_check 를 true 로 둬라.
"""
```

> `일시정지` 배제를 명시하는 이유: 실측 조사에서 두 학교의 «시정» 매칭이 전부
> 캐러셀 일시정지 버튼이었다.

- [ ] **Step 4: 본문 판독 — 글 먼저, 없으면 그림**

```python
async def extract_bell_periods(page_html: str, page_url: str) -> BellScheduleResult:
    """일과표 페이지에서 교시별 시각을 뽑는다.

    실측: 일과표는 글이 아니라 그림으로 올라간다. 부천부흥중 페이지는 본문 1,782자에
    교시 0개였고, 시각 4개는 전부 교무실 전화 운영시간이었다. 그래서 글에서 «교시»가
    안 잡히면 곧바로 본문 이미지를 판독한다.
    """
    text = _visible_text(page_html)
    if _looks_like_bell_table(text):       # 교시 3개 이상 + 시각 3개 이상
        return _parse_from_text(text, page_url)

    for image_url in _content_image_urls(page_html, page_url):
        data = await _fetch_bytes(image_url)
        parsed = await _read_bell_image(data)   # Gemini vision -> JSON
        if parsed:
            return BellScheduleResult(
                periods=normalize_bell_periods(parsed),
                source_url=image_url,
                confidence=parsed.get("confidence", 0.0),
                note="이미지 판독",
            )
    raise ValueError("일과표를 찾지 못했습니다.")
```

이미지 후보를 고를 때 `logo/icon/btn/bullet/banner/common/blank/sns/menuImg` 가 든
경로는 제외한다(실측에서 장식 이미지가 이 이름들로 구분됐다).

- [ ] **Step 5: 검증 — 뽑은 표가 말이 되는지**

```python
def normalize_bell_periods(payload: dict) -> list[dict]:
    """말이 안 되는 표는 통째로 버린다. 반쯤 맞는 일과표가 제일 위험하다 —
    틀린 하교 시각으로 알림이 나가면 아무 알림도 없느니만 못하다."""
    items = payload.get("periods") or []
    if not items:
        raise ValueError("교시가 비어 있습니다.")
    out = []
    prev_end = None
    for raw in sorted(items, key=lambda x: int(x["period"])):
        p = int(raw["period"])
        s, e = str(raw["start_time"])[:5], str(raw["end_time"])[:5]
        if not (1 <= p <= 12):
            raise ValueError(f"교시 범위를 벗어남: {p}")
        if _mins(s) >= _mins(e):
            raise ValueError(f"{p}교시 시작이 종료보다 늦음")
        if not (5 * 60 <= _mins(s) <= 22 * 60):
            raise ValueError(f"{p}교시 시각이 상식 밖: {s}")
        if prev_end is not None and _mins(s) < prev_end:
            raise ValueError(f"{p}교시가 앞 교시와 겹침")
        prev_end = _mins(e)
        out.append({"period": p, "start_time": s, "end_time": e})
    return out
```

- [ ] **Step 6: 테스트 통과 확인 + 커밋**

---

### Task 11: 관리자 승인 화면

**Files:**
- Create: `backend/app/api/admin_bell_schedule.py` (기존 `/admin/*` 라우터 관례 확인 후 위치 결정)
- Modify: `lib/admin/schools.ts`
- Create: `app/admin/(dashboard)/schools/[id]/BellScheduleCard.tsx` (실제 관리자 경로 확인 후)
- Modify: `messages/*.json` — **불필요.** 관리자 화면은 한국어 전용이다.

**Interfaces:**
- Produces:
  - `POST /admin/schools/{school_id}/bell-schedule/discover` → 수집 실행, `source='homepage'`, `confirmed_at=null` 로 저장
  - `POST /admin/schools/{school_id}/bell-schedule/confirm` → `confirmed_at=now()`, `confirmed_by=<관리자>`
  - `AdminSchoolRow` 에 `bellScheduleStatus: 'none' | 'default' | 'pending' | 'confirmed'`

- [ ] **Step 1: 관리자 API 두 개**

`discover` 는 저장만 하고 **절대 자동 승인하지 않는다.**
승인 전까지 표준값이 계속 쓰이므로 서비스는 멈추지 않는다.

- [ ] **Step 2: 학교 목록에 일과표 상태 열 추가**

`lib/admin/schools.ts` 의 `SCHOOL_CRAWL_STATE_COLUMNS` 주석이 말하는 대로,
열을 늘리려면 `AdminSchoolRow` · 조회 · 표 헤더를 **함께** 늘려야 한다.

- [ ] **Step 3: 승인 화면 — 읽어낸 표를 그대로 보여주고 원본 그림을 나란히 띄운다**

관리자가 그림과 표를 눈으로 대조할 수 있어야 한다. `source_url` 을 `<img>` 로 건다.

- [ ] **Step 4: 스케줄러를 만들지 않는다**

일과표는 1년에 한 번 바뀐다. 버튼으로 충분하다.

- [ ] **Step 5: 커밋**

---

# Phase 4 — 알림

### Task 12: 알림 테이블 3종

**Files:**
- Create: `supabase/migrations/0050_notifications.sql`
- Modify: `types/database.ts`

- [ ] **Step 1: 마이그레이션**

```sql
-- 브라우저 구독. endpoint 가 브라우저가 발급한 고유 주소다.
create table if not exists public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  locale text not null default 'ko',
  user_agent text,
  failure_count smallint not null default 0,
  last_success_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists push_subscriptions_user_idx on public.push_subscriptions (user_id);

alter table public.push_subscriptions enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='push_subscriptions' and policyname='push subs manage own') then
    create policy "push subs manage own" on public.push_subscriptions for all
    using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;

-- 알림 on/off. v1 은 사용자 단위(자녀별 세분화는 v2).
create table if not exists public.notification_preferences (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  dismissal_enabled boolean not null default true,
  activity_enabled boolean not null default true,
  deadline_enabled boolean not null default true,
  quiet_start time not null default '21:00',
  quiet_end time not null default '07:00',
  updated_at timestamptz not null default now()
);
alter table public.notification_preferences enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='notification_preferences' and policyname='notif prefs manage own') then
    create policy "notif prefs manage own" on public.notification_preferences for all
    using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;

drop trigger if exists notification_preferences_set_updated_at on public.notification_preferences;
create trigger notification_preferences_set_updated_at
before update on public.notification_preferences
for each row execute function public.set_updated_at();

-- 발송 예약함. dedupe_key 유니크가 중복 발송을 구조적으로 막는다.
create table if not exists public.notification_outbox (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  child_id uuid references public.children(id) on delete cascade,
  kind text not null check (kind in ('dismissal', 'activity', 'deadline')),
  target_date date not null,
  dedupe_key text not null unique,
  send_at timestamptz not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'sent', 'skipped', 'failed')),
  sent_at timestamptz,
  error text,
  created_at timestamptz not null default now()
);
create index if not exists notification_outbox_due_idx
  on public.notification_outbox (status, send_at);

-- app_jobs 와 같은 취급: RLS 켜고 정책 0개 = service_role 만 접근.
alter table public.notification_outbox enable row level security;
```

- [ ] **Step 2: 멱등성 확인 + 타입 추가 + 커밋**

---

### Task 13: 서비스워커 + 구독 + 아이폰 안내

**Files:**
- Create: `public/sw.js`
- Create: `components/push/PushSubscribeCard.tsx`
- Create: `app/(app)/settings/push-actions.ts`
- Modify: `app/(app)/settings/page.tsx`
- Modify: `messages/*.json` (9개)

**Interfaces:**
- Produces: 서버 액션 `savePushSubscription(sub, locale)`, `deletePushSubscription(endpoint)`

- [ ] **Step 1: 서비스워커**

```js
// public/sw.js
self.addEventListener('push', (event) => {
  if (!event.data) return
  const data = event.data.json()
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      data: { url: data.url || '/' },
      tag: data.tag,          // 같은 tag 는 덮어쓴다 — 알림이 쌓이지 않는다
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.includes(url) && 'focus' in c) return c.focus()
      }
      return clients.openWindow(url)
    })
  )
})
```

- [ ] **Step 2: 구독 UI — 상태 3가지를 구분해 보여준다**

```
① 알림 켤 수 있음      → "알림 받기" 버튼
② 이미 켜짐            → "알림 끄기" 버튼
③ 아이폰인데 홈 화면 미추가 → 안내(공유 → 홈 화면에 추가)
```

③ 판정:
```ts
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
const isStandalone = window.matchMedia('(display-mode: standalone)').matches
  || (navigator as any).standalone === true
const cannotSubscribe = isIOS && !isStandalone
```

- [ ] **Step 3: 안내 문구를 9개 언어로.** 이 화면이 가장 중요한 다국어 지점이다 —
      한국어를 못 읽는 부모가 정확히 여기서 막힌다.

- [ ] **Step 4: 구독 저장 서버 액션.** `locale` 을 함께 저장한다(발송 시 문구 선택에 쓴다).

- [ ] **Step 5: 실제 안드로이드 기기 또는 데스크톱 크롬에서 구독 → DB 행 확인**

- [ ] **Step 6: 커밋**

---

### Task 14: 알림 계획 잡 (planner)

**Files:**
- Create: `backend/app/jobs/notification_planner.py`
- Create: `backend/app/services/notification_planning_service.py`
- Create: `backend/tests/test_notification_planner.py`

**Interfaces:**
- Produces: `plan_for_date(target_date: date) -> dict[str, int]` (kind별 생성 건수)

- [ ] **Step 1: 실패하는 테스트 먼저**

```python
def test_dedupe_key_prevents_double_insert():
    """같은 날 두 번 돌려도 알림은 한 번만 생긴다."""
    first = plan_for_date(date(2026, 9, 1))
    second = plan_for_date(date(2026, 9, 1))
    assert second["dismissal"] == 0


def test_quiet_hours_skips_not_defers():
    """조용한 시간에 걸리면 «건너뛴다». 아침으로 미루면 이미 지난 일을 알리게 된다."""
    row = build_outbox_row(kind="activity", send_at_local=time(22, 30), prefs=DEFAULT_PREFS)
    assert row["status"] == "skipped"


def test_no_dismissal_when_timetable_missing():
    """시간표를 못 가져오는 학교는 하교 알림을 만들지 않는다."""
    assert plan_dismissal(child=CHILD_NO_TIMETABLE, target=date(2026, 9, 1)) is None


def test_deadline_uses_hedged_wording():
    """마감일은 AI 추출값이라 단정하지 않는다."""
    row = plan_deadline(event=DEADLINE_TOMORROW, prefs=DEFAULT_PREFS)
    assert row["payload"]["body_key"] == "notif_deadline_body"
```

- [ ] **Step 2: 구현 — 세 종류를 각각 계획**

```python
DISMISSAL_LEAD_MINUTES = 30
ACTIVITY_LEAD_MINUTES = 30
DEADLINE_SEND_AT_LOCAL = time(8, 0)


def _dedupe_key(kind: str, child_id: str, target: date, ref: str = "") -> str:
    return f"{kind}:{child_id}:{target.isoformat()}:{ref}"
```

- **하교**: NEIS 시간표 → 그날 마지막 교시 → `school_bell_schedules`(승인분) → `bell_offset_minutes` → +종례 10분 → 30분 전.
  시간표가 없거나 그날 수업이 없으면 만들지 않는다.
- **방과후**: `child_personal_schedules` 중 `day_of_week == target.weekday()` → `start_time` 30분 전. `ref` 는 일정 id.
- **D-day**: `school_events` 중 `event_kinds` 에 `deadline` 포함 & 날짜가 `target + 1일` → 그날 08:00. `ref` 는 이벤트 id.

- [ ] **Step 3: payload 는 «번역 키 + 파라미터»로 저장한다**

```python
payload = {
    "title_key": "notif_dismissal_title",
    "body_key": "notif_dismissal_body",
    "params": {"child": child["name"], "time": dismissal_hhmm},
    "url": "/calendar?tab=classes",
    "tag": f"dismissal-{child['id']}",
}
```

발송 시점에 구독의 `locale` 로 문구를 고른다. **번역 API 를 부르지 않는다.**

- [ ] **Step 4: 잡 진입점** — `translation_worker.py` 의 argparse/로깅/종료코드 관례를 따른다.

- [ ] **Step 5: 테스트 통과 + 커밋**

---

### Task 15: 알림 발송 잡 (sender)

**Files:**
- Create: `backend/app/jobs/notification_sender.py`
- Create: `backend/app/services/web_push_service.py`
- Modify: `backend/requirements.txt` — `pywebpush` 추가
- Create: `backend/tests/test_web_push_service.py`

**Interfaces:**
- Consumes: Task 14 의 `notification_outbox`
- Produces: `send_due(limit: int) -> dict[str, int]`

- [ ] **Step 1: 실패하는 테스트 먼저**

```python
def test_expired_subscription_is_deleted():
    """410 Gone / 404 는 브라우저가 구독을 버린 것이다. 우리도 지운다.
    안 지우면 매번 실패하며 영원히 재시도한다."""
    svc = WebPushService(sender=raising_sender(status=410))
    svc.send(SUB, PAYLOAD)
    assert SUB["endpoint"] in svc.deleted_endpoints


def test_transient_failure_does_not_delete():
    """500 은 서버 일시 오류다. 구독을 지우면 안 된다."""
    svc = WebPushService(sender=raising_sender(status=500))
    svc.send(SUB, PAYLOAD)
    assert svc.deleted_endpoints == []


def test_body_rendered_in_subscription_locale():
    msg = render_payload(PAYLOAD, locale="vi")
    assert "Tan học" in msg["body"]


def test_missing_locale_falls_back_to_korean():
    msg = render_payload(PAYLOAD, locale="xx")
    assert msg["body"]
```

- [ ] **Step 2: 문구 렌더러**

`messages/*.json` 을 백엔드에서도 읽는다. 프론트와 **같은 파일**을 쓴다 —
문구가 두 벌이 되면 반드시 어긋난다.

- [ ] **Step 3: 발송 + 결과 기록**

```python
# 성공: status='sent', sent_at=now, 구독 last_success_at 갱신, failure_count=0
# 410/404: 구독 삭제, status='failed', error 기록
# 그 외: failure_count += 1, status='failed'
#   failure_count 가 5를 넘으면 구독 삭제(죽은 구독 청소)
```

- [ ] **Step 4: 한 사용자의 여러 기기에 모두 보낸다** — `push_subscriptions` 는 user 당 N행이다.

- [ ] **Step 5: 테스트 통과 + 커밋**

---

### Task 16: 알림 설정 화면 + 문구 9개 언어

**Files:**
- Modify: `app/(app)/settings/page.tsx`
- Create: `app/(app)/settings/NotificationPreferencesForm.tsx`
- Modify: `app/(app)/settings/push-actions.ts`
- Modify: `messages/*.json` (9개)

- [ ] **Step 1: on/off 세 개 + 조용한 시간**

- [ ] **Step 2: 알림 문구 키를 9개 언어에 추가**

```json
"notif_dismissal_title": "하교 안내",
"notif_dismissal_body": "{child} 오늘 {time}쯤 끝나요",
"notif_activity_title": "방과후 일정",
"notif_activity_body": "{child} {time} {title} 시작해요",
"notif_deadline_title": "가정통신문 마감",
"notif_deadline_body": "«{title}» 내일 마감인 것 같아요. 공지를 확인해 주세요"
```

> D-day 문구가 단정형이 아닌 이유: 마감일은 AI 가 공지에서 읽어낸 값이라 틀릴 수 있다.
> 틀린 단정은 아무 알림도 없느니만 못하다.

- [ ] **Step 3: 9개 파일 키 셋 diff 로 누락 0 확인**

- [ ] **Step 4: `npm run build && npm run typecheck`**

- [ ] **Step 5: 커밋**

---

### Task 17: 배포 배선

**Files:**
- Modify: `.github/workflows/deploy-api-cloud-run.yml`
- Create: `docs/운영-알림-스케줄러.md`

- [ ] **Step 1: Cloud Run Job 2개 추가**

기존 5개 Job 의 배포 블록을 그대로 본떠 `notification-planner`, `notification-sender` 를 추가한다.

> ⚠️ `gcloud` 인자 사이에 `#` 주석을 넣지 않는다. `\` 줄 이음이 주석에 삼켜져
> 명령이 거기서 끊긴다. 설명은 `- name:` 스텝 «위»에 쓴다.

- [ ] **Step 2: 스케줄러 2개**

| 잡 | 주기 | 근거 |
| --- | --- | --- |
| planner | 매일 05:00 KST | 하교 알림(최이른 07:30경 발송)보다 충분히 앞선다 |
| sender | 5분마다 | 알림 오차 최대 5분. 하교 30분 전 알림에서 무해하다 |

- [ ] **Step 3: VAPID 키**

로컬에서 키쌍을 만들고 **비밀키만** Secret Manager 에 넣는다.
공개키는 설계상 클라이언트에 노출되는 값이므로 환경변수로 둔다.

> 키를 명령줄 인자나 URL 에 넣지 않는다. 실패하면 화면에 그대로 찍힌다.

- [ ] **Step 4: 배포 후 확인**

- planner 를 수동 1회 실행 → `notification_outbox` 에 행이 생기는지
- sender 를 수동 1회 실행 → 내 기기에 알림이 오는지
- 같은 날 planner 를 두 번 돌려 **중복이 안 생기는지**

- [ ] **Step 5: 커밋**

---

## 검증 (2-에이전트 워크플로)

개발 후 **검증 에이전트**가 독립 점검한다.

| 항목 | 확인 |
| --- | --- |
| 마이그레이션 0048–0050 | 재실행 안전(멱등) |
| 권한 | 부모가 `school_bell_schedules` 를 **수정 못 함**, 타 자녀 일정 접근 못 함, `notification_outbox` 접근 못 함 |
| 미승인 일과표 | `confirmed_at is null` 이 화면·알림 어디에도 안 새는지 |
| 하교 계산 | 부천부흥중 실측표로 6교시/7교시 값이 맞는지, 보정이 **두 번** 더해지지 않는지 |
| 중복 | planner 2회 실행 시 알림 0건 추가 |
| 조용한 시간 | 21:00–07:00 이 미뤄지지 않고 건너뛰어지는지 |
| 시간표 미지원 학교 | 하교 알림 없이도 개인 일정은 등록·표시되는지 |
| i18n | 9개 파일 키 누락 0 |
| 구독 정리 | 410 응답에 구독이 삭제되고, 500 에는 삭제되지 않는지 |
| 문구 | 개인 일정 제목과 자녀 이름이 번역 경로를 타지 않는지 |
| 빌드 | `npm run build` → `npm run typecheck` 순서로 통과 |
| 백엔드 | `pytest` 전량 통과 |

## 되돌리기

| 상황 | 조치 |
| --- | --- |
| 알림이 잘못 나감 | 스케줄러 2개 일시중지 — 화면 기능은 그대로 산다 |
| 하교 시각이 틀림 | 해당 학교 `confirmed_at` 을 null 로 → 표준값으로 되돌아감 |
| 특정 학교만 문제 | `bell_offset_minutes` 또는 관리자 화면에서 수정 |
| 전면 철회 | 0050 → 0049 → 0048 순으로 드롭. 기존 화면은 시각 없는 교시 목록으로 자연 복귀 |
