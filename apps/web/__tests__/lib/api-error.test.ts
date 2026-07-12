import { extractApiErrorDetail } from "@/lib/api-error"

describe("extractApiErrorDetail", () => {
  it("returns a string detail as-is (HTTPException shape)", () => {
    expect(extractApiErrorDetail({ detail: "Project not found" }, "fallback")).toBe(
      "Project not found"
    )
  })

  it("joins msg fields from an array detail (Pydantic validation shape)", () => {
    const body = {
      detail: [
        { type: "value_error", loc: ["body", "url"], msg: "Value error, Webhook URL is not allowed" },
        { type: "missing", loc: ["body", "name"], msg: "Field required" },
      ],
    }
    expect(extractApiErrorDetail(body, "fallback")).toBe(
      "Value error, Webhook URL is not allowed; Field required"
    )
  })

  it("falls back when detail is missing", () => {
    expect(extractApiErrorDetail({}, "fallback")).toBe("fallback")
  })

  it("falls back when body is null", () => {
    expect(extractApiErrorDetail(null, "fallback")).toBe("fallback")
  })

  it("falls back when array entries have no string msg", () => {
    expect(extractApiErrorDetail({ detail: [{ msg: 42 }, {}] }, "fallback")).toBe("fallback")
  })
})
