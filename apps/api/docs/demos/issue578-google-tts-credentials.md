# #578 — GOOGLE_CLOUD_CREDENTIALS wired into the Google TTS backends

*2026-10-10T02:42:36Z by Showboat 0.6.1*
<!-- showboat-id: d273d64c-c121-46f9-852f-53b317903d39 -->

Every run below has **no Application Default Credentials**: an empty HOME (no gcloud ADC file), GOOGLE_APPLICATION_CREDENTIALS unset, and NO_GCE_CHECK=True (no metadata server). Nothing is patched: each run drives the real `synthesise()` for both `gemini` and `gemini_multi` and makes real calls to Google. The key is freshly generated, so Google rejecting it with a 401 is the *expected* outcome. It proves the request went out signed with the setting's service account rather than failing locally on missing ADC. The script (`/tmp/demo_578.py`, run from `apps/api`):

```bash
sed -n '/^mode = /,$p' /tmp/demo_578.py
```

```output
mode = sys.argv[1]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
info = {
    "type": "service_account",
    "project_id": "podcast-demo",
    "private_key_id": "0" * 40,
    "private_key": key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode(),
    "client_email": "demo-tts@podcast-demo.iam.gserviceaccount.com",
    "client_id": "1",
    "token_uri": "https://oauth2.googleapis.com/token",
}
work = Path(tempfile.mkdtemp())
if mode == "json":
    settings.GOOGLE_CLOUD_CREDENTIALS = json.dumps(info)
elif mode == "path":
    (work / "sa.json").write_text(json.dumps(info))
    settings.GOOGLE_CLOUD_CREDENTIALS = str(work / "sa.json")
elif mode == "bad":
    settings.GOOGLE_CLOUD_CREDENTIALS = '{"type": "service_account", "private_key": "-----BEGIN PRIVATE KEY-----SECRET'
else:
    settings.GOOGLE_CLOUD_CREDENTIALS = None

print(f"GOOGLE_APPLICATION_CREDENTIALS={os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')!r}  HOME={os.environ['HOME']}")
script = Script(title="t", summary="s", turns=[
    {"speaker": "host", "text": "Hello."}, {"speaker": "guest", "text": "Hi."}])
config = {"model": "gemini-2.5-flash-tts", "language_code": "en-US",
          "voice_1": "Kore", "voice_2": "Charon"}
for provider in ("gemini", "gemini_multi"):
    try:
        synthesise(provider, script, config, work / provider)
        print(f"{provider}: synthesised")
    except TTSProviderError as exc:
        print(f"{provider}: TTSProviderError: {str(exc)[:300]}")
```

**Before the fix (main):** the setting is set as inline JSON, but nothing reads it, so both backends fall through to ADC and fail locally.

```bash
cd /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/04174f79-f676-4b28-8929-e04009aa35d0/scratchpad/main-wt/apps/api && env -u GOOGLE_APPLICATION_CREDENTIALS HOME=/tmp/noadc-gIPj NO_GCE_CHECK=True ENCRYPTION_KEY=demo-encryption-key-32-characters!! JWT_SECRET_KEY=demo-jwt-secret-key-at-least-32-chars-long DATABASE_URL=postgresql+asyncpg://u:p@localhost/db PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /tmp/demo_578.py json
```

```output
GOOGLE_APPLICATION_CREDENTIALS=None  HOME=/tmp/noadc-gIPj
gemini: TTSProviderError: Google Cloud TTS credentials are unavailable: Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
gemini_multi: TTSProviderError: Google Cloud TTS credentials are unavailable: Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
```

**AC1, inline JSON (this branch):** the same input now reaches Google, and the call is authenticated with the service-account key from the setting. The 401 comes back as a classified `TTSProviderError`, not a stack trace.

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS HOME=/tmp/noadc-gIPj NO_GCE_CHECK=True ENCRYPTION_KEY=demo-encryption-key-32-characters!! JWT_SECRET_KEY=demo-jwt-secret-key-at-least-32-chars-long DATABASE_URL=postgresql+asyncpg://u:p@localhost/db PYTHONPATH=. .venv/bin/python /tmp/demo_578.py json
```

```output
GOOGLE_APPLICATION_CREDENTIALS=None  HOME=/tmp/noadc-gIPj
gemini: TTSProviderError: Gemini TTS call failed: 401 Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.
gemini_multi: TTSProviderError: Gemini multi-speaker TTS call failed: 401 Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.
```

**AC1, path to a key file:** same outcome.

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS HOME=/tmp/noadc-gIPj NO_GCE_CHECK=True ENCRYPTION_KEY=demo-encryption-key-32-characters!! JWT_SECRET_KEY=demo-jwt-secret-key-at-least-32-chars-long DATABASE_URL=postgresql+asyncpg://u:p@localhost/db PYTHONPATH=. .venv/bin/python /tmp/demo_578.py path
```

```output
GOOGLE_APPLICATION_CREDENTIALS=None  HOME=/tmp/noadc-gIPj
gemini: TTSProviderError: Gemini TTS call failed: 401 Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.
gemini_multi: TTSProviderError: Gemini multi-speaker TTS call failed: 401 Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.
```

**AC2 / ADC fallback, setting unset:** the client goes to ADC as before. With no ADC on the host, that is the existing clear `TTSProviderError`.

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS HOME=/tmp/noadc-gIPj NO_GCE_CHECK=True ENCRYPTION_KEY=demo-encryption-key-32-characters!! JWT_SECRET_KEY=demo-jwt-secret-key-at-least-32-chars-long DATABASE_URL=postgresql+asyncpg://u:p@localhost/db PYTHONPATH=. .venv/bin/python /tmp/demo_578.py unset
```

```output
GOOGLE_APPLICATION_CREDENTIALS=None  HOME=/tmp/noadc-gIPj
gemini: TTSProviderError: Google Cloud TTS credentials are unavailable: Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
gemini_multi: TTSProviderError: Google Cloud TTS credentials are unavailable: Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
```

**Malformed setting** (a truncated key containing the marker `SECRET`): the error names the setting, does not fall back to ADC (which would hide the typo), and does not echo the value.

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS HOME=/tmp/noadc-gIPj NO_GCE_CHECK=True ENCRYPTION_KEY=demo-encryption-key-32-characters!! JWT_SECRET_KEY=demo-jwt-secret-key-at-least-32-chars-long DATABASE_URL=postgresql+asyncpg://u:p@localhost/db PYTHONPATH=. .venv/bin/python /tmp/demo_578.py bad
```

```output
GOOGLE_APPLICATION_CREDENTIALS=None  HOME=/tmp/noadc-gIPj
gemini: TTSProviderError: GOOGLE_CLOUD_CREDENTIALS does not hold valid JSON
gemini_multi: TTSProviderError: GOOGLE_CLOUD_CREDENTIALS does not hold valid JSON
```

**AC3:** the documented format.

```bash
grep -B3 '^GOOGLE_CLOUD_CREDENTIALS' .env.example ../../.env.example
```

```output
.env.example-# Google Cloud TTS (gemini / gemini_multi): a service-account key, given either as
.env.example-# the JSON itself on one line ({"type": "service_account", ...}) or as a path to the
.env.example-# .json file. Leave unset to use Application Default Credentials on the host.
.env.example:GOOGLE_CLOUD_CREDENTIALS=/path/to/google-service-account.json
--
../../.env.example-# Google Cloud TTS (gemini / gemini_multi): a service-account key, given either as
../../.env.example-# the JSON itself on one line ({"type": "service_account", ...}) or as a path to the
../../.env.example-# .json file. Leave unset to use Application Default Credentials on the host.
../../.env.example:GOOGLE_CLOUD_CREDENTIALS=/path/to/google-service-account.json
```
