import { z } from "zod"

// Project validation
export const projectSchema = z.object({
	title: z
		.string()
		.min(1, "Title is required")
		.max(200, "Title must be 200 characters or less")
		.transform((val) => val.trim())
		.refine((val) => val.length > 0, "Title is required"),
	description: z
		.string()
		.max(1000, "Description must be 1000 characters or less")
		.optional()
		.transform((val) => val?.trim()),
})

export type ProjectFormData = z.infer<typeof projectSchema>

// Episode validation
export const episodeSchema = z.object({
	title: z
		.string()
		.min(1, "Episode title is required")
		.max(200, "Episode title must be 200 characters or less")
		.transform((val) => val.trim())
		.refine((val) => val.length > 0, "Episode title is required"),
})

export type EpisodeFormData = z.infer<typeof episodeSchema>

// URL validation helper
function isValidUrl(val: string): boolean {
	try {
		const url = new URL(val)
		return url.protocol === "http:" || url.protocol === "https:"
	} catch {
		return false
	}
}

// Content source validation
export const contentSourceSchema = z
	.object({
		sourceType: z.enum(["url", "text"]),
		url: z.string().optional(),
		content: z.string().optional(),
	})
	.superRefine((data, ctx) => {
		if (data.sourceType === "url") {
			if (!data.url || data.url.trim() === "") {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "URL is required",
					path: ["url"],
				})
			} else if (!isValidUrl(data.url.trim())) {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "URL must be HTTP or HTTPS",
					path: ["url"],
				})
			}
		}
		if (data.sourceType === "text") {
			if (!data.content || data.content.trim() === "") {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "Content is required",
					path: ["content"],
				})
			} else if (data.content.trim().length < 10) {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "Content must be at least 10 characters",
					path: ["content"],
				})
			} else if (data.content.trim().length > 50000) {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "Content must be under 50,000 characters",
					path: ["content"],
				})
			}
		}
	})

export type ContentSourceData = z.infer<typeof contentSourceSchema>
