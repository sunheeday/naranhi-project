alter table public.school_events
  add column if not exists event_kinds jsonb not null default '["event"]'::jsonb;

update public.school_events
set event_kinds = case
  when notices.due_date is not null and school_events.event_date = notices.due_date
    then '["deadline"]'::jsonb
  else '["event"]'::jsonb
end
from public.notices
where notices.id = school_events.notice_id
  and (
    school_events.event_kinds is null
    or school_events.event_kinds = '["event"]'::jsonb
  );
