import type { NextRequest } from 'next/server'
import { getAdminRepository } from '@/lib/admin/backend'
import { pinPatchSchema } from '@/lib/admin/backend/validation'
import { ok, fail, invalid, serverError } from '@/lib/admin/backend/http'

export const dynamic = 'force-dynamic'

interface RouteContext {
  params: Promise<{ id: string }>
}

/** PATCH /api/admin/notices/:id — 상단 고정 토글 */
export async function PATCH(request: NextRequest, context: RouteContext) {
  const { id } = await context.params
  if (!id) return fail('missing_id', 400)

  const body = await request.json().catch(() => null)
  const parsed = pinPatchSchema.safeParse(body)
  if (!parsed.success) return invalid(parsed.error)

  try {
    const updated = await getAdminRepository().setNoticePinned(id, parsed.data.pinned)
    if (!updated) return fail('notice_not_found', 404)
    return ok(updated)
  } catch (e) {
    return serverError(e)
  }
}

/** DELETE /api/admin/notices/:id — 공지 삭제 */
export async function DELETE(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params
  if (!id) return fail('missing_id', 400)

  try {
    const deleted = await getAdminRepository().deleteNotice(id)
    if (!deleted) return fail('notice_not_found', 404)
    return ok({ id })
  } catch (e) {
    return serverError(e)
  }
}
