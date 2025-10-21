# Syncing with Upstream Podcastfy

This project (PodcastStudioHub) uses the [podcastfy](https://github.com/souzatharsis/podcastfy) CLI library as its core podcast generation engine. The `podcastfy/` directory in this repository contains a copy of the upstream podcastfy code.

## Git Remote Configuration

The repository has the following remotes configured:

- `podcaststudiohub` - Our main repository at https://github.com/frankbria/podcaststudiohub.git
- `origin` - Original fork at https://github.com/frankbria/podcastfy.git (legacy)
- `podcastfy-upstream` - Upstream podcastfy at https://github.com/souzatharsis/podcastfy.git

## Pulling Updates from Upstream

To update the podcastfy CLI to the latest version from upstream:

### Option 1: Manual Sync (Recommended for major updates)

1. Check the current version of podcastfy in the codebase:
```bash
cat podcastfy/__init__.py
```

2. Check available versions on upstream:
```bash
git fetch podcastfy-upstream
git tag -l "v*" | grep podcastfy-upstream
```

3. Create a new branch for the update:
```bash
git checkout -b update-podcastfy-v0.x.x
```

4. Copy the updated podcastfy directory from upstream:
```bash
# Add upstream as a remote if not already done
git remote add podcastfy-upstream https://github.com/souzatharsis/podcastfy.git
git fetch podcastfy-upstream

# Create a temporary directory and checkout upstream
mkdir -p /tmp/podcastfy-update
cd /tmp/podcastfy-update
git clone https://github.com/souzatharsis/podcastfy.git .
git checkout v0.x.x  # or main branch

# Copy podcastfy directory to your project
cp -r podcastfy /path/to/podcaststudiohub/

# Return to project
cd /path/to/podcaststudiohub
```

5. Review changes and test:
```bash
git diff podcastfy/
# Run tests to ensure compatibility with API
cd apps/api
pytest
```

6. Commit and push:
```bash
git add podcastfy/
git commit -m "chore: Update podcastfy CLI to v0.x.x"
git push podcaststudiohub update-podcastfy-v0.x.x
```

### Option 2: Git Subtree (For automated syncing)

If you prefer automated syncing, you can convert the `podcastfy/` directory to a git subtree:

1. Remove the existing podcastfy directory:
```bash
git rm -r podcastfy/
git commit -m "chore: Remove podcastfy directory for subtree conversion"
```

2. Add podcastfy as a subtree:
```bash
git subtree add --prefix podcastfy podcastfy-upstream main --squash
```

3. To pull updates in the future:
```bash
git fetch podcastfy-upstream
git subtree pull --prefix podcastfy podcastfy-upstream main --squash
```

## API Integration Points

The PodcastStudioHub API integrates with podcastfy through the following files:

- `apps/api/src/podcastfy/` - Symlink or copy of the podcastfy library
- `apps/api/src/services/generation.py` - Service that calls podcastfy CLI functions

When updating podcastfy, ensure these integration points remain compatible:

1. **Content Extraction**: `podcastfy.content_parser.content_extractor`
2. **LLM Generation**: `podcastfy.content_generator.ContentGenerator`
3. **TTS Conversion**: `podcastfy.text_to_speech.TextToSpeech`
4. **Configuration**: `podcastfy.utils.config` and YAML configs

## Testing After Updates

After updating podcastfy, run the following tests:

```bash
# API tests
cd apps/api
pytest tests/

# Integration test - generate a test podcast
python -m pytest tests/test_generation.py -v

# Manual test via API
curl -X POST http://localhost:8001/generation/episodes/{episode_id}/generate \
  -H "Authorization: Bearer {token}"
```

## Version Compatibility Matrix

| PodcastStudioHub | Podcastfy CLI | Notes |
|------------------|---------------|-------|
| 1.0.0            | 0.4.1         | Initial release |

## Reporting Issues

If you encounter issues with the podcastfy CLI:

1. Check if it's already reported at https://github.com/souzatharsis/podcastfy/issues
2. If it's PodcastStudioHub-specific, report at https://github.com/frankbria/podcaststudiohub/issues
3. If it's a podcastfy bug, contribute a fix upstream and we'll pull it in

## Contributing Improvements Upstream

If you make improvements to the podcastfy CLI code:

1. Create a branch with only podcastfy changes
2. Submit a PR to https://github.com/souzatharsis/podcastfy
3. Once merged upstream, pull the changes back into PodcastStudioHub
