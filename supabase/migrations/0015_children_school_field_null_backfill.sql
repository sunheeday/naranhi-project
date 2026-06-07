-- Clear duplicated child school fields only when the canonical schools row
-- already has the equivalent data. This keeps fallback data intact for any
-- incomplete or orphaned rows during the transition period.

update public.children as c
set
  school_name = case
    when s.name is not null then null
    else c.school_name
  end,
  neis_office_code = case
    when s.neis_office_code is not null then null
    else c.neis_office_code
  end,
  neis_school_code = case
    when s.neis_school_code is not null then null
    else c.neis_school_code
  end
from public.schools as s
where c.school_id = s.id
  and (
    (c.school_name is not null and s.name is not null)
    or (c.neis_office_code is not null and s.neis_office_code is not null)
    or (c.neis_school_code is not null and s.neis_school_code is not null)
  );
