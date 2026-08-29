/** 자동 로그인 유지 기간. Supabase refresh token 은 기본적으로 시간 제한이 없으므로
 *  브라우저 쿠키 수명이 곧 재로그인 없이 쓸 수 있는 기간이 된다. */
export const AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 14;

/** 세션 쿠키에 우리 정책(14일)을 씌운다.
 *
 *  삭제 의도(@supabase/ssr 이 maxAge 0 을 명시적으로 넘기거나 값이 빈 문자열)일 때는
 *  건드리지 않는다. 덮어쓰면 쿠키가 즉시 지워지지 않고 빈 값으로 14일 남는다.
 *
 *  set 일 때는 무조건 덮어쓴다 — 라이브러리가 setAll 호출 전에 이미
 *  DEFAULT_COOKIE_OPTIONS.maxAge(400일)를 채워 넘기므로 `??` 는 발동하지 않는다. */
export function withAuthCookieMaxAge<T extends { maxAge?: number }>(
  value: string,
  options: T | undefined
): T & { maxAge?: number } {
  const isRemoval = value === '' || options?.maxAge === 0
  return isRemoval
    ? ({ ...(options ?? {}) } as T)
    : ({ ...(options ?? {}), maxAge: AUTH_COOKIE_MAX_AGE_SECONDS } as T & { maxAge: number })
}

const requiredClientEnv = {
  url: process.env.NEXT_PUBLIC_SUPABASE_URL,
  anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
};

export function getSupabaseBrowserConfig() {
  const { url, anonKey } = requiredClientEnv;

  if (!url || !anonKey) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY"
    );
  }

  return { url, anonKey };
}

export function isSupabaseConfigured() {
  return Boolean(requiredClientEnv.url && requiredClientEnv.anonKey);
}
