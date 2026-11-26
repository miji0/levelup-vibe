import type { Metadata } from "next";
import "pretendard/dist/web/static/pretendard.css";
import "@fontsource-variable/plus-jakarta-sans";
import "./globals.css";
import { Shell } from "@/core/shell";
import { ThemeProvider } from "@/core/theme";
export const metadata: Metadata = {
  title: "LevelUp — 나를 위한 작은 성장",
  description: "개인용 기술 동향과 읽기 공간",
  robots: { index: false, follow: false },
};
const themeInit = `try{const t=localStorage.getItem('levelup.theme');document.documentElement.dataset.theme=t==='light'?'light':'dark'}catch{document.documentElement.dataset.theme='dark'}`;
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>
        <a className="skip-link" href="#main-content">
          본문으로 이동
        </a>
        <ThemeProvider>
          <Shell>{children}</Shell>
        </ThemeProvider>
      </body>
    </html>
  );
}
