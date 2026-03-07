import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { SkipLink } from "@/components/SkipLink";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Podcastfy Studio",
  description: "AI-powered podcast generation platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <SkipLink />
        <AuthProvider>
          <main id="main-content">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
