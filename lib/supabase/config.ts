/** 자동 로그인 유지 기간. Supabase refresh token 은 기본적으로 시간 제한이 없으므로
 *  브라우저 쿠키 수명이 곧 재로그인 없이 쓸 수 있는 기간이 된다. */
export const AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 14;

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
