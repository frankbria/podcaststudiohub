import * as React from 'react'

interface RootProps {
  children: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const RootContext = React.createContext<{
  open: boolean
  setOpen: (open: boolean) => void
}>({ open: false, setOpen: () => {} })

const Root = ({ children, open: controlledOpen, onOpenChange }: RootProps) => {
  const [internalOpen, setInternalOpen] = React.useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = (value: boolean) => {
    setInternalOpen(value)
    onOpenChange?.(value)
  }
  return (
    <RootContext.Provider value={{ open, setOpen }}>
      <div data-open={open}>{children}</div>
    </RootContext.Provider>
  )
}

const Trigger = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ children, className, ...props }, ref) => {
    const { open, setOpen } = React.useContext(RootContext)
    return (
      <button
        ref={ref}
        aria-expanded={open}
        aria-haspopup="menu"
        className={className}
        onClick={() => setOpen(!open)}
        {...props}
      >
        {children}
      </button>
    )
  }
)
Trigger.displayName = 'DropdownMenuTrigger'

const Portal = ({ children }: { children: React.ReactNode }) => <>{children}</>

const Content = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { sideOffset?: number; align?: string }
>(({ children, className, sideOffset: _sideOffset, align: _align, ...props }, ref) => {
  const { open } = React.useContext(RootContext)
  if (!open) return null
  return (
    <div ref={ref} role="menu" className={className} {...props}>
      {children}
    </div>
  )
})
Content.displayName = 'DropdownMenuContent'

const Item = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { inset?: boolean; disabled?: boolean }
>(({ children, className, inset: _inset, disabled, onClick, ...props }, ref) => {
  const { setOpen } = React.useContext(RootContext)
  return (
    <div
      ref={ref}
      role="menuitem"
      aria-disabled={disabled}
      className={className}
      onClick={(e) => {
        if (!disabled) {
          onClick?.(e)
          setOpen(false)
        }
      }}
      {...props}
    >
      {children}
    </div>
  )
})
Item.displayName = 'DropdownMenuItem'

const Label = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { inset?: boolean }
>(({ children, className, inset: _inset, ...props }, ref) => (
  <div ref={ref} className={className} {...props}>
    {children}
  </div>
))
Label.displayName = 'DropdownMenuLabel'

const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} role="separator" className={className} {...props} />
  )
)
Separator.displayName = 'DropdownMenuSeparator'

const Group = ({ children }: { children: React.ReactNode }) => <div role="group">{children}</div>

const Sub = ({ children }: { children: React.ReactNode }) => <>{children}</>

const RadioGroup = ({ children }: { children: React.ReactNode }) => <div>{children}</div>

export {
  Root,
  Trigger,
  Portal,
  Content,
  Item,
  Label,
  Separator,
  Group,
  Sub,
  RadioGroup,
}
