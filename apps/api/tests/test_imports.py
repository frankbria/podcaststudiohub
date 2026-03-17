"""
Tests to verify podcastfy is properly installed and importable without sys.path manipulation.
GAP-030: Remove fragile sys.path manipulation from Celery tasks.
"""


def test_podcastfy_imports():
	"""Verify podcastfy can be imported without sys.path manipulation."""
	from podcastfy.client import generate_podcast
	from podcastfy.content_generator import ContentGenerator
	from podcastfy.content_parser.website_extractor import WebsiteExtractor
	from podcastfy.content_parser.pdf_extractor import PDFExtractor

	assert callable(generate_podcast)
	assert ContentGenerator is not None
	assert WebsiteExtractor is not None
	assert PDFExtractor is not None


def test_podcast_generation_task_imports():
	"""Verify the Celery task module imports cleanly without sys.path manipulation."""
	from src.tasks.podcast_generation import generate_podcast_task

	assert generate_podcast_task is not None


def test_no_sys_path_manipulation_in_task():
	"""Verify the task file does not contain sys.path manipulation."""
	import ast
	import pathlib

	task_file = pathlib.Path(__file__).parent.parent / "src" / "tasks" / "podcast_generation.py"
	source = task_file.read_text()

	assert "sys.path.insert" not in source, (
		"sys.path.insert found in podcast_generation.py — remove the sys.path hack"
	)
	assert "sys.path.append" not in source, (
		"sys.path.append found in podcast_generation.py — remove the sys.path hack"
	)

	# Also verify the AST parses cleanly (no syntax errors introduced)
	tree = ast.parse(source)
	assert tree is not None
