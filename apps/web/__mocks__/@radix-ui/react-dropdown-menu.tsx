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
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen
  const setOpen = (val: boolean) => {
    setInternalOpen(val)
    onOpenChange?.(val)
  }
  return (
    <RootContext.Provider value={{ open, setOpen }}>
      <div>{children}</div>
    </RootContext.Provider>
  )
}

const Trigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }
>(({ children, asChild, ...props }, ref) => {
  const { open, setOpen } = React.useContext(RootContext)
  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<React.HTMLAttributes<HTMLElement>>, {
      onClick: () => setOpen(!open),
      'aria-expanded': open,
    } as React.HTMLAttributes<HTMLElement>)
  }
  return (
    <button ref={ref} aria-expanded={open} onClick={() => setOpen(!open)} {...props}>
      {children}
    </button>
  )
})
Trigger.displayName = 'DropdownMenuTrigger'

const Portal = ({ children }: { children: React.ReactNode }) => <>{children}</>

const Content = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { align?: string; sideOffset?: number }
>(({ children, className, align, sideOffset, ...props }, ref) => {
  const { open } = React.useContext(RootContext)
  if (!open) return null
  return (
    <div ref={ref} className={className} role="menu" {...props}>
      {children}
    </div>
  )
})
Content.displayName = 'DropdownMenuContent'

const Item = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { disabled?: boolean; asChild?: boolean; inset?: boolean }
>(({ children, className, disabled, onClick, ...props }, ref) => {
  const { setOpen } = React.useContext(RootContext)
  return (
    <div
      ref={ref}
      role="menuitem"
      className={className}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
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
>(({ children, className, ...props }, ref) => (
  <div ref={ref} className={className} {...props}>
    {children}
  </div>
))
Label.displayName = 'DropdownMenuLabel'

const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={className} role="separator" {...props} />
  )
)
Separator.displayName = 'DropdownMenuSeparator'

const Group = ({ children }: { children: React.ReactNode }) => <div role="group">{children}</div>

const Sub = ({ children }: { children: React.ReactNode }) => <>{children}</>

const SubTrigger = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { inset?: boolean }
>(({ children, className, ...props }, ref) => (
  <div ref={ref} role="menuitem" className={className} {...props}>
    {children}
  </div>
))
SubTrigger.displayName = 'DropdownMenuSubTrigger'

const SubContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={className} role="menu" {...props}>
      {children}
    </div>
  )
)
SubContent.displayName = 'DropdownMenuSubContent'

const CheckboxItem = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { checked?: boolean }
>(({ children, className, ...props }, ref) => (
  <div ref={ref} role="menuitemcheckbox" className={className} {...props}>
    {children}
  </div>
))
CheckboxItem.displayName = 'DropdownMenuCheckboxItem'

const RadioGroup = ({ children }: { children: React.ReactNode }) => <div role="radiogroup">{children}</div>

const RadioItem = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: string }
>(({ children, className, ...props }, ref) => (
  <div ref={ref} role="menuitemradio" className={className} {...props}>
    {children}
  </div>
))
RadioItem.displayName = 'DropdownMenuRadioItem'

const ItemIndicator = ({ children }: { children?: React.ReactNode }) => <span>{children}</span>
const Shortcut = ({ children }: { children?: React.ReactNode }) => <span>{children}</span>

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
  SubTrigger,
  SubContent,
  CheckboxItem,
  RadioGroup,
  RadioItem,
  ItemIndicator,
  Shortcut,
}
