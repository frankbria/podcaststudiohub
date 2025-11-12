---
agent: Agent_AI_ScriptGen
task_ref: Task 3.2 - Script Generation Service with Gemini
status: Completed
ad_hoc_delegation: false
compatibility_issues: false
important_findings: true
---

# Task Log: Task 3.2 - Script Generation Service with Gemini

## Summary
Successfully implemented script generation service wrapping Podcastfy content_generator to generate podcast transcripts using Gemini, with comprehensive status management, transcript file storage, and multi-source content aggregation. All tests passing with 95.05% coverage.

## Details

### Steps 1-4: Service Implementation (Single Comprehensive File)
Created `apps/api/src/services/script_generation_service.py` (370 lines) with all features integrated:

**GenerationResult Data Structure:**
- Fields: success (bool), transcript (Optional[str]), transcript_path (Optional[str]), error_message (Optional[str]), word_count (int)
- Used as return type for generate_script() method

**ScriptGenerationService Class:**
- Main method: `generate_script(db, episode_id, template_config, longform)`
- Integrates with Episode model via episode_service functions
- Integrates with ContentSource model via content_service functions
- Uses Podcastfy ContentGenerator with async wrappers

**Gemini API Integration (Step 2):**
- Wrapped Podcastfy ContentGenerator.generate_qa_content() with asyncio.to_thread()
- Model: gemini-1.5-pro-latest (configurable via GEMINI_MODEL_NAME env var)
- Parameters configured via Podcastfy (temperature=0.7, frequency_penalty=0.75, presence_penalty=0.75)
- API key: GEMINI_API_KEY environment variable
- Output format: XML with <Person1>/<Person2> tags

**Generation Logic (Step 3):**
- Retrieve episode using get_episode_by_id()
- Validate episode status (draft or queued only)
- Retrieve content sources with get_content_sources()
- Filter sources by extraction_status='complete'
- Validate at least one completed source with non-empty content
- Concatenate extracted_content from all sources with metadata headers
- Generate transcript via _call_gemini_api() (async wrapper)
- Validate transcript format (_validate_transcript checks for Person1/Person2 tags)
- Save transcript to file and update episode

**Multi-Source Content Handling:**
- `_concatenate_content()` method aggregates all completed sources
- Adds source metadata headers (URL title/URL, PDF filename, Text content marker)
- Separators between sources for clarity
- Example format:
  ```
  === Source: Test Article (https://example.com) ===
  [extracted content]

  === Source: PDF - document.pdf ===
  [extracted content]
  ```

**Status Management (Step 4):**
- Status flow implemented: draft ’ queued ’ generating ’ complete/failed
- Status transitions:
  * draft ’ queued (when generation starts, if currently draft)
  * queued ’ generating (before Gemini API call)
  * generating ’ complete (on successful generation)
  * generating ’ failed (on API failure, validation error, empty content)
- `_update_status()` helper wraps update_generation_status()

**Transcript Storage Strategy:**
- File-based storage: `data/transcripts/{episode_id}.xml`
- Directory auto-creation with Path.mkdir(parents=True, exist_ok=True)
- Async file I/O with asyncio.to_thread()
- transcript_path column updated in Episode model
- Format: XML with UTF-8 encoding

**generation_progress JSONB Structure:**
- Queued: `{"stage": "queued", "progress": 0, "started_at": ISO timestamp}`
- Generating: `{"stage": "generating", "progress": 50}`
- Complete: `{"stage": "complete", "progress": 100, "completed_at": ISO timestamp}`
- Failed: `{"stage": "generating", "progress": 0, "error_message": "..."}`

**Error Handling:**
- Episode not found: ValueError raised
- Invalid episode status: ValueError raised (must be draft or queued)
- No completed content sources: Failed status with error message
- Empty content: Failed status with "Combined content is empty" error
- Invalid transcript format: Failed status with "missing Person1/Person2 tags" error
- Gemini API failures: Exception caught, failed status with "Gemini API error: ..." message

**Helper Methods:**
- `_update_status()`: Update episode generation status and progress
- `_concatenate_content()`: Aggregate multi-source content with metadata
- `_call_gemini_api()`: Async wrapper for Podcastfy ContentGenerator
- `_validate_transcript()`: Check for Person1/Person2 XML tags
- `_save_transcript()`: Write transcript to file and return path

### Step 5: Test Suite
Created `apps/api/tests/test_script_generation.py` with 27 comprehensive tests:

**Generation Success Tests (3):**
- test_generate_script_success
- test_generate_script_with_template_config
- test_generate_script_longform

**Status Transition Tests (3):**
- test_status_transition_draft_to_complete (draft ’ queued ’ generating ’ complete)
- test_status_transition_queued_to_complete (queued ’ generating ’ complete)
- test_status_transition_to_failed_on_api_error (includes failed status)

**Content Validation Tests (3):**
- test_generate_script_no_content_sources
- test_generate_script_empty_content
- test_generate_script_only_pending_sources

**Transcript Validation Tests (2):**
- test_generate_script_invalid_transcript_missing_person1
- test_generate_script_invalid_transcript_missing_person2

**Multiple Content Sources Tests (2):**
- test_generate_script_multiple_sources (3 sources: URL, PDF, text)
- test_concatenate_content_with_separators

**API Failure Tests (2):**
- test_generate_script_gemini_timeout
- test_generate_script_gemini_api_error

**Episode State Validation Tests (2):**
- test_generate_script_episode_not_found
- test_generate_script_invalid_episode_status

**Transcript File Storage Tests (2):**
- test_save_transcript_creates_directory
- test_save_transcript_writes_file

**generation_progress JSONB Tests (2):**
- test_generation_progress_updates (started_at, completed_at)
- test_generation_progress_error_message

**GenerationResult Tests (2):**
- test_generation_result_success
- test_generation_result_failure

**Validate Transcript Method Tests (4):**
- test_validate_transcript_valid
- test_validate_transcript_missing_person1
- test_validate_transcript_missing_person2
- test_validate_transcript_empty

**Mocking Strategy:**
- Podcastfy ContentGenerator mocked to avoid real Gemini API calls
- Episode service functions mocked (get_episode_by_id, update_episode, update_generation_status)
- Content service mocked (get_content_sources)
- File I/O mocked with mock_open()
- No external dependencies in tests

## Output

**Files Created:**
- `apps/api/src/services/script_generation_service.py` (370 lines)
  - ScriptGenerationService class
  - GenerationResult data structure
  - Gemini API integration via Podcastfy
  - Multi-source content aggregation
  - Status management and transcript storage
  - Error handling for all failure cases

- `apps/api/tests/test_script_generation.py` (800+ lines)
  - 27 comprehensive tests covering all scenarios
  - Mocked Gemini API and service dependencies
  - Test coverage for status transitions, content validation, file storage

**Test Results:**
- All 27 tests passing 
- Coverage: **95.05%** on script_generation_service.py (exceeds 80% requirement)
- Total: 101 statements, 5 uncovered lines
- Uncovered lines: 298-312 (internal _call_gemini_api implementation details)

**Integration with Task 3.1:**
- Uses get_content_sources() from Task 2.7 content service
- Filters by extraction_status='complete' from Task 3.1
- Concatenates extracted_content column (Text) from all completed sources
- Multi-source aggregation demonstrated in tests

**Podcastfy Integration:**
- ContentGenerator initialized per-request with custom configs
- Synchronous generate_qa_content() wrapped with asyncio.to_thread()
- Model: gemini-1.5-pro-latest (default, configurable)
- Conversation config passed through template_config parameter
- Longform support via longform=True parameter (chunking strategy)

## Issues
None - All requirements completed successfully.

## Important Findings

**Podcastfy ContentGenerator API:**
- Class initialization: `ContentGenerator(is_local, model_name, api_key_label, conversation_config)`
- Generation method: `generate_qa_content(input_texts, longform=False)`
- Synchronous API - requires asyncio.to_thread() for async compatibility
- Returns XML-formatted transcript with <Person1>/<Person2> tags
- Supports custom conversation_config dict for podcast style/structure
- Longform parameter triggers content chunking (30+ min podcasts)

**Gemini API Configuration:**
- Configured via Podcastfy LLMBackend class (not direct control)
- Parameters: temperature (via creativity config), frequency_penalty=0.75, presence_penalty=0.75
- Max output tokens: 8192 (default, configurable via content_generator config)
- API key from environment: GEMINI_API_KEY
- Model name configurable via GEMINI_MODEL_NAME env var (default: gemini-1.5-pro-latest)

**Status Flow Design:**
- 5 states total: draft, queued, generating, complete, failed
- Task 3.2 handles: draft ’ queued ’ generating ’ complete/failed
- Future tasks will add: extracting, synthesizing states
- generation_progress JSONB tracks: stage, progress (0-100), started_at, completed_at, error_message

**Transcript Storage Decision:**
- Implemented file-based storage (Option A from task instructions)
- Path pattern: data/transcripts/{episode_id}.xml
- Aligns with existing audio_file_path pattern
- Enables future S3 upload workflow (similar to audio files)
- transcript_path column stores relative path

**Template Configuration:**
- Optional template_config parameter passed to ContentGenerator
- Structure: conversation_config dict with podcast_name, roles, style, etc.
- Future integration: ConversationTemplate model (Task 3.6) will provide configs
- Current implementation: accepts any dict, passed directly to Podcastfy

**Multi-Source Content Handling:**
- Concatenation includes source metadata for context
- URL sources: Include title and URL
- PDF sources: Include filename
- Text sources: Generic "Text Content" marker
- Separators (===) and newlines for readability
- Order preserved from database query (created_at ascending)

**Known Limitations:**
- Token limit: Gemini has max input/output tokens (8192 default)
  - No automatic chunking for very large combined content (>token limit)
  - Longform mode helps but doesn't guarantee success for massive content
  - Future enhancement: Add token counting and content truncation
- Model availability: gemini-1.5-pro-latest may change
  - Fallback model strategy not implemented
  - Error message guides user to check model availability
- Template validation: No schema validation for template_config dict
  - Podcastfy handles invalid configs, but errors may be unclear
- Concurrent generation: No locking mechanism for same episode
  - Multiple workers could attempt generation simultaneously
  - Future enhancement: Add distributed lock (Redis/DB-based)

**Next Phase Context:**
- Task 3.3 (Quality Metrics): Will parse transcript XML to calculate metrics
  - Word count: count words in Person1/Person2 tag content
  - Speaker balance: compare Person1 vs Person2 word counts
  - Engagement: analyze dialogue structure, questions, transitions
- Task 3.4 (Pre-Screening): Will use quality metrics to filter low-quality scripts
- Transcript format (XML with Person1/Person2) enables structured analysis
- generation_progress tracking enables real-time status monitoring

## Next Steps
- Task 3.3: Implement quality metrics calculator that parses transcript XML
- Quality metrics should extract content from <Person1> and <Person2> tags
- Consider adding token limit validation before Gemini API call
- Future: Add retry logic for transient Gemini API failures (rate limits)
- Future: Integrate ConversationTemplate model (Task 3.6) for template_config
