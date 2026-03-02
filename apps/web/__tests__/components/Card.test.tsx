import { render, screen } from '@testing-library/react'
import * as React from 'react'
import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'

describe('Card Components', () => {
  it('Card renders its children', () => {
    render(<Card>card content</Card>)
    expect(screen.getByText('card content')).toBeInTheDocument()
  })

  it('Card applies a custom className', () => {
    render(<Card className="my-card">content</Card>)
    expect(screen.getByText('content')).toHaveClass('my-card')
  })

  it('CardHeader renders children correctly', () => {
    render(<CardHeader>header content</CardHeader>)
    expect(screen.getByText('header content')).toBeInTheDocument()
  })

  it('CardContent renders children correctly', () => {
    render(<CardContent>body content</CardContent>)
    expect(screen.getByText('body content')).toBeInTheDocument()
  })

  it('CardFooter renders children correctly', () => {
    render(<CardFooter>footer content</CardFooter>)
    expect(screen.getByText('footer content')).toBeInTheDocument()
  })

  it('CardTitle renders as an h3', () => {
    render(<CardTitle>My Title</CardTitle>)
    const heading = screen.getByRole('heading', { name: /my title/i })
    expect(heading.tagName).toBe('H3')
  })

  it('CardDescription renders as a paragraph with children', () => {
    render(<CardDescription>Some description</CardDescription>)
    const desc = screen.getByText('Some description')
    expect(desc.tagName).toBe('P')
  })

  it('composed Card renders all nested components', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title Text</CardTitle>
          <CardDescription>Desc Text</CardDescription>
        </CardHeader>
        <CardContent>Body Text</CardContent>
        <CardFooter>Footer Text</CardFooter>
      </Card>
    )
    expect(screen.getByText('Title Text')).toBeInTheDocument()
    expect(screen.getByText('Desc Text')).toBeInTheDocument()
    expect(screen.getByText('Body Text')).toBeInTheDocument()
    expect(screen.getByText('Footer Text')).toBeInTheDocument()
  })
})
