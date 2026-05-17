create table if not exists public.notice_hides (
  user_id uuid not null references public.profiles(id) on delete cascade,
  notice_id uuid not null references public.notices(id) on delete cascade,
  hidden_at timestamptz not null default now(),
  primary key (user_id, notice_id)
);

create index if not exists notice_hides_notice_id_idx
on public.notice_hides (notice_id);

alter table public.notice_hides enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notice_hides'
      and policyname = 'notice hides manage own'
  ) then
    create policy "notice hides manage own"
    on public.notice_hides for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);
  end if;
end;
$$;
