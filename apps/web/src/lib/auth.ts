/**
 * NextAuth.js configuration for authentication
 */
import { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

interface AuthUser {
  id: string;
  email: string;
  name: string;
  accessToken: string;
  tenantId: string;
}

/**
 * Authenticate credentials against the backend API.
 * Extracted for testability.
 */
export async function authenticateCredentials(
  email: string | undefined,
  password: string | undefined
): Promise<AuthUser | null> {
  if (!email || !password) {
    return null;
  }

  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();

    return {
      id: data.user.id,
      email: data.user.email,
      name: data.user.full_name,
      accessToken: data.access_token,
      tenantId: data.user.tenant_id,
    };
  } catch (error) {
    console.error('Authentication error:', error);
    return null;
  }
}

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        return authenticateCredentials(credentials?.email, credentials?.password);
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      // Initial sign in
      if (user) {
        token.accessToken = (user as AuthUser).accessToken;
        token.tenantId = (user as AuthUser).tenantId;
        token.userId = user.id;
      }
      return token;
    },
    async session({ session, token }) {
      // Send properties to the client
      session.user.id = token.userId as string;
      (session.user as typeof session.user & { tenantId: string }).tenantId = token.tenantId as string;
      (session as typeof session & { accessToken: string }).accessToken = token.accessToken as string;
      return session;
    },
  },
  pages: {
    signIn: '/login',
    signOut: '/login',
    error: '/login',
  },
  session: {
    strategy: 'jwt',
    maxAge: 30 * 60, // 30 minutes
  },
  secret: process.env.NEXTAUTH_SECRET,
};
