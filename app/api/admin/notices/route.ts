import type { NextRequest } from 'next/server'
import { getAdminRepository } from '@/lib/admin/backend'
import { noticeInputSchema } from '@/lib/admin/backend/validation'
import { ok, invalid, serverError } from '@/lib/admin/backend/http'
import type { NoticeCategory, Audience } from '@/lib/admin/types'

export const dynamic = 'force-dynamic'

/** GET /api/admin/notices — 공지 목록 */
export async function GET() {
  try {
    return ok(await getAdminRepository().listNotices())
  } catch (e) {
    return serverError(e)
  }
}

/** POST /api/admin/notices — 공지 등록 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null)
  const parsed = noticeInputSchema.safeParse(body)
  if (!parsed.success) return invalid(parsed.error)

  try {
    const created = await getAdminRepository().createNotice({
      ...parsed.data,
      category: parsed.data.category as NoticeCategory,
      audience: parsed.data.audience as Audience,
    })
    return ok(created, 201)
  } catch (e) {
    return serverError(e)
  }
}
