"""
Unit tests for platform_distribution Celery task.

Tests cover:
- Task signature validation (parameter names)
- Platform routing to correct handler
- Unsupported platform error handling
- Webhook-specific logic (URL validation, HTTP calls, error propagation)
- Return value structure
- Progress state update calls
"""

import inspect
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from src.tasks.platform_distribution import distribute_to_platform_task


# ============================================================================
# SIGNATURE TESTS
# ============================================================================


def test_task_accepts_episode_id_parameter():
	"""Task signature must accept episode_id parameter."""
	sig = inspect.signature(distribute_to_platform_task.run)
	params = list(sig.parameters.keys())
	assert 'episode_id' in params


def test_task_accepts_platform_parameter():
	"""Task signature must accept platform parameter."""
	sig = inspect.signature(distribute_to_platform_task.run)
	params = list(sig.parameters.keys())
	assert 'platform' in params


def test_task_accepts_platform_config_parameter():
	"""Task signature must accept platform_config parameter."""
	sig = inspect.signature(distribute_to_platform_task.run)
	params = list(sig.parameters.keys())
	assert 'platform_config' in params


def test_task_accepts_episode_metadata_parameter():
	"""Task signature must accept episode_metadata parameter."""
	sig = inspect.signature(distribute_to_platform_task.run)
	params = list(sig.parameters.keys())
	assert 'episode_metadata' in params


# ============================================================================
# PLATFORM ROUTING TESTS
# ============================================================================


def test_task_routes_spotify_platform():
	"""Task must route platform='spotify' to _distribute_to_spotify."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="spotify",
			platform_config={},
			episode_metadata={}
		)

	assert result["status"] == "success"
	assert result["platform"] == "spotify"


def test_task_routes_apple_podcasts_platform():
	"""Task must route platform='apple_podcasts' to _distribute_to_apple."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="apple_podcasts",
			platform_config={},
			episode_metadata={}
		)

	assert result["platform"] == "apple_podcasts"
	assert result["platform_episode_id"] == "apple_placeholder_id"


def test_task_routes_webhook_platform():
	"""Task must route platform='webhook' to _distribute_via_webhook."""
	episode_id = str(uuid4())

	mock_response = MagicMock()
	mock_response.raise_for_status.return_value = None

	with patch('requests.post', return_value=mock_response):
		with patch.object(distribute_to_platform_task, 'update_state'):
			result = distribute_to_platform_task.run(
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": "https://example.com/hook"},
				episode_metadata={}
			)

	assert result["status"] == "success"
	assert result["platform"] == "webhook"


# ============================================================================
# UNSUPPORTED PLATFORM TESTS
# ============================================================================


def test_task_returns_failed_for_unsupported_platform():
	"""Task must return failed dict for unrecognised platform."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="youtube",
			platform_config={},
			episode_metadata={}
		)

	assert result["status"] == "failed"
	assert result["platform"] == "youtube"
	assert result["platform_episode_id"] is None
	assert result["platform_url"] is None
	assert "Unsupported platform" in result["error"]


# ============================================================================
# WEBHOOK-SPECIFIC TESTS
# ============================================================================


def test_webhook_missing_url_returns_failed():
	"""Task must return failed when platform_config has no webhook_url."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="webhook",
			platform_config={},
			episode_metadata={}
		)

	assert result["status"] == "failed"
	assert "Webhook URL" in result["error"]


def test_webhook_calls_requests_post_with_correct_args():
	"""Task must call requests.post with correct URL, json body, and timeout."""
	episode_id = str(uuid4())
	webhook_url = "https://example.com/hook"
	metadata = {"title": "Ep1"}

	mock_response = MagicMock()
	mock_response.raise_for_status.return_value = None

	with patch('requests.post', return_value=mock_response) as mock_post:
		with patch.object(distribute_to_platform_task, 'update_state'):
			distribute_to_platform_task.run(
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": webhook_url},
				episode_metadata=metadata
			)

	mock_post.assert_called_once()
	args, kwargs = mock_post.call_args
	assert args[0] == webhook_url
	assert kwargs["json"]["episode_id"] == episode_id
	assert kwargs["json"]["metadata"] == metadata
	assert kwargs["json"]["event"] == "episode_published"
	assert kwargs["timeout"] == 30


def test_webhook_success_returns_correct_shape():
	"""Successful webhook call must return correct result dict."""
	episode_id = str(uuid4())
	webhook_url = "https://example.com/hook"

	mock_response = MagicMock()
	mock_response.raise_for_status.return_value = None

	with patch('requests.post', return_value=mock_response):
		with patch.object(distribute_to_platform_task, 'update_state'):
			result = distribute_to_platform_task.run(
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": webhook_url},
				episode_metadata={}
			)

	assert result["status"] == "success"
	assert result["platform"] == "webhook"
	assert result["platform_episode_id"] is None
	assert result["platform_url"] == webhook_url
	assert result["error"] is None


def test_webhook_http_error_returns_failed():
	"""HTTP error from raise_for_status must propagate to failed return."""
	episode_id = str(uuid4())

	mock_response = MagicMock()
	mock_response.raise_for_status.side_effect = Exception("500 Server Error")

	with patch('requests.post', return_value=mock_response):
		with patch.object(distribute_to_platform_task, 'update_state'):
			result = distribute_to_platform_task.run(
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": "https://example.com/hook"},
				episode_metadata={}
			)

	assert result["status"] == "failed"
	assert "500 Server Error" in result["error"]


def test_webhook_requests_post_connection_error_returns_failed():
	"""ConnectionError from requests.post must propagate to failed return."""
	episode_id = str(uuid4())

	with patch('requests.post', side_effect=ConnectionError("Network unreachable")):
		with patch.object(distribute_to_platform_task, 'update_state'):
			result = distribute_to_platform_task.run(
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": "https://example.com/hook"},
				episode_metadata={}
			)

	assert result["status"] == "failed"
	assert "Network unreachable" in result["error"]


# ============================================================================
# RETURN VALUE STRUCTURE TESTS
# ============================================================================


def test_success_result_has_required_keys():
	"""Successful result must contain all five required keys."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="spotify",
			platform_config={},
			episode_metadata={}
		)

	assert "status" in result
	assert "platform" in result
	assert "platform_episode_id" in result
	assert "platform_url" in result
	assert "error" in result


def test_failed_result_has_required_keys():
	"""Failed result must contain all five required keys."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="unsupported",
			platform_config={},
			episode_metadata={}
		)

	assert "status" in result
	assert "platform" in result
	assert "platform_episode_id" in result
	assert "platform_url" in result
	assert "error" in result


def test_failed_result_platform_episode_id_is_none():
	"""Failed result must have platform_episode_id set to None."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="unsupported",
			platform_config={},
			episode_metadata={}
		)

	assert result["platform_episode_id"] is None


def test_failed_result_platform_url_is_none():
	"""Failed result must have platform_url set to None."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state'):
		result = distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="unsupported",
			platform_config={},
			episode_metadata={}
		)

	assert result["platform_url"] is None


# ============================================================================
# PROGRESS STATE UPDATE TESTS
# ============================================================================


def test_task_calls_update_state_on_start():
	"""Task must call update_state with state='PROGRESS' at the start."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state') as mock_update:
		distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="spotify",
			platform_config={},
			episode_metadata={}
		)

	# First call must be PROGRESS
	first_call_kwargs = mock_update.call_args_list[0].kwargs
	assert first_call_kwargs["state"] == 'PROGRESS'


def test_task_calls_update_state_on_success():
	"""Task must call update_state with state='SUCCESS' after successful distribution."""
	episode_id = str(uuid4())

	with patch.object(distribute_to_platform_task, 'update_state') as mock_update:
		distribute_to_platform_task.run(
			episode_id=episode_id,
			platform="spotify",
			platform_config={},
			episode_metadata={}
		)

	# Any call must have state='SUCCESS'
	all_states = [c.kwargs.get("state") for c in mock_update.call_args_list]
	assert 'SUCCESS' in all_states
