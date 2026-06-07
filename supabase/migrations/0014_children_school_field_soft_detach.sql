-- Safe transition before deleting duplicated child school fields.
-- Keep the columns for backward compatibility, but stop requiring school_name on new writes.

alter table public.children
  alter column school_name drop not null;
