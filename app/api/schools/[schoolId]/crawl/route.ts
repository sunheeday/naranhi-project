import { NextResponse } from 'next/server'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  triggerPendingSchoolExtraction,
} from '@/lib/school-crawler-trigger'

interface RouteContext {
  params: Promise<{ schoolId: string }>
}

interface SchoolStateRow {
  id: string
  crawl_status: string | null
  crawl_board_url: string | null
  crawl_last_checked_at: string | null
}

interface ChildSchoolLookupRow {
  id: string
  schools: SchoolStateRow | SchoolStateRow[] | null
}

export async function POST(_request: Request, context: RouteContext) {
  const { schoolId } = await context.params
  if (!schoolId) {
    return NextResponse.json({ ok: false, error: 'missing_school_id' }, { status: 400 })
  }

  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { data: lookupRow, error: lookupError } = await supabase
    .from('children')
    .select(`
      id,
      schools!inner (
        id,
        crawl_status,
        crawl_board_url,
        crawl_last_checked_at
      )
    `)
    .eq('user_id', user.id)
    .eq('school_id', schoolId)
    .limit(1)
    .maybeSingle()

  if (lookupError) {
    return NextResponse.json({ ok: false, error: 'school_lookup_failed' }, { status: 500 })
  }

  if (!lookupRow) {
    return NextResponse.json({ ok: false, error: 'school_not_allowed' }, { status: 403 })
  }

  const childWithSchool = lookupRow as unknown as ChildSchoolLookupRow
  const school = Array.isArray(childWithSchool.schools)
    ? childWithSchool.schools[0]
    : childWithSchool.schools
  if (!school) {
    return NextResponse.json({ ok: false, error: 'school_not_found' }, { status: 404 })
  }

  const { count: pendingNoticeCount, error: pendingCountError } = await supabase
    .from('notices')
    .select('id', { count: 'exact', head: true })
    .eq('school_id', schoolId)
    .eq('status', 'pending')

  if (pendingCountError) {
    return NextResponse.json({ ok: false, error: 'pending_notice_lookup_failed' }, { status: 500 })
  }

  const pendingCount = pendingNoticeCount ?? 0

  if (!schoolNeedsInitialCrawl(school)) {
    const extractionQueued = pendingCount > 0
      ? await triggerPendingSchoolExtraction(schoolId, Math.min(pendingCount, 20))
      : false
    return NextResponse.json({
      ok: true,
      skipped: true,
      extractionQueued,
      pendingCount,
    })
  }

  const crawlQueued = await triggerInitialSchoolCrawl(schoolId)
  return NextResponse.json({
    ok: true,
    skipped: false,
    crawlQueued,
    extractionQueued: crawlQueued,
    pendingCount,
  })
}
