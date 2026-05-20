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
