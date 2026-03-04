"""
Comprehensive test suite for Audio Snippet CRUD API.

Tests file upload, CRUD operations, pagination, filtering, validation,
and authentication requirements for audio snippets.
"""

import io
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# HELPER FIXTURES
# ============================================================================

def make_fake_audio_bytes() -> bytes:
	"""Create minimal valid-looking MP3 bytes (ID3 header)."""
	# Minimal fake MP3: ID3 tag + enough bytes to pass size check (>100KB)
	header = b"ID3\x03\x00\x00\x00\x00\x00\x00"
	padding = b"\x00" * (110 * 1024)  # 110 KB of padding
	return header + padding


def make_audio_file(filename: str = "test.mp3", size_bytes: int = 150 * 1024) -> bytes:
	"""Create fake audio file bytes of given size."""
	return b"ID3" + b"\x00" * (size_bytes - 3)


@pytest.fixture
async def auth_headers(client):
	"""Register a user and return auth headers."""
	reg_response = await client.post("/auth/register", json={
		"email": f"test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Test User"
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def project_and_auth(client, auth_headers):
	"""Create a project and return (project_id, auth_headers)."""
	proj_response = await client.post("/projects", headers=auth_headers, json={
		"name": "Test Project",
		"podcast_metadata": {
			"show_title": "Test Show",
			"author": "Test Author",
			"description": "Test Description"
		}
	})
	assert proj_response.status_code == 201
	project_id = proj_response.json()["id"]
	return project_id, auth_headers


# ============================================================================
# UNIT TESTS - AUDIO UTILITIES
# ============================================================================

class TestAudioUtils:
	"""Unit tests for audio utility functions."""

	def test_validate_audio_format_mp3(self):
		"""Test MP3 format validation."""
		from src.utils.audio_utils import validate_audio_format
		ext = validate_audio_format("intro.mp3")
		assert ext == "mp3"

	def test_validate_audio_format_wav(self):
		"""Test WAV format validation."""
		from src.utils.audio_utils import validate_audio_format
		ext = validate_audio_format("outro.wav")
		assert ext == "wav"

	def test_validate_audio_format_aac(self):
		"""Test AAC format validation."""
		from src.utils.audio_utils import validate_audio_format
		ext = validate_audio_format("music.aac")
		assert ext == "aac"

	def test_validate_audio_format_ogg(self):
		"""Test OGG format validation."""
		from src.utils.audio_utils import validate_audio_format
		ext = validate_audio_format("sound.ogg")
		assert ext == "ogg"

	def test_validate_audio_format_uppercase(self):
		"""Test format validation is case insensitive."""
		from src.utils.audio_utils import validate_audio_format
		ext = validate_audio_format("INTRO.MP3")
		assert ext == "mp3"

	def test_validate_audio_format_invalid(self):
		"""Test rejection of invalid format."""
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError, match="Unsupported file format"):
			validate_audio_format("video.mp4")

	def test_validate_audio_format_txt_rejected(self):
		"""Test rejection of non-audio format."""
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError):
			validate_audio_format("document.txt")

	def test_validate_file_size_valid(self):
		"""Test file size validation with valid size."""
		from src.utils.audio_utils import validate_file_size
		# 1 MB - should not raise
		validate_file_size(1 * 1024 * 1024)

	def test_validate_file_size_too_large(self):
		"""Test file size validation rejects oversized files."""
		from src.utils.audio_utils import validate_file_size
		with pytest.raises(ValueError, match="too large"):
			validate_file_size(51 * 1024 * 1024)  # 51 MB

	def test_validate_file_size_too_small(self):
		"""Test file size validation rejects undersized files."""
		from src.utils.audio_utils import validate_file_size
		with pytest.raises(ValueError, match="too small"):
			validate_file_size(50 * 1024)  # 50 KB

	def test_generate_s3_key_format(self):
		"""Test S3 key generation follows expected format."""
		from src.utils.audio_utils import generate_s3_key
		user_id = str(uuid4())
		snippet_id = str(uuid4())
		key = generate_s3_key(user_id, snippet_id, "mp3")
		assert key.startswith("audio-snippets/")
		assert user_id in key
		assert snippet_id in key
		assert key.endswith(".mp3")

	def test_get_content_type_mp3(self):
		"""Test content type for MP3."""
		from src.utils.audio_utils import get_content_type
		assert get_content_type("mp3") == "audio/mpeg"

	def test_get_content_type_wav(self):
		"""Test content type for WAV."""
		from src.utils.audio_utils import get_content_type
		assert get_content_type("wav") == "audio/wav"

	def test_get_content_type_unknown(self):
		"""Test content type fallback for unknown format."""
		from src.utils.audio_utils import get_content_type
		assert get_content_type("xyz") == "application/octet-stream"


# ============================================================================
# UNIT TESTS - SCHEMAS
# ============================================================================

class TestAudioSnippetSchemas:
	"""Unit tests for Pydantic schemas."""

	def test_snippet_type_enum_valid(self):
		"""Test SnippetType enum with all valid values."""
		from src.schemas.audio_snippet import SnippetType
		assert SnippetType.intro == "intro"
		assert SnippetType.outro == "outro"
		assert SnippetType.midroll == "midroll"
		assert SnippetType.ad == "ad"
		assert SnippetType.music == "music"
		assert SnippetType.other == "other"

	def test_audio_snippet_update_partial(self):
		"""Test partial update with only name."""
		from src.schemas.audio_snippet import AudioSnippetUpdate
		update = AudioSnippetUpdate(name="New Name")
		data = update.model_dump(exclude_unset=True)
		assert data == {"name": "New Name"}

	def test_audio_snippet_update_empty_name_rejected(self):
		"""Test that empty name is rejected."""
		from src.schemas.audio_snippet import AudioSnippetUpdate
		with pytest.raises(ValueError):
			AudioSnippetUpdate(name="   ")

	def test_audio_snippet_update_all_optional(self):
		"""Test that all update fields are optional."""
		from src.schemas.audio_snippet import AudioSnippetUpdate
		update = AudioSnippetUpdate()
		data = update.model_dump(exclude_unset=True)
		assert data == {}

	def test_audio_snippet_response_from_attributes(self):
		"""Test AudioSnippetResponse accepts ORM model attributes."""
		from src.schemas.audio_snippet import AudioSnippetResponse
		assert AudioSnippetResponse.model_config.get("from_attributes") is True


# ============================================================================
# INTEGRATION TESTS - UPLOAD
# ============================================================================

@pytest.mark.asyncio
async def test_upload_requires_auth(client):
	"""Test that upload endpoint requires authentication."""
	audio_bytes = make_audio_file()
	response = await client.post(
		"/audio-snippets/upload",
		files={"file": ("test.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
		data={"name": "Test Intro", "snippet_type": "intro"},
	)
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_mp3_snippet(client, auth_headers):
	"""Test successful MP3 snippet upload."""
	audio_bytes = make_audio_file("intro.mp3")

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = "https://bucket.s3.amazonaws.com/audio-snippets/test.mp3"
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=15.5):
			response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Tech Unpacked Intro", "snippet_type": "intro"},
			)

	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "Tech Unpacked Intro"
	assert data["snippet_type"] == "intro"
	assert data["file_format"] == "mp3"
	assert data["file_size_bytes"] == len(audio_bytes)
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_upload_wav_snippet(client, auth_headers):
	"""Test WAV format upload."""
	audio_bytes = make_audio_file("outro.wav", 200 * 1024)

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=8.2):
			response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("outro.wav", io.BytesIO(audio_bytes), "audio/wav")},
				data={
					"name": "Thanks for listening",
					"snippet_type": "outro",
					"description": "Outro with music fade",
				},
			)

	assert response.status_code == 201
	data = response.json()
	assert data["file_format"] == "wav"
	assert data["snippet_type"] == "outro"
	assert data["description"] == "Outro with music fade"


@pytest.mark.asyncio
async def test_upload_with_project_id(client, project_and_auth):
	"""Test upload with optional project_id."""
	project_id, auth_headers = project_and_auth
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("music.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={
					"name": "Background Music",
					"snippet_type": "music",
					"project_id": project_id,
				},
			)

	assert response.status_code == 201
	data = response.json()
	assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_upload_with_invalid_project_id(client, auth_headers):
	"""Test upload with non-existent project_id returns 404."""
	audio_bytes = make_audio_file()
	fake_project_id = str(uuid4())

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock):
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=5.0):
			response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("music.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={
					"name": "Background Music",
					"snippet_type": "music",
					"project_id": fake_project_id,
				},
			)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_rejects_invalid_format(client, auth_headers):
	"""Test that non-audio formats are rejected with 422."""
	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("video.mp4", io.BytesIO(b"fake video content" * 1000 * 6), "video/mp4")},
		data={"name": "Video File", "snippet_type": "other"},
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, auth_headers):
	"""Test that files over 50MB are rejected with 413."""
	# 51 MB of bytes
	oversized = b"x" * (51 * 1024 * 1024)

	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("big.mp3", io.BytesIO(oversized), "audio/mpeg")},
		data={"name": "Too Big", "snippet_type": "music"},
	)
	assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_undersized_file(client, auth_headers):
	"""Test that files under 100KB are rejected with 422."""
	tiny = b"ID3" + b"\x00" * 50  # Only 53 bytes

	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("tiny.mp3", io.BytesIO(tiny), "audio/mpeg")},
		data={"name": "Tiny File", "snippet_type": "intro"},
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_missing_name(client, auth_headers):
	"""Test that missing name returns 422."""
	audio_bytes = make_audio_file()

	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
		data={"snippet_type": "intro"},  # Missing name
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_missing_snippet_type(client, auth_headers):
	"""Test that missing snippet_type returns 422."""
	audio_bytes = make_audio_file()

	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
		data={"name": "Test"},  # Missing snippet_type
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_invalid_snippet_type(client, auth_headers):
	"""Test that invalid snippet_type returns 422."""
	audio_bytes = make_audio_file()

	response = await client.post(
		"/audio-snippets/upload",
		headers=auth_headers,
		files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
		data={"name": "Test", "snippet_type": "invalid_type"},
	)
	assert response.status_code == 422


# ============================================================================
# INTEGRATION TESTS - LIST
# ============================================================================

@pytest.mark.asyncio
async def test_list_requires_auth(client):
	"""Test that list endpoint requires authentication."""
	response = await client.get("/audio-snippets")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_empty(client, auth_headers):
	"""Test listing when no snippets exist."""
	response = await client.get("/audio-snippets", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert data["snippets"] == []


@pytest.mark.asyncio
async def test_list_with_pagination(client, auth_headers):
	"""Test paginated listing of snippets."""
	audio_bytes = make_audio_file()

	# Create 3 snippets
	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			for i in range(3):
				await client.post(
					"/audio-snippets/upload",
					headers=auth_headers,
					files={"file": (f"snippet{i}.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
					data={"name": f"Snippet {i}", "snippet_type": "intro"},
				)

	response = await client.get("/audio-snippets", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] >= 3
	assert len(data["snippets"]) >= 3
	assert "page" in data
	assert "page_size" in data
	assert "total_pages" in data


@pytest.mark.asyncio
async def test_list_filter_by_type(client, auth_headers):
	"""Test filtering snippets by type."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			# Create intro snippet
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "My Intro", "snippet_type": "intro"},
			)
			# Create outro snippet
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("outro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "My Outro", "snippet_type": "outro"},
			)

	# Filter by intro
	response = await client.get("/audio-snippets?type=intro", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] >= 1
	for snippet in data["snippets"]:
		assert snippet["snippet_type"] == "intro"


@pytest.mark.asyncio
async def test_list_filter_by_project(client, project_and_auth):
	"""Test filtering snippets by project_id."""
	project_id, auth_headers = project_and_auth
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			# Create snippet scoped to project
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("music.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Project Music", "snippet_type": "music", "project_id": project_id},
			)
			# Create tenant-wide snippet (no project)
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("global.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Global Snippet", "snippet_type": "other"},
			)

	# Filter by project
	response = await client.get(f"/audio-snippets?project_id={project_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["snippets"][0]["project_id"] == project_id


@pytest.mark.asyncio
async def test_list_search_by_name(client, auth_headers):
	"""Test searching snippets by name."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("special.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Special Intro Theme", "snippet_type": "intro"},
			)
			await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("other.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Regular Background Music", "snippet_type": "music"},
			)

	# Search for "Special"
	response = await client.get("/audio-snippets?search=Special", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] >= 1
	names = [s["name"] for s in data["snippets"]]
	assert any("Special" in n for n in names)


@pytest.mark.asyncio
async def test_list_pagination_page_size(client, auth_headers):
	"""Test pagination with custom page size."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=5.0):
			for i in range(5):
				await client.post(
					"/audio-snippets/upload",
					headers=auth_headers,
					files={"file": (f"s{i}.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
					data={"name": f"Snippet {i}", "snippet_type": "other"},
				)

	# Request page with size 2
	response = await client.get("/audio-snippets?page=1&page_size=2", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert len(data["snippets"]) <= 2
	assert data["page"] == 1
	assert data["page_size"] == 2


# ============================================================================
# INTEGRATION TESTS - GET BY ID
# ============================================================================

@pytest.mark.asyncio
async def test_get_by_id_requires_auth(client):
	"""Test that get by ID requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/audio-snippets/{fake_id}")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_audio_snippet_by_id(client, auth_headers):
	"""Test retrieving a specific snippet by ID."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = "https://bucket.s3.amazonaws.com/test.mp3"
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=15.5):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Specific Snippet", "snippet_type": "intro"},
			)

	assert create_response.status_code == 201
	snippet_id = create_response.json()["id"]

	# Get by ID
	response = await client.get(f"/audio-snippets/{snippet_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["id"] == snippet_id
	assert data["name"] == "Specific Snippet"


@pytest.mark.asyncio
async def test_get_nonexistent_snippet(client, auth_headers):
	"""Test getting snippet that doesn't exist returns 404."""
	fake_id = str(uuid4())
	response = await client.get(f"/audio-snippets/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


# ============================================================================
# INTEGRATION TESTS - UPDATE
# ============================================================================

@pytest.mark.asyncio
async def test_update_requires_auth(client):
	"""Test that update requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/audio-snippets/{fake_id}", json={"name": "New Name"})
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_snippet_name(client, auth_headers):
	"""Test updating snippet name."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("intro.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Original Name", "snippet_type": "intro"},
			)

	snippet_id = create_response.json()["id"]

	# Update name
	response = await client.put(
		f"/audio-snippets/{snippet_id}",
		headers=auth_headers,
		json={"name": "Updated Name"},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "Updated Name"
	assert data["snippet_type"] == "intro"  # Unchanged


@pytest.mark.asyncio
async def test_update_snippet_type(client, auth_headers):
	"""Test updating snippet type."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("ad.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Ad Snippet", "snippet_type": "ad"},
			)

	snippet_id = create_response.json()["id"]

	# Change type to midroll
	response = await client.put(
		f"/audio-snippets/{snippet_id}",
		headers=auth_headers,
		json={"snippet_type": "midroll"},
	)
	assert response.status_code == 200
	assert response.json()["snippet_type"] == "midroll"


@pytest.mark.asyncio
async def test_update_snippet_description(client, auth_headers):
	"""Test updating snippet description."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=10.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("music.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Background", "snippet_type": "music"},
			)

	snippet_id = create_response.json()["id"]

	response = await client.put(
		f"/audio-snippets/{snippet_id}",
		headers=auth_headers,
		json={"description": "New description added"},
	)
	assert response.status_code == 200
	assert response.json()["description"] == "New description added"


@pytest.mark.asyncio
async def test_update_nonexistent_snippet(client, auth_headers):
	"""Test updating non-existent snippet returns 404."""
	fake_id = str(uuid4())
	response = await client.put(
		f"/audio-snippets/{fake_id}",
		headers=auth_headers,
		json={"name": "New Name"},
	)
	assert response.status_code == 404


# ============================================================================
# INTEGRATION TESTS - DELETE
# ============================================================================

@pytest.mark.asyncio
async def test_delete_requires_auth(client):
	"""Test that delete requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/audio-snippets/{fake_id}")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_snippet(client, auth_headers):
	"""Test successful snippet deletion."""
	audio_bytes = make_audio_file()

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=5.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("todelete.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "To Delete", "snippet_type": "other"},
			)

	snippet_id = create_response.json()["id"]

	# Delete snippet
	delete_response = await client.delete(
		f"/audio-snippets/{snippet_id}",
		headers=auth_headers,
	)
	assert delete_response.status_code == 204

	# Verify deleted
	get_response = await client.get(f"/audio-snippets/{snippet_id}", headers=auth_headers)
	assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_snippet(client, auth_headers):
	"""Test deleting non-existent snippet returns 404."""
	fake_id = str(uuid4())
	response = await client.delete(f"/audio-snippets/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


# ============================================================================
# INTEGRATION TESTS - DOWNLOAD URL
# ============================================================================

@pytest.mark.asyncio
async def test_download_url_requires_auth(client):
	"""Test that download URL endpoint requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/audio-snippets/{fake_id}/download")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_download_url_nonexistent_snippet(client, auth_headers):
	"""Test download URL for non-existent snippet returns 404."""
	fake_id = str(uuid4())
	response = await client.get(f"/audio-snippets/{fake_id}/download", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_url_no_s3_config(client, auth_headers):
	"""Test download URL when S3 not configured returns 503."""
	audio_bytes = make_audio_file()

	# Upload without S3 (s3_key will be set but no bucket configured)
	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = None  # No S3 URL
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=5.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("test.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Test", "snippet_type": "other"},
			)

	snippet_id = create_response.json()["id"]

	# Try to get download URL - s3_key is set but no bucket configured
	with patch("src.services.audio_snippet_service.generate_download_url") as mock_gen:
		from fastapi import HTTPException, status as http_status
		mock_gen.side_effect = HTTPException(
			status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="File storage not configured"
		)
		response = await client.get(
			f"/audio-snippets/{snippet_id}/download",
			headers=auth_headers,
		)

	assert response.status_code == 503


@pytest.mark.asyncio
async def test_download_url_with_s3(client, auth_headers):
	"""Test download URL generation when S3 is configured."""
	audio_bytes = make_audio_file()
	presigned_url = "https://bucket.s3.amazonaws.com/audio-snippets/test.mp3?sig=xyz&expires=1234"

	with patch("src.services.audio_snippet_service._upload_to_s3", new_callable=AsyncMock) as mock_s3:
		mock_s3.return_value = "https://bucket.s3.amazonaws.com/test.mp3"
		with patch("src.services.audio_snippet_service.get_audio_duration", return_value=5.0):
			create_response = await client.post(
				"/audio-snippets/upload",
				headers=auth_headers,
				files={"file": ("test.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
				data={"name": "Test", "snippet_type": "other"},
			)

	snippet_id = create_response.json()["id"]

	with patch("src.services.audio_snippet_service.generate_download_url", new_callable=AsyncMock) as mock_url:
		mock_url.return_value = presigned_url
		response = await client.get(
			f"/audio-snippets/{snippet_id}/download",
			headers=auth_headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert data["snippet_id"] == snippet_id
	assert data["download_url"] == presigned_url
	assert data["expires_in_seconds"] == 3600
