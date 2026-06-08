with ranked as (
  select
    ctid,
    row_number() over (
      partition by notice_id, event_date
      order by updated_at desc nulls last, created_at desc nulls last, id desc
    ) as rn
  from public.school_events
)
delete from public.school_events
where ctid in (
  select ctid
  from ranked
  where rn > 1
);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.school_events'::regclass
      and conname = 'school_events_notice_id_event_date_key'
  ) then
    alter table public.school_events
      add constraint school_events_notice_id_event_date_key
      unique (notice_id, event_date);
  end if;
end;
$$;
