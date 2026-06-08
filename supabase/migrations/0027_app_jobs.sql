create table if not exists public.app_jobs (
  id uuid primary key default gen_random_uuid(),
  job_type text not null,
  job_key text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 5,
  available_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  result jsonb,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint app_jobs_status_check check (status in ('queued', 'processing', 'completed', 'failed'))
);

create index if not exists app_jobs_type_status_available_idx
  on public.app_jobs (job_type, status, available_at, created_at);

create unique index if not exists app_jobs_active_job_key_idx
  on public.app_jobs (job_key)
  where status in ('queued', 'processing');
