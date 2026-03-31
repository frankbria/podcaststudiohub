import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { useFocusTrap } from '@/hooks/useFocusTrap'

function TestDialog({ isOpen }: { isOpen: boolean }) {
  const ref = useFocusTrap(isOpen)
  return (
    <div ref={ref as React.RefObject<HTMLDivElement>} data-testid="dialog">
      <button data-testid="first-btn">First</button>
      <button data-testid="second-btn">Second</button>
      <button data-testid="last-btn">Last</button>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('returns a ref object', () => {
    const { result } = require('@testing-library/react').renderHook(() =>
      useFocusTrap(false)
    )
    expect(result.current).toHaveProperty('current')
  })

  it('focuses the first focusable element when opened', () => {
    render(<TestDialog isOpen={true} />)
    expect(document.activeElement).toBe(screen.getByTestId('first-btn'))
  })

  it('does not focus when isOpen is false', () => {
    render(<TestDialog isOpen={false} />)
    // activeElement should not be one of the buttons (defaults to body)
    expect(document.activeElement).toBe(document.body)
  })

  it('traps Tab key within the container', async () => {
    const user = userEvent.setup()
    render(<TestDialog isOpen={true} />)

    // Focus is on first-btn
    expect(document.activeElement).toBe(screen.getByTestId('first-btn'))

    // Tab to second
    await user.tab()
    expect(document.activeElement).toBe(screen.getByTestId('second-btn'))

    // Tab to last
    await user.tab()
    expect(document.activeElement).toBe(screen.getByTestId('last-btn'))

    // Tab from last should wrap to first
    await user.tab()
    expect(document.activeElement).toBe(screen.getByTestId('first-btn'))
  })

  it('traps Shift+Tab key within the container', async () => {
    const user = userEvent.setup()
    render(<TestDialog isOpen={true} />)

    // Focus is on first-btn; Shift+Tab from first should wrap to last
    await user.tab({ shift: true })
    expect(document.activeElement).toBe(screen.getByTestId('last-btn'))
  })
})
