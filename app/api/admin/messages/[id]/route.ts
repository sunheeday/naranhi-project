import type { NextRequest } from 'next/server'
import { getAdminRepository } from '@/lib/admin/backend'
import { ok, fail, serverError } from '@/lib/admin/backend/http'

export const dynamic = 'force-dynamic'

interface RouteContext {
  params: Promise<{ id: string }>
}

/** DELETE /api/admin/messages/:id — 메시지 삭제 */
export async function DELETE(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params
  if (!id) return fail('missing_id', 400)

  try {
    const deleted = await getAdminRepository().deleteMessage(id)
    if (!deleted) return fail('message_not_found', 404)
    return ok({ id })
  } catch (e) {
    return serverError(e)
  }
}
