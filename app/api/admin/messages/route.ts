import type { NextRequest } from 'next/server'
import { getAdminRepository } from '@/lib/admin/backend'
import { messageInputSchema } from '@/lib/admin/backend/validation'
import { ok, invalid, serverError } from '@/lib/admin/backend/http'
import type { Audience } from '@/lib/admin/types'

export const dynamic = 'force-dynamic'

/** GET /api/admin/messages — 보낸 메시지 목록 */
export async function GET() {
  try {
    return ok(await getAdminRepository().listMessages())
  } catch (e) {
    return serverError(e)
  }
}

/** POST /api/admin/messages — 메시지 보내기 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null)
  const parsed = messageInputSchema.safeParse(body)
  if (!parsed.success) return invalid(parsed.error)

  try {
    const created = await getAdminRepository().createMessage({
      ...parsed.data,
      audience: parsed.data.audience as Audience,
    })
    return ok(created, 201)
  } catch (e) {
    return serverError(e)
  }
}
