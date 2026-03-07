import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { useFocusTrap } from '@/hooks/useFocusTrap'

function TestDialog({ isOpen }: { isOpen: boolean }) {
  const containerRef = useFocusTrap(isOpen)
  return (
    <div ref={containerRef} data-testid="dialog">
      <button data-testid="first-btn">First</button>
      <button data-testid="second-btn">Second</button>
      <button data-testid="last-btn">Last</button>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('returns a ref object', () => {
    const { container } = render(<TestDialog isOpen={false} />)
    expect(container.querySelector('[data-testid="dialog"]')).toBeInTheDocument()
  })

  it('focuses first element when isOpen becomes true', async () => {
    const { rerender } = render(<TestDialog isOpen={false} />)
    rerender(<TestDialog isOpen={true} />)

    // First focusable element should be focused
    await act(async () => {})
    const firstBtn = screen.getByTestId('first-btn')
    expect(document.activeElement).toBe(firstBtn)
  })

  it('does not focus when isOpen is false', async () => {
    render(<TestDialog isOpen={false} />)
    await act(async () => {})
    const firstBtn = screen.getByTestId('first-btn')
    expect(document.activeElement).not.toBe(firstBtn)
  })
})
