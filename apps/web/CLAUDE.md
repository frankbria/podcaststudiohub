# apps/web — Frontend Design System

This Next.js app uses the **shadcn Nova template** with a gray theme.

## Rules (enforced by ESLint)

- **Never import from `lucide-react`** — it is banned. ESLint will error.
- **Always use `@hugeicons/react` + `@hugeicons/core-free-icons`** for icons.

## Backend Error Bodies — Always Use `extractApiErrorDetail`

FastAPI returns `detail` in **two** shapes:

| Source | Shape |
|---|---|
| `HTTPException` | `{"detail": "Email already registered"}` — a string |
| Pydantic validation (**every 422**) | `{"detail": [{"msg", "loc", "type"}, …]}` — an **array** |

Never read `body.detail` directly. `response.json()` is `any`, so TypeScript will not catch it,
and putting the array into string state and rendering it throws *"Objects are not valid as a React
child"* — which killed the whole signup route in #481.

```ts
import { extractApiErrorDetail } from "@/lib/api-error"

const body = await response.json()
setError(extractApiErrorDetail(body, "Registration failed"))
```

A route-level error boundary (`src/app/error.tsx`) bounds the damage from any render throw, but it
is a backstop, not a licence to skip the helper.

## Icon Usage

```tsx
import { HugeiconsIcon } from "@hugeicons/react"
import { Cancel01Icon, Tick01Icon, ArrowDown01Icon } from "@hugeicons/core-free-icons"

<HugeiconsIcon icon={Cancel01Icon} size={16} />
```

Common mappings from lucide names:
| lucide-react | Hugeicons |
|---|---|
| `X` / `XIcon` | `Cancel01Icon` |
| `Check` | `Tick01Icon` |
| `ChevronDown` | `ArrowDown01Icon` |
| `ChevronUp` | `ArrowUp01Icon` |
| `Clock` | `Loading03Icon` |
| `CheckCircle` | `CheckmarkCircle01Icon` |
| `FileText` | `FileEditIcon` |

## Colors — Use Design Tokens, Not Hardcoded Classes

| Instead of | Use |
|---|---|
| `bg-gray-50` | `bg-background` |
| `bg-gray-100` / `bg-gray-200` | `bg-muted` |
| `text-gray-600` / `text-gray-700` | `text-muted-foreground` |
| `text-gray-900` | `text-foreground` |
| `text-red-600` | `text-destructive` |
| `text-blue-600` | `text-primary` |
| `bg-red-*/text-red-*` | `bg-destructive/20 text-destructive` |
| `bg-green-*/text-green-*` | `bg-muted text-foreground` (or a Badge) |
| `bg-yellow-*/text-yellow-*` | `bg-accent text-accent-foreground` |

## Typography

Font: **Nunito Sans** via `next/font/google` — loaded in `layout.tsx` as a CSS variable `--font-nunito-sans`, applied via `tailwind.config.ts` `fontFamily.sans`.

## Adding New Components

```bash
cd apps/web
npx shadcn@latest add <component>
```

With `components.json` in place (style=nova, baseColor=gray, iconLibrary=hugeicons), this will auto-generate Nova-styled components.

## Adding New Jest Mocks for Hugeicons

If you add a new Hugeicons icon and tests fail, add the icon name to `__mocks__/@hugeicons/core-free-icons.ts`:

```ts
export const MyNewIcon = { type: 'svg', data: [] }
```
