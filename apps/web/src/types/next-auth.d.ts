/**
 * NextAuth module augmentation.
 *
 * Extends the session/JWT types with the fields populated in `src/lib/auth.ts`.
 * The backend accessToken lives only in the server-side JWT and is injected into
 * backend calls by the /api/proxy Route Handler — it is never serialized to the
 * client session (issue #212).
 */
import 'next-auth';

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      tenantId: string;
    };
  }

  // The User object returned by `authorize` carries the backend token into the
  // jwt callback; it is server-side only and never serialized to the client.
  interface User {
    id: string;
    email: string;
    name: string;
    accessToken: string;
    tenantId: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken: string;
    tenantId: string;
    userId: string;
  }
}
