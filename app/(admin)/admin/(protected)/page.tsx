import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { AdminApiError, listSchedulers, type SchedulerJob } from '@/lib/admin/gcp'
import { describeAdminApiFailure } from '@/lib/admin/admin-api-messages'
import { createSupabaseServiceClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

/** 잘못 눌린 정지로 수집이 조용히 멈추는 것이 이 콘솔의 가장 큰 부작용 위험이다.
 *  "마지막 성공 실행 시각"과 PAUSED 개수를 대시보드 최상단에 상시로 띄운다.
 *  0041이 아직 운영에 없으면 조회가 에러를 낼 수 있으므로 fail-closed로
 *  null(= "기록 없음")로 떨어뜨린다 — 페이지 자체가 죽지 않게 한다. */
async function lastSuccessfulRunAt(): Promise<string | null> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service
    .from('crawl_run_history')
    .select('finished_at')
    .eq('outcome', 'ok')
    .order('finished_at', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (error) {
    console.error(`crawl_run_history 조회 실패(0041 미적용일 수 있음): ${error.message}`)
    return null
  }
  return data?.finished_at ?? null
}

interface SchedulersSummary {
  jobs: SchedulerJob[]
  error: string | null
}

async function schedulersSummary(): Promise<SchedulersSummary> {
  try {
    return { jobs: await listSchedulers(), error: null }
  } catch (caught) {
    // 2026-08-29 기준 naranhi-api 런타임 서비스 계정에 cloudscheduler IAM 권한이
    // 없어 이 조회 자체가 502로 실패한다 — "알 수 없는 오류"로 뭉개지 않는다.
    return {
      jobs: [],
      error:
        caught instanceof AdminApiError
          ? describeAdminApiFailure(caught.status, caught.message)
          : String(caught),
    }
  }
}

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403 이 아니라 404 로 매핑한다(403은 「있지만 권한 없음」을 흘려 관리자 URL의
 *  존재를 알려준다). 정상 경로에서는 상위 (protected)/layout.tsx 가 이미
 *  getAdminSession() 으로 걸러내므로 이 catch 는 레이아웃 통과 이후 세션이
 *  폐기되는 경합(레이스) 등 방어적 상황에만 발동한다. */
export default async function AdminDashboardPage() {
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  const [lastOk, schedulers] = await Promise.all([lastSuccessfulRunAt(), schedulersSummary()])
  const paused = schedulers.jobs.filter((job) => job.state === 'PAUSED')

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">운영 대시보드</h1>

      <section className="rounded border border-slate-800 p-4">
        <h2 className="text-sm text-slate-400">마지막 성공 수집</h2>
        <p className={lastOk ? 'text-lg' : 'text-lg text-rose-400'}>
          {lastOk ? lastOk.slice(0, 19) : '기록 없음'}
        </p>
      </section>

      <section className="rounded border border-slate-800 p-4">
        <h2 className="text-sm text-slate-400">정지된 스케줄러</h2>
        {schedulers.error ? (
          <p className="text-sm text-rose-400">조회 실패 — {schedulers.error}</p>
        ) : (
          <>
            <p className={paused.length > 0 ? 'text-lg font-semibold text-rose-400' : 'text-lg text-emerald-300'}>
              {paused.length}개 / 전체 {schedulers.jobs.length}개
            </p>
            {paused.length > 0 ? (
              <ul className="mt-2 text-xs text-slate-300">
                {paused.map((job) => (
                  <li key={job.name}>{job.name}</li>
                ))}
              </ul>
            ) : null}
          </>
        )}
        <a href="/admin/schedulers" className="mt-2 inline-block text-xs text-slate-400 underline">
          스케줄러 관리 →
        </a>
      </section>

      <p className="text-sm text-slate-400">
        {session.displayName ?? session.username} · 세션 만료 {session.expiresAt}
      </p>
    </main>
  )
}
