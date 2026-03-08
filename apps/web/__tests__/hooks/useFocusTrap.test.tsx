import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { useFocusTrap } from '@/hooks/useFocusTrap'

function TestDialog({ isOpen }: { isOpen: boolean }) {
  const containerRef = useFocusTrap(isOpen)
  if (!isOpen) return null
  return (
    <div ref={containerRef} role="dialog" aria-modal="true">
      <button data-testid="btn-first">First</button>
      <button data-testid="btn-second">Second</button>
      <button data-testid="btn-last">Last</button>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('moves focus to first focusable element when opened', () => {
    const { rerender } = render(<TestDialog isOpen={false} />)
    rerender(<TestDialog isOpen={true} />)
    expect(screen.getByTestId('btn-first')).toHaveFocus()
  })

  it('wraps focus forward from last to first element on Tab', async () => {
    const user = userEvent.setup()
    render(<TestDialog isOpen={true} />)
    // Focus on last element
    screen.getByTestId('btn-last').focus()
    expect(screen.getByTestId('btn-last')).toHaveFocus()
    await user.tab()
    expect(screen.getByTestId('btn-first')).toHaveFocus()
  })

  it('wraps focus backward from first to last on Shift+Tab', async () => {
    const user = userEvent.setup()
    render(<TestDialog isOpen={true} />)
    // Focus on first element
    screen.getByTestId('btn-first').focus()
    expect(screen.getByTestId('btn-first')).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByTestId('btn-last')).toHaveFocus()
  })

  it('does not render the dialog when isOpen is false', () => {
    render(<TestDialog isOpen={false} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
