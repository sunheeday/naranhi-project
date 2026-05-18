alter type public.notice_card_type add value if not exists 'summary';
alter type public.notice_card_type add value if not exists 'info';

with ranked_cards as (
  select
    id,
    row_number() over (
      partition by notice_id, type, "order"
      order by created_at asc, id asc
    ) as duplicate_rank
  from public.notice_cards
)
delete from public.notice_cards
using ranked_cards
where notice_cards.id = ranked_cards.id
  and ranked_cards.duplicate_rank > 1;

create unique index if not exists notice_cards_notice_type_order_uidx
on public.notice_cards (notice_id, type, "order");

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
