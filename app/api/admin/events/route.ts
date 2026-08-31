import type { NextRequest } from 'next/server'
import { getAdminRepository } from '@/lib/admin/backend'
import { eventInputSchema } from '@/lib/admin/backend/validation'
import { ok, invalid, serverError } from '@/lib/admin/backend/http'
import type { EventType, Audience } from '@/lib/admin/types'

export const dynamic = 'force-dynamic'

/** GET /api/admin/events — 일정 목록 */
export async function GET() {
  try {
    return ok(await getAdminRepository().listEvents())
  } catch (e) {
    return serverError(e)
  }
}

/** POST /api/admin/events — 일정 등록 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null)
  const parsed = eventInputSchema.safeParse(body)
  if (!parsed.success) return invalid(parsed.error)

  try {
    const created = await getAdminRepository().createEvent({
      ...parsed.data,
      type: parsed.data.type as EventType,
      audience: parsed.data.audience as Audience,
    })
    return ok(created, 201)
  } catch (e) {
    return serverError(e)
  }
}
