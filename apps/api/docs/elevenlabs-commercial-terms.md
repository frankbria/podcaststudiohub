# ElevenLabs commercial terms — Output vs reselling the Service

**Issue**: #544 (P2.19.1) · **Gates**: #543 (P2.20) making ElevenLabs the default premium backend
**Status**: ⏳ **Awaiting written answer from ElevenLabs.** Nothing below the
"Vendor answer" heading is confirmed. Do not cite this document as clearance.

## Why this document exists

ElevenLabs' [Prohibited Use Policy](https://elevenlabs.io/use-policy) bars
"selling, reselling, renting, leasing, loaning, assigning, licensing, or
sub-licensing our Services" without prior written authorisation, with a
carve-out: this "does not preclude your use of Output in accordance with the
applicable terms and conditions." It separately bars embedding "any part of the
Services" in another service without written consent.

Our read is that we consume Output, not resell the Service: the customer
supplies content, we call the API with the platform key, the customer receives
finished audio and never touches ElevenLabs. But the clause is load-bearing for
the premium tier and is the kind that gets enforced inconsistently, so the read
needs to be theirs in writing, not ours.

All of these sit in **section 9**, "Do not use our Services in any manner
contrary to ElevenLabs' policies, purpose or mission" — the reselling clause is
9(b). Two further clauses in the same section bear on this, both easy to miss:

- **(q)**, the embedding clause, covers "framing, mirroring, or otherwise
  embedding any part of the Services, including **trademarks, names, logos**, or
  any portion of the Services, within another website, mobile application, or
  service" without express prior written consent. Naming ElevenLabs in our voice
  picker is their *name* in our web app, so question 2 below is squarely on this
  clause rather than a stretch reading of it.
- **(i)** bars "developing or using any applications or software that interact
  with our Services without our prior written authorization (such as through our
  APIs)." Read literally that covers every API customer they have, so it is
  plainly not enforced as written — but it is the same inconsistently-enforced
  hazard as the reselling clause, and costs nothing to clear in the same email.

Not in scope but worth knowing: **(c)** separately bars commercially exploiting
Sound Effects output on a standalone basis. We generate dialogue via
Text-to-Dialogue, not Sound Effects, so this does not bite — it would if we ever
shipped generated stings or beds as separable assets.

Also in scope: commercial use requires a paid plan (the free tier is
non-commercial and requires attribution), and API tiers are priced separately
from the consumer plans.

## The questions asked

1. Is generating finished podcast audio for our paying customers, using our
   platform API key, permitted use of Output?
2. Does offering ElevenLabs as a selectable voice option in our UI — named as
   such — constitute embedding the Service under (q)?
3. Does (i) require written authorization for our API integration as such?
4. Which API tier is recommended for our expected character volume?

The email as sent is in [Appendix: email sent](#appendix-email-sent).

## Where to send it

Nothing in this repo held a contact address; these were confirmed 2026-09-21.

| Route | Address | Notes |
|---|---|---|
| **Enterprise sales** | https://elevenlabs.io/enterprise → "Contact sales" | **Primary.** Form only, no public email. Reaches people who can give a binding answer and who want the deal — we are also asking which tier to buy. |
| **General support** | **team@elevenlabs.io** | **Send in parallel.** Named in their help centre and in the Terms of Use as the address for "a question or complaint regarding the Services". Support may not answer a licensing question itself, but this is what produces the written ticket reference recorded above. |
| Policy ticket form | https://help.elevenlabs.io/hc/en-us/requests/new | The route the Prohibited Use Policy itself names for authorization requests and appeals. Use if the other two stall. |

Email from a company address, not a personal one, and keep the reply — the
point of this exercise is a written record, not a verbal assurance.

## Vendor answer

> _Not yet received._ When it arrives, paste it here **verbatim**, with the date
> and the support/sales ticket reference. No contact names — this repo is public.

- **Date sent**: _(fill in)_
- **Date received**: _(fill in)_
- **Ticket reference**: _(fill in)_

## Decision: platform key vs BYOK

_Undecided — blocked on the answer above._

| Answer | Decision |
|---|---|
| Output use is permitted, UI option is not embedding | Platform key. ElevenLabs can be the default premium backend in #543. |
| Permitted only under a reseller agreement | Either sign it, or fall back to BYOK. |
| Not permitted / no answer by the time #543 is ready | ElevenLabs becomes an optional **bring-your-own-key** backend; default premium tier ships on Edge/Gemini TTS. Open a `PX.Y` follow-up for the BYOK work. |

### What BYOK actually costs (corrected)

The #544 thread says "per-tenant key already supported by the scoped-client
design." That is half right, and the half that is wrong matters for sizing.

What the scoped-client design **does** give us: no module-global API key.
`ElevenLabsTTS.synthesise` builds its own client per call
(`apps/api/src/engine/tts/elevenlabs.py:54`), unlike podcastfy's
`openai.api_key = ...` global. So there is no cross-tenant key bleed to untangle.

What it does **not** give us: any way to pass a key in. The key is read from
`settings.ELEVENLABS_API_KEY`; neither `get_backend(provider)` nor
`synthesise(script, voices, workdir)` takes one, and `tts_configurations` has no
key column. BYOK is therefore a real change, roughly:

1. An encrypted key column on `tts_configurations` — reuse the existing
   `encrypt_credential` / `decrypt_credential_sync` helpers in
   `apps/api/src/utils/encryption.py` (already used by `distribution_targets`),
   plus an Alembic migration.
2. Thread an optional key through `get_backend` → `synthesise`, falling back to
   `settings.ELEVENLABS_API_KEY` when absent.
3. Surface the field in the TTS-config schema, router, and web form.

Small — a day or so, no redesign — but not zero, and the seam in (2) does not
exist yet. If we want the "config flag, not a rewrite" property the thread
assumes, add the key parameter when #543 cuts over, whatever the vendor says.

## Re-evaluation triggers

Revisit this document when any of these fire:

- ElevenLabs answers (obviously) — fill in the sections above and update #543.
- ElevenLabs revises the Prohibited Use Policy or the API terms.
- We move from "customer never sees ElevenLabs" to anything that exposes the
  Service directly — passing through voice-library browsing, letting customers
  supply ElevenLabs voice IDs we do not host, or surfacing their quota.
- We start reselling voice cloning, which is a separate consent regime.

Note for whoever picks this up: **owning more of the generation stack does not
weaken the reselling question.** The clause turns on whose key makes the call
and whether the Service is exposed as a selectable option, not on how much of
the surrounding product is ours. The in-house engine (#541, #542) changes
nothing here.

## Appendix: email sent

Send from a company address to ElevenLabs sales/support, then record the date
and ticket reference above.

> **Subject:** Commercial use question — generating audio for our customers with our API key
>
> Hello,
>
> We run a hosted service that generates AI podcasts. Our customers supply the
> source content (articles, notes, URLs); our backend calls the ElevenLabs API
> with our own paid platform API key to synthesise the dialogue, and the
> customer receives a finished audio file. Customers do not hold ElevenLabs
> accounts, do not call your API, and are not given access to any ElevenLabs
> interface or credential — they choose a voice from a short list we present and
> receive the resulting audio.
>
> We would like written confirmation on four points before we make ElevenLabs
> our default premium voice option:
>
> 1. Is this permitted use of Output under the Prohibited Use Policy — that is,
>    does generating finished audio for paying customers with our own API key
>    fall under "your use of Output in accordance with the applicable terms and
>    conditions" rather than under selling or sub-licensing the Services
>    (section 9(b))?
> 2. Section 9(q) covers embedding "any part of the Services, including
>    trademarks, names, logos" in another service without written consent. We
>    present ElevenLabs by name as one selectable voice option in our interface,
>    with all synthesis server-side on our key. Does naming you in that way
>    require consent under 9(q), and if so, may we have it? We are happy to
>    follow any attribution or brand guidelines you prefer.
> 3. Section 9(i) refers to "developing or using any applications or software
>    that interact with our Services without our prior written authorization
>    (such as through our APIs)". We assume holding a paid API account is that
>    authorization, but would like it confirmed rather than assumed.
> 4. Which API tier would you recommend for our expected volume, and is a
>    reseller or enterprise agreement required for this model?
>
> Happy to provide more detail on the architecture or volume estimates if that
> helps. We would appreciate the answer in writing so we can file it internally.
>
> Thank you,
> _(name, title, company)_
