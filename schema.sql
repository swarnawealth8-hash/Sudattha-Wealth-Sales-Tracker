-- Sudattha Wealth Sales Tracker
-- Run this entire file in Supabase > SQL Editor after creating your project.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  role text not null default 'teammate' check (role in ('admin','teammate')),
  created_at timestamptz not null default now()
);

create table if not exists public.leads (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id) on delete cascade,
  name text not null,
  contact_number text not null,
  email text,
  call_booking_date date not null,
  lead_source text not null check (lead_source in ('Referral','Instagram','Ads','Other')),
  invitation_sent boolean not null default false,
  one_on_one_status text not null default 'Not scheduled' check (one_on_one_status in ('Not scheduled','Scheduled','Completed','No show')),
  one_on_one_date date,
  followup_status text not null default 'Pending' check (followup_status in ('Not required','Pending','Follow-up again','Closed')),
  followup_date date,
  signup_date date,
  revenue_type text not null default 'New onboarding' check (revenue_type in ('New onboarding','Existing student')),
  amount_pitched numeric(12,2) not null default 0 check (amount_pitched >= 0),
  amount_paid numeric(12,2) not null default 0 check (amount_paid >= 0),
  payment_mode text not null default 'Not paid yet' check (payment_mode in ('Not paid yet','UPI','Credit card','Bank transfer','Cash','Other')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Automatically create a teammate profile for every new auth user.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, role)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.email), 'teammate')
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.leads enable row level security;

-- Profiles: each user can see their own profile; admins can see all profiles.
drop policy if exists "profiles_select" on public.profiles;
create policy "profiles_select" on public.profiles
for select to authenticated
using (
  id = auth.uid()
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  )
);

-- Leads visibility rule:
-- 1) Admin sees every lead.
-- 2) Teammate sees only leads they created.
drop policy if exists "leads_select" on public.leads;
create policy "leads_select" on public.leads
for select to authenticated
using (
  created_by = auth.uid()
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  )
);

-- Users can create only their own records.
drop policy if exists "leads_insert" on public.leads;
create policy "leads_insert" on public.leads
for insert to authenticated
with check (created_by = auth.uid());

-- Admin can update every lead; teammate can update only own leads.
drop policy if exists "leads_update" on public.leads;
create policy "leads_update" on public.leads
for update to authenticated
using (
  created_by = auth.uid()
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  )
)
with check (
  created_by = auth.uid()
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  )
);

-- Admin can delete every lead; teammate can delete only own leads.
drop policy if exists "leads_delete" on public.leads;
create policy "leads_delete" on public.leads
for delete to authenticated
using (
  created_by = auth.uid()
  or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  )
);

-- Helpful indexes
create index if not exists leads_created_by_idx on public.leads(created_by);
create index if not exists leads_call_booking_date_idx on public.leads(call_booking_date);
create index if not exists leads_followup_date_idx on public.leads(followup_date);
create index if not exists leads_signup_date_idx on public.leads(signup_date);
