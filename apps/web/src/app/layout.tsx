import type { Metadata } from "next";
import { headers } from "next/headers";
import { Nunito_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { ToastProvider } from "@/components/providers/toast-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { SkipLink } from "@/components/SkipLink";

const nunitoSans = Nunito_Sans({
  subsets: ["latin"],
  variable: "--font-nunito-sans",
});

export const metadata: Metadata = {
  title: "Podcastfy Studio",
  description: "AI-powered podcast generation platform",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Per-request CSP nonce from the middleware (issue #307) — without it the
  // theme-flash script below is blocked, since script-src has no
  // 'unsafe-inline' anymore.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          nonce={nonce}
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');else document.documentElement.classList.remove('dark');}catch(e){}`,
          }}
        />
      </head>
      <body className={nunitoSans.variable}>
        <SkipLink />
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider />
            {/*
              The skip-link target (<main id="main-content">) is owned by each
              route, not this root layout — otherwise it would wrap the (auth)
              group's <MainNav>, so "skip to main content" would land the user
              *before* the nav, and the (auth) layout's own <main> nested a
              second landmark inside this one (issue #323).
            */}
            {children}
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
