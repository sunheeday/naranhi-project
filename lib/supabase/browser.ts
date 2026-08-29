"use client";

import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseBrowserConfig } from "./config";
import type { Database } from "@/types/database";

/** 브라우저 클라이언트.
 *
 *  ⚠️ 이 클라이언트는 14일 세션 정책(AUTH_COOKIE_MAX_AGE_SECONDS) 밖에 있다.
 *  커스텀 `cookies` 어댑터가 없어 @supabase/ssr 의 document.cookie 기본 스토리지로
 *  폴백하고, 그 경로는 항상 400일을 쓴다. `cookieOptions: { maxAge }` 를 넘겨도
 *  소용없다 — 라이브러리가 set 경로에서 `{...cookieOptions, maxAge: DEFAULT}` 순서로
 *  덮어쓰기 때문이다(cookies.js).
 *
 *  지금은 무해하다: 이 클라이언트는 클릭 핸들러 안에서만 생성되어 autoRefreshToken
 *  타이머가 상주하지 않고, 실제로 쓰는 것은 OAuth PKCE code_verifier(코드 교환 후
 *  삭제되는 임시 쿠키)뿐이다.
 *
 *  ⚠️ 어떤 클라이언트 컴포넌트가 이것을 마운트해 상주시키면, 세션 갱신 때마다
 *  sb-...-auth-token 이 400일로 재기록되어 14일 정책이 조용히 무력화된다.
 *  그렇게 쓰려면 먼저 커스텀 쿠키 어댑터를 붙여라. */
export function createSupabaseBrowserClient() {
  const { url, anonKey } = getSupabaseBrowserConfig();

  return createBrowserClient<Database>(url, anonKey);
}
