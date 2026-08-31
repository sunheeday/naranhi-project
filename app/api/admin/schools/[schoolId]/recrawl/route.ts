import { NextResponse, type NextRequest } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { executeRecrawl, previewRecrawl } from '@/lib/admin/recrawl'

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message === 'school_not_found'
}

/** 이중 방어 ②. 거절은 401 이 아니라 404 다 — /api/admin/* 전체가 지키는 정책
 *  (middleware.ts:adminGate, app/api/admin/jobs/route.ts, app/api/admin/schedulers/route.ts 와 동일). */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ schoolId: string }> },
) {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const { schoolId } = await params
  try {
    return NextResponse.json({ ok: true, preview: await previewRecrawl(schoolId) })
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: String(error) },
      { status: isNotFoundError(error) ? 404 : 500 },
    )
  }
}

/** 되돌릴 수 없는 작업이다: notices DELETE 가 translations/events/cards 를
 *  캐스케이드로 지운다(scripts/recrawl_trigger.py:51 은 확인 없이 이 DELETE 를
 *  던진다). 그래서 실행 전에 사람이 본 건수(confirmNoticeCount)를 서버가 지금
 *  건수와 다시 대조한다 — 다르면 409 로 되돌리고 새 숫자로 다시 묻는다.
 *
 *  ignoreWatermark 는 «따로 걸린 더 강한 확인» 이다: 체크박스 하나로 부족하므로
 *  학교 이름을 그대로 입력해야만(confirmSchoolName) 서버가 실행한다. 클라이언트
 *  확인만 믿지 않는다 — 스크립트로 body 를 직접 조작해도 이름이 맞아야 통과한다. */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ schoolId: string }> },
) {
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const { schoolId } = await params
  const body = await request.json().catch(() => null)
  const confirmed = Number(body?.confirmNoticeCount)
  const ignoreWatermark = body?.ignoreWatermark === true

  let preview
  try {
    preview = await previewRecrawl(schoolId)
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: String(error) },
      { status: isNotFoundError(error) ? 404 : 500 },
    )
  }

  // 사람이 본 숫자와 지금 숫자가 같아야 실행한다. 미리보기와 실행 사이에
  // 크롤이 돌아 건수가 바뀌었다면 다시 보여주고 다시 묻는다.
  if (!Number.isInteger(confirmed) || confirmed !== preview.noticeCount) {
    return NextResponse.json({ ok: false, error: 'preview_stale', preview }, { status: 409 })
  }

  if (ignoreWatermark && body?.confirmSchoolName !== preview.schoolName) {
    return NextResponse.json(
      { ok: false, error: 'ignore_watermark_confirmation_mismatch', preview },
      { status: 400 },
    )
  }

  let result
  try {
    result = await executeRecrawl(schoolId, { ignoreWatermark })
  } catch (error) {
    await writeAdminAudit(session, 'school_recrawl_failed', schoolId, {
      school: preview.schoolName,
      ignore_watermark: ignoreWatermark,
      error: String(error),
    })
    return NextResponse.json({ ok: false, error: String(error) }, { status: 500 })
  }

  await writeAdminAudit(session, 'school_recrawl', schoolId, {
    school: preview.schoolName,
    deleted_notices: result.deletedNotices,
    cascaded_translations: preview.translationCount,
    cascaded_events: preview.eventCount,
    cascaded_cards: preview.cardCount,
    watermark_had_boards: preview.watermarkBoards,
    watermark_ignored: ignoreWatermark,
    watermark_cleared: result.watermarkCleared,
    crawl_queued: result.crawlQueued,
  })

  return NextResponse.json({ ok: true, preview, result })
}
