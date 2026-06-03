import { NextResponse, type NextRequest } from 'next/server'
import { isValidLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'

interface RequestBody {
  noticeIds?: unknown
  targetLanguage?: unknown
}

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const body = (await request.json().catch(() => ({}))) as RequestBody
  const targetLanguage = typeof body.targetLanguage === 'string' ? body.targetLanguage : ''
  if (!isValidLocale(targetLanguage)) {
    return NextResponse.json({ ok: false, error: 'invalid_target_language' }, { status: 400 })
  }

  const noticeIds = Array.isArray(body.noticeIds)
    ? Array.from(new Set(body.noticeIds.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)))
    : []
  if (noticeIds.length === 0) {
    return NextResponse.json({
      ok: true,
      targetLanguage,
      total: 0,
      completedCount: 0,
      pendingCount: 0,
      complete: true,
      pendingNoticeIds: [],
    })
  }

  const { data: rows, error } = await supabase
    .from('notice_ai_translations')
    .select('notice_id, translated_text, validation_status')
    .eq('target_language', targetLanguage)
    .in('notice_id', noticeIds)

  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 })
  }

  const completedIds = new Set(
    (rows ?? [])
      .filter(row => row.translated_text && row.validation_status !== 'failed')
      .map(row => row.notice_id)
      .filter((value): value is string => typeof value === 'string' && value.length > 0)
  )

  const pendingNoticeIds = noticeIds.filter(noticeId => !completedIds.has(noticeId))

  return NextResponse.json({
    ok: true,
    targetLanguage,
    total: noticeIds.length,
    completedCount: completedIds.size,
    pendingCount: pendingNoticeIds.length,
    complete: pendingNoticeIds.length === 0,
    pendingNoticeIds,
  })
}
