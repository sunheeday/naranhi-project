import 'server-only'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'
import { pickTranslation, type Translations } from '@/lib/translations'
import type { CardType, Json, NoticeStatus } from '@/types/database'

/**
 * 공지 상세 조회용 DTO — 프론트(`/notices/[id]/page.tsx`)가 바로 소비할 수 있는 형태.
 */
/** 원본 첨부 파일 링크 (needs_file 일 때 "원본 파일 직접 확인"에서 사용) */
export interface NoticeFileLink {
  filename: string
  url: string
}

/** 소스(본문/첨부)별 카드 — 각 소스의 정제 본문을 따로 보여준다. */
export interface NoticeSourceCard {
  kind: 'body' | 'attachment'
  /** 첨부일 때 파일명(본문은 빈 문자열) */
  filename: string
  /** 정제된 markdown 본문(본문은 번역본 우선, 첨부는 한국어 정제본 — 번역은 후속 단계) */
  content: string
  /** 형식이 복잡해 정제본 대신 원본 파일을 안내해야 하는지 */
  needsFile: boolean
  /** 브라우저에서 미리보기 가능한 형식인지(PDF·이미지) */
  previewable: boolean
  /** 우리 Supabase Storage 의 파일 URL(첨부만) */
  publicUrl: string | null
}

/** 원본 파일 카드에 보여줄 첨부 파일(우리 Storage 사본). */
export interface NoticeAttachmentFile {
  filename: string
  publicUrl: string
  previewable: boolean
}

export interface NoticeDetailDto {
  id: string
  status: NoticeStatus
  errorMessage: string | null
  createdAt: string
  summary: string | null
  /** 요약(extracted_content.summary)이 생성돼 있는지 — 요약 카드 노출 여부 */
  hasSummary: boolean
  /** 사용자 locale에 해당 번역이 캐시돼 있는지 (lazy 번역 트리거용) */
  hasLocaleTranslation: boolean
  summaryTranslations: Translations
  cards: NoticeCardDto[]
  /** 정제 품질이 낮아(평탄화/할루시네이션 위험) 본문 대신 원본 파일을 안내해야 하는지 */
  needsFile: boolean
  /** 사용자가 직접 확인할 원본 첨부 파일들 */
  fileLinks: NoticeFileLink[]
  /** 본문/첨부 소스별 카드(순서: 본문 → 첨부…) */
  sourceCards: NoticeSourceCard[]
  /** 원본 파일 카드용 첨부 파일 목록(중복 파일 제거) */
  attachmentFiles: NoticeAttachmentFile[]
}

export interface NoticeCardDto {
  id: string
  type: CardType
  order: number
  content: Json
}

/**
 * 공지 + notice_cards JOIN 조회. RLS에 의해 본인 자녀의 학교 공지만 반환된다.
 * 인증된 사용자 세션(서버 컨텍스트)에서만 호출할 것.
 */
export async function getNoticeDetail(
  noticeId: string,
  locale: Locale = 'ko'
): Promise<NoticeDetailDto | null> {
  const supabase = await createSupabaseServerClient()

  const { data: notice, error } = await supabase
    .from('notices')
    .select(
      'id, status, error_message, created_at, title, original_text, extracted_content'
    )
    .eq('id', noticeId)
    .single()

  if (error || !notice) return null

  const translationQuery = supabase
    .from('notice_ai_translations')
    .select('target_language, translated_text')
    .eq('notice_id', noticeId)

  const { data: translationRows } = locale === 'ko'
    ? { data: [] }
    : await translationQuery.eq('target_language', locale)

  const { data: cardRows } = await supabase
    .from('notice_cards')
    .select('id, type, order, content')
    .eq('notice_id', noticeId)
    .order('order', { ascending: true })

  const cards: NoticeCardDto[] = (cardRows ?? []).map(r => ({
    id: r.id,
    type: r.type,
    order: r.order,
    content: r.content,
  }))

  const translations: Translations = {}
  if (notice.original_text) translations.ko = notice.original_text
  for (const row of translationRows ?? []) {
    if (row.target_language && row.translated_text) {
      translations[row.target_language] = row.translated_text
    }
  }
  const summary = pickTranslation(translations, locale) ?? notice.title ?? null

  const extracted = asJsonObject(notice.extracted_content)
  const needsFile = extracted?.needs_file === true
  const fileLinks = extractFileLinks(extracted)
  const sourceCards = buildSourceCards(extracted)
  const attachmentFiles = buildAttachmentFiles(extracted)
  const summaryObj = asJsonObject(extracted?.summary)
  const hasSummary = Boolean(summaryObj && typeof summaryObj.body === 'string' && summaryObj.body.trim())

  return {
    id: notice.id,
    status: notice.status,
    errorMessage: notice.error_message,
    createdAt: notice.created_at,
    summary,
    hasSummary,
    hasLocaleTranslation: locale === 'ko' ? Boolean(notice.original_text || notice.title) : !!translations[locale],
    summaryTranslations: translations,
    cards,
    needsFile,
    fileLinks,
    sourceCards,
    attachmentFiles,
  }
}

/** PDF·이미지면 브라우저 미리보기 가능. metadata.file_type 로 판단. */
function isPreviewable(source: Record<string, unknown>): boolean {
  const meta = asJsonObject(source.metadata)
  const fileType = typeof meta?.file_type === 'string' ? meta.file_type : ''
  return fileType === 'pdf' || fileType === 'image'
}

/** 본문에서 제목(#)·게시판메타(이름/등록일/조회수…)·첨부파일목록(첨부N, *.hwp 등)을 걷어내고
 *  실질 내용이 한 줄이라도 남는지. 없으면(제목·메타·첨부목록뿐이면) 본문 카드를 만들지 않는다. */
function bodyHasContent(text: string): boolean {
  const attachExt = /\.(hwp|hwpx|pdf|jpe?g|png|gif|docx?|xlsx?|pptx?|zip|hwt|txt)$/i
  const attachRef = /^\[?첨부\s*\d|^첨부파일/
  const metaLabel = /^(이름|성명|작성자|작성일|등록일|게시일|수정일|조회수|조회|추천|댓글|좋아요)\s*[:：]/
  for (const raw of text.split('\n')) {
    const s = raw.trim()
    if (!s) continue
    if (s.startsWith('#')) continue                  // 제목/소제목
    const core = s.replace(/^[-*•·\s]+/, '').trim()  // 불릿 제거
    if (!core) continue
    if (metaLabel.test(core)) continue               // 게시판 메타
    if (attachRef.test(core) || attachExt.test(core)) continue  // 첨부 파일 참조/목록
    return true                                       // 실질 내용 발견
  }
  return false
}

/** extracted_content.sources[] → 정제된 소스(본문 carrier + 첨부)를 본문→첨부 순의 카드로.
 *  본문(게시판 본문 + 사진)은 백엔드에서 carrier 한 곳에 합쳐지므로, refined_text 가 있는 소스만
 *  카드가 된다(합쳐진 본문 외의 inline_image 는 refined_text 가 없어 자동 제외). */
function buildSourceCards(
  extracted: Record<string, unknown> | null
): NoticeSourceCard[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const rows: (NoticeSourceCard & { _isBody: boolean; _order: number })[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    // 정제된 소스만 카드(본문 carrier + 첨부). 본문에 합쳐진 사진 등은 refined_text 가 없어 제외.
    if (typeof obj.refined_text !== 'string') continue
    const sourceType = obj.source_type
    const isBody = sourceType === 'html_body' || sourceType === 'inline_image'
    const refined = obj.refined_text
    // 본문·첨부 카드는 한국어 정제본(원본). 번역되는 표층은 맨 앞 '요약' 카드 하나다(요약→original_text→번역).
    const content = refined || ''
    // 본문에 제목·게시판메타·첨부목록만 있고 실질 내용이 없으면 본문 카드 생략.
    if (isBody && !bodyHasContent(content)) continue
    const meta = asJsonObject(obj.metadata)
    rows.push({
      kind: isBody ? 'body' : 'attachment',
      filename: typeof obj.filename === 'string' ? obj.filename : '',
      content,
      needsFile: obj.needs_file === true,
      previewable: isPreviewable(obj),
      publicUrl: typeof obj.public_url === 'string' ? obj.public_url : null,
      _isBody: isBody,
      _order: typeof meta?.order_index === 'number' ? meta.order_index : 999,
    })
  }
  rows.sort((a, b) => (a._isBody === b._isBody ? a._order - b._order : a._isBody ? -1 : 1))
  return rows.map(({ _isBody, _order, ...card }) => card)
}

/** extracted_content.sources[] → public_url 있는 첨부 파일들(중복 URL 제거). */
function buildAttachmentFiles(extracted: Record<string, unknown> | null): NoticeAttachmentFile[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const seen = new Set<string>()
  const files: NoticeAttachmentFile[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const url = typeof obj.public_url === 'string' ? obj.public_url.trim() : ''
    if (!url || seen.has(url)) continue
    seen.add(url)
    const filename = typeof obj.filename === 'string' && obj.filename.trim() ? obj.filename.trim() : 'attachment'
    files.push({ filename, publicUrl: url, previewable: isPreviewable(obj) })
  }
  return files
}

function asJsonObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** extracted_content.sources[] 에서 사용자가 열어볼 원본 첨부 파일(파일명+URL)을 추린다. */
function extractFileLinks(extracted: Record<string, unknown> | null): NoticeFileLink[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const links: NoticeFileLink[] = []
  const seen = new Set<string>()
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const url = typeof obj.origin_url === 'string' ? obj.origin_url.trim() : ''
    const filename = typeof obj.filename === 'string' ? obj.filename.trim() : ''
    if (!url || !filename || seen.has(url)) continue
    seen.add(url)
    links.push({ filename, url })
  }
  return links
}
