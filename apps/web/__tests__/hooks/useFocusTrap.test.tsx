import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { useFocusTrap } from '@/hooks/useFocusTrap'

function FocusTrapWrapper({ isOpen }: { isOpen: boolean }) {
  const ref = useFocusTrap(isOpen)
  return (
    <div ref={ref}>
      <button>First</button>
      <button>Second</button>
      <button>Last</button>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('focuses the first element when opened', () => {
    render(<FocusTrapWrapper isOpen={true} />)
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
  })

  it('does not focus when closed', () => {
    render(<FocusTrapWrapper isOpen={false} />)
    // No button should have focus
    expect(screen.getByRole('button', { name: 'First' })).not.toHaveFocus()
  })

  it('wraps Tab from last to first element', async () => {
    const user = userEvent.setup()
    render(<FocusTrapWrapper isOpen={true} />)

    // Focus starts at first
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()

    // Tab to second
    await user.tab()
    expect(screen.getByRole('button', { name: 'Second' })).toHaveFocus()

    // Tab to last
    await user.tab()
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus()

    // Tab from last should wrap to first
    await user.tab()
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
  })

  it('wraps Shift+Tab from first to last element', async () => {
    const user = userEvent.setup()
    render(<FocusTrapWrapper isOpen={true} />)

    // Focus starts at first
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()

    // Shift+Tab from first should wrap to last
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus()
  })
})
