import { notFound } from 'next/navigation'
import { listAdminSchools } from '@/lib/admin/schools'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import type { SchoolCrawlBoardKind } from '@/types/database'
import RecrawlButton from './RecrawlButton'

export const dynamic = 'force-dynamic'

/** 0013:23 의 세 값. announcement_fallback 과 unknown 은 «오선택» 이므로 눈에 띄어야 한다.
 *  지금은 scripts/probe_school_state.py:67 이 텍스트로 찍어야만 보인다. */
const BOARD_KIND_BADGE: Record<SchoolCrawlBoardKind, { label: string; className: string }> = {
  family_notice: { label: '가정통신문', className: 'bg-emerald-900 text-emerald-200' },
  announcement_fallback: { label: '일반공지 대체', className: 'bg-amber-900 text-amber-100' },
  unknown: { label: '미정', className: 'bg-rose-900 text-rose-100' },
}

/** crawl_status 값 도메인은 DB CHECK 가 없는 자유 text 라 school_crawler_service.py 의
 *  분류 함수(_classify_fetch_exception 등)가 어떤 코드를 새로 뱉어도 화면이 깨지지
 *  않아야 한다. 'success' 만 정상, 'pending'(0013 기본값, 아직 한 번도 안 돈 학교)은
 *  중립, 그 외 전부(homepage_fetch_failed 등)를 실패로 본다 — 특정 학교 id 를
 *  하드코딩하지 않고 상태값만으로 판정한다. 그중 일부는 홈페이지 자체가 데모용이라
 *  구조적으로 못 고치는 실패일 수 있는데(사업 D 가 정리 예정), 그 사정은 이 화면이
 *  판단할 수 없으므로 "실패"로만 표시하고 원인은 오류 메시지 칸에 맡긴다. */
function statusClassName(status: string): string {
  if (status === 'success') return 'text-emerald-300'
  if (status === 'pending') return 'text-slate-500'
  return 'text-rose-300'
}

export default async function AdminSchoolsPage() {
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  const schools = await listAdminSchools()

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">학교별 수집 상태</h1>
        <p className="text-sm text-slate-400">
          school_crawl_state 현황. 공지 제목·본문은 어디에도 표시하지 않는다 — 학교
          이름·상태·시각·개수만 보여준다.
        </p>
      </div>

      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full min-w-[1000px] text-left text-xs">
          <thead className="text-slate-400">
            <tr className="border-b border-slate-800">
              <th className="py-2 px-3">학교</th>
              <th className="py-2 px-3">게시판 종류</th>
              <th className="py-2 px-3">게시판 URL</th>
              <th className="py-2 px-3">수집 상태</th>
              <th className="py-2 px-3">마지막 확인</th>
              <th className="py-2 px-3">watermark</th>
              <th className="py-2 px-3">공지</th>
              <th className="py-2 px-3">대기</th>
              <th className="py-2 px-3">오류</th>
              <th className="py-2 px-3">재크롤</th>
            </tr>
          </thead>
          <tbody>
            {schools.length === 0 && (
              <tr>
                <td colSpan={10} className="py-4 px-3 text-slate-500">
                  등록된 학교가 없습니다.
                </td>
              </tr>
            )}
            {schools.map((school) => {
              const badge = BOARD_KIND_BADGE[school.crawlBoardKind]
              return (
                <tr key={school.id} className="border-b border-slate-900 align-top">
                  <td className="py-2 px-3">{school.name}</td>
                  <td className="py-2 px-3">
                    <span className={`rounded px-1.5 py-0.5 ${badge.className}`}>{badge.label}</span>
                  </td>
                  <td className="py-2 px-3 max-w-[280px] truncate" title={school.crawlBoardUrl ?? ''}>
                    {school.crawlBoardUrl ?? '-'}
                  </td>
                  <td className={`py-2 px-3 ${statusClassName(school.crawlStatus)}`}>
                    {school.crawlStatus}
                  </td>
                  <td className="py-2 px-3 whitespace-nowrap">
                    {school.crawlLastCheckedAt?.slice(0, 19) ?? '-'}
                  </td>
                  <td className="py-2 px-3">{school.watermarkBoards}개 게시판</td>
                  <td className="py-2 px-3">{school.noticeCount}</td>
                  <td className={`py-2 px-3 ${school.pendingNoticeCount > 0 ? 'text-amber-300' : ''}`}>
                    {school.pendingNoticeCount}
                  </td>
                  <td className="py-2 px-3 max-w-[240px] whitespace-pre-wrap break-words text-rose-300">
                    {school.crawlErrorMessage ?? '-'}
                  </td>
                  <td className="py-2 px-3">
                    <RecrawlButton schoolId={school.id} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500">{schools.length}개 학교 표시</p>
    </main>
  )
}
