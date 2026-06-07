alter table public.notices
  add column if not exists source_hard_facts jsonb not null default '{}'::jsonb;

update public.notices
set source_hard_facts = coalesce(latest.source_hard_facts, '{}'::jsonb)
from (
  select distinct on (notice_id)
    notice_id,
    source_hard_facts
  from public.notice_ai_translations
  order by notice_id, created_at desc
) as latest
where notices.id = latest.notice_id
  and notices.source_hard_facts = '{}'::jsonb;
