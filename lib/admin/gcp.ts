import 'server-only'

const ADMIN_API_TIMEOUT_MS = 20_000

export class AdminApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'AdminApiError'
  }
}

export interface SchedulerJob {
  name: string
  schedule: string | null
  timeZone: string | null
  state: string | null
  lastAttemptTime: string | null
  controllable: boolean
}

interface RawSchedulerJob {
  name: string
  schedule: string | null
  time_zone: string | null
  state: string | null
  last_attempt_time: string | null
  controllable: boolean
}

function toSchedulerJob(raw: RawSchedulerJob): SchedulerJob {
  return {
    name: raw.name,
    schedule: raw.schedule,
    timeZone: raw.time_zone,
    state: raw.state,
    lastAttemptTime: raw.last_attempt_time,
    controllable: raw.controllable,
  }
}

/** ADMIN_API_TOKEN 은 브라우저로 절대 내려가지 않는다. 이 파일은 server-only 이고,
 *  클라이언트 컴포넌트가 FastAPI /admin/* 를 직접 부르는 코드는 만들지 않는다 —
 *  브라우저는 오직 이 저장소의 /api/admin/schedulers* Next 라우트만 호출하고,
 *  그 라우트가 이 함수를 통해 FastAPI 를 대리 호출한다.
 *
 *  actorId 는 호출자(Next API 라우트)가 자신의 admin_sessions 세션에서 꺼낸
 *  session.adminUserId 여야 한다. X-Admin-Actor 는 FastAPI 쪽 감사 로그
 *  (admin_audit_log, backend/app/services/gcp_admin_service.py:record_admin_action)의
 *  "누가" 만 채우는 용도다 — 인가에는 쓰이지 않는다. FastAPI 는 이 헤더가 UUID
 *  형식이 아니면 조용히 버린다(parse_admin_actor). 인가는 여전히 X-Admin-Token
 *  하나뿐이므로 이 헤더를 위조해도 권한이 올라가지 않는다.
 */
async function callAdminApi<T>(
  path: string,
  actorId: string | null,
  init: RequestInit = {},
): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '')
  if (!base) throw new AdminApiError('NEXT_PUBLIC_API_BASE_URL 이 설정되지 않았습니다.', 503)
  const token = process.env.ADMIN_API_TOKEN?.trim()
  if (!token) throw new AdminApiError('ADMIN_API_TOKEN 이 설정되지 않았습니다.', 503)

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    'X-Admin-Token': token,
    'content-type': 'application/json',
  }
  if (actorId) headers['X-Admin-Actor'] = actorId

  let response: Response
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(ADMIN_API_TIMEOUT_MS),
    })
  } catch (error) {
    // FastAPI 자체가 죽었거나 타임아웃 — GCP 응답 실패(502)와 같은 갈래로 취급한다.
    throw new AdminApiError(`admin api 연결 실패: ${String(error)}`, 502)
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.ok) {
    // FastAPI 의 HTTPException 은 {"detail": "..."} 형태다(payload.ok 가 없다) —
    // 성공 응답만 명시적으로 ok:true 를 담는다(backend/app/api/admin.py).
    throw new AdminApiError(payload?.detail ?? `admin api ${response.status}`, response.status)
  }
  return payload as T
}

export async function listSchedulers(): Promise<SchedulerJob[]> {
  // 조회는 부수효과가 없고 "누가"를 감사 로그에 남길 필요도 없다 — actor 불필요.
  const payload = await callAdminApi<{ jobs: RawSchedulerJob[] }>('/admin/schedulers', null)
  return payload.jobs.map(toSchedulerJob)
}

export async function setSchedulerState(
  name: string,
  action: 'pause' | 'resume',
  actorId: string,
): Promise<SchedulerJob> {
  // backend/app/api/admin.py 의 실제 경로는 pause/resume 이 분리된 두 엔드포인트다
  // (POST /admin/schedulers/{name}/pause, .../resume) — action 이 body 로 들어가는
  // 단일 엔드포인트가 아니다. 응답도 {name,state,schedule} 세 필드뿐이라
  // time_zone/last_attempt_time 은 이 응답에 없다(목록 조회에만 있다) — null 로 채운다.
  const payload = await callAdminApi<{
    job: { name: string; state: string | null; schedule: string | null }
  }>(`/admin/schedulers/${encodeURIComponent(name)}/${action}`, actorId, { method: 'POST' })
  return toSchedulerJob({
    name: payload.job.name,
    schedule: payload.job.schedule,
    time_zone: null,
    state: payload.job.state,
    last_attempt_time: null,
    controllable: true,
  })
}

/** Task 15 가 쓴다. 화이트리스트(RUNNABLE_JOBS)는 백엔드 상수라 여기서 임의
 *  job_name 을 받아도 화이트리스트 밖이면 403 이 그대로 올라온다. */
export async function runAdminJob(
  jobName: string,
  args: string[],
  actorId: string,
): Promise<{ operation: string }> {
  const payload = await callAdminApi<{ job_name: string; operation: string; args: string[] }>(
    `/admin/jobs/${encodeURIComponent(jobName)}/run`,
    actorId,
    { method: 'POST', body: JSON.stringify({ args }) },
  )
  return { operation: payload.operation }
}
