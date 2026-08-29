-- 관리자 자격·세션·감사 추적. 학부모 인증(Supabase Auth)과 분리된 별도 체계다.
--
-- 왜 profiles.role 을 되살리지 않는가:
--   0001_initial_schema.sql:138-141 의 "profiles update own" 정책은 행 단위라
--   role 컬럼까지 갱신을 허용한다. /home 개발 진입로가 프로덕션에서 켜져 있으므로
--   (사업 A 결정) 누구나 세션을 얻어 anon 키로 PATCH /rest/v1/profiles {"role":"admin"}
--   을 던져 스스로 관리자가 될 수 있다. 자격 저장소 자체를 분리한다.
--
-- 세 테이블 모두 RLS 활성 + 정책 0개 = anon/authenticated 전면 차단.
-- 선례: 0013_school_crawl_state.sql:72, 0036_app_jobs_rls.sql
-- 접근 경로는 service_role(Next.js 관리자 라우트)뿐이고, service_role 은 RLS 를 우회한다.
--
-- 비밀번호 해시에 새 의존성이 없다 — pgcrypto 는 0001_initial_schema.sql:1 이 이미 켰다.

create table if not exists public.admin_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,
  display_name text,
  is_active boolean not null default true,
  -- 2단계 인증은 1단계에서 하지 않는다. 컬럼 자리만 남긴다 — 필요해지면
  -- 마이그레이션 없이 검증 코드만 붙일 수 있다.
  totp_secret text,
  failed_attempts integer not null default 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.admin_sessions (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references public.admin_users(id) on delete cascade,
  -- 원본 토큰은 쿠키에만 있다. DB 에는 sha256 해시만 둔다.
  token_hash text not null unique,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists admin_sessions_expires_idx
  on public.admin_sessions (expires_at);

create table if not exists public.admin_audit_log (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid references public.admin_users(id) on delete set null,
  action text not null,
  target text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists admin_audit_log_created_idx
  on public.admin_audit_log (created_at desc);

alter table public.admin_users     enable row level security;
alter table public.admin_sessions  enable row level security;
alter table public.admin_audit_log enable row level security;

-- 자격 검증은 security definer 함수 하나로 감싼다. 앱은 «맞다/틀리다» 와 계정 id 만 받는다.
-- 실패 카운터와 잠금도 여기서 갱신한다 — 앱이 잊어버릴 여지를 없앤다.
-- search_path 에 extensions 를 넣는 이유: Supabase 는 pgcrypto 를 extensions 스키마에
-- 두는 경우가 있어 crypt/gen_salt 를 무자격 이름으로 못 찾을 수 있다.
create or replace function public.admin_verify_password(
  p_username text,
  p_password text
)
returns table (admin_user_id uuid, display_name text, outcome text)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_user public.admin_users%rowtype;
  v_next_attempts integer;
begin
  select * into v_user from public.admin_users where username = p_username;

  if not found or not v_user.is_active then
    return query select null::uuid, null::text, 'invalid'::text;
    return;
  end if;

  if v_user.locked_until is not null and v_user.locked_until > now() then
    return query select null::uuid, null::text, 'locked'::text;
    return;
  end if;

  if v_user.password_hash = crypt(p_password, v_user.password_hash) then
    update public.admin_users
       set failed_attempts = 0,
           locked_until = null,
           last_login_at = now(),
           updated_at = now()
     where id = v_user.id;
    return query select v_user.id, v_user.display_name, 'ok'::text;
    return;
  end if;

  -- 5회 실패 → 15분 잠금.
  v_next_attempts := v_user.failed_attempts + 1;
  update public.admin_users
     set failed_attempts = v_next_attempts,
         locked_until = case
           when v_next_attempts >= 5 then now() + interval '15 minutes'
           else v_user.locked_until
         end,
         updated_at = now()
   where id = v_user.id;

  return query select null::uuid, null::text, 'invalid'::text;
end;
$$;

-- 계정 생성·비밀번호 회전. 원본은 이 함수 안에서만 존재하고 해시만 남는다.
create or replace function public.admin_set_password(
  p_username text,
  p_password text,
  p_display_name text default null
)
returns uuid
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_id uuid;
begin
  insert into public.admin_users (username, password_hash, display_name)
  values (p_username, crypt(p_password, gen_salt('bf', 12)), p_display_name)
  on conflict (username) do update
     set password_hash = crypt(p_password, gen_salt('bf', 12)),
         display_name = coalesce(excluded.display_name, public.admin_users.display_name),
         failed_attempts = 0,
         locked_until = null,
         is_active = true,
         updated_at = now()
  returning id into v_id;
  return v_id;
end;
$$;

-- security definer 함수는 기본적으로 public 에 EXECUTE 가 있다. 회수하지 않으면
-- anon 키로 자격 검증기와 비밀번호 설정기가 그대로 공개된다.
revoke all on function public.admin_verify_password(text, text) from public;
revoke all on function public.admin_verify_password(text, text) from anon;
revoke all on function public.admin_verify_password(text, text) from authenticated;
revoke all on function public.admin_set_password(text, text, text) from public;
revoke all on function public.admin_set_password(text, text, text) from anon;
revoke all on function public.admin_set_password(text, text, text) from authenticated;
