import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { defaultLocale, isRtl, isValidLocale, type Locale } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "나란히",
  description: "학교 공지를 내 언어로",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "나란히"
  },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" }
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#5DAFEA"
};

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get("locale")?.value;
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale;
  const dir = isRtl(locale) ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={dir}>
      <body className="bg-canvas text-ink antialiased">
        <div className="mx-auto max-w-app min-h-screen relative">{children}</div>
      </body>
    </html>
  );
}
