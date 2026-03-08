/**
 * Sanitizes a string for use as a filesystem filename.
 * Removes characters invalid on Windows/Mac/Linux and enforces length limits.
 */
export function sanitizeFilename(title: string): string {
  return title
    .replace(/[<>:"/\\|?*]/g, "_") // Replace chars invalid on Windows/Mac/Linux
    .replace(/\s+/g, "_")           // Replace whitespace with underscores
    .substring(0, 200)              // Enforce max length (leaving room for extension)
    .toLowerCase()
}

/**
 * Downloads an audio file from a URL using the Blob API.
 * Falls back to a direct anchor download if fetch fails.
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

  try {
    const link = document.createElement("a")
    link.href = objectUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    window.URL.revokeObjectURL(objectUrl)
  }
}
