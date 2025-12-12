---
task_id: "Task_2_7"
task_name: "Content Source Management API"
assigned_agent: "Agent_Backend_Core"
phase: "Phase 02 - Core Backend Infrastructure"
priority: "high"
status: "assigned"
created_date: "2025-11-11"
dependencies:
  - "Task_2_6"  # Episode Management API
estimated_effort: "4 hours"
---

# Task 2.7 Assignment - Content Source Management API

## Agent Assignment
**Agent:** Agent_Backend_Core
**Phase:** Phase 02 - Core Backend Infrastructure
**Dependencies:** Task 2.6 (Episode Management API)

## Task Objective
Implement complete RESTful API for content source management with CRUD operations, episode relationship validation, source type validation, extraction status tracking, and tenant isolation.

## Task Specifications

### 1. Content Source Schemas
**File:** `apps/api/src/schemas/content.py`

Create comprehensive Pydantic schemas:

**ContentSourceCreate Schema:**
- Fields: `episode_id` (UUID, required), `source_type` (enum: "url", "pdf", "text", required), `source_data` (dict, required)
- Custom validator for `source_data` structure based on `source_type`:
  - URL type: Must contain `{"url": str, "title": str}`
  - PDF type: Must contain `{"filename": str, "s3_key": str}`
  - Text type: Must contain `{"content": str}`
- Validate types and non-empty strings for required fields

**ContentSourceUpdate Schema:**
- Optional fields: `source_data`, `extraction_status` (enum: "pending", "processing", "completed", "failed")
- Same validation as ContentSourceCreate when fields are provided

**ContentSourceResponse Schema:**
- All ContentSource model fields: `id`, `episode_id`, `source_type`, `source_data`, `extraction_status`, `extracted_content`, `tenant_id`, `user_id`, `created_at`, `updated_at`
- Use `from_attributes = True` for ORM conversion

**ContentSourceListResponse Schema:**
- Pagination response with `content_sources` (list), `total` (int), `page` (int), `page_size` (int), `total_pages` (int)

### 2. Content Service
**File:** `apps/api/src/services/content_service.py`

Implement business logic layer with CRUD operations:

**add_content_source():**
- Validates episode exists (404 if not)
- RLS automatically ensures episode belongs to correct tenant
- Validates source_data structure matches source_type
- Initializes extraction_status as "pending"
- Auto-assigns user_id and tenant_id from authenticated user

**get_content_sources():**
- Paginated retrieval scoped to episode_id
- Optional skip/limit parameters
- Returns tuple: (content_sources list, total count)
- Ordered by created_at ascending

**get_content_source_by_id():**
- Retrieves single content source by UUID
- Returns None if not found or different tenant (RLS filtering)

**update_content_source():**
- Partial updates using `model_dump(exclude_unset=True)`
- Only updates provided fields
- Validates source_data structure if provided

**delete_content_source():**
- Hard delete (not soft delete)
- Returns True if deleted, False if not found

### 3. Content Router
**File:** `apps/api/src/routers/content.py`

Implement RESTful endpoints nested under episodes:

**POST /episodes/{episode_id}/content** (201 Created):
- Creates new content source for episode
- Requires authentication (`get_current_user` dependency)
- Validates episode exists and belongs to user's tenant
- Auto-assigns user's tenant_id and user_id

**GET /episodes/{episode_id}/content** (200 OK):
- Lists content sources for episode with pagination
- Query params: `page` (default 1), `page_size` (default 20, max 100)
- Returns ContentSourceListResponse with pagination metadata
- Validates episode ownership

**GET /content/{id}** (200 OK / 404 Not Found):
- Retrieves specific content source by UUID
- 404 if not found or different tenant

**PUT /content/{id}** (200 OK / 404 Not Found):
- Updates content source with partial data
- Supports updating source_data, extraction_status

**DELETE /content/{id}** (204 No Content / 404 Not Found):
- Hard deletes content source
- No soft delete needed for content sources

All endpoints require authentication and respect RLS tenant isolation.

### 4. Router Registration
**File:** `apps/api/src/main.py`

Register content router in main application if not already registered.

### 5. Test Suite
**File:** `apps/api/tests/test_content.py`

Comprehensive test suite with target >80% coverage:

**CRUD Tests:**
- Create content source with URL type
- Create content source with PDF type
- Create content source with text type
- List content sources for episode (empty and populated)
- Get content source by ID
- Update content source (extraction_status, source_data)
- Delete content source
- Handle non-existent content sources (404)

**Episode Relationship Tests:**
- Verify content source requires valid episode_id
- Verify 404 when episode doesn't exist
- Verify content sources filtered by episode_id
- Verify cascade deletion when episode deleted

**Source Type Validation Tests:**
- URL type: missing url field, missing title field, invalid URL format
- PDF type: missing filename field, missing s3_key field
- Text type: missing content field, empty content
- Invalid source_type value
- Mismatched source_data structure for type

**Extraction Status Tests:**
- Verify initialization as "pending"
- Update extraction_status to "processing", "completed", "failed"
- Invalid extraction_status values rejected

**Pagination Tests:**
- Basic pagination with multiple content sources
- Custom page size
- Last page handling
- Beyond last page (empty results)

**Authentication Tests:**
- All endpoints require authentication
- Return 403 Forbidden when no valid token provided

**Tenant Isolation Tests (optional - can skip with justification):**
- Similar to Tasks 2.5 and 2.6, tenant isolation tests may be skipped due to test fixture transaction handling
- Document skip reason: "Test fixture transaction handling interferes with RLS. Manual/integration tests verify RLS works."

## Key Integration Points

### Episode Model
- Uses corrected Episode model from Task 2.1
- Foreign key relationship: `content_sources.episode_id` → `episodes.id`
- Cascade deletion configured in migration

### Authentication
- Uses `get_current_user` from `src/middleware/auth.py` (Task 2.3)
- All endpoints require valid JWT token
- Extracts user_id and tenant_id from token

### Tenant Isolation
- RLS policies from Task 2.4 automatically filter by tenant
- No explicit `WHERE tenant_id=?` clauses needed in queries
- TenantContextMiddleware sets `request.state.tenant_id`
- Database dependency calls `set_tenant_context()` to set PostgreSQL session variable

## Architecture Patterns to Follow

Apply the same patterns established in Tasks 2.5 and 2.6:

1. **Service Layer Pattern**: Business logic separated from HTTP handling
2. **Dependency Injection**: FastAPI dependencies for database and authentication
3. **Pydantic Validation**: Schema validation with custom validators
4. **Hard Delete**: Remove records permanently (no is_archived flag)
5. **Pagination**: Cursor-based pagination with page/page_size
6. **Partial Updates**: Using `model_dump(exclude_unset=True)`
7. **Nested Routes**: Content sources nested under episodes endpoint

## Testing Approach

1. **Focus on Functional Coverage**: Test all CRUD operations and validation rules
2. **Skip RLS Unit Tests**: Document justification matching Tasks 2.5 and 2.6
3. **Source Type Validation**: Thoroughly test all three source types (URL, PDF, text)
4. **Episode Relationships**: Verify FK validation and cascade behavior
5. **Extraction Status**: Test status initialization and transitions
6. **Pagination**: Verify page calculations and edge cases
7. **Coverage Target**: Achieve >80% coverage on schemas, close coverage on service/routers

## Success Criteria

- [ ] All 5 CRUD endpoints functional
- [ ] Pagination working with page/page_size
- [ ] Source type validation enforced for all three types
- [ ] Episode FK validation working (404 for invalid episode)
- [ ] Extraction status initialized as "pending"
- [ ] Tenant isolation implemented (RLS in production)
- [ ] Hard delete for content sources
- [ ] Comprehensive test suite with >80% schema coverage
- [ ] All functional tests passing
- [ ] No explicit WHERE tenant_id clauses (RLS handles it)
- [ ] Router registered in main app

## Output File Locations

### Files to Create:
1. **Schemas:** `apps/api/src/schemas/content.py`
2. **Service:** `apps/api/src/services/content_service.py`
3. **Router:** `apps/api/src/routers/content.py`
4. **Tests:** `apps/api/tests/test_content.py`

### Files to Modify:
1. **Schema Init:** `apps/api/src/schemas/__init__.py` (update imports)
2. **Main App:** `apps/api/src/main.py` (register router if needed)

## Memory Log Requirements

Upon completion, create a comprehensive memory log at:
`.apm/Memory/Phase_02_Core_Backend_Infrastructure/Task_2_7_Content_Source_Management_API.md`

Include:
- Implementation summary for each component (schemas, service, router, tests)
- Test results with coverage percentages
- Key features implemented
- Known limitations or skipped tests with justifications
- Integration points with other tasks
- Next steps for Task 3.1

## Reference Materials

**Previous Task Patterns:**
- Task 2.5 memory log: `.apm/Memory/Phase_02_Core_Backend_Infrastructure/Task_2_5_Project_Management_API.md`
- Task 2.6 memory log: `.apm/Memory/Phase_02_Core_Backend_Infrastructure/Task_2_6_Episode_Management_API.md`

**Database Model:**
- `apps/api/src/models/content_source.py` (created in Task 2.1)

**Testing Examples:**
- `apps/api/tests/test_projects.py` (Task 2.5)
- `apps/api/tests/test_episodes.py` (Task 2.6)

## Notes

- This is the **final task in Phase 2**
- Upon completion, Phase 2 will be fully finished
- Next phase (Phase 3) will begin AI Script Generation work with Agent_AI_ScriptGen
- Content sources created in this task will be consumed by content extraction service in Task 3.1

## Begin Implementation

Please proceed with implementing Task 2.7 following the specifications above. Apply the established patterns from Tasks 2.5 and 2.6, and maintain consistency with the existing codebase architecture.

Good luck, Agent_Backend_Core!
