import { isSupabaseConfigured } from "@/lib/supabase/config";

export async function GET() {
  return Response.json({
    ok: true,
    supabaseConfigured: isSupabaseConfigured()
  });
}
