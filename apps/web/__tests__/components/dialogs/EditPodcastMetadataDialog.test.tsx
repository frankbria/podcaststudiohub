import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditPodcastMetadataDialog } from '@/components/dialogs/EditPodcastMetadataDialog'

describe('EditPodcastMetadataDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: jest.fn(),
    onSubmitMetadata: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the dialog title', () => {
    render(<EditPodcastMetadataDialog {...defaultProps} />)
    expect(screen.getByText('Edit Podcast Metadata')).toBeInTheDocument()
  })

  it('does not render content when closed', () => {
    render(<EditPodcastMetadataDialog {...defaultProps} open={false} />)
    expect(screen.queryByText('Edit Podcast Metadata')).not.toBeInTheDocument()
  })

  it('prefills fields from initialMetadata', () => {
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        initialMetadata={{
          showTitle: 'My Show',
          author: 'Jane Doe',
          description: 'A great show',
          category: 'Technology',
          language: 'en-US',
          explicit: true,
          copyright: '© 2026 Jane',
          artworkUrl: 'https://example.com/art.png',
          websiteUrl: 'https://example.com',
        }}
      />
    )
    expect(screen.getByDisplayValue('My Show')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Jane Doe')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A great show')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Technology')).toBeInTheDocument()
    expect(screen.getByDisplayValue('en-US')).toBeInTheDocument()
    expect(screen.getByLabelText('Explicit content')).toBeChecked()
    expect(screen.getByDisplayValue('© 2026 Jane')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://example.com/art.png')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://example.com')).toBeInTheDocument()
  })

  it('renders empty fields when no initialMetadata is given', () => {
    render(<EditPodcastMetadataDialog {...defaultProps} />)
    expect(screen.getByLabelText(/show title/i)).toHaveValue('')
    expect(screen.getByLabelText('Explicit content')).not.toBeChecked()
  })

  it('shows validation errors when required fields are empty and touched', async () => {
    const user = userEvent.setup()
    render(<EditPodcastMetadataDialog {...defaultProps} />)

    const showTitleInput = screen.getByLabelText(/show title/i)
    await user.type(showTitleInput, 'x')
    await user.clear(showTitleInput)

    await waitFor(() => {
      expect(screen.getByText('Show title is required')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
  })

  it('shows a validation error when author is cleared', async () => {
    const user = userEvent.setup()
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        initialMetadata={{ showTitle: 'My Show', author: 'Jane Doe', description: 'A great show' }}
      />
    )

    const authorInput = screen.getByLabelText(/^author/i)
    await user.clear(authorInput)

    await waitFor(() => {
      expect(screen.getByText('Author is required')).toBeInTheDocument()
    })
  })

  it('shows a validation error when description is cleared', async () => {
    const user = userEvent.setup()
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        initialMetadata={{ showTitle: 'My Show', author: 'Jane Doe', description: 'A great show' }}
      />
    )

    const descriptionInput = screen.getByLabelText(/description/i)
    await user.clear(descriptionInput)

    await waitFor(() => {
      expect(screen.getByText('Description is required')).toBeInTheDocument()
    })
  })

  it('rejects an invalid website URL', async () => {
    const user = userEvent.setup()
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        initialMetadata={{
          showTitle: 'My Show',
          author: 'Jane Doe',
          description: 'A great show',
        }}
      />
    )

    const websiteInput = screen.getByLabelText(/website url/i)
    await user.type(websiteInput, 'not-a-url')

    await waitFor(() => {
      expect(screen.getByText('Must be a valid URL')).toBeInTheDocument()
    })
  })

  it('rejects an invalid artwork URL', async () => {
    const user = userEvent.setup()
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        initialMetadata={{
          showTitle: 'My Show',
          author: 'Jane Doe',
          description: 'A great show',
        }}
      />
    )

    const artworkInput = screen.getByLabelText(/artwork url/i)
    await user.type(artworkInput, 'not-a-url')

    await waitFor(() => {
      expect(screen.getByText('Must be a valid URL')).toBeInTheDocument()
    })
  })

  it('calls onSubmitMetadata with trimmed values and snake_case-ready camelCase data on submit', async () => {
    const user = userEvent.setup()
    const onSubmitMetadata = jest.fn().mockResolvedValue(undefined)
    render(
      <EditPodcastMetadataDialog
        {...defaultProps}
        onSubmitMetadata={onSubmitMetadata}
        initialMetadata={{
          showTitle: '  My Show  ',
          author: '  Jane Doe  ',
          description: '  A great show  ',
        }}
      />
    )

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(onSubmitMetadata).toHaveBeenCalledWith(
        expect.objectContaining({
          showTitle: 'My Show',
          author: 'Jane Doe',
          description: 'A great show',
        })
      )
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditPodcastMetadataDialog {...defaultProps} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
