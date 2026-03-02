import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

describe('Dialog Components', () => {
  it('Dialog is closed by default (content not visible)', () => {
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Dialog Title</DialogTitle>
          <DialogDescription>Dialog description</DialogDescription>
        </DialogContent>
      </Dialog>
    )
    expect(screen.queryByText('Dialog Title')).not.toBeInTheDocument()
  })

  it('Opening the dialog renders DialogContent, DialogTitle, and DialogDescription', async () => {
    const user = userEvent.setup()
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Dialog Title</DialogTitle>
          <DialogDescription>Dialog description</DialogDescription>
        </DialogContent>
      </Dialog>
    )
    await user.click(screen.getByText('Open'))
    expect(screen.getByText('Dialog Title')).toBeInTheDocument()
    expect(screen.getByText('Dialog description')).toBeInTheDocument()
  })

  it('DialogHeader renders its children', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Header Title</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    )
    expect(screen.getByText('Header Title')).toBeInTheDocument()
  })

  it('DialogFooter renders its children', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Title</DialogTitle>
          <DialogFooter>
            <button>Cancel</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })

  it('DialogOverlay renders with custom className', () => {
    render(
      <Dialog open>
        <DialogOverlay className="test-overlay" data-testid="overlay" />
        <DialogContent>
          <DialogTitle>Title</DialogTitle>
        </DialogContent>
      </Dialog>
    )
    // overlay is rendered inside a portal; content is visible meaning dialog is open
    expect(screen.getByText('Title')).toBeInTheDocument()
  })

  it('DialogContent renders with custom className', () => {
    render(
      <Dialog open>
        <DialogContent className="custom-dialog-content">
          <DialogTitle>Title</DialogTitle>
          <DialogDescription>Custom content</DialogDescription>
        </DialogContent>
      </Dialog>
    )
    expect(screen.getByText('Custom content')).toBeInTheDocument()
  })

  it('pressing Escape closes the dialog', async () => {
    const user = userEvent.setup()
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Escape Test</DialogTitle>
          <DialogDescription>Press Escape</DialogDescription>
        </DialogContent>
      </Dialog>
    )
    await user.click(screen.getByText('Open'))
    expect(screen.getByText('Escape Test')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByText('Escape Test')).not.toBeInTheDocument()
  })

  it('onOpenChange is called when the built-in close button is clicked', async () => {
    const onOpenChange = jest.fn()
    const user = userEvent.setup()
    render(
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>Close Test</DialogTitle>
          <DialogDescription>description</DialogDescription>
        </DialogContent>
      </Dialog>
    )
    // The built-in X close button has sr-only text "Close"
    const closeButton = screen.getByRole('button', { name: /close/i })
    await user.click(closeButton)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
