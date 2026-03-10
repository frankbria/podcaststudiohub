import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { EditEpisodeDialog } from '@/components/dialogs/EditEpisodeDialog'

const mockEpisode = {
  id: 'ep-1',
  title: 'Episode 1',
  description: 'First episode',
  generation_status: 'draft',
  project_id: 'proj-1',
}

describe('EditEpisodeDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    episode: mockEpisode,
    onUpdate: jest.fn(),
    token: 'test-token',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()
  })

  it('renders dialog when open', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByText(/edit episode/i)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<EditEpisodeDialog {...defaultProps} open={false} />)
    expect(screen.queryByText(/edit episode/i)).not.toBeInTheDocument()
  })

  it('pre-populates title from episode', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByDisplayValue('Episode 1')).toBeInTheDocument()
  })

  it('renders Cancel and Update buttons', () => {
    render(<EditEpisodeDialog {...defaultProps} />)
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('disables Update button when title is empty', async () => {
    const user = userEvent.setup()
    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1')
    await user.clear(titleInput)
    expect(screen.getByRole('button', { name: /update/i })).toBeDisabled()
  })

  it('calls PATCH API and onUpdate on successful submission', async () => {
    const user = userEvent.setup()
    const updatedEpisode = { ...mockEpisode, title: 'Updated Episode' }
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => updatedEpisode,
    })

    render(<EditEpisodeDialog {...defaultProps} />)
    const titleInput = screen.getByDisplayValue('Episode 1')
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Episode')
    await user.click(screen.getByRole('button', { name: /update/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/episodes/ep-1'),
        expect.objectContaining({ method: 'PATCH' })
      )
      expect(defaultProps.onUpdate).toHaveBeenCalledWith(updatedEpisode)
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

    render(<EditEpisodeDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /update/i }))

    await waitFor(() => {
      expect(screen.getByText(/failed to update/i)).toBeInTheDocument()
    })
  })
})
