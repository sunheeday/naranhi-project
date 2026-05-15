import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Naranhi",
  description: "School notices made easier for multilingual families"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
