import { NextResponse, type NextRequest } from "next/server";
import { isValidLocale } from "@/lib/i18n";

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

  return response;
}
