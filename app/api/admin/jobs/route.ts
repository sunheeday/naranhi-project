import { NextResponse, type NextRequest } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { countAppJobsByStatus, listAppJobs, toSafeJobView } from '@/lib/admin/jobs'
import type { AppJobStatus } from '@/types/database'

const STATUSES = new Set<AppJobStatus>(['queued', 'processing', 'completed', 'failed'])

export async function GET(request: NextRequest) {
  // 이중 방어 ②. middleware(adminGate)는 쿠키 존재만 봤다. 여기서는 실제 세션을
  // 검증하고, 거절이면 401 이 아니라 404 를 낸다 — 미들웨어가 무쿠키 요청에
  // /api/admin/* 전체를 404 로 응답하는 것(middleware.ts:41-51, db857f7)과 같은
  // 정책이다. 여기서만 401 이면 "인증하면 뭔가 있다"는 힌트가 이 한 곳에서 샌다.
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const params = request.nextUrl.searchParams
  const statusParam = params.get('status')
  const status =
    statusParam && STATUSES.has(statusParam as AppJobStatus) ? (statusParam as AppJobStatus) : undefined

  const [jobs, counts] = await Promise.all([
    listAppJobs({ jobType: params.get('job_type') ?? undefined, status }),
    countAppJobsByStatus(),
  ])

  // 원본 row(payload/last_error 포함)를 그대로 내보내지 않는다. payload 에는
  // 공지 원문(source_text)까지 실릴 수 있고(backend/app/api/notices.py:148-154),
  // last_error 는 로깅 계층의 sanitize_error 를 거치지 않은 원문 예외 메시지다.
  return NextResponse.json({ ok: true, jobs: jobs.map(toSafeJobView), counts })
}
