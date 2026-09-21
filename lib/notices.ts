import 'server-only'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import { ensureTestBypassChild, isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'
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
  /** 첨부 서명 URL 발급 라우트 경로(첨부만). 실제 Storage URL 이 아니다. */
  publicUrl: string | null
}

/** 원본 파일 카드에 보여줄 첨부 파일(우리 Storage 사본). */
export interface NoticeAttachmentFile {
  filename: string
  /** 첨부 서명 URL 발급 라우트 경로(`/api/notices/…/attachments/…`). */
  publicUrl: string
  previewable: boolean
}

/** 번역 잡의 최근 상태 — 실패면 상세 화면이 '준비중' 대신 실패+재시도 배너를 띄운다. */
export type TranslationJobStatus = 'none' | 'queued' | 'processing' | 'completed' | 'failed'

export async function fetchTranslationJobStatus(
  noticeId: string,
  locale: Locale,
): Promise<TranslationJobStatus> {
  if (locale === 'ko') return 'none'
  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')
  if (!apiBase) return 'none'

  try {
    const res = await fetch(
      `${apiBase}/notices/${encodeURIComponent(noticeId)}/translate/status?target_language=${encodeURIComponent(locale)}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return 'none'
    const body = (await res.json().catch(() => null)) as { job_status?: string } | null
    const status = body?.job_status
    if (status === 'queued' || status === 'processing' || status === 'completed' || status === 'failed') {
      return status
    }
    return 'none'
  } catch {
    // 상태 조회 실패는 표시용 정보라 조용히 '없음'으로 처리한다.
    return 'none'
  }
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
  const sessionClient = await createSupabaseServerClient()
  let supabase = sessionClient

  // 시연 방문자(로그인 없음)는 RLS 가 아무것도 열어주지 않는다 — 서버 권한으로 읽는다.
  // 스위치가 꺼져 있으면 아래 분기는 실행되지 않는다(getUser 왕복도 없다).
  let isDemoVisitor = false
  let demoSchoolId: string | null = null
  if (isTestEntryBypassEnabled()) {
    const { data: { user } } = await sessionClient.auth.getUser()
    if (!user) {
      supabase = createSupabaseServiceClient()
      isDemoVisitor = true
      demoSchoolId = (await ensureTestBypassChild()).school_id
    }
  }

  const { data: notice, error } = await supabase
    .from('notices')
    .select(
      'id, school_id, status, error_message, created_at, title, original_text, extracted_content'
    )
    .eq('id', noticeId)
    .single()

  if (error || !notice) return null
  // 서버 권한은 RLS 를 건너뛰므로, 시연 방문자가 지금 고른 학교의 공지만 연다.
  // (다른 사용자가 촬영해 올린 공지가 주소만 알면 열리는 것을 막는다.)
  // 학교 id 가 비어 있으면(있을 수 없는 경우지만) 열지 않는다 — 실패하면 «닫힘» 이어야 한다.
  if (isDemoVisitor && (demoSchoolId === null || notice.school_id !== demoSchoolId)) return null

  const translationQuery = supabase
    .from('notice_ai_translations')
    .select('target_language, translated_title, translated_text')
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

  const cardTranslationRows = locale !== 'ko' && cards.length > 0
    ? (await supabase
        .from('notice_card_translations')
        .select('notice_card_id, translated_content')
        .eq('target_language', locale)
        .in('notice_card_id', cards.map(card => card.id))).data ?? []
    : []

  const translations: Translations = {}
  const translatedTitles: Translations = {}
  if (notice.original_text) translations.ko = notice.original_text
  for (const row of translationRows ?? []) {
    if (row.target_language && row.translated_text) {
      translations[row.target_language] = row.translated_text
    }
    if (row.target_language && row.translated_title) {
      translatedTitles[row.target_language] = row.translated_title
    }
  }
  const translatedBodyText = locale === 'ko' ? null : (translations[locale] ?? null)
  const cardTranslationsById = new Map<string, Json>()
  for (const row of cardTranslationRows) {
    if (typeof row.notice_card_id === 'string') {
      cardTranslationsById.set(row.notice_card_id, row.translated_content)
    }
  }
  let localizedCardCount = 0
  for (const card of cards) {
    const translatedContent = cardTranslationsById.get(card.id)
    const canonicalContent = (asJsonObject(card.content)?.ko ?? card.content) as Json
    if (translatedContent !== undefined) {
      card.content = {
        ko: canonicalContent,
        [locale]: translatedContent,
      } as Json
      localizedCardCount += 1
      continue
    }
    card.content = canonicalContent
  }
  const extracted = asJsonObject(notice.extracted_content)
  const needsFile = extracted?.needs_file === true
  const fileLinks = extractFileLinks(extracted)
  const sourceCards = buildSourceCards(extracted, locale, translatedBodyText, notice.id)
  const attachmentFiles = buildAttachmentFiles(extracted, notice.id)
  const summaryObj = asJsonObject(extracted?.summary)
  const hasSummary = Boolean(summaryObj && typeof summaryObj.rendered === 'string' && summaryObj.rendered.trim())
  // 요약 텍스트 = extracted_content.summary 의 렌더 텍스트(ko) + 번역(다른 언어).
  // original_text 는 이제 '풀 본문'(팀 구조화/번역 입력)이라 요약은 여기서 따로 읽는다.
  const summary = pickTranslation(summaryTextMap(summaryObj), locale)
    ?? pickTranslation(translatedTitles, locale)
    ?? notice.title
    ?? null
  const hasCompleteSourceTranslations = locale === 'ko'
    ? true
    : hasCompleteTranslatedSources(extracted, locale)

  return {
    id: notice.id,
    status: notice.status,
    errorMessage: notice.error_message,
    createdAt: notice.created_at,
    summary,
    hasSummary,
    hasLocaleTranslation: locale === 'ko'
      ? Boolean(notice.original_text || notice.title)
      : Boolean(translations[locale])
        && (cards.length === 0 || localizedCardCount >= cards.length)
        && hasCompleteSourceTranslations,
    summaryTranslations: translations,
    cards,
    needsFile,
    fileLinks,
    sourceCards,
    attachmentFiles,
  }
}

function hasCompleteTranslatedSources(
  extracted: Record<string, unknown> | null,
  locale: Locale,
): boolean {
  if (!extracted) return true

  const summary = asJsonObject(extracted.summary)
  const summaryRendered = typeof summary?.rendered === 'string' ? summary.rendered.trim() : ''
  if (summaryRendered) {
    const summaryTranslations = asJsonObject(summary?.translations)
    const localizedSummary = typeof summaryTranslations?.[locale] === 'string'
      ? summaryTranslations[locale].trim()
      : ''
    if (!localizedSummary) {
      return false
    }
  }

  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  for (const source of sources) {
    const sourceObj = asJsonObject(source)
    const refinedText = typeof sourceObj?.refined_text === 'string' ? sourceObj.refined_text.trim() : ''
    if (!refinedText) continue
    const translations = asJsonObject(sourceObj?.translations)
    const localized = typeof translations?.[locale] === 'string' ? translations[locale].trim() : ''
    if (!localized) {
      return false
    }
  }

  return true
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
  extracted: Record<string, unknown> | null,
  locale: Locale,
  translatedBodyText: string | null,
  noticeId: string,
): NoticeSourceCard[] {
  if (!extracted) {
    return translatedBodyText
      ? [{
          kind: 'body',
          filename: '',
          content: translatedBodyText,
          needsFile: false,
          previewable: false,
          publicUrl: null,
        }]
      : []
  }
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const rows: (NoticeSourceCard & { _isBody: boolean; _order: number })[] = []
  let usedTranslatedBodyText = false
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    // 정제된 소스만 카드(본문 carrier + 첨부). 본문에 합쳐진 사진 등은 refined_text 가 없어 제외.
    if (typeof obj.refined_text !== 'string') continue
    const sourceType = obj.source_type
    const isBody = sourceType === 'html_body' || sourceType === 'inline_image'
    const refined = obj.refined_text
    // 빈 본문 판정은 한국어 정제본 기준(제목·메타·첨부목록 패턴이 한국어라서).
    if (isBody && !bodyHasContent(refined)) continue
    // 표시 본문 = 소스별 번역(있으면) → 없으면 한국어 정제본.
    const localized = asJsonObject(obj.translations)?.[locale]
    const content = (
      isBody && translatedBodyText
        ? translatedBodyText
        : typeof localized === 'string' && localized.trim()
          ? localized
          : refined
    ) || ''
    if (isBody && translatedBodyText) {
      usedTranslatedBodyText = true
    }
    const meta = asJsonObject(obj.metadata)
    rows.push({
      kind: isBody ? 'body' : 'attachment',
      filename: typeof obj.filename === 'string' ? obj.filename : '',
      content,
      needsFile: obj.needs_file === true,
      previewable: isPreviewable(obj),
      publicUrl: typeof obj.source_id === 'string' && obj.source_id.trim() && typeof obj.storage_path === 'string' && obj.storage_path.trim()
        ? attachmentRoute(noticeId, obj.source_id.trim())
        : null,
      _isBody: isBody,
      _order: typeof meta?.order_index === 'number' ? meta.order_index : 999,
    })
  }
  if (translatedBodyText && !usedTranslatedBodyText) {
    rows.unshift({
      kind: 'body',
      filename: '',
      content: translatedBodyText,
      needsFile: false,
      previewable: false,
      publicUrl: null,
      _isBody: true,
      _order: -1,
    })
  }
  rows.sort((a, b) => (a._isBody === b._isBody ? a._order - b._order : a._isBody ? -1 : 1))
  return rows.map(({ _isBody, _order, ...card }) => card)
}

/** 요약 카드 텍스트 맵: ko=summary.rendered, 그 외=summary.translations[lang].
 *  pickTranslation 으로 사용자 locale → ko fallback 선택한다. */
function summaryTextMap(summary: Record<string, unknown> | null): Translations {
  const map: Translations = {}
  if (!summary) return map
  if (typeof summary.rendered === 'string') map.ko = summary.rendered
  const i18n = asJsonObject(summary.translations)
  if (i18n) {
    for (const [k, v] of Object.entries(i18n)) {
      if (typeof v === 'string') map[k] = v
    }
  }
  return map
}

/** extracted_content.sources[] → 첨부 다운로드 경로(중복 제거).
 *  실제 URL 은 저장하지 않는다. 접근 검사를 거쳐 서명 URL 을 내주는 라우트를 가리킨다. */
function buildAttachmentFiles(
  extracted: Record<string, unknown> | null,
  noticeId: string,
): NoticeAttachmentFile[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const seen = new Set<string>()
  const files: NoticeAttachmentFile[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const storagePath = typeof obj.storage_path === 'string' ? obj.storage_path.trim() : ''
    const sourceId = typeof obj.source_id === 'string' ? obj.source_id.trim() : ''
    if (!storagePath || !sourceId || seen.has(sourceId)) continue
    seen.add(sourceId)
    const filename = typeof obj.filename === 'string' && obj.filename.trim() ? obj.filename.trim() : 'attachment'
    files.push({
      filename,
      publicUrl: attachmentRoute(noticeId, sourceId),
      previewable: isPreviewable(obj),
    })
  }
  return files
}

/** 첨부 서명 URL 발급 라우트 경로. */
function attachmentRoute(noticeId: string, sourceId: string): string {
  return `/api/notices/${encodeURIComponent(noticeId)}/attachments/${encodeURIComponent(sourceId)}`
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
