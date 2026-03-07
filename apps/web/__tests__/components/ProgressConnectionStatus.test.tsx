import React from "react"
import { render, screen } from "@testing-library/react"
import { ProgressConnectionStatus } from "@/components/ProgressConnectionStatus"
import type { ConnectionStatus } from "@/lib/event-source-client"

describe("ProgressConnectionStatus", () => {
  const cases: Array<{ status: ConnectionStatus; expectedText: string }> = [
    { status: "connecting", expectedText: "Connecting..." },
    { status: "connected", expectedText: "Connected" },
    { status: "reconnecting", expectedText: "Reconnecting..." },
    { status: "error", expectedText: "Connection lost, retrying..." },
    { status: "polling", expectedText: "Using polling mode" },
    { status: "complete", expectedText: "Generation complete" },
  ]

  test.each(cases)("renders correct text for status '$status'", ({ status, expectedText }) => {
    render(<ProgressConnectionStatus status={status} />)
    expect(screen.getByText(expectedText)).toBeInTheDocument()
  })

  it("has a status role for accessibility", () => {
    render(<ProgressConnectionStatus status="connected" />)
    expect(screen.getByRole("status")).toBeInTheDocument()
  })

  it("has an aria-label matching the status text", () => {
    render(<ProgressConnectionStatus status="reconnecting" />)
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Reconnecting...")
  })
})
