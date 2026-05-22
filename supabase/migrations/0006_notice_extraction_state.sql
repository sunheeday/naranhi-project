alter table public.notices
  add column if not exists extracted_content jsonb,
  add column if not exists extraction_attempts int not null default 0,
  add column if not exists extraction_started_at timestamptz,
  add column if not exists extraction_next_run_at timestamptz,
  add column if not exists extraction_error_code text;

create index if not exists notices_extraction_claim_idx
on public.notices (
  status,
  extraction_next_run_at,
  created_at
)
where school_id is not null
  and detail_url is not null
  and status in ('pending', 'error');

create index if not exists notices_extraction_stale_processing_idx
on public.notices (
  extraction_started_at
)
where school_id is not null
  and detail_url is not null
  and status = 'processing';

create or replace function public.claim_notice_extractions(
  p_limit int default 1,
  p_stale_minutes int default 180,
  p_notice_id uuid default null,
  p_force boolean default false
)
returns setof public.notices
language sql
security definer
set search_path = public
as $$
  update public.notices as notices
  set
    status = 'processing',
    extraction_attempts = notices.extraction_attempts + 1,
    extraction_started_at = now(),
    extraction_next_run_at = null,
    extraction_error_code = null,
    error_message = null
  where notices.id in (
    select candidate.id
    from public.notices as candidate
    where candidate.school_id is not null
      and candidate.detail_url is not null
      and (p_notice_id is null or candidate.id = p_notice_id)
      and (
        (p_force and p_notice_id is not null)
        or (
          not p_force
          and (
            candidate.status = 'pending'
            or (
              candidate.status = 'error'
              and (
                candidate.extraction_error_code = 'gemini_quota_exhausted'
                or candidate.extraction_attempts < 3
              )
              and coalesce(candidate.extraction_next_run_at, now()) <= now()
            )
            or (
              candidate.status = 'processing'
              and candidate.extraction_started_at < now() - make_interval(mins => p_stale_minutes)
            )
          )
        )
      )
    order by
      candidate.created_at asc,
      candidate.id asc
    limit greatest(p_limit, 1)
    for update skip locked
  )
  returning notices.*;
$$;

revoke all on function public.claim_notice_extractions(int, int, uuid, boolean)
from public, anon, authenticated;

grant execute on function public.claim_notice_extractions(int, int, uuid, boolean)
to service_role;
