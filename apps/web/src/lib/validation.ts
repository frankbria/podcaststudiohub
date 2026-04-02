import { z } from "zod"

// Project validation
export const projectSchema = z.object({
  title: z
    .string()
    .min(1, "Title is required")
    .max(200, "Title must be 200 characters or less")
    .refine((val) => val.trim().length > 0, "Title cannot be only whitespace"),
  description: z
    .string()
    .max(1000, "Description must be 1000 characters or less")
    .optional(),
})

export type ProjectFormData = z.infer<typeof projectSchema>

// Episode validation
export const episodeSchema = z.object({
  title: z
    .string()
    .min(1, "Episode title is required")
    .max(200, "Episode title must be 200 characters or less")
    .refine((val) => val.trim().length > 0, "Title cannot be only whitespace"),
})

export type EpisodeFormData = z.infer<typeof episodeSchema>

// Content source validation
export const contentSourceSchema = z
  .object({
    sourceType: z.enum(["url", "text"], {
      errorMap: () => ({ message: "Select URL or Text" }),
    }),
    url: z
      .string()
      .optional(),
    content: z
      .string()
      .optional(),
  })
  .superRefine((data, ctx) => {
    if (data.sourceType === "url") {
      if (!data.url || data.url.trim() === "") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "URL is required",
          path: ["url"],
        })
        return
      }
      try {
        const parsed = new URL(data.url)
        // Accept http and https (YouTube and other common hosts use https)
        const isAllowed =
          parsed.protocol === "http:" ||
          parsed.protocol === "https:"
        if (!isAllowed) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "URL must use HTTP or HTTPS protocol",
            path: ["url"],
          })
        }
      } catch {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Invalid URL format",
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
        return
      }
      if (data.content.trim().length < 10) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Content must be at least 10 characters",
          path: ["content"],
        })
      }
      if (data.content.length > 50000) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Content must be under 50,000 characters",
          path: ["content"],
        })
      }
    }
  })

export type ContentSourceFormData = z.infer<typeof contentSourceSchema>
