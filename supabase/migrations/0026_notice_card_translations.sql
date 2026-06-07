create table if not exists public.notice_card_translations (
  id uuid primary key default gen_random_uuid(),
  notice_card_id uuid not null references public.notice_cards(id) on delete cascade,
  target_language text not null,
  translated_content jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (notice_card_id, target_language)
);

create index if not exists notice_card_translations_notice_card_id_idx
  on public.notice_card_translations (notice_card_id);

create index if not exists notice_card_translations_target_language_idx
  on public.notice_card_translations (target_language);

alter table public.notice_card_translations enable row level security;

drop policy if exists "notice card translations select own school" on public.notice_card_translations;

create policy "notice card translations select own school"
  on public.notice_card_translations for select
  using (
    exists (
      select 1
      from public.notice_cards
      join public.notices on notices.id = notice_cards.notice_id
      join public.children on children.school_id = notices.school_id
      where notice_cards.id = notice_card_translations.notice_card_id
        and children.user_id = auth.uid()
    )
  );
