/**
 * Sanitizes a string for use as a filesystem filename.
 * Removes characters invalid on Windows/Mac/Linux and limits length.
 */
export function sanitizeFilename(title: string): string {
  return (
    title
      .replace(/[<>:"/\\|?*]/g, "_") // Replace invalid chars
      .replace(/\s+/g, "_") // Replace whitespace with underscores
      .replace(/_+/g, "_") // Collapse multiple underscores
      .replace(/^_|_$/g, "") // Trim leading/trailing underscores
      .toLowerCase()
      .substring(0, 251) // Leave room for ".mp3"
      + ".mp3"
  )
}

/**
 * Downloads a file from the given URL by fetching it as a blob and
 * triggering a browser download with the provided filename.
 */
export async function downloadAudioFile(
  audioUrl: string,
  filename: string
): Promise<void> {
  const response = await fetch(audioUrl)
  if (!response.ok) {
    throw new Error(`Failed to fetch audio: ${response.status} ${response.statusText}`)
  }
  const blob = await response.blob()
  const objectUrl = window.URL.createObjectURL(blob)

  const link = document.createElement("a")
  link.href = objectUrl
  link.download = filename
  let appended = false
  try {
    document.body.appendChild(link)
    appended = true
    link.click()
  } finally {
    window.URL.revokeObjectURL(objectUrl)
    if (appended) document.body.removeChild(link)
  }
}
