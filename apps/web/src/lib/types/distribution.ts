// Mirrors apps/api/src/schemas/distribution_target.py — shared because the
// /distribution page and the three connect dialogs all consume these shapes.
export type DistributionTargetType = "spotify" | "apple_podcasts" | "webhook"

export interface DistributionTarget {
  id: string
  user_id: string
  tenant_id: string
  project_id: string | null
  target_type: DistributionTargetType
  is_active: boolean
  created_at: string
  updated_at: string
  // Derived safe fields — credentials are never returned by the API.
  show_id?: string | null
  platform_name?: string | null
  // Spotify only
  token_expires_at?: string | null
  token_valid?: boolean | null
}

export interface DistributionTargetListResponse {
  targets: DistributionTarget[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
