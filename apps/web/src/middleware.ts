/**
 * Server-side route protection for the (auth) route group (issue #222).
 *
 * Previously the (auth) pages were gated only client-side (a post-hydration
 * useEffect redirect), so protected page bundles were served to unauthenticated
 * users and the gate could be bypassed by disabling JS or racing the redirect.
 *
 * next-auth's withAuth runs in middleware before the page renders: it reads the
 * session JWT (httpOnly cookie) via NEXTAUTH_SECRET and redirects requests
 * without a valid session to /login. The client-side redirect stays as a
 * secondary, defense-in-depth guard. Data is also protected by backend authz.
 */
import { withAuth } from 'next-auth/middleware'

// Default authorized check is `!!token`; we only override the sign-in page so
// redirects land on our /login route instead of next-auth's built-in page.
export default withAuth({
  pages: { signIn: '/login' },
})

export const config = {
  // Route group "(auth)" is not part of the URL, so match the actual paths.
  matcher: ['/dashboard/:path*', '/episodes/:path*', '/projects/:path*'],
}
