import type { Metadata } from "next";
import { Nunito_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { SkipLink } from "@/components/SkipLink";

const nunitoSans = Nunito_Sans({
  subsets: ["latin"],
  variable: "--font-nunito-sans",
});

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
      <body className={nunitoSans.variable}>
        <SkipLink />
        <AuthProvider>
          <main id="main-content">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
