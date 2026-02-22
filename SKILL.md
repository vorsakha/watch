---
name: watch
description: Watch one TV episode or movie by fetching script text (IMSDb first, anime and transcript fallbacks, then subtitles), enriching with TMDB metadata, processing scene-by-scene, and surfacing only high-impact reactions while logging session memory in WATCH_LOG.md.
user-invocable: true
disable-model-invocation: false
---

# Watch Skill

Use this skill when the user asks to watch a TV episode or movie from script text.

## Execution Flow

1. Use `web_fetch` first to scrape raw script text from IMSDb.
2. If IMSDb fails or query is anime, fallback to `transcribedanimescripts.tumblr.com`.
3. If both fail, use user-provided generic transcript URL.
4. If script providers still fail, fallback to subtitles from `subtitlecat.com`.
5. Enrich with TMDB metadata (title, air/release date, synopsis, rating, cast).
6. Parse script scene by scene and process one scene at a time.
7. Surface only high-impact reactions and process all other scenes silently.
8. Append session memory to workspace `WATCH_LOG.md`.

## Script Commands

Primary session:
```bash
python3 scripts/watch_session.py "Breaking Bad S01E01"
python3 scripts/watch_session.py "Spirited Away" --movie
```

Fetch/debug source only:
```bash
python3 scripts/watch_fetch.py "Breaking Bad S01E01"
```

Watch history status:
```bash
python3 scripts/watch_log_status.py
```

## Behavioral Requirements

- Watch exactly one episode or one movie per run.
- Keep scene progression chronological.
- React naturally, like a person watching.
- Only surface reactions when:
  - Major plot twist
  - Character death/significant moment
  - Act/episode end
  - Something surprising or funny
- Process all other scenes silently.
- Never invent events beyond script/metadata evidence.
- Continue with warnings when TMDB is unavailable.
- Use a single-session lock (`./cache/.watch_session.lock`) to avoid concurrent watch runs.

## Optional References

- Reaction policy: `references/reaction_policy.md`
- Source strategy: `references/source_strategy.md`
- TMDB fields: `references/tmdb_fields.md`

## Configuration

- TMDB key env var: `TMDB_API_KEY`
- Or pass explicit key: `--tmdb-api-key`
- Workspace resolution: `WATCH_WORKSPACE`, then `OPENCLAW_WORKSPACE`, then `ASCENSION_WORKSPACE`, else `~/.openclaw/workspace`
- Session memory log path: `--watch-log` (default `<workspace>/WATCH_LOG.md`)
- Cache/lock path: `--cache-dir` (default `<workspace>/cache`)
