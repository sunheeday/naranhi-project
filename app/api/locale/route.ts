import { NextResponse, type NextRequest } from "next/server";
import { isValidLocale } from "@/lib/i18n";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function POST(request: NextRequest) {
  const { locale } = (await request.json().catch(() => ({}))) as {
    locale?: unknown;
  };

  if (!isValidLocale(locale)) {
    return NextResponse.json({ error: "Invalid locale" }, { status: 400 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set("locale", locale, {
    path: "/",
    maxAge: 31_536_000,
    sameSite: "lax"
  });

  try {
    const supabase = await createSupabaseServerClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      await supabase
        .from("profiles")
        .update({ locale })
        .eq("id", user.id);
    }
  } catch {
    // Locale cookie is still the primary source for immediate UI switching.
  }

  return response;
}
