import { getAdminRepository } from '@/lib/admin/backend'
import { ok, serverError } from '@/lib/admin/backend/http'

export const dynamic = 'force-dynamic'

/** POST /api/admin/reset — 데모 데이터를 시드 상태로 초기화(인메모리 전용) */
export async function POST() {
  try {
    return ok(await getAdminRepository().reset())
  } catch (e) {
    return serverError(e)
  }
}
