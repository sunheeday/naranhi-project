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
