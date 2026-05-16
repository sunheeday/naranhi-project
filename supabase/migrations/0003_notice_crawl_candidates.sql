alter table public.notices
  add column if not exists source_post_id text,
  add column if not exists source_post_uid text,
  add column if not exists detail_url text,
  add column if not exists crawl_result jsonb not null default '{}'::jsonb;

create unique index if not exists notices_crawl_source_uid_uidx
on public.notices (school_id, source, source_post_uid);

create unique index if not exists notices_crawl_detail_url_uidx
on public.notices (school_id, source, detail_url);

create index if not exists children_user_school_id_idx
on public.children (user_id, school_id)
where school_id is not null;

create index if not exists notices_school_id_idx
on public.notices (school_id)
where school_id is not null;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notices'
      and policyname = 'notices select own school'
  ) then
    create policy "notices select own school"
    on public.notices for select
    using (
      school_id is not null
      and exists (
        select 1
        from public.children
        where children.user_id = auth.uid()
          and children.school_id = notices.school_id
      )
    );
  end if;
end;
$$;
