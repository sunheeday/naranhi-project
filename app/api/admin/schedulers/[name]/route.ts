import { NextResponse, type NextRequest } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { AdminApiError, setSchedulerState } from '@/lib/admin/gcp'

/** 이중 방어 ②. 거절은 401 이 아니라 404 다 — /api/admin/* 전체가 지키는 정책
 *  (middleware.ts:adminGate, app/api/admin/jobs/[jobId]/route.ts와 동일). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ name: string }> }) {
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const { name } = await params
  const body = await request.json().catch(() => null)
  const action = body?.action
  if (action !== 'pause' && action !== 'resume') {
    return NextResponse.json({ ok: false, error: 'unknown_action' }, { status: 400 })
  }

  try {
    const job = await setSchedulerState(name, action, session.adminUserId)
    // 성공 감사 로그는 여기서 다시 남기지 않는다 — FastAPI 가 X-Admin-Actor 로 이미
    // admin_audit_log 에 scheduler_pause/scheduler_resume 1행을 남긴다
    // (backend/app/services/gcp_admin_service.py:record_admin_action, 성공했을 때만
    // 호출됨). 여기서도 writeAdminAudit 을 부르면 같은 사건이 두 번 남는다.
    return NextResponse.json({ ok: true, job })
  } catch (error) {
    // 실패는 FastAPI 의 record_admin_action 에 절대 도달하지 않는다(_wrap 이
    // HTTPException 을 먼저 던진다) — 실패 흔적은 이 쪽에서 남기지 않으면 사라진다.
    // 정지 시도가 화이트리스트 밖이거나(403) GCP 권한 문제(502)여도 "무엇을
    // 시도했는지"는 감사 로그에 남아야 한다.
    await writeAdminAudit(session, `scheduler_${action}_failed`, name, { error: String(error) })
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
