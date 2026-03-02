import { cn } from '@/lib/utils'

describe('cn utility', () => {
  it('returns a single class string when given one class', () => {
    expect(cn('p-2')).toBe('p-2')
  })

  it('merges multiple classes', () => {
    expect(cn('p-2', 'm-4')).toBe('p-2 m-4')
  })

  it('conditionally includes classes — false values are omitted', () => {
    expect(cn('p-2', false && 'hidden')).toBe('p-2')
  })

  it('conditionally includes classes — undefined values are omitted', () => {
    expect(cn('p-2', undefined)).toBe('p-2')
  })

  it('resolves Tailwind conflicts (last wins)', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })

  it('handles empty call (returns empty string)', () => {
    expect(cn()).toBe('')
  })

  it('handles object syntax for conditional classes', () => {
    expect(cn({ 'text-red-500': true, 'text-blue-500': false })).toBe('text-red-500')
  })
})
