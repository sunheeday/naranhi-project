import { NextResponse, type NextRequest } from 'next/server'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'

const BUCKET = 'notice-attachments'
const SIGNED_URL_TTL_SECONDS = 300

interface RouteContext {
  params: Promise<{ noticeId: string; sourceId: string }>
}

function notFound() {
  return NextResponse.json({ error: 'not_found' }, { status: 404 })
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/**
 * 첨부 다운로드. 로그인한 사용자가 해당 학교에 자녀를 등록한 경우에만
 * 단명(5분) 서명 URL 로 리다이렉트한다. 권한이 없으면 존재 여부도 알리지 않는다(404).
 *
 * 오브젝트 경로는 사용자 입력에서 받지 않는다 — 공지 id + source_id 로 DB 에서 읽는다.
 * `?download` 가 붙으면 첨부로 내려받고, 없으면 브라우저 미리보기(inline).
 */
export async function GET(request: NextRequest, context: RouteContext) {
  const { noticeId, sourceId } = await context.params
  if (!noticeId || !sourceId) return notFound()

  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return notFound()

  const service = createSupabaseServiceClient()

  const { data: notice } = await service
    .from('notices')
    .select('id, school_id, extracted_content')
    .eq('id', noticeId)
    .maybeSingle()
  if (!notice?.school_id) return notFound()

  // 접근 검사: 요청자가 그 학교에 자녀를 등록한 학부모인가.
  const { data: children } = await service
    .from('children')
    .select('id')
    .eq('user_id', user.id)
    .eq('school_id', notice.school_id)
    .limit(1)
  if (!children || children.length === 0) return notFound()

  const extracted = asRecord(notice.extracted_content)
  const sources = Array.isArray(extracted?.sources) ? extracted.sources : []
  const source = sources
    .map(asRecord)
    .find(obj => obj !== null && obj.source_id === sourceId)

  const storagePath = typeof source?.storage_path === 'string' ? source.storage_path.trim() : ''
  if (!storagePath) return notFound()

  // 파일명은 DB 값만 쓴다(쿼리 값은 다운로드 여부 스위치로만 쓴다).
  const filename = typeof source?.filename === 'string' && source.filename.trim()
    ? source.filename.trim()
    : ''
  const wantsDownload = request.nextUrl.searchParams.has('download')

  const { data: signed, error } = await service.storage
    .from(BUCKET)
    .createSignedUrl(
      storagePath,
      SIGNED_URL_TTL_SECONDS,
      wantsDownload && filename ? { download: filename } : undefined,
    )

  if (error || !signed?.signedUrl) return notFound()

  const response = NextResponse.redirect(signed.signedUrl, 302)
  response.headers.set('Cache-Control', 'no-store')
  return response
}
