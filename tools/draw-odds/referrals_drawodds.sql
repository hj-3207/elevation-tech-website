-- Draw Odds -> app click counter. Run once in the Supabase SQL editor.
--
-- One row per click on an app link on draw-odds.html: which app, where on the page,
-- and when. No visitor data. Same pattern as the download counters: anyone may
-- INSERT, nobody may UPDATE or DELETE, and only the admin may read.
--
-- The admin read rule is copied from the existing `downloads` table's SELECT policy,
-- so the admin email never has to appear in this (public) repo.

create table if not exists public.referrals_drawodds (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  app         text not null check (app in ('detector', 'viewer', 'tracker', 'scorer', 'apps')),
  placement   text not null check (placement in ('top', 'detail', 'after'))
);

alter table public.referrals_drawodds enable row level security;

grant insert on public.referrals_drawodds to anon, authenticated;
grant select on public.referrals_drawodds to authenticated;

drop policy if exists "anyone can count a click" on public.referrals_drawodds;
create policy "anyone can count a click" on public.referrals_drawodds
  for insert to anon, authenticated with check (true);

do $$
declare q text;
begin
  select qual into q from pg_policies
   where schemaname = 'public' and tablename = 'downloads' and cmd = 'SELECT'
   limit 1;
  if q is null then
    raise exception 'No SELECT policy found on public.downloads to copy';
  end if;
  execute 'drop policy if exists "admin can read" on public.referrals_drawodds';
  execute format('create policy "admin can read" on public.referrals_drawodds for select to authenticated using (%s)', q);
end $$;

-- Check: should list the two policies.
select policyname, cmd, roles, qual from pg_policies where tablename = 'referrals_drawodds';
