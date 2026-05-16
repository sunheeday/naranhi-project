import { NextResponse } from 'next/server'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { schoolNeedsInitialCrawl, triggerInitialSchoolCrawl } from '@/lib/school-crawler-trigger'

interface RouteContext {
  params: Promise<{ schoolId: string }>
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

  const { data: child, error: childError } = await supabase
    .from('children')
    .select('id')
    .eq('user_id', user.id)
    .eq('school_id', schoolId)
    .limit(1)
    .maybeSingle()

  if (childError) {
    return NextResponse.json({ ok: false, error: 'child_lookup_failed' }, { status: 500 })
  }

  if (!child) {
    return NextResponse.json({ ok: false, error: 'school_not_allowed' }, { status: 403 })
  }

  const { data: school, error: schoolError } = await supabase
    .from('schools')
    .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
    .eq('id', schoolId)
    .maybeSingle()

  if (schoolError) {
    return NextResponse.json({ ok: false, error: 'school_lookup_failed' }, { status: 500 })
  }

  if (!school) {
    return NextResponse.json({ ok: false, error: 'school_not_found' }, { status: 404 })
  }

  if (!schoolNeedsInitialCrawl(school)) {
    return NextResponse.json({ ok: true, skipped: true })
  }

  await triggerInitialSchoolCrawl(schoolId)
  return NextResponse.json({ ok: true, skipped: false })
}
