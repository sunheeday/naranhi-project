import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { AppJobStatus, Database } from '@/types/database'

export type AppJobRow = Database['public']['Tables']['app_jobs']['Row']

const JOB_COLUMNS =
  'id,job_type,job_key,status,attempts,max_attempts,available_at,started_at,finished_at,last_error,result,payload,created_at,updated_at'

/** 페이징을 만들지 않는다 — 필터(job_type/status)로 좁혀 보는 것으로 충분하다는
 *  브리프(task-10-brief.md)의 판단을 따르되, 브리프가 박아 둔 구체적 운영 행수는
 *  스냅샷일 뿐이라 그대로 믿지 않는다(크롤 스케줄러가 계속 돌아 늘어난다).
 *  대신 넉넉한 상한만 둔다. */
const DEFAULT_LIMIT = 300

export interface JobListFilter {
  jobType?: string
  status?: AppJobStatus
  limit?: number
}

export async function listAppJobs(filter: JobListFilter = {}): Promise<AppJobRow[]> {
  const service = createSupabaseServiceClient()
  let query = service
    .from('app_jobs')
    .select(JOB_COLUMNS)
    .order('created_at', { ascending: false })
    .limit(filter.limit ?? DEFAULT_LIMIT)
  if (filter.jobType) query = query.eq('job_type', filter.jobType)
  if (filter.status) query = query.eq('status', filter.status)

  const { data, error } = await query
  if (error) throw new Error(`잡 목록 조회 실패: ${error.message}`)
  return (data ?? []) as AppJobRow[]
}

const ALL_STATUSES: AppJobStatus[] = ['queued', 'processing', 'completed', 'failed']

/** COUNT 만 셋다(head:true) — app_jobs 전체를 끌어와 메모리에서 세지 않는다.
 *  4개 상태를 병렬로 묻는다. */
export async function countAppJobsByStatus(): Promise<Record<AppJobStatus, number>> {
  const service = createSupabaseServiceClient()
  const results = await Promise.all(
    ALL_STATUSES.map((status) =>
      service.from('app_jobs').select('id', { count: 'exact', head: true }).eq('status', status),
    ),
  )
  const counts = { queued: 0, processing: 0, completed: 0, failed: 0 }
  results.forEach(({ count, error }, index) => {
    if (error) throw new Error(`잡 상태 집계 실패: ${error.message}`)
    counts[ALL_STATUSES[index]] = count ?? 0
  })
  return counts
}

/** 재시도. failed 인 잡만 되살린다.
 *
 *  attempts 는 되돌리지 않는다. claim(job_queue_service.py:198)이 attempts+1 을 하고
 *  fail(job_queue_service.py:256-)이 attempts < max_attempts 로 재시도 여부를 정하므로,
 *  이미 소진된 잡은 «딱 한 번 더» 돌고 다시 failed 가 된다 — 무한 재시도를 만들지 않는다.
 *
 *  job_key unique index(0027, status in ('queued','processing'))가 같은 job_key 로
 *  이미 도는 잡이 있으면 23505 를 낸다. 조용히 삼키지 않고 사유를 돌려준다. */
export async function retryAppJob(
  jobId: string,
): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }> {
  const service = createSupabaseServiceClient()
  const now = new Date().toISOString()
  const { data, error } = await service
    .from('app_jobs')
    .update({ status: 'queued', available_at: now, last_error: null, updated_at: now })
    .eq('id', jobId)
    .eq('status', 'failed')
    .select(JOB_COLUMNS)
    .maybeSingle()

  if (error) {
    if (error.code === '23505') {
      return { ok: false, error: 'job_key_already_active' }
    }
    return { ok: false, error: error.message }
  }
  if (!data) return { ok: false, error: 'not_failed_or_not_found' }
  return { ok: true, job: data as AppJobRow }
}

/** 포기. 큐에 남아 워커를 계속 물어뜯는(또는 좀비로 멈춘) 잡을 끊는다. */
export async function abandonAppJob(
  jobId: string,
): Promise<{ ok: true; job: AppJobRow } | { ok: false; error: string }> {
  const service = createSupabaseServiceClient()
  const now = new Date().toISOString()
  const { data, error } = await service
    .from('app_jobs')
    .update({ status: 'failed', finished_at: now, updated_at: now })
    .eq('id', jobId)
    .in('status', ['queued', 'processing'])
    .select(JOB_COLUMNS)
    .maybeSingle()

  if (error) return { ok: false, error: error.message }
  if (!data) return { ok: false, error: 'not_active_or_not_found' }
  return { ok: true, job: data as AppJobRow }
}

// ---------------------------------------------------------------------------
// 화면·API 응답에 실제로 내보내는 값 — 여기서부터는 전부 "개인정보를 화면에 붓지
// 않는다"는 요구를 지키기 위한 코드다.
// ---------------------------------------------------------------------------

/** app_jobs 를 실제로 enqueue 하는 곳 전부(2026-08-29 기준 grep 실측):
 *  backend/app/api/crawler.py:49,79, backend/app/api/notices.py:146,
 *  backend/app/services/content_extraction_service.py:929.
 *  이 목록 밖의 job_type 은 payload 구조를 모른다는 뜻이라 extractSafePayload 가
 *  자동으로 빈 값을 낸다 — 모르는 필드를 추측해 보여주지 않는다(화이트리스트,
 *  블랙리스트 아님). */
const KNOWN_JOB_TYPES = [
  'notice_translation',
  'school_board_discovery',
  'school_notice_extraction',
] as const

/** backend/app/core/config.py:223 WORKER_JOB_STALE_MINUTES 기본값(180분)과 맞춘다.
 *  워커의 reclaim_stale_jobs(backend/app/services/job_queue_service.py:135)가
 *  started_at 이 이보다 오래된 processing 잡을 좀비로 보고 회수한다 — 화면의
 *  "오래됨(좀비 의심)" 표시도 같은 기준을 쓴다(숫자를 새로 지어내지 않는다). */
export const STALE_PROCESSING_MINUTES = 180

/** backend/extractor/http_security.py 의 sanitize_error 를 TS 쪽에서 다시 구현한 것.
 *
 *  app_jobs.last_error 는 워커가 `f"{type(exc).__name__}: {exc}"` 를 그대로 적재한다
 *  (backend/app/jobs/translation_worker.py:91,95, backend/app/jobs/crawler_worker.py:94,98).
 *  로깅 계층의 sanitize_error(backend/app/core/logging_setup.py:90-99)는 로그 "줄"에만
 *  적용되고 이 DB 컬럼에는 전혀 적용되지 않는다 — 즉 last_error 에는 이미 열쇠가 섞여
 *  들어와 있을 수 있다(예: Gemini 요청 URL 의 key=..., x-goog-api-key=...). 화면·API
 *  응답에 내보내기 전에 여기서 한 번 더 가린다. */
function sanitizeLastError(raw: string | null): string | null {
  if (!raw) return null
  let text = raw
  text = text.replace(/(x-goog-api-key=)[^&\s]+/gi, '$1[REDACTED]')
  text = text.replace(/([?&]key=)[^&\s]+/gi, '$1[REDACTED]')
  text = text.replace(/(bearer\s+)[a-z0-9._-]+/gi, '$1[REDACTED]')
  text = text.replace(/(authorization["'\s:=]+)[^\s"',}]+/gi, '$1[REDACTED]')
  // DB 자체도 job_queue_service.fail()에서 1000자로 자른다(job_queue_service.py:270).
  // 화면 한 줄에는 더 짧게 자른다.
  return text.length > 400 ? `${text.slice(0, 400)}…` : text
}

/** payload 는 job_type 마다 구조가 다르고, notice_translation 은 요청에 따라
 *  source_text(공지 원문 전체) · approved_ingredient_dictionary 까지 담을 수 있다
 *  (backend/app/api/notices.py:148-154) — 브리프가 "payload 에는 공지 id·언어만
 *  있다"고 적은 것과 달리, 실제로는 원문 전체가 실리는 경로가 있다. payload 를
 *  통째로 보여주면 그 원문이 관리자 화면에 그대로 뜬다. 그래서 job_type 별로
 *  "안전하다"고 직접 확인한 키만 화이트리스트로 뽑는다 — 전부 id/언어코드/개수
 *  같은 스칼라이고, 텍스트 본문류는 이 목록에 없다. */
function extractSafePayload(jobType: string, payload: unknown): Record<string, string | number> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {}
  const record = payload as Record<string, unknown>
  const pick = (keys: string[]): Record<string, string | number> => {
    const out: Record<string, string | number> = {}
    for (const key of keys) {
      const value = record[key]
      if (typeof value === 'string' || typeof value === 'number') out[key] = value
    }
    return out
  }
  switch (jobType) {
    case 'notice_translation':
      return pick(['notice_id', 'target_language'])
    case 'school_board_discovery':
      return pick(['school_id', 'max_posts'])
    case 'school_notice_extraction':
      return pick(['school_id', 'max_notices'])
    default:
      return {}
  }
}

export interface SafeJobView {
  id: string
  jobType: string
  jobKey: string
  status: string
  attempts: number
  maxAttempts: number
  createdAt: string
  availableAt: string
  startedAt: string | null
  finishedAt: string | null
  updatedAt: string
  lastError: string | null
  safePayload: Record<string, string | number>
  isStaleProcessing: boolean
}

/** AppJobRow(원본, payload/last_error 포함) → 화면·JSON 응답에 실제로 내보낼 값.
 *  API 라우트와 페이지 컴포넌트가 반드시 이 함수를 거친 뒤에만 클라이언트로
 *  내보낸다 — 원본 row 를 그대로 res.json() 하거나 JSX 에 꽂지 않는다. */
export function toSafeJobView(job: AppJobRow): SafeJobView {
  const staleCutoff = Date.now() - STALE_PROCESSING_MINUTES * 60 * 1000
  const isStaleProcessing =
    job.status === 'processing' && !!job.started_at && new Date(job.started_at).getTime() < staleCutoff

  return {
    id: job.id,
    jobType: job.job_type,
    jobKey: job.job_key,
    status: job.status,
    attempts: job.attempts,
    maxAttempts: job.max_attempts,
    createdAt: job.created_at,
    availableAt: job.available_at,
    startedAt: job.started_at,
    finishedAt: job.finished_at,
    updatedAt: job.updated_at,
    lastError: sanitizeLastError(job.last_error),
    safePayload: extractSafePayload(job.job_type, job.payload),
    isStaleProcessing,
  }
}

export { KNOWN_JOB_TYPES }
