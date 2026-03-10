import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditProjectDialog } from '@/components/dialogs/EditProjectDialog'

const mockProject = {
  id: 'proj-1',
  title: 'My Podcast',
  description: 'A great podcast',
}

describe('EditProjectDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    project: mockProject,
    onUpdate: jest.fn(),
    token: 'test-token',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()
  })

  it('renders dialog when open', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByText(/edit project/i)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<EditProjectDialog {...defaultProps} open={false} />)
    expect(screen.queryByText(/edit project/i)).not.toBeInTheDocument()
  })

  it('pre-populates title and description from project', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByDisplayValue('My Podcast')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A great podcast')).toBeInTheDocument()
  })

  it('renders Cancel and Update buttons', () => {
    render(<EditProjectDialog {...defaultProps} />)
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('disables Update button when title is empty', async () => {
    const user = userEvent.setup()
    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    expect(screen.getByRole('button', { name: /update/i })).toBeDisabled()
  })

  it('calls PATCH API and onUpdate on successful submission', async () => {
    const user = userEvent.setup()
    const updatedProject = { ...mockProject, title: 'Updated Title' }
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => updatedProject,
    })

    render(<EditProjectDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('My Podcast')
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Title')
    await user.click(screen.getByRole('button', { name: /update/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/projects/proj-1'),
        expect.objectContaining({ method: 'PATCH' })
      )
      expect(defaultProps.onUpdate).toHaveBeenCalledWith(updatedProject)
    })
  })

  it('shows error message when update fails', async () => {
    const user = userEvent.setup()
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Server error' }),
      statusText: 'Internal Server Error',
    })

    render(<EditProjectDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /update/i }))

    await waitFor(() => {
      expect(screen.getByText(/failed to update/i)).toBeInTheDocument()
    })
  })

  it('disables Update button while submitting', async () => {
    const user = userEvent.setup()
    let resolveRequest: (value: any) => void
    const pendingRequest = new Promise((resolve) => {
      resolveRequest = resolve
    })
    ;(global.fetch as jest.Mock).mockReturnValue(pendingRequest)

    render(<EditProjectDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /update/i }))

    expect(screen.getByRole('button', { name: /updating/i })).toBeDisabled()
    resolveRequest!({ ok: true, json: async () => mockProject })
  })
})
