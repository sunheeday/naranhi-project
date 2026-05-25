create table if not exists public.notice_ai_translations (
  id uuid primary key default gen_random_uuid(),
  notice_id uuid not null references public.notices(id) on delete cascade,
  target_language text not null,
  source_language text not null default 'ko',
  source_text text not null,
  translated_text text not null,
  source_hard_facts jsonb not null default '{}'::jsonb,
  target_hard_facts jsonb not null default '{}'::jsonb,
  ingredient_identity_map jsonb not null default '{}'::jsonb,
  validation jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  raw_pipeline jsonb not null default '{}'::jsonb,
  validation_status text not null default 'human_review_required'
    check (validation_status in ('passed', 'human_review_required', 'failed')),
  requires_admin_review boolean not null default true,
  admin_review_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (notice_id, target_language)
);

create index if not exists notice_ai_translations_notice_idx
on public.notice_ai_translations (notice_id);

create index if not exists notice_ai_translations_review_idx
on public.notice_ai_translations (requires_admin_review, validation_status);

create trigger notice_ai_translations_set_updated_at
before update on public.notice_ai_translations
for each row execute function public.set_updated_at();

alter table public.notice_ai_translations enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notice_ai_translations'
      and policyname = 'notice ai translations select own notice'
  ) then
    create policy "notice ai translations select own notice"
    on public.notice_ai_translations for select
    using (
      exists (
        select 1
        from public.notices
        join public.children on children.id = notices.child_id
        where notices.id = notice_ai_translations.notice_id
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;
