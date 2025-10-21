/**
 * TypeScript types for API contracts
 *
 * These types will be generated from the OpenAPI specification
 * using openapi-typescript-codegen or similar tool.
 *
 * For now, this file contains manual type definitions.
 */

// User types
export interface User {
  id: string;
  email: string;
  full_name: string | null;
  tenant_id: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login: string | null;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name?: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// Project types
export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  podcast_metadata: PodcastMetadata;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface PodcastMetadata {
  show_title?: string;
  author?: string;
  description?: string;
  category?: string;
  language?: string;
  explicit?: boolean;
  copyright?: string;
  artwork_url?: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  podcast_metadata?: PodcastMetadata;
}

// Episode types
export interface Episode {
  id: string;
  project_id: string;
  episode_number: number | null;
  metadata: EpisodeMetadata;
  file_path: string | null;
  s3_url: string | null;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  generation_status: GenerationStatus;
  generation_progress: GenerationProgress;
  created_at: string;
  updated_at: string;
}

export interface EpisodeMetadata {
  title?: string;
  description?: string;
  pub_date?: string;
  guid?: string;
  explicit?: boolean;
  keywords?: string[];
}

export type GenerationStatus =
  | 'draft'
  | 'queued'
  | 'extracting'
  | 'generating'
  | 'synthesizing'
  | 'complete'
  | 'failed';

export interface GenerationProgress {
  stage?: 'extraction' | 'transcript' | 'audio' | 'complete' | 'failed';
  progress?: number;
  status?: string;
}

export interface EpisodeCreate {
  project_id: string;
  metadata?: EpisodeMetadata;
}

// Content source types
export interface ContentSource {
  id: string;
  episode_id: string;
  source_type: 'url' | 'pdf' | 'youtube' | 'text' | 'image' | 'topic';
  source_data: Record<string, any>;
  extraction_status: 'pending' | 'extracting' | 'complete' | 'failed';
  error_message: string | null;
  created_at: string;
}

export interface ContentSourceCreate {
  episode_id: string;
  source_type: string;
  source_data: Record<string, any>;
}

// Audio snippet types
export interface AudioSnippet {
  id: string;
  user_id: string;
  project_id: string | null;
  name: string;
  snippet_type: 'intro' | 'outro' | 'midroll' | 'ad' | 'music' | 'other';
  description: string | null;
  s3_url: string | null;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  file_format: string | null;
  created_at: string;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Error response
export interface ErrorResponse {
  detail: string;
}

// NextAuth session extension
declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      tenantId: string;
    };
    accessToken: string;
  }

  interface User {
    id: string;
    email: string;
    name: string;
    accessToken: string;
    tenantId: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken: string;
    tenantId: string;
    userId: string;
  }
}
