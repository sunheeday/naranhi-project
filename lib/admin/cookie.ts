/** 관리자 세션 쿠키 상수.
 *
 *  middleware(Edge 런타임)와 서버 라우트가 함께 쓴다. 그래서 이 파일에는
 *  import 를 하나도 두지 않는다 — session.ts 를 middleware 에서 import 하면
 *  server-only / node:crypto / supabase-js 가 Edge 번들로 끌려 들어간다.
 *
 *  __Host- 접두는 Secure + Domain 없음 + Path=/ 를 강제한다. 이 접두를 쓰면
 *  형제 호스트(같은 상위 도메인의 다른 서브도메인)가 이 쿠키를 덮어쓰지 못한다.
 *  Path=/admin 처럼 좁히는 것과는 배타적이다(__Host- 는 Path=/ 를 강제하므로).
 *  이 쿠키는 어차피 HttpOnly라 자바스크립트로 경로를 가려 읽는 이득이 없고,
 *  대신 __Host- 가 주는 호스트 격리가 더 값지므로 __Host- 를 택한다.
 */
export const ADMIN_COOKIE_NAME = '__Host-naranhi_admin'

/** 8시간 절대 만료. 슬라이딩 갱신을 붙이지 않는다 —
 *  「훔친 쿠키의 최대 수명 = 8시간」이 보장되어야 한다.
 *  학부모 세션(14일, `lib/supabase/config.ts` AUTH_COOKIE_MAX_AGE_SECONDS)과
 *  의도적으로 다르다: 관리자 세션은 파괴적 작업(공지 승인/삭제 등) 권한을 쥐므로
 *  탈취 시 피해 반경이 크고, 관리자는 학부모와 달리 매일 재로그인해도 되는
 *  사용 빈도를 가정한다. */
export const ADMIN_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8
