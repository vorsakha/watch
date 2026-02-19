# Watch Skill

`watch` is an OpenClaw skill that simulates watching one movie or one TV episode by reading script text scene-by-scene, enriching context with TMDB metadata, and surfacing only major reactions.

## What It Does

- Fetches script text with fallback order:
  1. IMSDb (`imsdb.com`)
  2. Anime fallback (`transcribedanimescripts.tumblr.com`)
  3. Generic transcript URL (`--source-url`)
- Enriches context from TMDB:
  - title
  - air/release date
  - synopsis
  - rating
  - cast
- Parses script into scenes and processes in chronological order.
- Surfaces reactions only for high-impact moments:
  - major twists
  - deaths/significant moments
  - act/episode endings
  - surprising/funny beats
- Logs surfaced session memory to `WATCH_LOG.md`.
- Enforces single active session with lock file: `./cache/.watch_session.lock`.

## Repository Structure

- `SKILL.md` - main skill instructions and behavior
- `skill.json` - OpenClaw manifest wiring
- `agents/openai.yaml` - agent metadata
- `scripts/` - executable helper scripts
- `references/` - concise policy and strategy docs
- `tests/` - manifest integrity test

## Requirements

- Python 3.10+
- `requests`
- `beautifulsoup4`

Install locally (optional virtualenv):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install requests beautifulsoup4
```

## Usage

Watch one episode:

```bash
python3 scripts/watch_session.py "Breaking Bad S01E01"
```

Watch one movie:

```bash
python3 scripts/watch_session.py "Spirited Away" --movie
```

Provide generic transcript fallback URL:

```bash
python3 scripts/watch_session.py "Some Title" --source-url "https://example.com/transcript"
```

Fetch-only debug:

```bash
python3 scripts/watch_fetch.py "Breaking Bad S01E01"
```

Watch log summary:

```bash
python3 scripts/watch_log_status.py --path WATCH_LOG.md
```

## TMDB Configuration

Use either:

- environment variable: `TMDB_API_KEY`
- CLI override: `--tmdb-api-key`

If TMDB is unavailable, sessions continue with warnings.

## Notes

- This skill intentionally processes one title per run to reduce rate-limit risk.
- In restricted/sandboxed environments, network calls to IMSDb/TMDB may fail; scripts still return structured errors.
