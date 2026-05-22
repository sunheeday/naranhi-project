do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notice_cards'
      and policyname = 'notice cards select own school notice'
  ) then
    create policy "notice cards select own school notice"
    on public.notice_cards for select
    using (
      exists (
        select 1
        from public.notices
        join public.children on children.school_id = notices.school_id
        where notices.id = notice_cards.notice_id
          and notices.school_id is not null
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notice_ai_translations'
      and policyname = 'notice ai translations select own school notice'
  ) then
    create policy "notice ai translations select own school notice"
    on public.notice_ai_translations for select
    using (
      exists (
        select 1
        from public.notices
        join public.children on children.school_id = notices.school_id
        where notices.id = notice_ai_translations.notice_id
          and notices.school_id is not null
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;
