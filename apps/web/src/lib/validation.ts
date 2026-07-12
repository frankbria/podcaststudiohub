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
