/**
 * The Hugeicons-only policy in apps/web/CLAUDE.md is enforced by exactly one
 * thing: the `no-restricted-imports` rule on `lucide-react` in
 * eslint.config.mjs. A config migration that drops it (the eslintrc -> flat
 * config move in #458 was one such migration) would take the enforcement with
 * it and nothing would report the loss -- the tree would simply keep linting
 * clean while the wrong icon library walked back in.
 *
 * So assert the rule fires, rather than trusting that the config still says so.
 */
import { execFileSync } from "node:child_process"
import path from "node:path"

import type { Linter } from "eslint"

// Each case spawns a real eslint, which loads next's plugins from disk.
jest.setTimeout(120_000)

const webRoot = path.resolve(__dirname, "..", "..")
// eslint's exports map does not expose bin/, so resolve the package root.
const eslintBin = path.join(path.dirname(require.resolve("eslint/package.json")), "bin", "eslint.js")

/**
 * eslint is run as a subprocess rather than through its Node API: the API
 * reaches the .mjs config by dynamic import, which jest's VM refuses without
 * --experimental-vm-modules. The subprocess also exercises the same entry
 * point CI does.
 */
const lint = (code: string, filePath: string): Linter.LintMessage[] => {
  const args = [eslintBin, "--stdin", "--stdin-filename", filePath, "-f", "json"]
  let stdout: string

  try {
    stdout = execFileSync(process.execPath, args, {
      cwd: webRoot,
      input: code,
      encoding: "utf8",
    })
  } catch (err) {
    const failure = err as { status?: number | null; stdout?: string }
    // Exit 1 just means eslint reported problems, which is the point here.
    // Anything else (2 = config could not be loaded) is a genuine failure.
    if (failure.status !== 1 || !failure.stdout) throw err
    stdout = failure.stdout
  }

  return JSON.parse(stdout)[0].messages
}

const restrictedImports = (messages: Linter.LintMessage[]) =>
  messages.filter((m) => m.ruleId === "no-restricted-imports")

describe("icon library policy", () => {
  it("rejects a lucide-react import in src/", () => {
    const messages = lint(
      `import { Home } from "lucide-react"\nexport const icon = Home\n`,
      "src/components/icon-policy-probe.ts",
    )

    const restricted = restrictedImports(messages)
    expect(restricted).toHaveLength(1)
    expect(restricted[0].severity).toBe(2)
    expect(restricted[0].message).toMatch(/Hugeicons/)
  })

  it("allows the Hugeicons imports it points people at", () => {
    const messages = lint(
      `import { HugeiconsIcon } from "@hugeicons/react"\n` +
        `import { Home01Icon } from "@hugeicons/core-free-icons"\n` +
        `export const icon = [HugeiconsIcon, Home01Icon]\n`,
      "src/components/icon-policy-probe.ts",
    )

    expect(restrictedImports(messages)).toHaveLength(0)
  })
})
