# Supabase Schema

The initial schema lives in `supabase/migrations/0001_initial_schema.sql`.

It adds the first production-facing data model:

- `profiles`: user profile attached to Supabase Auth users
- `schools`: school metadata and optional NEIS identifiers
- `children`: parent-managed student records
- `notices`: uploaded or collected school notices
- `notice_cards`: card-news payloads extracted from notices
- `schedules`: deadlines and events extracted from notices
- `meals`: NEIS meal data cached per school and date
- `document_files`: metadata for files stored in the private `notice-originals` bucket

Row-level security is enabled on every application table. Parent users can manage their own children, read notices for their children, and read derived card/schedule data. Shared school and meal data is readable by authenticated users. File uploads are scoped to each user's own storage folder.

Apply the migration with the Supabase CLI:

```bash
supabase link --project-ref your-project-ref
supabase db push
```
