create extension if not exists "pgcrypto";

create type public.user_role as enum ('parent', 'school_admin');
create type public.notice_source as enum ('upload', 'crawl', 'manual');
create type public.notice_status as enum ('pending', 'processing', 'done', 'error');
create type public.notice_card_type as enum ('supplies', 'action', 'schedule');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  avatar_url text,
  locale text not null default 'ko',
  native_language text not null default 'ko',
  role public.user_role not null default 'parent',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.schools (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  neis_office_code text,
  neis_school_code text,
  address text,
  created_at timestamptz not null default now(),
  unique (neis_office_code, neis_school_code)
);

create table public.children (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  school_id uuid references public.schools(id) on delete set null,
  name text not null,
  school_name text not null,
  grade smallint not null check (grade between 1 and 12),
  class_no smallint,
  neis_office_code text,
  neis_school_code text,
  created_at timestamptz not null default now()
);

create table public.notices (
  id uuid primary key default gen_random_uuid(),
  child_id uuid references public.children(id) on delete cascade,
  school_id uuid references public.schools(id) on delete set null,
  source public.notice_source not null default 'upload',
  title text,
  original_text text,
  summary_translations jsonb not null default '{}'::jsonb,
  storage_path text,
  status public.notice_status not null default 'pending',
  error_message text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.notice_cards (
  id uuid primary key default gen_random_uuid(),
  notice_id uuid not null references public.notices(id) on delete cascade,
  type public.notice_card_type not null,
  content jsonb not null default '{}'::jsonb,
  "order" smallint not null default 0,
  created_at timestamptz not null default now()
);

create table public.schedules (
  id uuid primary key default gen_random_uuid(),
  notice_id uuid not null references public.notices(id) on delete cascade,
  child_id uuid not null references public.children(id) on delete cascade,
  title text not null,
  event_date date not null,
  location text,
  description text,
  gcal_event_id text,
  created_at timestamptz not null default now()
);

create table public.meals (
  id uuid primary key default gen_random_uuid(),
  office_code text not null,
  school_code text not null,
  meal_date date not null,
  meal_type smallint not null,
  meal_type_name text not null,
  dishes jsonb not null default '[]'::jsonb,
  calories text,
  nutrients jsonb,
  origins jsonb,
  fetched_at timestamptz not null default now(),
  unique (office_code, school_code, meal_date, meal_type)
);

create table public.document_files (
  id uuid primary key default gen_random_uuid(),
  notice_id uuid references public.notices(id) on delete cascade,
  storage_bucket text not null default 'notice-originals',
  storage_path text not null,
  mime_type text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger notices_set_updated_at
before update on public.notices
for each row execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.schools enable row level security;
alter table public.children enable row level security;
alter table public.notices enable row level security;
alter table public.notice_cards enable row level security;
alter table public.schedules enable row level security;
alter table public.meals enable row level security;
alter table public.document_files enable row level security;

create policy "profiles select own"
on public.profiles for select
using (auth.uid() = id);

create policy "profiles insert own"
on public.profiles for insert
with check (auth.uid() = id);

create policy "profiles update own"
on public.profiles for update
using (auth.uid() = id)
with check (auth.uid() = id);

create policy "schools select authenticated"
on public.schools for select
to authenticated
using (true);

create policy "children manage own"
on public.children for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "notices select own child"
on public.notices for select
using (
  exists (
    select 1 from public.children
    where children.id = notices.child_id
      and children.user_id = auth.uid()
  )
);

create policy "notices insert own child"
on public.notices for insert
with check (
  child_id is null
  or exists (
    select 1 from public.children
    where children.id = notices.child_id
      and children.user_id = auth.uid()
  )
);

create policy "notices update own child"
on public.notices for update
using (
  exists (
    select 1 from public.children
    where children.id = notices.child_id
      and children.user_id = auth.uid()
  )
);

create policy "notices delete own child"
on public.notices for delete
using (
  exists (
    select 1 from public.children
    where children.id = notices.child_id
      and children.user_id = auth.uid()
  )
);

create policy "notice cards select own notice"
on public.notice_cards for select
using (
  exists (
    select 1
    from public.notices
    join public.children on children.id = notices.child_id
    where notices.id = notice_cards.notice_id
      and children.user_id = auth.uid()
  )
);

create policy "schedules select own child"
on public.schedules for select
using (
  exists (
    select 1 from public.children
    where children.id = schedules.child_id
      and children.user_id = auth.uid()
  )
);

create policy "schedules delete own child"
on public.schedules for delete
using (
  exists (
    select 1 from public.children
    where children.id = schedules.child_id
      and children.user_id = auth.uid()
  )
);

create policy "meals select authenticated"
on public.meals for select
to authenticated
using (true);

create policy "document files select own notice"
on public.document_files for select
using (
  exists (
    select 1
    from public.notices
    join public.children on children.id = notices.child_id
    where notices.id = document_files.notice_id
      and children.user_id = auth.uid()
  )
);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'notice-originals',
  'notice-originals',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "notice originals upload own folder"
on storage.objects for insert
to authenticated
with check (
  bucket_id = 'notice-originals'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "notice originals read own folder"
on storage.objects for select
to authenticated
using (
  bucket_id = 'notice-originals'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "notice originals delete own folder"
on storage.objects for delete
to authenticated
using (
  bucket_id = 'notice-originals'
  and (storage.foldername(name))[1] = auth.uid()::text
);
