// Registers @testing-library/jest-dom's global `jest.Matchers` augmentation
// (toBeInTheDocument, toBeEnabled, …) for `tsc --noEmit`. The matchers are
// loaded at runtime by jest.setup.js; this .d.ts makes them visible to the
// type checker, which doesn't pick up the augmentation from the .js setup file.
import "@testing-library/jest-dom"
