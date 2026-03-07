import { z } from "zod"

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

export const episodeSchema = z.object({
	title: z
		.string()
		.min(1, "Episode title is required")
		.max(200, "Episode title must be 200 characters or less")
		.transform((val) => val.trim())
		.refine((val) => val.length > 0, "Episode title is required"),
})

export type EpisodeFormData = z.infer<typeof episodeSchema>

export const contentSourceSchema = z
	.object({
		sourceType: z.enum(["url", "text"], {
			errorMap: () => ({ message: "Select URL or Text" }),
		}),
		url: z
			.string()
			.optional()
			.refine(
				(val) => {
					if (!val || val === "") return true
					try {
						const url = new URL(val)
						return url.protocol === "http:" || url.protocol === "https:"
					} catch {
						return false
					}
				},
				{ message: "URL must be HTTP or HTTPS" }
			),
		content: z
			.string()
			.optional()
			.refine(
				(val) => {
					if (val === undefined || val === "") return true
					return val.length >= 10
				},
				{ message: "Content must be at least 10 characters" }
			)
			.refine(
				(val) => {
					if (val === undefined || val === "") return true
					return val.length <= 50000
				},
				{ message: "Content must be under 50,000 characters" }
			),
	})
	.superRefine((data, ctx) => {
		if (data.sourceType === "url") {
			if (!data.url || data.url === "") {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "URL is required",
					path: ["url"],
				})
			}
		}
		if (data.sourceType === "text") {
			if (!data.content || data.content === "") {
				ctx.addIssue({
					code: z.ZodIssueCode.custom,
					message: "Content is required",
					path: ["content"],
				})
			}
		}
	})

export type ContentSourceFormData = z.infer<typeof contentSourceSchema>
