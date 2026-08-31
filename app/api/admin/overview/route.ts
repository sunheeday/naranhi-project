import { getAdminRepository } from '@/lib/admin/backend'
import { ok, serverError } from '@/lib/admin/backend/http'

export const dynamic = 'force-dynamic'

/** GET /api/admin/overview — 대시보드/목록용 전체 스냅샷 */
export async function GET() {
  try {
    const data = await getAdminRepository().getOverview()
    return ok(data)
  } catch (e) {
    return serverError(e)
  }
}
