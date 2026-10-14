"use client"

import type { FieldErrors, UseFormRegister, UseFormReturn } from "react-hook-form"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { ContentSourceFormData } from "@/lib/validation"

type FieldErrorLike = { message?: string } | undefined
type SourceType = ContentSourceFormData["sourceType"]

interface FieldProps {
  register: UseFormRegister<ContentSourceFormData>
  errors: FieldErrors<ContentSourceFormData>
}

function errorAttrs(error: FieldErrorLike, errorId: string) {
  return {
    "aria-invalid": error ? ("true" as const) : ("false" as const),
    "aria-describedby": error ? errorId : undefined,
  }
}

function errorBorder(error: FieldErrorLike): string {
  return error ? "border-destructive" : ""
}

interface FieldErrorTextProps {
  id: string
  error: FieldErrorLike
}

function FieldErrorText({ id, error }: FieldErrorTextProps) {
  if (!error) return null
  return (
    <p id={id} className="text-destructive text-sm mt-1" role="alert">
      {error.message}
    </p>
  )
}

function UrlField({ register, errors }: FieldProps) {
  const error = errors.url
  return (
    <div>
      <Label htmlFor="content-url" className="mb-1">
        URL <span className="text-destructive">*</span>
      </Label>
      <Input
        id="content-url"
        type="url"
        placeholder="https://example.com/article"
        {...errorAttrs(error, "content-url-error")}
        {...register("url")}
        className={errorBorder(error)}
      />
      <FieldErrorText id="content-url-error" error={error} />
      <p className="text-muted-foreground text-xs mt-1">
        Supports public HTTP/HTTPS article URLs
      </p>
    </div>
  )
}

function PdfField({ register, errors }: FieldProps) {
  const error = errors.file as FieldErrorLike
  return (
    <div>
      <Label htmlFor="content-pdf" className="mb-1">
        PDF File <span className="text-destructive">*</span>
      </Label>
      <Input
        id="content-pdf"
        type="file"
        accept=".pdf,application/pdf"
        {...errorAttrs(error, "content-pdf-error")}
        {...register("file")}
        className={errorBorder(error)}
      />
      <FieldErrorText id="content-pdf-error" error={error} />
      <p className="text-muted-foreground text-xs mt-1">
        PDF files up to 50MB
      </p>
    </div>
  )
}

function TextField({ register, errors }: FieldProps) {
  const error = errors.content
  return (
    <div>
      <Label htmlFor="content-text" className="mb-1">
        Text Content <span className="text-destructive">*</span>
      </Label>
      <Textarea
        id="content-text"
        className={`h-32 ${errorBorder(error)}`}
        placeholder="Enter your content here..."
        {...errorAttrs(error, "content-text-error")}
        {...register("content")}
      />
      <FieldErrorText id="content-text-error" error={error} />
      <p className="text-muted-foreground text-xs mt-1">
        10 – 50,000 characters
      </p>
    </div>
  )
}

interface SourceFieldsProps extends FieldProps {
  sourceType: SourceType
}

const FIELD_BY_TYPE = { url: UrlField, pdf: PdfField, text: TextField }

function SourceFields({ sourceType, register, errors }: SourceFieldsProps) {
  const Field = FIELD_BY_TYPE[sourceType]
  return <Field register={register} errors={errors} />
}

interface SourceTypeButtonProps {
  type: SourceType
  label: string
  current: SourceType
  onSelect: (type: SourceType) => void
}

function SourceTypeButton({ type, label, current, onSelect }: SourceTypeButtonProps) {
  const select = () => onSelect(type)
  return (
    <Button
      type="button"
      variant={current === type ? "default" : "outline"}
      aria-pressed={current === type}
      onClick={select}
      className="flex-1"
    >
      {label}
    </Button>
  )
}

interface AddContentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<ContentSourceFormData>
  sourceType: SourceType
  onSubmit: (data: ContentSourceFormData) => Promise<void>
}

export function AddContentDialog(props: AddContentDialogProps) {
  const { open, onOpenChange, form, sourceType, onSubmit } = props
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting, isValid },
  } = form
  const selectType = (type: SourceType) => setValue("sourceType", type, { shouldValidate: true })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Content Source</DialogTitle>
          <DialogDescription>Add content to generate your podcast from</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label className="mb-2">Content Type</Label>
            <div className="flex gap-2" role="group" aria-label="Content source type">
              <SourceTypeButton type="url" label="URL" current={sourceType} onSelect={selectType} />
              <SourceTypeButton type="text" label="Text" current={sourceType} onSelect={selectType} />
              <SourceTypeButton type="pdf" label="PDF" current={sourceType} onSelect={selectType} />
            </div>
          </div>

          <SourceFields sourceType={sourceType} register={register} errors={errors} />

          <Button
            type="submit"
            disabled={isSubmitting || !isValid}
            className="w-full"
          >
            {isSubmitting ? "Adding..." : "Add Content"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
