"""
Unit tests for bidirectional ORM relationships (GAP-017).

Verifies that all relationship declarations are properly configured with
back_populates on both sides, using SQLAlchemy mapper inspection.
No database connection required.
"""
from sqlalchemy import inspect as sa_inspect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relationships(model_class) -> dict:
	"""Return a dict of {attr_name: RelationshipProperty} for a model."""
	mapper = sa_inspect(model_class)
	return {r.key: r for r in mapper.relationships}


def _assert_backpopulates(model_cls, rel_name: str, expected_back_populates: str):
	"""Assert a relationship has the expected back_populates value."""
	rels = _relationships(model_cls)
	assert rel_name in rels, (
		f"{model_cls.__name__} is missing relationship '{rel_name}'"
	)
	actual = rels[rel_name].back_populates
	assert actual == expected_back_populates, (
		f"{model_cls.__name__}.{rel_name}.back_populates should be "
		f"'{expected_back_populates}', got '{actual}'"
	)


# ---------------------------------------------------------------------------
# Import models (env vars already set by conftest.py)
# ---------------------------------------------------------------------------

from src.models.user import User  # noqa: E402
from src.models.project import Project  # noqa: E402
from src.models.episode import Episode  # noqa: E402
from src.models.tts_configuration import TTSConfiguration  # noqa: E402
from src.models.conversation_template import ConversationTemplate  # noqa: E402
from src.models.distribution_target import DistributionTarget  # noqa: E402
from src.models.audio_snippet import AudioSnippet  # noqa: E402
from src.models.episode_layout import EpisodeLayout  # noqa: E402
from src.models.episode_composition import EpisodeComposition  # noqa: E402
from src.models.rss_feed import RSSFeed  # noqa: E402


# ============================================================================
# User relationships
# ============================================================================

class TestUserRelationships:
	def test_user_projects_back_populates(self):
		"""User.projects already has back_populates='user'."""
		_assert_backpopulates(User, "projects", "user")

	def test_user_episodes_back_populates(self):
		"""User.episodes must have back_populates='user'."""
		_assert_backpopulates(User, "episodes", "user")

	def test_user_tts_configs_back_populates(self):
		"""User.tts_configs must have back_populates='user'."""
		_assert_backpopulates(User, "tts_configs", "user")

	def test_user_templates_back_populates(self):
		"""User.templates must have back_populates='user'."""
		_assert_backpopulates(User, "templates", "user")

	def test_user_distribution_targets_back_populates(self):
		"""User.distribution_targets must have back_populates='user'."""
		_assert_backpopulates(User, "distribution_targets", "user")

	def test_user_audio_snippets_back_populates(self):
		"""User.audio_snippets must have back_populates='user'."""
		_assert_backpopulates(User, "audio_snippets", "user")

	def test_user_episode_layouts_back_populates(self):
		"""User.episode_layouts must have back_populates='user'."""
		_assert_backpopulates(User, "episode_layouts", "user")


# ============================================================================
# Project relationships
# ============================================================================

class TestProjectRelationships:
	def test_project_user_back_populates(self):
		"""Project.user must have back_populates='projects'."""
		_assert_backpopulates(Project, "user", "projects")

	def test_project_episodes_back_populates(self):
		"""Project.episodes already has back_populates='project'."""
		_assert_backpopulates(Project, "episodes", "project")

	def test_project_distribution_targets_back_populates(self):
		"""Project.distribution_targets must have back_populates='project'."""
		_assert_backpopulates(Project, "distribution_targets", "project")

	def test_project_audio_snippets_back_populates(self):
		"""Project.audio_snippets must have back_populates='project'."""
		_assert_backpopulates(Project, "audio_snippets", "project")

	def test_project_episode_layouts_back_populates(self):
		"""Project.episode_layouts must have back_populates='project'."""
		_assert_backpopulates(Project, "episode_layouts", "project")

	def test_project_rss_feed_back_populates(self):
		"""Project.rss_feed must have back_populates='project'."""
		_assert_backpopulates(Project, "rss_feed", "project")

	def test_project_rss_feed_is_scalar(self):
		"""Project.rss_feed is a one-to-one (uselist=False)."""
		rels = _relationships(Project)
		assert "rss_feed" in rels
		assert rels["rss_feed"].uselist is False


# ============================================================================
# Episode relationships
# ============================================================================

class TestEpisodeRelationships:
	def test_episode_user_back_populates(self):
		"""Episode.user must have back_populates='episodes'."""
		_assert_backpopulates(Episode, "user", "episodes")

	def test_episode_project_back_populates(self):
		"""Episode.project already has back_populates='episodes'."""
		_assert_backpopulates(Episode, "project", "episodes")

	def test_episode_content_sources_back_populates(self):
		"""Episode.content_sources already has back_populates='episode'."""
		_assert_backpopulates(Episode, "content_sources", "episode")

	def test_episode_tts_config_back_populates(self):
		"""Episode.tts_config must have back_populates='episodes'."""
		_assert_backpopulates(Episode, "tts_config", "episodes")

	def test_episode_template_back_populates(self):
		"""Episode.template must have back_populates='episodes'."""
		_assert_backpopulates(Episode, "template", "episodes")

	def test_episode_composition_back_populates(self):
		"""Episode.composition must have back_populates='episode'."""
		_assert_backpopulates(Episode, "composition", "episode")

	def test_episode_composition_is_scalar(self):
		"""Episode.composition is a one-to-one (uselist=False)."""
		rels = _relationships(Episode)
		assert "composition" in rels
		assert rels["composition"].uselist is False


# ============================================================================
# TTSConfiguration relationships
# ============================================================================

class TestTTSConfigurationRelationships:
	def test_tts_config_user_back_populates(self):
		"""TTSConfiguration.user must have back_populates='tts_configs'."""
		_assert_backpopulates(TTSConfiguration, "user", "tts_configs")

	def test_tts_config_episodes_back_populates(self):
		"""TTSConfiguration.episodes must have back_populates='tts_config'."""
		_assert_backpopulates(TTSConfiguration, "episodes", "tts_config")


# ============================================================================
# ConversationTemplate relationships
# ============================================================================

class TestConversationTemplateRelationships:
	def test_template_user_back_populates(self):
		"""ConversationTemplate.user must have back_populates='templates'."""
		_assert_backpopulates(ConversationTemplate, "user", "templates")

	def test_template_episodes_back_populates(self):
		"""ConversationTemplate.episodes must have back_populates='template'."""
		_assert_backpopulates(ConversationTemplate, "episodes", "template")


# ============================================================================
# DistributionTarget relationships
# ============================================================================

class TestDistributionTargetRelationships:
	def test_distribution_target_user_back_populates(self):
		"""DistributionTarget.user must have back_populates='distribution_targets'."""
		_assert_backpopulates(DistributionTarget, "user", "distribution_targets")

	def test_distribution_target_project_back_populates(self):
		"""DistributionTarget.project must have back_populates='distribution_targets'."""
		_assert_backpopulates(DistributionTarget, "project", "distribution_targets")


# ============================================================================
# AudioSnippet relationships
# ============================================================================

class TestAudioSnippetRelationships:
	def test_audio_snippet_user_back_populates(self):
		"""AudioSnippet.user must have back_populates='audio_snippets'."""
		_assert_backpopulates(AudioSnippet, "user", "audio_snippets")

	def test_audio_snippet_project_back_populates(self):
		"""AudioSnippet.project must have back_populates='audio_snippets'."""
		_assert_backpopulates(AudioSnippet, "project", "audio_snippets")


# ============================================================================
# EpisodeLayout relationships
# ============================================================================

class TestEpisodeLayoutRelationships:
	def test_episode_layout_user_back_populates(self):
		"""EpisodeLayout.user must have back_populates='episode_layouts'."""
		_assert_backpopulates(EpisodeLayout, "user", "episode_layouts")

	def test_episode_layout_project_back_populates(self):
		"""EpisodeLayout.project must have back_populates='episode_layouts'."""
		_assert_backpopulates(EpisodeLayout, "project", "episode_layouts")

	def test_episode_layout_compositions_back_populates(self):
		"""EpisodeLayout.compositions must have back_populates='layout'."""
		_assert_backpopulates(EpisodeLayout, "compositions", "layout")


# ============================================================================
# EpisodeComposition relationships
# ============================================================================

class TestEpisodeCompositionRelationships:
	def test_episode_composition_episode_back_populates(self):
		"""EpisodeComposition.episode must have back_populates='composition'."""
		_assert_backpopulates(EpisodeComposition, "episode", "composition")

	def test_episode_composition_layout_back_populates(self):
		"""EpisodeComposition.layout must have back_populates='compositions'."""
		_assert_backpopulates(EpisodeComposition, "layout", "compositions")


# ============================================================================
# RSSFeed relationships
# ============================================================================

class TestRSSFeedRelationships:
	def test_rss_feed_project_back_populates(self):
		"""RSSFeed.project must have back_populates='rss_feed'."""
		_assert_backpopulates(RSSFeed, "project", "rss_feed")
