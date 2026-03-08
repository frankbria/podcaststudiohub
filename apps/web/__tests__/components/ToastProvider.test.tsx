import { render } from "@testing-library/react"
import * as React from "react"
import { ToastProvider } from "@/components/providers/toast-provider"

// Mock sonner Toaster component
jest.mock("sonner", () => ({
  Toaster: jest.fn(({ position, richColors, closeButton, visibleToasts, expand }: any) => (
    <div
      data-testid="sonner-toaster"
      data-position={position}
      data-rich-colors={String(richColors)}
      data-close-button={String(closeButton)}
      data-visible-toasts={visibleToasts}
      data-expand={String(expand)}
    />
  )),
}))

describe("ToastProvider", () => {
  it("renders the Toaster component", () => {
    const { getByTestId } = render(<ToastProvider />)
    expect(getByTestId("sonner-toaster")).toBeInTheDocument()
  })

  it("renders Toaster with top-right position", () => {
    const { getByTestId } = render(<ToastProvider />)
    expect(getByTestId("sonner-toaster")).toHaveAttribute(
      "data-position",
      "top-right"
    )
  })

  it("renders Toaster with richColors enabled", () => {
    const { getByTestId } = render(<ToastProvider />)
    expect(getByTestId("sonner-toaster")).toHaveAttribute(
      "data-rich-colors",
      "true"
    )
  })

  it("renders Toaster with closeButton enabled", () => {
    const { getByTestId } = render(<ToastProvider />)
    expect(getByTestId("sonner-toaster")).toHaveAttribute(
      "data-close-button",
      "true"
    )
  })

  it("renders Toaster with visibleToasts=3", () => {
    const { getByTestId } = render(<ToastProvider />)
    expect(getByTestId("sonner-toaster")).toHaveAttribute(
      "data-visible-toasts",
      "3"
    )
  })
})
