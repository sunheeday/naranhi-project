import { NextResponse } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { AdminApiError, listSchedulers } from '@/lib/admin/gcp'

/** 이중 방어 ②. 거절은 401 이 아니라 404 다 — /api/admin/* 전체가 지키는 정책
 *  (middleware.ts:adminGate, app/api/admin/jobs/route.ts와 동일). */
export async function GET() {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  try {
    return NextResponse.json({ ok: true, jobs: await listSchedulers() })
  } catch (error) {
    // GCP 쪽 실패(권한 없음 포함)를 조용히 200으로 덮지 않는다 — 그대로 상태코드를 올린다.
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
