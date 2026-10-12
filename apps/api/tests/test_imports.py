"""
Tests to verify the generation engine is importable without sys.path manipulation.
GAP-030: Remove fragile sys.path manipulation from Celery tasks.
"""


def test_generation_engine_imports():
	"""The engine and the libraries it needs import cleanly (#543)."""
	import pymupdf
	import youtube_transcript_api
	from src.engine import generate_script
	from src.engine.tts import synthesise
	from src.services.text_extraction import html_to_text, pdf_to_text

	assert callable(generate_script) and callable(synthesise)
	assert callable(html_to_text) and callable(pdf_to_text)
	assert pymupdf is not None and youtube_transcript_api is not None


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
