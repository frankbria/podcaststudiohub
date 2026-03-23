"""
Comprehensive test suite for Conversation Template CRUD API.

Tests CRUD operations, pagination, validation, default template management,
and authentication for conversation templates.
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CONFIG = {
	"word_count": 300,
	"conversation_style": ["casual", "humorous"],
	"roles_person1": "host",
	"roles_person2": "expert guest",
	"dialogue_structure": ["Introduction", "Main Content", "Conclusion"],
	"podcast_name": "Tech Today",
	"output_language": "en",
	"creativity": 0.7,
}

FORMAL_CONFIG = {
	"word_count": 500,
	"conversation_style": ["formal", "educational"],
	"roles_person1": "analyst",
	"roles_person2": "commentator",
	"dialogue_structure": ["Executive summary", "Key findings", "Implications", "Q&A"],
	"podcast_name": "Business Insights",
	"output_language": "en",
	"creativity": 0.3,
	"podcast_tagline": "Deep business analysis",
	"engagement_techniques": ["statistics", "expert quotes"],
}


@pytest.fixture
async def auth_headers(client):
	"""Create user and return auth headers."""
	response = await client.post("/auth/register", json={
		"email": f"tmpl_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Template User"
	})
	assert response.status_code == 201
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


async def _create_template(client, auth_headers, name="Test Template", config=None, **kwargs):
	"""Helper to create a template via API."""
	payload = {
		"name": name,
		"config": config or VALID_CONFIG,
		**kwargs,
	}
	response = await client.post("/conversation-templates", headers=auth_headers, json=payload)
	return response


# ============================================================================
# CREATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_conversation_template(client, auth_headers):
	"""Test successful template creation."""
	response = await _create_template(client, auth_headers, name="Casual Tech Podcast")
	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "Casual Tech Podcast"
	assert data["config"]["word_count"] == 300
	assert data["config"]["creativity"] == 0.7
	assert not data["is_default"]
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data
	assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_template_with_all_fields(client, auth_headers):
	"""Test template creation with all optional fields."""
	response = await _create_template(
		client, auth_headers,
		name="Full Template",
		config=FORMAL_CONFIG,
		description="A formal business template",
		is_default=True,
	)
	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "Full Template"
	assert data["description"] == "A formal business template"
	assert data["is_default"]
	assert data["config"]["engagement_techniques"] == ["statistics", "expert quotes"]
	assert data["config"]["podcast_tagline"] == "Deep business analysis"


@pytest.mark.asyncio
async def test_create_template_without_description(client, auth_headers):
	"""Test template creation without optional description."""
	response = await _create_template(client, auth_headers)
	assert response.status_code == 201
	assert response.json()["description"] is None


# ============================================================================
# LIST TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_templates_empty(client, auth_headers):
	"""Test listing when no templates exist."""
	response = await client.get("/conversation-templates", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert data["templates"] == []
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_templates(client, auth_headers):
	"""Test listing templates with pagination metadata."""
	for i in range(3):
		await _create_template(client, auth_headers, name=f"Template {i}")

	response = await client.get("/conversation-templates", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 3
	assert len(data["templates"]) == 3
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_templates_pagination(client, auth_headers):
	"""Test pagination with multiple pages."""
	for i in range(25):
		await _create_template(client, auth_headers, name=f"Template {i}")

	page1 = await client.get("/conversation-templates?page=1&page_size=20", headers=auth_headers)
	assert page1.status_code == 200
	d1 = page1.json()
	assert d1["total"] == 25
	assert len(d1["templates"]) == 20
	assert d1["total_pages"] == 2

	page2 = await client.get("/conversation-templates?page=2&page_size=20", headers=auth_headers)
	assert page2.status_code == 200
	d2 = page2.json()
	assert len(d2["templates"]) == 5
	assert d2["page"] == 2


# ============================================================================
# GET BY ID TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_template_by_id(client, auth_headers):
	"""Test retrieving specific template by ID."""
	create_resp = await _create_template(client, auth_headers, name="Specific Template")
	assert create_resp.status_code == 201
	template_id = create_resp.json()["id"]

	response = await client.get(f"/conversation-templates/{template_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "Specific Template"
	assert data["id"] == template_id


@pytest.mark.asyncio
async def test_get_nonexistent_template(client, auth_headers):
	"""Test getting template that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.get(f"/conversation-templates/{fake_id}", headers=auth_headers)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


# ============================================================================
# UPDATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_template_name(client, auth_headers):
	"""Test partial update of template name only."""
	create_resp = await _create_template(client, auth_headers, name="Original Name")
	template_id = create_resp.json()["id"]

	response = await client.put(
		f"/conversation-templates/{template_id}",
		headers=auth_headers,
		json={"name": "Updated Name"}
	)
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "Updated Name"
	assert data["config"]["word_count"] == VALID_CONFIG["word_count"]  # Unchanged


@pytest.mark.asyncio
async def test_update_template_config(client, auth_headers):
	"""Test updating template config."""
	create_resp = await _create_template(client, auth_headers)
	template_id = create_resp.json()["id"]

	updated_config = {**VALID_CONFIG, "word_count": 800, "creativity": 0.9}
	response = await client.put(
		f"/conversation-templates/{template_id}",
		headers=auth_headers,
		json={"config": updated_config}
	)
	assert response.status_code == 200
	data = response.json()
	assert data["config"]["word_count"] == 800
	assert data["config"]["creativity"] == 0.9


@pytest.mark.asyncio
async def test_update_nonexistent_template(client, auth_headers):
	"""Test updating template that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.put(
		f"/conversation-templates/{fake_id}",
		headers=auth_headers,
		json={"name": "New Name"}
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_invalid_config_rejected(client, auth_headers):
	"""Test that invalid config update is rejected."""
	create_resp = await _create_template(client, auth_headers)
	template_id = create_resp.json()["id"]

	bad_config = {**VALID_CONFIG, "word_count": 99999}  # Out of range
	response = await client.put(
		f"/conversation-templates/{template_id}",
		headers=auth_headers,
		json={"config": bad_config}
	)
	assert response.status_code == 422


# ============================================================================
# DELETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_delete_template(client, auth_headers):
	"""Test deleting a template."""
	create_resp = await _create_template(client, auth_headers)
	assert create_resp.status_code == 201
	template_id = create_resp.json()["id"]

	response = await client.delete(f"/conversation-templates/{template_id}", headers=auth_headers)
	assert response.status_code == 204

	# Verify it's gone
	get_resp = await client.get(f"/conversation-templates/{template_id}", headers=auth_headers)
	assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_template(client, auth_headers):
	"""Test deleting template that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.delete(f"/conversation-templates/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_from_list(client, auth_headers):
	"""Test that deleted template no longer appears in list."""
	for i in range(3):
		await _create_template(client, auth_headers, name=f"Template {i}")

	list_resp = await client.get("/conversation-templates", headers=auth_headers)
	assert list_resp.json()["total"] == 3
	template_id = list_resp.json()["templates"][0]["id"]

	await client.delete(f"/conversation-templates/{template_id}", headers=auth_headers)

	list_resp2 = await client.get("/conversation-templates", headers=auth_headers)
	assert list_resp2.json()["total"] == 2


# ============================================================================
# SET DEFAULT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_set_default_template(client, auth_headers):
	"""Test setting a template as default."""
	create_resp = await _create_template(client, auth_headers)
	template_id = create_resp.json()["id"]
	assert not create_resp.json()["is_default"]

	response = await client.post(
		f"/conversation-templates/{template_id}/set-default",
		headers=auth_headers
	)
	assert response.status_code == 200
	assert response.json()["is_default"]


@pytest.mark.asyncio
async def test_set_default_clears_previous_default(client, auth_headers):
	"""Test that setting a new default clears the previous one."""
	r1 = await _create_template(client, auth_headers, name="Template 1")
	r2 = await _create_template(client, auth_headers, name="Template 2")
	t1_id = r1.json()["id"]
	t2_id = r2.json()["id"]

	# Set template 1 as default
	await client.post(f"/conversation-templates/{t1_id}/set-default", headers=auth_headers)

	# Set template 2 as default - should clear template 1
	response = await client.post(f"/conversation-templates/{t2_id}/set-default", headers=auth_headers)
	assert response.status_code == 200
	assert response.json()["is_default"]

	# Template 1 should no longer be default
	t1_resp = await client.get(f"/conversation-templates/{t1_id}", headers=auth_headers)
	assert not t1_resp.json()["is_default"]


@pytest.mark.asyncio
async def test_set_default_nonexistent_template(client, auth_headers):
	"""Test set-default for nonexistent template returns 404."""
	fake_id = str(uuid4())
	response = await client.post(
		f"/conversation-templates/{fake_id}/set-default",
		headers=auth_headers
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_with_is_default_true_clears_others(client, auth_headers):
	"""Test that creating with is_default=True clears existing defaults."""
	# Create first template and set as default
	r1 = await _create_template(client, auth_headers, name="Template 1")
	t1_id = r1.json()["id"]
	await client.post(f"/conversation-templates/{t1_id}/set-default", headers=auth_headers)

	# Create second template with is_default=True
	r2 = await _create_template(client, auth_headers, name="Template 2", is_default=True)
	assert r2.status_code == 201
	assert r2.json()["is_default"]

	# Template 1 should no longer be default
	t1_resp = await client.get(f"/conversation-templates/{t1_id}", headers=auth_headers)
	assert not t1_resp.json()["is_default"]


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_template_requires_auth(client):
	"""Test that creating template requires authentication."""
	response = await client.post("/conversation-templates", json={
		"name": "Test",
		"config": VALID_CONFIG,
	})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_templates_requires_auth(client):
	"""Test that listing templates requires authentication."""
	response = await client.get("/conversation-templates")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_template_requires_auth(client):
	"""Test that getting template requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/conversation-templates/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_template_requires_auth(client):
	"""Test that updating template requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/conversation-templates/{fake_id}", json={"name": "New"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_template_requires_auth(client):
	"""Test that deleting template requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/conversation-templates/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_set_default_requires_auth(client):
	"""Test that set-default requires authentication."""
	fake_id = str(uuid4())
	response = await client.post(f"/conversation-templates/{fake_id}/set-default")
	assert response.status_code == 401


# ============================================================================
# VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_validation_missing_name(client, auth_headers):
	"""Test validation when name is missing."""
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"config": VALID_CONFIG,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_empty_name(client, auth_headers):
	"""Test validation for empty name."""
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "",
		"config": VALID_CONFIG,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_name_too_long(client, auth_headers):
	"""Test validation for name exceeding 255 chars."""
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "A" * 300,
		"config": VALID_CONFIG,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_missing_config(client, auth_headers):
	"""Test validation when config is missing."""
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test Template",
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_word_count_too_low(client, auth_headers):
	"""Test validation for word_count below minimum."""
	bad_config = {**VALID_CONFIG, "word_count": 50}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_word_count_too_high(client, auth_headers):
	"""Test validation for word_count above maximum."""
	bad_config = {**VALID_CONFIG, "word_count": 9999}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_creativity_out_of_range(client, auth_headers):
	"""Test validation for creativity value out of [0.0, 1.0] range."""
	bad_config = {**VALID_CONFIG, "creativity": 1.5}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_conversation_style(client, auth_headers):
	"""Test validation for invalid conversation style value."""
	bad_config = {**VALID_CONFIG, "conversation_style": ["sarcastic"]}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422
	assert "sarcastic" in response.text


@pytest.mark.asyncio
async def test_validation_empty_conversation_style(client, auth_headers):
	"""Test validation for empty conversation style list."""
	bad_config = {**VALID_CONFIG, "conversation_style": []}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_too_many_conversation_styles(client, auth_headers):
	"""Test validation for more than 5 conversation styles."""
	bad_config = {**VALID_CONFIG, "conversation_style": [
		"casual", "formal", "humorous", "educational", "technical", "storytelling"
	]}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_dialogue_structure_too_few(client, auth_headers):
	"""Test validation for dialogue structure with less than 2 sections."""
	bad_config = {**VALID_CONFIG, "dialogue_structure": ["Introduction"]}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_dialogue_structure_too_many(client, auth_headers):
	"""Test validation for dialogue structure with more than 10 sections."""
	bad_config = {**VALID_CONFIG, "dialogue_structure": [f"Section {i}" for i in range(11)]}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_engagement_technique(client, auth_headers):
	"""Test validation for invalid engagement technique."""
	bad_config = {**VALID_CONFIG, "engagement_techniques": ["clickbait"]}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": bad_config,
	})
	assert response.status_code == 422
	assert "clickbait" in response.text


@pytest.mark.asyncio
async def test_validation_valid_engagement_techniques(client, auth_headers):
	"""Test that valid engagement techniques are accepted."""
	good_config = {
		**VALID_CONFIG,
		"engagement_techniques": ["rhetorical questions", "anecdotes", "humor"]
	}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": good_config,
	})
	assert response.status_code == 201
	data = response.json()
	assert data["config"]["engagement_techniques"] == ["rhetorical questions", "anecdotes", "humor"]


@pytest.mark.asyncio
async def test_validation_all_valid_conversation_styles(client, auth_headers):
	"""Test that all valid conversation style values are accepted (up to 5)."""
	good_config = {
		**VALID_CONFIG,
		"conversation_style": ["casual", "formal", "humorous", "educational", "technical"]
	}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": good_config,
	})
	assert response.status_code == 201


@pytest.mark.asyncio
async def test_validation_missing_required_config_fields(client, auth_headers):
	"""Test that missing required config fields are rejected."""
	incomplete_config = {
		"word_count": 300,
		"conversation_style": ["casual"],
		# missing roles_person1, roles_person2, dialogue_structure, podcast_name, output_language, creativity
	}
	response = await client.post("/conversation-templates", headers=auth_headers, json={
		"name": "Test",
		"config": incomplete_config,
	})
	assert response.status_code == 422
