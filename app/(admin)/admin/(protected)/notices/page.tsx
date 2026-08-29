import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'
import { listAdminNotices, NOTICE_LIST_LIMIT } from '@/lib/admin/notices'
import type { NoticeStatus } from '@/types/database'
import ReextractButton from './ReextractButton'

export const dynamic = 'force-dynamic'

const STATUS_BADGE: Record<NoticeStatus, { label: string; className: string }> = {
  pending: { label: '대기', className: 'text-slate-400' },
  processing: { label: '처리 중', className: 'text-amber-300' },
  done: { label: '완료', className: 'text-emerald-300' },
  error: { label: '오류', className: 'text-rose-400 font-semibold' },
}

export default async function AdminNoticesPage() {
  // 이중 방어 ②. app/(admin)/admin/(protected)/schools/page.tsx 와 동일 패턴 —
  // requireAdminSession() 을 try/catch 로 감싸 AdminUnauthorizedError 만 404 로
  // 매핑한다(브리프 예시가 이 try/catch 없이 401 을 흘리는 반복 결함, 여기서는 피함).
  try {
    await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  const notices = await listAdminNotices()

  return (
    <main className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">공지 검수</h1>
        <p className="text-sm text-slate-400">
          공지 제목·본문은 이 화면 어디에도 표시하지 않는다 — 한국 학교 공지에는
          학생 이름·학년반·보호자 연락처가 섞일 수 있다. 검수는 &ldquo;원문&rdquo; 링크로
          학교 게시판 원본을 직접 열어서 하고, 여기는 상태·오류·추출 신호(첨부
          개수·원본 파일 확인 필요 여부)만 보여준다.
        </p>
      </div>

      <div className="overflow-x-auto rounded border border-slate-800">
        <table className="w-full min-w-[1000px] text-left text-xs">
          <thead className="text-slate-400">
            <tr className="border-b border-slate-800">
              <th className="py-2 px-3">생성</th>
              <th className="py-2 px-3">학교</th>
              <th className="py-2 px-3">상태</th>
              <th className="py-2 px-3">오류</th>
              <th className="py-2 px-3">첨부</th>
              <th className="py-2 px-3">추출 신호</th>
              <th className="py-2 px-3">시도</th>
              <th className="py-2 px-3">원문</th>
              <th className="py-2 px-3">조작</th>
            </tr>
          </thead>
          <tbody>
            {notices.length === 0 && (
              <tr>
                <td colSpan={9} className="py-4 px-3 text-slate-500">
                  공지가 없습니다.
                </td>
              </tr>
            )}
            {notices.map((notice) => {
              const badge = STATUS_BADGE[notice.status] ?? { label: notice.status, className: '' }
              return (
                <tr key={notice.id} className="border-b border-slate-900 align-top">
                  <td className="py-2 px-3 whitespace-nowrap">{notice.createdAt.slice(0, 19)}</td>
                  <td className="py-2 px-3">{notice.schoolName}</td>
                  <td className={`py-2 px-3 ${badge.className}`}>{badge.label}</td>
                  <td className="py-2 px-3 max-w-[220px] whitespace-pre-wrap break-words text-rose-300">
                    {notice.errorMessage ?? '-'}
                  </td>
                  <td className="py-2 px-3">{notice.attachmentCount}</td>
                  <td className="py-2 px-3 max-w-[220px]">
                    {notice.needsFile ? (
                      <span className="text-amber-300">
                        원본 파일 확인 필요
                        {notice.needsFileReason.length > 0 ? ` (${notice.needsFileReason.join(', ')})` : ''}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="py-2 px-3">{notice.extractionAttempts}</td>
                  <td className="py-2 px-3">
                    {notice.detailUrl ? (
                      <a href={notice.detailUrl} target="_blank" rel="noreferrer" className="underline">
                        원문
                      </a>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="py-2 px-3">
                    <ReextractButton noticeId={notice.id} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500">
        {notices.length}개 공지 표시(최근 {NOTICE_LIST_LIMIT}건까지)
      </p>
    </main>
  )
}
