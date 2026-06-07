do $$
declare
  unresolved_count bigint;
begin
  select count(*)
    into unresolved_count
  from public.children c
  left join public.schools s on s.id = c.school_id
  where c.school_id is null
     or s.id is null
     or s.name is null
     or s.neis_office_code is null
     or s.neis_school_code is null;

  if unresolved_count > 0 then
    raise exception
      'Cannot drop duplicated child school fields: % unresolved children still require fallback school data.',
      unresolved_count;
  end if;
end;
$$;

alter table public.children
  drop constraint if exists children_school_id_fkey;

alter table public.children
  add constraint children_school_id_fkey
  foreign key (school_id)
  references public.schools(id)
  on delete restrict;

alter table public.children
  drop column if exists school_name,
  drop column if exists neis_office_code,
  drop column if exists neis_school_code;
