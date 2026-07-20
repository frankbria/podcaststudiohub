import { render, screen } from '@testing-library/react'
import AuthLayout from '@/app/(auth)/layout'

// The nav's internals (session, theme, dropdown) are covered by MainNav's own
// test; here we only care that the layout owns a single <main> landmark placed
// after the nav — the structure that makes the skip link work (issue #323).
jest.mock('@/components/navigation/MainNav', () => ({
  MainNav: () => <nav aria-label="Main navigation">nav</nav>,
}))

describe('AuthLayout landmark structure', () => {
  it('renders exactly one <main> and it is the skip-link target', () => {
    render(<AuthLayout><p>content</p></AuthLayout>)

    const mains = screen.getAllByRole('main')
    expect(mains).toHaveLength(1)
    expect(mains[0]).toHaveAttribute('id', 'main-content')
    expect(mains[0]).toHaveTextContent('content')
  })

  it('places the nav before the main so "skip to main content" skips the nav', () => {
    render(<AuthLayout><p>content</p></AuthLayout>)

    const nav = screen.getByRole('navigation')
    const main = screen.getByRole('main')
    // nav must appear earlier in the document than main
    expect(nav.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // and the nav must not be nested inside the main
    expect(main.contains(nav)).toBe(false)
  })
})
