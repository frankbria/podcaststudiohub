import { render, screen } from '@testing-library/react'
import * as React from 'react'
import { AuthProvider } from '@/components/providers/auth-provider'

// Mock next-auth/react SessionProvider
jest.mock('next-auth/react', () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="session-provider">{children}</div>
  ),
}))

describe('AuthProvider', () => {
  it('renders children when wrapped in AuthProvider', () => {
    render(
      <AuthProvider>
        <span>child content</span>
      </AuthProvider>
    )
    expect(screen.getByText('child content')).toBeInTheDocument()
  })

  it('passes children through SessionProvider', () => {
    render(
      <AuthProvider>
        <span>session child</span>
      </AuthProvider>
    )
    const provider = screen.getByTestId('session-provider')
    expect(provider).toBeInTheDocument()
    expect(provider).toHaveTextContent('session child')
  })
})
