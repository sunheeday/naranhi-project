import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { searchSchools } from '@/lib/neis'

export const runtime = 'nodejs'

export async function GET(req: NextRequest) {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) {
    return NextResponse.json({ error: '인증이 필요합니다.' }, { status: 401 })
  }

  const { searchParams } = new URL(req.url)
  const query = (searchParams.get('q') ?? '').trim()
  if (query.length < 2) {
    return NextResponse.json({ results: [] })
  }

  try {
    const results = await searchSchools(query)
    return NextResponse.json({ results })
  } catch (e) {
    console.error('[api/schools/search] failed:', e instanceof Error ? e.message : e)
    return NextResponse.json({ results: [], error: '학교 검색에 실패했어요.' }, { status: 500 })
  }
}
