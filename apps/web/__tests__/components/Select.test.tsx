import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
// @radix-ui/react-select is mapped to a stub via jest.config.js moduleNameMapper

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

describe('Select Components', () => {
  function SelectFixture({ defaultValue }: { defaultValue?: string }) {
    return (
      <Select defaultValue={defaultValue}>
        <SelectTrigger aria-label="select-trigger">
          <SelectValue placeholder="Pick an option" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Fruits</SelectLabel>
            <SelectItem value="apple">Apple</SelectItem>
            <SelectItem value="banana">Banana</SelectItem>
            <SelectSeparator />
            <SelectItem value="cherry">Cherry</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    )
  }

  it('renders the select trigger', () => {
    render(<SelectFixture />)
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('shows placeholder when no value is selected', () => {
    render(<SelectFixture />)
    expect(screen.getByText('Pick an option')).toBeInTheDocument()
  })

  it('opens the select and shows options when trigger is clicked', async () => {
    const user = userEvent.setup()
    render(<SelectFixture />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.getByText('Banana')).toBeInTheDocument()
    expect(screen.getByText('Cherry')).toBeInTheDocument()
  })

  it('shows group label when open', async () => {
    const user = userEvent.setup()
    render(<SelectFixture />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByText('Fruits')).toBeInTheDocument()
  })

  it('renders with a default value selected', () => {
    render(<SelectFixture defaultValue="banana" />)
    expect(screen.getByText('banana')).toBeInTheDocument()
  })

  it('applies custom className to SelectTrigger', () => {
    render(
      <Select>
        <SelectTrigger className="custom-trigger" aria-label="trigger">
          <SelectValue placeholder="Pick" />
        </SelectTrigger>
      </Select>
    )
    expect(screen.getByRole('combobox')).toHaveClass('custom-trigger')
  })

  it('SelectContent uses popper position by default', async () => {
    const user = userEvent.setup()
    render(<SelectFixture />)
    await user.click(screen.getByRole('combobox'))
    // When open, content renders with position=popper
    const listbox = screen.getByRole('listbox')
    expect(listbox).toHaveAttribute('data-position', 'popper')
  })
})
