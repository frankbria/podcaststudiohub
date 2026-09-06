import { createRequire } from 'node:module'

import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'
import nextTypescript from 'eslint-config-next/typescript'

const require = createRequire(import.meta.url)

// eslint-plugin-react detects the React version by resolving from
// `context.getFilename()`, which ESLint 10 removed -- leaving it to autodetect
// crashes the run outright. Reading the version from the installed package
// pins it without hard-coding a number that would silently go stale on the
// next React upgrade.
const reactVersion = require('react/package.json').version

// Flat config. The legacy .eslintrc.json this replaces was demoted behind a
// flag in ESLint 9 and removed outright in ESLint 10 (#458); eslint-config-next
// 16 exports flat config arrays directly, so no FlatCompat shim is needed.
const config = [
  {
    ignores: [
      'node_modules/',
      '.next/',
      'out/',
      'coverage/',
      'next-env.d.ts',
      'playwright-report/',
      'test-results/',
    ],
  },

  ...nextCoreWebVitals,
  ...nextTypescript,

  {
    settings: { react: { version: reactVersion } },
    rules: {
      // Enforcement mechanism for the Hugeicons-only policy in
      // apps/web/CLAUDE.md -- without it nothing stops lucide-react from
      // creeping back into the codebase.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'lucide-react',
              message:
                "This project uses Hugeicons. Import from '@hugeicons/react' and '@hugeicons/core-free-icons' instead. See apps/web/CLAUDE.md for icon mappings.",
            },
          ],
        },
      ],

      // eslint-config-next 16 pulls eslint-plugin-react-hooks 7, which added a
      // compiler-derived rule set the 15.x config never ran. Adopting it is
      // real refactoring (10 findings across app code, chiefly effects that
      // setState synchronously), not lint plumbing -- the same call made for
      // ruff's widened default set, which is pinned in apps/api/pyproject.toml
      // rather than adopted here. Tracked in #482; delete these two lines when
      // that lands.
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/incompatible-library': 'off',
    },
  },

  {
    // Tests exercise untyped mocks and jest.requireActual, so `any` and
    // require() are idiomatic here rather than a smell. src/ stays strict:
    // it lints clean with these rules on, and that is the point of scoping
    // the relaxation instead of disabling the rules outright.
    files: [
      '__tests__/**/*.{ts,tsx,js,jsx}',
      'e2e/**/*.{ts,tsx}',
      '**/*.test.{ts,tsx,js,jsx}',
      'jest.setup.{js,ts}',
    ],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-require-imports': 'off',
    },
  },

  {
    // Tooling configs are CommonJS by contract (jest, tailwind plugins);
    // require() is the supported form, not a lapse.
    files: ['*.config.{js,ts,mjs,cjs}'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
]

export default config
