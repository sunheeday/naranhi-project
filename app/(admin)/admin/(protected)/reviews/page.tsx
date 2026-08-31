import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { listReviewQueue, ReviewQueueUnavailableError, type ReviewQueueRow } from '@/lib/admin/reviews'

export const dynamic = 'force-dynamic'

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403 이 아니라 404 로 매핑한다(app/(admin)/admin/(protected)/jobs/page.tsx 와 동일
 *  패턴 — Task 9·10·11·13·15 에서 다섯 번 반복된 "try/catch 없이 호출" 결함을
 *  처음부터 넣지 않는다). */
export default async function AdminReviewsPage() {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  let rows: ReviewQueueRow[] = []
  let unavailable = false
  try {
    rows = await listReviewQueue()
  } catch (error) {
    if (error instanceof ReviewQueueUnavailableError) {
      unavailable = true
    } else {
      throw error
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">번역 검토 대기</h1>
        {/* 이 목록에 오른 번역도 사용자에게는 그대로 나가고 있다.
            validation_status 는 여전히 'passed' 다(notice_service.py:786-788).
            needs_review 는 «표시» 만 바꾼다 — 여기 있다고 사용자 노출이 막힌 게 아니다. */}
        <p className="text-xs text-slate-500">
          검증 경고가 붙은 번역이다. 사용자에게는 이미 노출되고 있다 — 여기 있다고 막힌 것이 아니다.
        </p>
      </div>

      {/* 🔴 원문·번역문·공지 제목은 이 화면 어디에도 없다. 한국 학교 공지 제목엔
          학생 이름·학년반이 섞일 수 있다(Task 10/11/15 와 같은 결정). 대신 학교
          게시판 원문 링크(detail_url)로 대체했다 — 검수가 필요하면 관리자가 그
          공개 페이지를 직접 연다. review_reason 은 자유서술이 아니라
          "hard_fact_validation_failed" 류 짧은 사유 코드다(Task 7·9 실측). */}

      {unavailable ? (
        <p className="rounded border border-amber-800 bg-amber-950 p-3 text-sm text-amber-200">
          검토 큐를 표시할 수 없습니다 — notice_ai_translations.needs_review/review_reason
          컬럼이 없습니다 (마이그레이션 0041 미적용). 번역 자체는 정상 저장되고 있으나
          검증 경고 신호는 아직 화면에 반영되지 않습니다. 아래 「검토 대기 없음」과는
          다른 상태입니다 — 0041 을 적용하기 전까지는 진짜로 대기가 없는지 알 수 없습니다.
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-400">
          검토 대기 없음. (0041 적용 전에 저장된 번역은 needs_review 가 false 다 —
          컬럼 기본값이지 «검증을 통과했다» 는 뜻이 아니다.)
        </p>
      ) : (
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="text-slate-400">
              <tr className="border-b border-slate-800">
                <th className="py-2 px-3">갱신</th>
                <th className="py-2 px-3">학교</th>
                <th className="py-2 px-3">공지</th>
                <th className="py-2 px-3">언어</th>
                <th className="py-2 px-3">사유</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.noticeId}:${row.targetLanguage}`} className="border-b border-slate-900 align-top">
                  <td className="py-2 px-3 whitespace-nowrap">{row.updatedAt.slice(0, 19)}</td>
                  <td className="py-2 px-3">{row.schoolName ?? '-'}</td>
                  <td className="py-2 px-3">
                    {row.detailUrl ? (
                      <a href={row.detailUrl} target="_blank" rel="noreferrer" className="underline">
                        원문
                      </a>
                    ) : (
                      <span className="text-slate-500">원문 링크 없음</span>
                    )}
                  </td>
                  <td className="py-2 px-3">{row.targetLanguage}</td>
                  <td className="py-2 px-3 max-w-[360px] whitespace-pre-wrap break-words text-amber-200">
                    {row.reviewReason ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!unavailable && <p className="text-xs text-slate-500">{rows.length}건</p>}
    </main>
  )
}
