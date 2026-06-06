# Supabase Schema

The initial schema lives in `supabase/migrations/0001_initial_schema.sql`.

It adds the first production-facing data model:

- `profiles`: user profile attached to Supabase Auth users
- `schools`: school metadata and optional NEIS identifiers
- `children`: parent-managed student records
- `notices`: school-crawled notices (school-only, no manual/upload)
- `notice_cards`: card-news payloads extracted from notices
- `notice_hides`: per-user soft-delete for notices
- `schedules`: deadlines and events extracted from notices
- `meals`: NEIS meal data cached per school and date

Row-level security is enabled on every application table. Parent users can manage their own children, read notices for their school, and read derived card/schedule data. Shared school and meal data is readable by authenticated users.

Apply the migration with the Supabase CLI:

```bash
supabase link --project-ref your-project-ref
supabase db push
```

## ⚠️ 미적용 마이그레이션 (다음 작업자 필독)

`supabase/migrations/0012_children_dietary_restrictions.sql` 은 **아직 운영 Supabase DB에 적용되지 않았습니다.**
이 컬럼이 없으면 급식·설정 화면이 `dietary_restrictions` 조회에서 실패합니다.

배포 전에 반드시 아래 중 하나로 적용하세요.

- **CLI**: `supabase db push`
- **대시보드 SQL Editor**에 아래 SQL을 직접 실행:

```sql
alter table public.children
  add column if not exists dietary_restrictions text[] not null default '{}';
```

(`if not exists` 라 여러 번 실행해도 안전합니다.)
