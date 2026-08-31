import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { AdminApiError, listSchedulers, type SchedulerJob } from '@/lib/admin/gcp'
import { describeAdminApiFailure } from '@/lib/admin/admin-api-messages'
import SchedulerActions from './SchedulerActions'

export const dynamic = 'force-dynamic'

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403이 아니라 404로 매핑한다(app/(admin)/admin/(protected)/jobs/page.tsx와 동일
 *  패턴, task-13-brief.md의 예시 코드에는 이 try/catch가 없다 — Task 9·10·11에서
 *  세 번 반복된 누락이라 여기서 처음부터 넣는다). */
export default async function AdminSchedulersPage() {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  let jobs: SchedulerJob[] = []
  let error: string | null = null
  try {
    jobs = await listSchedulers()
  } catch (caught) {
    // 2026-08-29 기준 naranhi-api 런타임 서비스 계정에 cloudscheduler IAM 권한이
    // 없다 — 이 목록 조회(GET /admin/schedulers)조차 지금은 502로 실패한다.
    // "알 수 없는 오류"로 뭉개지 않고 원인 후보를 화면에 그대로 보여준다.
    error =
      caught instanceof AdminApiError
        ? describeAdminApiFailure(caught.status, caught.message)
        : String(caught)
  }

  const pausedCount = jobs.filter((job) => job.state === 'PAUSED').length

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">스케줄러</h1>
        {/* 문서가 아니라 Cloud Scheduler API가 돌려준 실제 cron과 state를 보여준다.
            문서(docs/기능명세서.md)는 요일 제한이 있는 것처럼 적었지만 실제는
            매일 06:00/19:00, 07:00/20:00이다 — 화면은 드러내기만 한다. */}
        <p className="text-xs text-slate-500">
          Cloud Scheduler API가 돌려준 실제 값이다. 문서에 적힌 시각·주기와 다를 수 있다.
        </p>
      </div>

      {error ? (
        <div className="rounded border border-rose-800 bg-rose-950 p-3 text-sm text-rose-300">
          목록을 불러오지 못했습니다. {error}
        </div>
      ) : (
        <div className={`rounded border p-3 text-sm ${pausedCount > 0 ? 'border-rose-800 bg-rose-950 text-rose-300' : 'border-slate-800 text-slate-400'}`}>
          정지된 스케줄러 {pausedCount}개 / 전체 {jobs.length}개
        </div>
      )}

      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="text-slate-400">
            <tr className="border-b border-slate-800">
              <th className="py-2 px-3">이름</th>
              <th className="py-2 px-3">cron</th>
              <th className="py-2 px-3">시간대</th>
              <th className="py-2 px-3">상태</th>
              <th className="py-2 px-3">마지막 시도</th>
              <th className="py-2 px-3">조작</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && !error && (
              <tr>
                <td colSpan={6} className="py-4 px-3 text-slate-500">
                  스케줄러가 없습니다.
                </td>
              </tr>
            )}
            {jobs.map((job) => (
              <tr key={job.name} className="border-b border-slate-900">
                <td className="py-2 px-3 font-mono">{job.name}</td>
                <td className="py-2 px-3 font-mono">{job.schedule ?? '-'}</td>
                <td className="py-2 px-3">{job.timeZone ?? '-'}</td>
                <td className="py-2 px-3">
                  <span className={job.state === 'PAUSED' ? 'font-semibold text-rose-400' : 'text-emerald-300'}>
                    {job.state ?? '-'}
                  </span>
                </td>
                <td className="py-2 px-3 whitespace-nowrap">{job.lastAttemptTime?.slice(0, 19) ?? '-'}</td>
                <td className="py-2 px-3">
                  <SchedulerActions name={job.name} state={job.state} controllable={job.controllable} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  )
}
