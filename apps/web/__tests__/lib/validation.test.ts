import {
	projectSchema,
	episodeSchema,
	contentSourceSchema,
} from "@/lib/validation"

describe("projectSchema", () => {
	it("accepts a valid title", async () => {
		const result = await projectSchema.parseAsync({ title: "My Podcast" })
		expect(result.title).toBe("My Podcast")
	})

	it("rejects an empty title", async () => {
		await expect(projectSchema.parseAsync({ title: "" })).rejects.toThrow()
	})

	it("rejects a whitespace-only title", async () => {
		await expect(
			projectSchema.parseAsync({ title: "   " })
		).rejects.toThrow()
	})

	it("trims whitespace from title", async () => {
		const result = await projectSchema.parseAsync({ title: "  My Podcast  " })
		expect(result.title).toBe("My Podcast")
	})

	it("rejects title exceeding 200 characters", async () => {
		await expect(
			projectSchema.parseAsync({ title: "a".repeat(201) })
		).rejects.toThrow()
	})

	it("accepts title at exactly 200 characters", async () => {
		const result = await projectSchema.parseAsync({ title: "a".repeat(200) })
		expect(result.title).toHaveLength(200)
	})

	it("accepts optional description", async () => {
		const result = await projectSchema.parseAsync({
			title: "My Podcast",
			description: "A great show",
		})
		expect(result.description).toBe("A great show")
	})

	it("accepts missing description", async () => {
		const result = await projectSchema.parseAsync({ title: "My Podcast" })
		expect(result.description).toBeUndefined()
	})

	it("rejects description exceeding 1000 characters", async () => {
		await expect(
			projectSchema.parseAsync({
				title: "My Podcast",
				description: "a".repeat(1001),
			})
		).rejects.toThrow()
	})

	it("accepts description at exactly 1000 characters", async () => {
		const result = await projectSchema.parseAsync({
			title: "My Podcast",
			description: "a".repeat(1000),
		})
		expect(result.description).toHaveLength(1000)
	})

	it("trims whitespace from description", async () => {
		const result = await projectSchema.parseAsync({
			title: "My Podcast",
			description: "  A great show  ",
		})
		expect(result.description).toBe("A great show")
	})
})

describe("episodeSchema", () => {
	it("accepts a valid episode title", async () => {
		const result = await episodeSchema.parseAsync({ title: "Episode 1" })
		expect(result.title).toBe("Episode 1")
	})

	it("rejects an empty episode title", async () => {
		await expect(episodeSchema.parseAsync({ title: "" })).rejects.toThrow()
	})

	it("rejects a whitespace-only episode title", async () => {
		await expect(
			episodeSchema.parseAsync({ title: "   " })
		).rejects.toThrow()
	})

	it("trims whitespace from episode title", async () => {
		const result = await episodeSchema.parseAsync({ title: "  Episode 1  " })
		expect(result.title).toBe("Episode 1")
	})

	it("rejects episode title exceeding 200 characters", async () => {
		await expect(
			episodeSchema.parseAsync({ title: "a".repeat(201) })
		).rejects.toThrow()
	})

	it("accepts episode title at exactly 200 characters", async () => {
		const result = await episodeSchema.parseAsync({ title: "a".repeat(200) })
		expect(result.title).toHaveLength(200)
	})
})

describe("contentSourceSchema - URL type", () => {
	it("accepts a valid HTTP URL", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "url",
			url: "http://example.com/article",
		})
		expect(result.url).toBe("http://example.com/article")
	})

	it("accepts a valid HTTPS URL", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "url",
			url: "https://example.com/article",
		})
		expect(result.url).toBe("https://example.com/article")
	})

	it("accepts a YouTube HTTPS URL", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "url",
			url: "https://www.youtube.com/watch?v=abc123",
		})
		expect(result.url).toContain("youtube.com")
	})

	it("rejects an empty URL when sourceType is url", async () => {
		await expect(
			contentSourceSchema.parseAsync({ sourceType: "url", url: "" })
		).rejects.toThrow()
	})

	it("rejects missing URL when sourceType is url", async () => {
		await expect(
			contentSourceSchema.parseAsync({ sourceType: "url" })
		).rejects.toThrow()
	})

	it("rejects an invalid URL format", async () => {
		await expect(
			contentSourceSchema.parseAsync({
				sourceType: "url",
				url: "not-a-url",
			})
		).rejects.toThrow()
	})

	it("rejects ftp:// protocol", async () => {
		await expect(
			contentSourceSchema.parseAsync({
				sourceType: "url",
				url: "ftp://example.com/file",
			})
		).rejects.toThrow()
	})
})

describe("contentSourceSchema - Text type", () => {
	it("accepts valid text content", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "text",
			content: "This is some valid text content for the podcast.",
		})
		expect(result.content).toContain("valid text content")
	})

	it("rejects empty text content when sourceType is text", async () => {
		await expect(
			contentSourceSchema.parseAsync({ sourceType: "text", content: "" })
		).rejects.toThrow()
	})

	it("rejects missing content when sourceType is text", async () => {
		await expect(
			contentSourceSchema.parseAsync({ sourceType: "text" })
		).rejects.toThrow()
	})

	it("rejects content shorter than 10 characters", async () => {
		await expect(
			contentSourceSchema.parseAsync({ sourceType: "text", content: "Short" })
		).rejects.toThrow()
	})

	it("rejects content longer than 50000 characters", async () => {
		await expect(
			contentSourceSchema.parseAsync({
				sourceType: "text",
				content: "a".repeat(50001),
			})
		).rejects.toThrow()
	})

	it("accepts content at exactly 10 characters", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "text",
			content: "a".repeat(10),
		})
		expect(result.content).toHaveLength(10)
	})

	it("accepts content at exactly 50000 characters", async () => {
		const result = await contentSourceSchema.parseAsync({
			sourceType: "text",
			content: "a".repeat(50000),
		})
		expect(result.content).toHaveLength(50000)
	})
})

describe("contentSourceSchema - sourceType enum", () => {
	it("rejects invalid sourceType", async () => {
		await expect(
			contentSourceSchema.parseAsync({
				sourceType: "file",
				url: "https://example.com",
			})
		).rejects.toThrow()
	})
})
