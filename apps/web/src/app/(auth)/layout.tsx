import { MainNav } from "@/components/navigation/MainNav"

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-background">
      <MainNav />
      <main>{children}</main>
    </div>
  )
}
