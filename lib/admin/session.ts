import 'server-only'

import { createHash, randomBytes } from 'node:crypto'
import { cookies } from 'next/headers'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS } from '@/lib/admin/cookie'

export { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS }

export interface AdminSession {
  adminUserId: string
  username: string
  displayName: string | null
  expiresAt: string
}

export type VerifyOutcome =
  | { status: 'ok'; adminUserId: string; displayName: string | null }
  | { status: 'invalid' }
  | { status: 'locked' }

export class AdminUnauthorizedError extends Error {
  constructor() {
    super('admin_unauthorized')
    this.name = 'AdminUnauthorizedError'
  }
}

/** 쿠키에는 원본 토큰이, DB 에는 이 해시가 들어간다.
 *  DB 가 유출돼도 세션을 재현할 수 없고, 서버는 해시로 즉시 조회할 수 있다. */
function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex')
}

/** 자격 검증. 실패 카운터·잠금(5회/15분)은 DB 함수(admin_verify_password,
 *  0038_admin_console_auth.sql:64-113)가 갱신한다. 앱은 「맞다/틀리다/잠김」과
 *  계정 id 만 받는다 — 해시가 앱 메모리로 나오지 않는다.
 *
 *  fail-closed: 0038 이 아직 운영에 없어 admin_verify_password 자체가 없으면
 *  RPC 가 error 를 낸다. 그 경우 여기서 즉시 throw 한다 — 조용히 「invalid」로
 *  떨어뜨리지 않는 이유는, 그렇게 하면 「이 계정은 존재하지 않는다」와 「검증
 *  자체가 고장났다」를 호출자가 구분할 수 없어 장애를 인증 실패로 오인하기
 *  쉬워지기 때문이다. 어느 쪽이든 세션은 발급되지 않는다(호출자가 로그인
 *  라우트라면 500 으로 떨어질 뿐, 로그인은 되지 않는다).
 */
export async function verifyAdminPassword(
  username: string,
  password: string,
): Promise<VerifyOutcome> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service.rpc('admin_verify_password', {
    p_username: username,
    p_password: password,
  })
  if (error) {
    throw new Error(`관리자 자격 검증 실패: ${error.message}`)
  }
  const row = Array.isArray(data) ? data[0] : null
  if (!row) return { status: 'invalid' }
  if (row.outcome === 'locked') return { status: 'locked' }
  if (row.outcome !== 'ok' || !row.admin_user_id) return { status: 'invalid' }
  return {
    status: 'ok',
    adminUserId: row.admin_user_id,
    displayName: row.display_name ?? null,
  }
}

export async function createAdminSession(
  adminUserId: string,
): Promise<{ token: string; expiresAt: string }> {
  const token = randomBytes(32).toString('base64url')
  const expiresAt = new Date(Date.now() + ADMIN_SESSION_MAX_AGE_SECONDS * 1000).toISOString()
  const service = createSupabaseServiceClient()
  const { error } = await service.from('admin_sessions').insert({
    admin_user_id: adminUserId,
    token_hash: hashToken(token),
    expires_at: expiresAt,
  })
  if (error) {
    throw new Error(`관리자 세션 생성 실패: ${error.message}`)
  }
  return { token, expiresAt }
}

/** 세션 검증. 이 함수만이 「관리자인가」의 답을 안다 — middleware(Task 5)는
 *  Edge 런타임 제약상 쿠키 존재만 보고, 실제 판정은 전부 여기를 지난다.
 *  쿠키 값을 그대로 신뢰하지 않는다: 매 호출마다 DB(admin_sessions)를
 *  조회해 token_hash 로 세션 행을 찾고, revoked_at·expires_at·연결된
 *  admin_users.is_active 까지 확인한 뒤에만 세션을 인정한다.
 *
 *  fail-closed: admin_sessions/admin_users 조회가 에러거나(0038 미적용 시
 *  PostgREST 가 테이블을 못 찾아 error 를 반환한다) 행이 없으면 null 을
 *  반환한다 — 즉 「미인증」이다. 절대 세션을 조용히 통과시키지 않는다.
 */
export async function getAdminSession(): Promise<AdminSession | null> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value
  if (!token) return null

  const service = createSupabaseServiceClient()
  const { data: session, error } = await service
    .from('admin_sessions')
    .select('admin_user_id,expires_at,revoked_at')
    .eq('token_hash', hashToken(token))
    .maybeSingle()
  if (error || !session) return null
  if (session.revoked_at) return null
  if (new Date(session.expires_at).getTime() <= Date.now()) return null

  const { data: user, error: userError } = await service
    .from('admin_users')
    .select('username,display_name,is_active')
    .eq('id', session.admin_user_id)
    .maybeSingle()
  if (userError || !user || !user.is_active) return null

  return {
    adminUserId: session.admin_user_id,
    username: user.username,
    displayName: user.display_name,
    expiresAt: session.expires_at,
  }
}

export async function requireAdminSession(): Promise<AdminSession> {
  const session = await getAdminSession()
  if (!session) throw new AdminUnauthorizedError()
  return session
}

/** 로그아웃. JWT 가 아니라 DB 세션이라 서버 측에서 즉시 회수된다.
 *  실패해도 던지지 않는다 — 로그아웃은 방어선이 아니라 정리 동작이라, 여기서
 *  에러가 나도 최악의 경우 세션이 원래 만료 시각(최대 8시간)까지 유효한 채로
 *  남을 뿐이다. 쿠키 삭제는 호출자(Task 5 라우트)가 응답에서 처리한다. */
export async function revokeCurrentAdminSession(): Promise<void> {
  const cookieStore = await cookies()
  const token = cookieStore.get(ADMIN_COOKIE_NAME)?.value
  if (!token) return
  const service = createSupabaseServiceClient()
  const { error } = await service
    .from('admin_sessions')
    .update({ revoked_at: new Date().toISOString() })
    .eq('token_hash', hashToken(token))
    .is('revoked_at', null)
  if (error) {
    console.error(`관리자 세션 회수 실패: ${error.message}`)
  }
}

/** 파괴적 작업의 사람별 추적. 실패해도 조작을 되돌리지 않는다 —
 *  감사 기록 실패로 「이미 지운 공지」를 되살릴 수는 없기 때문이다. 대신 크게 남긴다.
 *  (비밀번호 등 민감값은 이 함수의 호출자가 애초에 detail 에 담지 않아야 한다 —
 *  이 함수는 받은 값을 그대로 적재할 뿐 마스킹하지 않는다.) */
export async function writeAdminAudit(
  session: AdminSession,
  action: string,
  target: string | null,
  detail: Record<string, unknown> = {},
): Promise<void> {
  const service = createSupabaseServiceClient()
  const { error } = await service.from('admin_audit_log').insert({
    admin_user_id: session.adminUserId,
    action,
    target,
    detail: detail as never,
  })
  if (error) {
    console.error(
      `관리자 감사 로그 기록 실패: action=${action} target=${target ?? '-'} error=${error.message}`,
    )
  }
}
