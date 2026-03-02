import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { Input } from '@/components/ui/input'

describe('Input Component', () => {
  it('renders with a placeholder', () => {
    render(<Input placeholder="Enter value" />)
    expect(screen.getByPlaceholderText('Enter value')).toBeInTheDocument()
  })

  it('accepts and reflects typed value via onChange', async () => {
    const handleChange = jest.fn()
    const user = userEvent.setup()
    render(<Input onChange={handleChange} />)
    const input = screen.getByRole('textbox')
    await user.type(input, 'hello')
    expect(handleChange).toHaveBeenCalled()
  })

  it('is disabled when disabled prop is set', () => {
    render(<Input disabled placeholder="disabled" />)
    const input = screen.getByPlaceholderText('disabled')
    expect(input).toBeDisabled()
    expect(input).toHaveClass('disabled:cursor-not-allowed')
  })

  it('forwards ref to the underlying input element', () => {
    const ref = React.createRef<HTMLInputElement>()
    render(<Input ref={ref} placeholder="ref-test" />)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.tagName).toBe('INPUT')
  })

  it('applies a custom className alongside base classes', () => {
    render(<Input className="my-custom-class" placeholder="cls" />)
    const input = screen.getByPlaceholderText('cls')
    expect(input).toHaveClass('my-custom-class')
    expect(input).toHaveClass('flex')
  })

  it('supports type=email', () => {
    render(<Input type="email" placeholder="email" />)
    const input = screen.getByPlaceholderText('email')
    expect(input).toHaveAttribute('type', 'email')
  })

  it('supports type=password', () => {
    render(<Input type="password" placeholder="password" />)
    const input = screen.getByPlaceholderText('password')
    expect(input).toHaveAttribute('type', 'password')
  })

  it('supports type=text (default)', () => {
    render(<Input type="text" placeholder="text" />)
    const input = screen.getByPlaceholderText('text')
    expect(input).toHaveAttribute('type', 'text')
  })
})
