alter table public.children
  add column if not exists dietary_restrictions text[] not null default '{}'::text[];

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
      check (
        dietary_restrictions <@ array[
          'halal',
          'no_pork',
          'no_beef',
          'vegetarian',
          'kosher'
        ]::text[]
      );
  end if;
end $$;
