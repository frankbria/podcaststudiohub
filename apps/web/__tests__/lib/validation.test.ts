import {
  projectSchema,
  episodeSchema,
  contentSourceSchema,
} from "@/lib/validation"

describe("projectSchema", () => {
  it("accepts valid title", () => {
    const result = projectSchema.safeParse({ title: "My Podcast" })
    expect(result.success).toBe(true)
  })

  it("rejects empty title", () => {
    const result = projectSchema.safeParse({ title: "" })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("Title is required")
    }
  })

  it("rejects whitespace-only title", () => {
    const result = projectSchema.safeParse({ title: "   " })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toMatch(/whitespace|required/i)
    }
  })

  it("rejects title over 200 characters", () => {
    const result = projectSchema.safeParse({ title: "a".repeat(201) })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("Title must be 200 characters or less")
    }
  })

  it("accepts title of exactly 200 characters", () => {
    const result = projectSchema.safeParse({ title: "a".repeat(200) })
    expect(result.success).toBe(true)
  })

  it("accepts description within limit", () => {
    const result = projectSchema.safeParse({ title: "Test", description: "A description" })
    expect(result.success).toBe(true)
  })

  it("rejects description over 1000 characters", () => {
    const result = projectSchema.safeParse({ title: "Test", description: "a".repeat(1001) })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("Description must be 1000 characters or less")
    }
  })

  it("accepts missing description", () => {
    const result = projectSchema.safeParse({ title: "Test" })
    expect(result.success).toBe(true)
  })
})

describe("episodeSchema", () => {
  it("accepts valid title", () => {
    const result = episodeSchema.safeParse({ title: "Episode 1" })
    expect(result.success).toBe(true)
  })

  it("rejects empty title", () => {
    const result = episodeSchema.safeParse({ title: "" })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("Episode title is required")
    }
  })

  it("rejects whitespace-only title", () => {
    const result = episodeSchema.safeParse({ title: "  " })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toMatch(/whitespace|required/i)
    }
  })

  it("rejects title over 200 characters", () => {
    const result = episodeSchema.safeParse({ title: "a".repeat(201) })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("Episode title must be 200 characters or less")
    }
  })
})

describe("contentSourceSchema - URL type", () => {
  it("accepts valid http URL", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "http://example.com",
    })
    expect(result.success).toBe(true)
  })

  it("accepts valid https URL", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "https://example.com/article",
    })
    expect(result.success).toBe(true)
  })

  it("accepts YouTube URL", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "https://www.youtube.com/watch?v=test123",
    })
    expect(result.success).toBe(true)
  })

  it("rejects empty URL", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "",
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const urlError = result.error.issues.find((i) => i.path.includes("url"))
      expect(urlError?.message).toBeTruthy()
    }
  })

  it("rejects non-URL string", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "not-a-url",
    })
    expect(result.success).toBe(false)
  })

  it("rejects ftp protocol", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "url",
      url: "ftp://example.com",
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const urlError = result.error.issues.find((i) => i.path.includes("url"))
      expect(urlError?.message).toMatch(/http|https|protocol/i)
    }
  })
})

describe("contentSourceSchema - text type", () => {
  it("accepts valid text content", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "text",
      content: "This is some valid content that is long enough",
    })
    expect(result.success).toBe(true)
  })

  it("rejects empty content", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "text",
      content: "",
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const contentError = result.error.issues.find((i) => i.path.includes("content"))
      expect(contentError?.message).toBeTruthy()
    }
  })

  it("rejects content under 10 characters", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "text",
      content: "short",
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const contentError = result.error.issues.find((i) => i.path.includes("content"))
      expect(contentError?.message).toBe("Content must be at least 10 characters")
    }
  })

  it("rejects content over 50000 characters", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "text",
      content: "a".repeat(50001),
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const contentError = result.error.issues.find((i) => i.path.includes("content"))
      expect(contentError?.message).toBe("Content must be under 50,000 characters")
    }
  })

  it("accepts content of exactly 10 characters", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "text",
      content: "a".repeat(10),
    })
    expect(result.success).toBe(true)
  })
})

describe("contentSourceSchema - PDF type", () => {
  const makePdf = (overrides: { type?: string; size?: number } = {}) => {
    const file = new File(["%PDF-1.4"], "doc.pdf", {
      type: overrides.type ?? "application/pdf",
    })
    if (overrides.size !== undefined) {
      Object.defineProperty(file, "size", { value: overrides.size })
    }
    return file
  }

  it("accepts a selected PDF file", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "pdf",
      file: [makePdf()],
    })
    expect(result.success).toBe(true)
  })

  it("rejects when no file is selected", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "pdf",
      file: [],
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const fileError = result.error.issues.find((i) => i.path.includes("file"))
      expect(fileError?.message).toBe("PDF file is required")
    }
  })

  it("rejects a non-PDF file", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "pdf",
      file: [makePdf({ type: "text/plain" })],
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const fileError = result.error.issues.find((i) => i.path.includes("file"))
      expect(fileError?.message).toBe("File must be a PDF")
    }
  })

  it("rejects a PDF over 50MB", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "pdf",
      file: [makePdf({ size: 50 * 1024 * 1024 + 1 })],
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const fileError = result.error.issues.find((i) => i.path.includes("file"))
      expect(fileError?.message).toBe("PDF must be 50MB or less")
    }
  })

  it("accepts a PDF of exactly 50MB", () => {
    const result = contentSourceSchema.safeParse({
      sourceType: "pdf",
      file: [makePdf({ size: 50 * 1024 * 1024 })],
    })
    expect(result.success).toBe(true)
  })
})
