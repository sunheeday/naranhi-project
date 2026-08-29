import { NextResponse, type NextRequest } from 'next/server'
import { AdminUnauthorizedError, requireAdminSession, writeAdminAudit } from '@/lib/admin/session'
import { AdminApiError, runAdminJob } from '@/lib/admin/gcp'

/** docs/content-extractor-job.md:137-141 의 수동 gcloud 와 같은 args 다.
 *  scheduled_content_extractor 의 파서는 --force 에 --notice-id 를 요구한다
 *  (backend/app/jobs/scheduled_content_extractor.py:57-58). --max-notices=1 을
 *  더해 이 실행이 정확히 공지 하나에만 영향을 주도록 고정한다. */
const EXTRACTOR_JOB = 'naranhi-content-extractor'

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ noticeId: string }> },
) {
  // 404 준수 — Task 9·10·11·13 이 반복한 "브리프 예시가 401 을 쓴다" 함정을
  // 여기서는 피한다. middleware.ts 의 adminGate() 주석대로 401 은 "인증하면 뭔가
  // 있다"는 힌트를 흘린다.
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 })
    }
    throw error
  }

  const { noticeId } = await params
  const args = [`--notice-id=${noticeId}`, '--force', '--max-notices=1']

  try {
    // runAdminJob 은 Cloud Run Job 실행 하나를 큐잉할 뿐이다 — 이 args 조합
    // 자체가 "공지 하나만" 을 강제한다(RUNNABLE_JOBS 화이트리스트는 백엔드 상수,
    // gcp_admin_service.py). 버튼도 한 번에 이 라우트를 한 건씩만 부른다 —
    // 일괄 재추출 엔드포인트는 만들지 않았다.
    const { operation } = await runAdminJob(EXTRACTOR_JOB, args, session.adminUserId)
    // Gemini 호출 비용이 실제로 발생하는 조작이다. 누가 어떤 공지를 눌렀는지가
    // 남아야 한다. detail 에는 식별자(noticeId)·args·operation 만 싣는다 —
    // 공지 제목·본문은 이 함수 호출부 어디에도 없다(writeAdminAudit 은 받은 값을
    // 그대로 적재할 뿐이라, 애초에 담지 않는 것이 유일한 방어선이다).
    //
    // FastAPI 쪽(backend/app/api/admin.py:post_job_run)도 성공 시 자체적으로
    // record_admin_action(action="job_run", target=job_name=...)을 남기지만,
    // 그 target 은 "naranhi-content-extractor"(job 이름) 고정이라 "이 공지가
    // 재추출됐는가"를 admin_audit_log 만으로 조회하려면 매번 detail.args 를
    // 훑어야 한다. 여기서 target=noticeId 로 한 번 더 남기는 것은 Task 13 이
    // 스케줄러에서 피한 "완전 중복 기록"과 다르다 — target 단위(job 전체 vs
    // 공지 하나)가 서로 다른 조회 축이라 겹치지 않는다.
    await writeAdminAudit(session, 'notice_reextract', noticeId, { args, operation })
    return NextResponse.json({ ok: true, operation })
  } catch (error) {
    await writeAdminAudit(session, 'notice_reextract_failed', noticeId, { args, error: String(error) })
    const status = error instanceof AdminApiError ? error.status : 502
    return NextResponse.json({ ok: false, error: String(error) }, { status })
  }
}
