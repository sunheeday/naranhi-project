/** AdminApiError.status(서버 컴포넌트) 또는 fetch 응답 status(클라이언트 컴포넌트)를
 *  사람이 읽을 문구로 바꾼다. 두 쪽 다 같은 문구를 써야 해서 'server-only' 가 아닌
 *  별도 파일에 둔다 — SchedulerActions.tsx('use client')가 lib/admin/gcp.ts를 직접
 *  import 할 수 없기 때문이다.
 *
 *  502는 "알 수 없는 오류"로 뭉개지 않는다: Task 12가 실측한 대로 지금
 *  naranhi-api 런타임 서비스 계정에는 Cloud Scheduler IAM 권한이 없고, 이 상태에서
 *  스케줄러 조회/정지/재개는 전부 502로 떨어진다(backend/app/api/admin.py의 _wrap이
 *  RuntimeError를 502로 매핑). 원인을 짐작만 하지 않도록 502에는 이 가능성을 명시하고,
 *  원본 오류 메시지도 함께 보여준다.
 */
export function describeAdminApiFailure(status: number, message?: string | null): string {
  const detail = message ? ` — ${message}` : ''
  switch (status) {
    case 502:
      return `GCP 응답 실패(502). naranhi-api 서비스 계정에 Cloud Scheduler IAM 권한이 없을 가능성이 높습니다. 관리자에게 IAM 부여 여부를 확인하세요.${detail}`
    case 403:
      return `허용되지 않은 조작입니다(403, 화이트리스트 밖).${detail}`
    case 503:
      return `관리자 API 설정이 아직 안 됐습니다(503, ADMIN_API_TOKEN 또는 NEXT_PUBLIC_API_BASE_URL 미설정).${detail}`
    case 401:
      return `관리자 API 인증 실패(401, X-Admin-Token 불일치).${detail}`
    default:
      return `실패(${status}).${detail}`
  }
}
