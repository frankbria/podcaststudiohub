/**
 * @jest-environment node
 *
 * The NextAuth route handler is just glue: it wires the shared authOptions
 * (tested separately in __tests__/lib/auth.test.ts) into the NextAuth()
 * factory and re-exports the resulting handler for GET and POST.
 */
jest.mock('next-auth', () => ({
  __esModule: true,
  default: jest.fn(() => 'nextauth-handler'),
}))

jest.mock('@/lib/auth', () => ({
  authOptions: { providers: [] },
}))

import NextAuth from 'next-auth'
import { GET, POST } from '@/app/api/auth/[...nextauth]/route'
import { authOptions } from '@/lib/auth'

const nextAuthMock = NextAuth as unknown as jest.Mock

describe('NextAuth route handler', () => {
  it('configures NextAuth with the shared authOptions', () => {
    expect(nextAuthMock).toHaveBeenCalledWith(authOptions)
  })

  it('exports the same handler for both GET and POST', () => {
    expect(GET).toBe('nextauth-handler')
    expect(POST).toBe('nextauth-handler')
    expect(GET).toBe(POST)
  })
})
