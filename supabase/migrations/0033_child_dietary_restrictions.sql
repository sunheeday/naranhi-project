alter table public.children
  add column if not exists dietary_restrictions jsonb not null default '[]'::jsonb;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'children_dietary_restrictions_array_check'
      and conrelid = 'public.children'::regclass
  ) then
    alter table public.children
      add constraint children_dietary_restrictions_array_check
      check (jsonb_typeof(dietary_restrictions) = 'array');
  end if;
end $$;
