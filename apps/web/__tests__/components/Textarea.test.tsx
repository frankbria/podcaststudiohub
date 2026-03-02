import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { Textarea } from '@/components/ui/textarea'

describe('Textarea Component', () => {
  it('renders with a placeholder', () => {
    render(<Textarea placeholder="Enter text here" />)
    expect(screen.getByPlaceholderText('Enter text here')).toBeInTheDocument()
  })

  it('accepts typed content', async () => {
    const handleChange = jest.fn()
    const user = userEvent.setup()
    render(<Textarea onChange={handleChange} />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Hello')
    expect(handleChange).toHaveBeenCalled()
  })

  it('is disabled when disabled prop is set', () => {
    render(<Textarea disabled placeholder="disabled" />)
    expect(screen.getByPlaceholderText('disabled')).toBeDisabled()
  })

  it('applies a custom className alongside base classes', () => {
    render(<Textarea className="my-textarea" placeholder="cls" />)
    const ta = screen.getByPlaceholderText('cls')
    expect(ta).toHaveClass('my-textarea')
    expect(ta).toHaveClass('flex')
  })

  it('forwards ref to the underlying textarea element', () => {
    const ref = React.createRef<HTMLTextAreaElement>()
    render(<Textarea ref={ref} placeholder="ref-test" />)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.tagName).toBe('TEXTAREA')
  })
})
