import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { countAppJobsByStatus, listAppJobs, toSafeJobView } from '@/lib/admin/jobs'
import type { AppJobStatus } from '@/types/database'
import JobActions from './JobActions'

export const dynamic = 'force-dynamic'

const STATUSES: AppJobStatus[] = ['queued', 'processing', 'completed', 'failed']

function formatPayload(payload: Record<string, string | number>): string {
  const entries = Object.entries(payload)
  if (entries.length === 0) return '-'
  return entries.map(([key, value]) => `${key}=${value}`).join(' · ')
}

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403 이 아니라 404 로 매핑한다(app/(admin)/admin/(protected)/page.tsx 와 동일한
 *  패턴). 정상 경로에서는 상위 layout.tsx 가 이미 getAdminSession() 으로 걸러내므로
 *  이 catch 는 레이아웃 통과 이후 세션이 폐기되는 경합 등 방어적 상황에서만 발동한다.
 *
 *  (task-10-brief.md 의 예시 코드는 이 try/catch 없이 requireAdminSession() 을 그냥
 *  불러 던진다 — 그러면 AdminUnauthorizedError 가 안 잡혀 Next 기본 500 에러 페이지로
 *  샌다. 다른 관리자 페이지 전부가 지키는 "거절=404" 원칙과 어긋나 여기서 고쳐 뗀다.) */
export default async function AdminJobsPage({
  searchParams,
}: {
  searchParams: Promise<{ job_type?: string; status?: string }>
}) {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  const query = await searchParams
  const status = STATUSES.includes(query.status as AppJobStatus) ? (query.status as AppJobStatus) : undefined

  const [rawJobs, counts] = await Promise.all([
    listAppJobs({ jobType: query.job_type, status }),
    countAppJobsByStatus(),
  ])
  const jobs = rawJobs.map(toSafeJobView)
  const staleCount = jobs.filter((j) => j.isStaleProcessing).length

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">잡 큐</h1>
        <p className="text-sm text-slate-400">
          app_jobs 현황. payload·오류 메시지는 통째로 보여주지 않고, 안전하다고 확인한
          필드만 뽑아 표시한다(공지 원문·열쇠류 제외).
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <a href="/admin/jobs" className={`underline ${!query.status ? 'text-white' : 'text-slate-400'}`}>
          전체
        </a>
        {STATUSES.map((s) => (
          <a
            key={s}
            href={`/admin/jobs?status=${s}`}
            className={`underline ${
              s === 'failed' || s === 'processing' ? 'font-semibold' : ''
            } ${query.status === s ? 'text-white' : 'text-slate-400'} ${
              (s === 'failed' && counts[s] > 0) || (s === 'processing' && counts[s] > 0)
                ? 'text-amber-300'
                : ''
            }`}
          >
            {s} ({counts[s]})
          </a>
        ))}
        {staleCount > 0 && (
          <span className="rounded border border-amber-800 bg-amber-950 px-2 py-0.5 text-xs text-amber-300">
            오래된 processing {staleCount}건 (좀비 의심)
          </span>
        )}
      </div>

      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full min-w-[1100px] text-left text-xs">
          <thead className="text-slate-400">
            <tr className="border-b border-slate-800">
              <th className="py-2 px-3">생성</th>
              <th className="py-2 px-3">job_type</th>
              <th className="py-2 px-3">job_key</th>
              <th className="py-2 px-3">상태</th>
              <th className="py-2 px-3">시도</th>
              <th className="py-2 px-3">시작</th>
              <th className="py-2 px-3">종료</th>
              <th className="py-2 px-3">필드</th>
              {/* last_error 는 DB 에서도 1000자로 잘려 저장되고(job_queue_service.py:270),
                  여기서는 lib/admin/jobs.ts:sanitizeLastError 로 열쇠류를 가리고 400자로
                  더 자른 값만 받는다 — 원본을 그대로 내지 않는다. */}
              <th className="py-2 px-3">오류(가림 처리)</th>
              <th className="py-2 px-3">조작</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr>
                <td colSpan={9} className="py-4 px-3 text-slate-500">
                  해당하는 잡이 없습니다.
                </td>
              </tr>
            )}
            {jobs.map((job) => (
              <tr key={job.id} className="border-b border-slate-900 align-top">
                <td className="py-2 px-3 whitespace-nowrap">{job.createdAt.slice(0, 19)}</td>
                <td className="py-2 px-3 whitespace-nowrap font-mono">{job.jobType}</td>
                <td className="py-2 px-3 max-w-[200px] truncate font-mono" title={job.jobKey}>
                  {job.jobKey}
                </td>
                <td className="py-2 px-3">
                  <span className={job.status === 'failed' ? 'text-rose-400' : ''}>{job.status}</span>
                  {job.isStaleProcessing && (
                    <span className="ml-1 rounded border border-amber-800 bg-amber-950 px-1 text-[10px] text-amber-300">
                      좀비 의심
                    </span>
                  )}
                </td>
                <td className="py-2 px-3 whitespace-nowrap">
                  {job.attempts}/{job.maxAttempts}
                </td>
                <td className="py-2 px-3 whitespace-nowrap">{job.startedAt?.slice(0, 19) ?? '-'}</td>
                <td className="py-2 px-3 whitespace-nowrap">{job.finishedAt?.slice(0, 19) ?? '-'}</td>
                <td className="py-2 px-3 font-mono text-slate-300">{formatPayload(job.safePayload)}</td>
                <td className="py-2 px-3 max-w-[320px] whitespace-pre-wrap break-words font-mono text-slate-400">
                  {job.lastError ?? '-'}
                </td>
                <td className="py-2 px-3">
                  <JobActions jobId={job.id} status={job.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500">{jobs.length}건 표시</p>
    </main>
  )
}
