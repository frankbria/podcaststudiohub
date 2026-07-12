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
    sourceType: z.enum(["url", "text", "pdf"], {
      error: () => "Select URL, Text, or PDF",
    }),
    url: z
      .string()
      .optional(),
    content: z
      .string()
      .optional(),
    // FileList from an <input type="file"> (array-like of File)
    file: z.custom<FileList>().optional(),
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
        // Accept http and https article URLs
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
    if (data.sourceType === "pdf") {
      const file = data.file?.[0]
      if (!file) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "PDF file is required",
          path: ["file"],
        })
        return
      }
      // Mirrors the backend validate_pdf_format: .pdf extension required,
      // MIME type lenient (browsers may report empty or octet-stream)
      const validType =
        !file.type ||
        file.type === "application/pdf" ||
        file.type === "application/octet-stream"
      if (!file.name.toLowerCase().endsWith(".pdf") || !validType) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "File must be a PDF",
          path: ["file"],
        })
      }
      // Mirrors the backend MAX_PDF_SIZE_BYTES limit (50MB)
      if (file.size > 50 * 1024 * 1024) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "PDF must be 50MB or less",
          path: ["file"],
        })
      }
    }
  })

export type ContentSourceFormData = z.infer<typeof contentSourceSchema>

// Apple Podcasts distribution target (mirrors AppleDistributionCreate)
export const appleDistributionSchema = z.object({
  showId: z
    .string()
    .min(1, "Show ID is required")
    .max(255, "Show ID must be 255 characters or less")
    .refine((val) => val.trim().length > 0, "Show ID is required"),
  apiKey: z.string().min(1, "API key is required"),
})

export type AppleDistributionFormData = z.infer<typeof appleDistributionSchema>

// Webhook distribution target (mirrors WebhookDistributionCreate: https only, ≤500 chars)
export const webhookDistributionSchema = z.object({
  name: z
    .string()
    .min(1, "Name is required")
    .max(255, "Name must be 255 characters or less")
    .refine((val) => val.trim().length > 0, "Name is required"),
  url: z
    .string()
    .min(1, "URL is required")
    .max(500, "URL must be 500 characters or less")
    .superRefine((val, ctx) => {
      let parsed: URL
      try {
        parsed = new URL(val)
      } catch {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Invalid URL format" })
        return
      }
      if (parsed.protocol !== "https:") {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: "URL must use HTTPS" })
      }
    }),
  method: z.enum(["POST", "GET"]).default("POST"),
})

export type WebhookDistributionFormData = z.infer<typeof webhookDistributionSchema>

// Podcast RSS metadata (mirrors PodcastMetadataUpdate; show_title/author/description
// are required here because feed generation 422s without them)
const optionalUrl = z
  .string()
  .refine((val) => {
    if (val === "") return true
    try {
      const parsed = new URL(val)
      return parsed.protocol === "http:" || parsed.protocol === "https:"
    } catch {
      return false
    }
  }, "Must be a valid URL")
  .optional()

export const podcastMetadataSchema = z.object({
  showTitle: z
    .string()
    .min(1, "Show title is required")
    .refine((val) => val.trim().length > 0, "Show title is required"),
  author: z
    .string()
    .min(1, "Author is required")
    .refine((val) => val.trim().length > 0, "Author is required"),
  description: z
    .string()
    .min(1, "Description is required")
    .refine((val) => val.trim().length > 0, "Description is required"),
  category: z.string().optional(),
  language: z.string().optional(),
  explicit: z.boolean().optional(),
  copyright: z.string().optional(),
  artworkUrl: optionalUrl,
  websiteUrl: optionalUrl,
})

export type PodcastMetadataFormData = z.infer<typeof podcastMetadataSchema>
