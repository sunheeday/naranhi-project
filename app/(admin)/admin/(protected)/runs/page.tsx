import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { CrawlRunHistoryUnavailableError, listCrawlRuns, type CrawlRunRow } from '@/lib/admin/runs'
import type { CrawlRunOutcome } from '@/types/database'

export const dynamic = 'force-dynamic'

/** ⚠️ processed_count == 0 은 «성공» 이 아니라 «미실행» 이다.
 *  scheduled_crawler_service.py:335-336 이 그 경우 success_rate 를 1.0,
 *  alarm 을 False 로 만들기 때문에, 숫자만 보면 완벽한 실행처럼 보인다. */
const OUTCOME_BADGE: Record<CrawlRunOutcome, { label: string; className: string }> = {
  ok: { label: '성공', className: 'bg-emerald-900 text-emerald-200' },
  idle: { label: '미실행', className: 'bg-slate-700 text-slate-200' },
  alarm: { label: '성공률 미달', className: 'bg-amber-900 text-amber-100' },
  crashed: { label: '크래시', className: 'bg-rose-900 text-rose-100' },
}

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403 이 아니라 404 로 매핑한다(다른 관리자 페이지 전부와 동일 패턴). */
export default async function AdminRunsPage() {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  let runs: CrawlRunRow[] = []
  let unavailable = false
  try {
    runs = await listCrawlRuns()
  } catch (error) {
    if (error instanceof CrawlRunHistoryUnavailableError) {
      unavailable = true
    } else {
      throw error
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">정기 크롤 실행 이력</h1>
        <p className="text-xs text-slate-500">
          «성공률 임계치» 는 CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD 다. 이름은 fail_rate 지만
          실제로는 성공률과 비교한다(기본 0.5).
        </p>
      </div>

      {unavailable ? (
        <p className="rounded border border-amber-800 bg-amber-950 p-3 text-sm text-amber-200">
          실행 이력을 표시할 수 없습니다 — crawl_run_history 테이블이 없습니다
          (마이그레이션 0041 미적용). 스케줄러가 정상 실행 중이어도 이력이 쌓이지
          않는 상태입니다. 아래 「아직 이력 없음」과는 다른 상태입니다 — 실행 여부
          자체는 Cloud Logging(크롤러 stdout)에서 직접 확인해야 합니다.
        </p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-slate-400">
          아직 이력 없음. 테이블은 존재하지만 쌓인 실행이 없다 — 스케줄러가 하루
          2회(06/18시) 도므로 정상이라면 다음 실행 후 채워진다. 스케줄러가 PAUSED
          라면 정기 실행이 없다 — 스케줄러 화면을 확인한다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="text-slate-400">
              <tr className="border-b border-slate-800">
                <th className="py-2 px-3">시작</th>
                <th className="py-2 px-3">결과</th>
                <th className="py-2 px-3">등록</th>
                <th className="py-2 px-3">선택</th>
                <th className="py-2 px-3">건너뜀</th>
                <th className="py-2 px-3">처리</th>
                <th className="py-2 px-3">성공/실패</th>
                <th className="py-2 px-3">성공률</th>
                <th className="py-2 px-3">오류</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const badge = OUTCOME_BADGE[run.outcome]
                return (
                  <tr key={run.id} className="border-b border-slate-900 align-top">
                    <td className="py-2 px-3 whitespace-nowrap">{run.started_at.slice(0, 19)}</td>
                    <td className="py-2 px-3">
                      <span className={`rounded px-1.5 py-0.5 ${badge.className}`}>{badge.label}</span>
                    </td>
                    <td className="py-2 px-3">{run.total_registered}</td>
                    <td className="py-2 px-3">{run.selected_count}</td>
                    <td className="py-2 px-3">{run.skipped_count}</td>
                    <td className="py-2 px-3">{run.processed_count}</td>
                    <td className="py-2 px-3">
                      {run.success_count}/{run.failure_count}
                    </td>
                    <td className="py-2 px-3">
                      {run.processed_count === 0 ? '-' : `${Math.round(run.success_rate * 100)}%`}
                    </td>
                    <td className="py-2 px-3 max-w-[300px] whitespace-pre-wrap break-words text-rose-300">
                      {run.error_message ?? '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {!unavailable && <p className="text-xs text-slate-500">{runs.length}건</p>}
    </main>
  )
}
