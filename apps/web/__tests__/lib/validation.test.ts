import {
	projectSchema,
	episodeSchema,
	contentSourceSchema,
} from "@/lib/validation"

describe("projectSchema", () => {
	it("accepts a valid title", () => {
		const result = projectSchema.safeParse({ title: "My Podcast" })
		expect(result.success).toBe(true)
	})

	it("trims whitespace from title", () => {
		const result = projectSchema.safeParse({ title: "  My Podcast  " })
		expect(result.success).toBe(true)
		if (result.success) {
			expect(result.data.title).toBe("My Podcast")
		}
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
	})

	it("rejects title over 200 characters", () => {
		const result = projectSchema.safeParse({ title: "a".repeat(201) })
		expect(result.success).toBe(false)
		if (!result.success) {
			expect(result.error.issues[0].message).toContain("200")
		}
	})

	it("accepts title of exactly 200 characters", () => {
		const result = projectSchema.safeParse({ title: "a".repeat(200) })
		expect(result.success).toBe(true)
	})

	it("accepts optional description", () => {
		const result = projectSchema.safeParse({
			title: "My Podcast",
			description: "A great podcast",
		})
		expect(result.success).toBe(true)
	})

	it("accepts missing description", () => {
		const result = projectSchema.safeParse({ title: "My Podcast" })
		expect(result.success).toBe(true)
	})

	it("rejects description over 1000 characters", () => {
		const result = projectSchema.safeParse({
			title: "My Podcast",
			description: "a".repeat(1001),
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			expect(result.error.issues[0].message).toContain("1000")
		}
	})

	it("trims whitespace from description", () => {
		const result = projectSchema.safeParse({
			title: "My Podcast",
			description: "  A great podcast  ",
		})
		expect(result.success).toBe(true)
		if (result.success) {
			expect(result.data.description).toBe("A great podcast")
		}
	})
})

describe("episodeSchema", () => {
	it("accepts a valid title", () => {
		const result = episodeSchema.safeParse({ title: "Episode 1" })
		expect(result.success).toBe(true)
	})

	it("trims whitespace from title", () => {
		const result = episodeSchema.safeParse({ title: "  Episode 1  " })
		expect(result.success).toBe(true)
		if (result.success) {
			expect(result.data.title).toBe("Episode 1")
		}
	})

	it("rejects empty title", () => {
		const result = episodeSchema.safeParse({ title: "" })
		expect(result.success).toBe(false)
		if (!result.success) {
			expect(result.error.issues[0].message).toBe("Episode title is required")
		}
	})

	it("rejects whitespace-only title", () => {
		const result = episodeSchema.safeParse({ title: "   " })
		expect(result.success).toBe(false)
	})

	it("rejects title over 200 characters", () => {
		const result = episodeSchema.safeParse({ title: "a".repeat(201) })
		expect(result.success).toBe(false)
		if (!result.success) {
			expect(result.error.issues[0].message).toContain("200")
		}
	})
})

describe("contentSourceSchema — URL type", () => {
	it("accepts a valid http URL", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "http://example.com/article",
		})
		expect(result.success).toBe(true)
	})

	it("accepts a valid https URL", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "https://example.com/article",
		})
		expect(result.success).toBe(true)
	})

	it("accepts a YouTube https URL", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "https://www.youtube.com/watch?v=abc123",
		})
		expect(result.success).toBe(true)
	})

	it("rejects an empty URL when sourceType is url", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "",
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			const urlError = result.error.issues.find((e) => e.path[0] === "url")
			expect(urlError?.message).toContain("required")
		}
	})

	it("rejects a missing URL when sourceType is url", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
		})
		expect(result.success).toBe(false)
	})

	it("rejects an invalid URL format", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "not-a-url",
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			const urlError = result.error.issues.find((e) => e.path[0] === "url")
			expect(urlError?.message).toContain("HTTP or HTTPS")
		}
	})

	it("rejects ftp:// URLs", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "url",
			url: "ftp://weird-protocol.com",
		})
		expect(result.success).toBe(false)
	})
})

describe("contentSourceSchema — text type", () => {
	it("accepts valid text content", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "This is enough content to be valid.",
		})
		expect(result.success).toBe(true)
	})

	it("rejects empty content when sourceType is text", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "",
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			const contentError = result.error.issues.find(
				(e) => e.path[0] === "content"
			)
			expect(contentError?.message).toContain("required")
		}
	})

	it("rejects content shorter than 10 characters", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "short",
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			const contentError = result.error.issues.find(
				(e) => e.path[0] === "content"
			)
			expect(contentError?.message).toContain("10 characters")
		}
	})

	it("rejects content over 50000 characters", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "a".repeat(50001),
		})
		expect(result.success).toBe(false)
		if (!result.success) {
			const contentError = result.error.issues.find(
				(e) => e.path[0] === "content"
			)
			expect(contentError?.message).toContain("50,000")
		}
	})

	it("accepts content of exactly 10 characters", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "1234567890",
		})
		expect(result.success).toBe(true)
	})

	it("accepts content of exactly 50000 characters", () => {
		const result = contentSourceSchema.safeParse({
			sourceType: "text",
			content: "a".repeat(50000),
		})
		expect(result.success).toBe(true)
	})
})
