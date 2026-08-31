import { NextResponse, type NextRequest } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { abandonAppJob, retryAppJob, toSafeJobView } from '@/lib/admin/jobs'

export async function POST(request: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  // 이중 방어 ②. GET /api/admin/jobs 와 동일하게 401 대신 404.
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const { jobId } = await params
  const body = await request.json().catch(() => null)
  const action = body?.action

  if (action !== 'retry' && action !== 'abandon') {
    return NextResponse.json({ ok: false, error: 'unknown_action' }, { status: 400 })
  }

  const result = action === 'retry' ? await retryAppJob(jobId) : await abandonAppJob(jobId)
  // 파괴적 조작(재시도/포기)의 사람별 추적. job_key 는 id 조합 문자열이라
  // (backend/app/api/notices.py:196 등) 개인정보가 아니다 — writeAdminAudit 은
  // 받은 detail 을 그대로 적재하므로 여기서 안전한 값만 넘긴다.
  await writeAdminAudit(session, `job_${action}`, jobId, {
    ok: result.ok,
    detail: result.ok ? result.job.job_key : result.error,
  })

  if (!result.ok) {
    return NextResponse.json({ ok: false, error: result.error }, { status: 409 })
  }
  return NextResponse.json({ ok: true, job: toSafeJobView(result.job) })
}
