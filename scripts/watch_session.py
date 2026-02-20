#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


@dataclass
class WatchTarget:
    query: str
    title: str
    content_type: Literal["movie", "episode"] = "episode"
    season: int | None = None
    episode: int | None = None


@dataclass
class SourceCandidate:
    provider: Literal["imsdb", "transcribed_anime", "generic_transcript"]
    url: str | None = None
    confidence: float = 0.0
    script_text: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class CastMember:
    name: str
    character: str | None = None


@dataclass
class TmdbMetadata:
    title: str | None = None
    air_date: str | None = None
    synopsis: str | None = None
    rating: float | None = None
    runtime_minutes: int | None = None
    cast: list[CastMember] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Scene:
    index: int
    heading: str | None
    body: str
    estimated_start_sec: int | None = None
    estimated_end_sec: int | None = None
    characters: list[str] = field(default_factory=list)


@dataclass
class SceneReaction:
    scene_index: int
    trigger: Literal[
        "plot_twist",
        "character_death",
        "significant_character_moment",
        "act_or_episode_end",
        "surprising_or_funny",
        "none",
    ] = "none"
    text: str | None = None
    surfaced: bool = False


@dataclass
class WatchResult:
    target: WatchTarget
    source: SourceCandidate | None = None
    metadata: TmdbMetadata | None = None
    scenes_processed: int = 0
    surfaced_reactions: list[SceneReaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallback_trace: list[str] = field(default_factory=list)
    cache: dict = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)


class WatchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SourceError(WatchError):
    pass


class SessionLockError(WatchError):
    pass


SCENE_HEADING_RE = re.compile(
    r"^(INT\.|EXT\.|INT/EXT\.|ESTABLISHING|COLD OPEN|ACT\s+[IVX0-9]+|SCENE\s+\d+|\[[^\]]+\])",
    re.IGNORECASE,
)
CHARACTER_RE = re.compile(r"^[A-Z][A-Z0-9 .\-']{2,}$")


def resolve_workspace_root() -> Path:
    for key in ("WATCH_WORKSPACE", "OPENCLAW_WORKSPACE", "ASCENSION_WORKSPACE"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return (Path.home() / ".openclaw" / "workspace").resolve()


OPENCLAW_WORKSPACE = resolve_workspace_root()
DEFAULT_WATCH_LOG_PATH = (OPENCLAW_WORKSPACE / "WATCH_LOG.md").resolve()
DEFAULT_CACHE_DIR = (OPENCLAW_WORKSPACE / "cache").resolve()


def _slug(title: str) -> str:
    return re.sub(r"\s+", "-", title.strip())


def _parse_target(query: str, movie: bool = False, season: int | None = None, episode: int | None = None) -> WatchTarget:
    title = query.strip()
    parsed_season = season
    parsed_episode = episode

    if not movie:
        match = re.search(r"s(\d{1,2})e(\d{1,2})", query, flags=re.IGNORECASE)
        if match:
            parsed_season = parsed_season or int(match.group(1))
            parsed_episode = parsed_episode or int(match.group(2))
            title = re.sub(r"s\d{1,2}e\d{1,2}", "", query, flags=re.IGNORECASE).strip(" -_")

    return WatchTarget(
        query=query,
        title=title,
        content_type="movie" if movie else "episode",
        season=parsed_season if not movie else None,
        episode=parsed_episode if not movie else None,
    )


def _extract_script_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    pre = soup.find("pre")
    if pre:
        return pre.get_text("\n", strip=True)
    article = soup.find("article")
    if article:
        return article.get_text("\n", strip=True)
    body = soup.find("body")
    if body:
        return body.get_text("\n", strip=True)
    return soup.get_text("\n", strip=True)


def _fetch_url(url: str, timeout_sec: int) -> str:
    response = requests.get(url, timeout=timeout_sec)
    response.raise_for_status()
    return response.text


def _fetch_imsdb(target: WatchTarget, timeout_sec: int) -> SourceCandidate:
    search_url = f"https://imsdb.com/search.php?query={quote_plus(target.title)}"
    search_html = _fetch_url(search_url, timeout_sec)
    soup = BeautifulSoup(search_html, "html.parser")

    script_link = None
    for anchor in soup.select("a"):
        href = anchor.get("href")
        if href and "/scripts/" in href and href.endswith(".html"):
            script_link = href
            break

    if not script_link:
        script_link = f"/scripts/{_slug(target.title)}.html"
    script_url = script_link if script_link.startswith("http") else f"https://imsdb.com{script_link}"

    html = _fetch_url(script_url, timeout_sec)
    text = _extract_script_text_from_html(html)
    if len(text) < 400:
        raise SourceError("SOURCE_TEXT_TOO_SHORT", f"IMSDb returned too little text for {target.title}")

    return SourceCandidate(provider="imsdb", url=script_url, confidence=0.9, script_text=text)


def _fetch_transcribed_anime(target: WatchTarget, timeout_sec: int) -> SourceCandidate:
    slug = _slug(target.title.lower())
    url = f"https://transcribedanimescripts.tumblr.com/tagged/{slug}"
    html = _fetch_url(url, timeout_sec)
    text = _extract_script_text_from_html(html)
    if len(text) < 400:
        raise SourceError("SOURCE_TEXT_TOO_SHORT", f"Anime transcript returned too little text for {target.title}")

    return SourceCandidate(provider="transcribed_anime", url=url, confidence=0.75, script_text=text)


def _fetch_generic(source_url: str | None, timeout_sec: int) -> SourceCandidate:
    if not source_url:
        raise SourceError("SOURCE_URL_REQUIRED", "Generic transcript fallback requires --source-url")
    html = _fetch_url(source_url, timeout_sec)
    text = _extract_script_text_from_html(html)
    if len(text) < 250:
        raise SourceError("SOURCE_TEXT_TOO_SHORT", "Generic transcript fallback returned too little text")
    return SourceCandidate(provider="generic_transcript", url=source_url, confidence=0.55, script_text=text)


def _is_anime_query(query: str) -> bool:
    q = query.lower()
    tokens = ["anime", "ova", "naruto", "one piece", "bleach", "attack on titan", "my hero", "jujutsu"]
    return any(token in q for token in tokens)


def fetch_script_text(target: WatchTarget, timeout_sec: int, source_url: str | None = None) -> tuple[SourceCandidate, list[str], list[str]]:
    trace: list[str] = []
    warnings: list[str] = []

    providers = ["imsdb", "transcribed_anime", "generic_transcript"]
    if _is_anime_query(target.query):
        providers = ["imsdb", "transcribed_anime", "generic_transcript"]

    last_error: SourceError | None = None
    for provider in providers:
        try:
            if provider == "imsdb":
                source = _fetch_imsdb(target, timeout_sec)
            elif provider == "transcribed_anime":
                source = _fetch_transcribed_anime(target, timeout_sec)
            else:
                source = _fetch_generic(source_url, timeout_sec)
            trace.append(f"source:{provider}:success")
            return source, trace, warnings
        except SourceError as exc:
            last_error = exc
            trace.append(f"source:{provider}:failed:{exc.code}")
        except requests.RequestException as exc:
            last_error = SourceError("SOURCE_HTTP_ERROR", str(exc))
            trace.append(f"source:{provider}:failed:SOURCE_HTTP_ERROR")

    if last_error:
        raise last_error
    raise SourceError("SOURCE_NOT_FOUND", "No script source produced a usable script")


def _tmdb_get(path: str, api_key: str, params: dict | None = None, timeout_sec: int = 10) -> dict:
    query = dict(params or {})
    query["api_key"] = api_key
    url = f"https://api.themoviedb.org/3/{path}"
    response = requests.get(url, params=query, timeout=timeout_sec)
    response.raise_for_status()
    return response.json()


def enrich_from_tmdb(target: WatchTarget, tmdb_api_key: str | None, timeout_sec: int = 10) -> TmdbMetadata:
    api_key = tmdb_api_key or os.getenv("TMDB_API_KEY")
    if not api_key:
        return TmdbMetadata(warnings=["TMDB_API_KEY_MISSING"])

    try:
        if target.content_type == "movie":
            search = _tmdb_get("search/movie", api_key, {"query": target.title}, timeout_sec)
            results = search.get("results") or []
            if not results:
                return TmdbMetadata(warnings=["TMDB_MOVIE_NOT_FOUND"])
            top = results[0]
            movie_id = top.get("id")
            details = _tmdb_get(f"movie/{movie_id}", api_key, timeout_sec=timeout_sec)
            credits = _tmdb_get(f"movie/{movie_id}/credits", api_key, timeout_sec=timeout_sec)
            cast = [
                CastMember(name=item.get("name", ""), character=item.get("character"))
                for item in (credits.get("cast") or [])[:12]
                if item.get("name")
            ]
            return TmdbMetadata(
                title=details.get("title") or top.get("title"),
                air_date=details.get("release_date"),
                synopsis=details.get("overview"),
                rating=details.get("vote_average"),
                runtime_minutes=details.get("runtime"),
                cast=cast,
            )

        search = _tmdb_get("search/tv", api_key, {"query": target.title}, timeout_sec)
        results = search.get("results") or []
        if not results:
            return TmdbMetadata(warnings=["TMDB_SHOW_NOT_FOUND"])
        top = results[0]
        tv_id = top.get("id")
        season = target.season or 1
        episode = target.episode or 1
        details = _tmdb_get(f"tv/{tv_id}/season/{season}/episode/{episode}", api_key, timeout_sec=timeout_sec)
        credits = _tmdb_get(f"tv/{tv_id}/season/{season}/episode/{episode}/credits", api_key, timeout_sec=timeout_sec)
        cast = [
            CastMember(name=item.get("name", ""), character=item.get("character"))
            for item in (credits.get("cast") or [])[:12]
            if item.get("name")
        ]
        return TmdbMetadata(
            title=details.get("name"),
            air_date=details.get("air_date"),
            synopsis=details.get("overview"),
            rating=details.get("vote_average"),
            runtime_minutes=details.get("runtime"),
            cast=cast,
        )
    except requests.RequestException as exc:
        return TmdbMetadata(warnings=[f"TMDB_HTTP_ERROR:{exc}"])


def _extract_characters(lines: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = line.strip()
        if CHARACTER_RE.match(text) and text not in seen:
            found.append(text)
            seen.add(text)
    return found[:10]


def _estimate_scene_times(scenes: list[Scene], runtime_minutes: int | None) -> list[Scene]:
    if not scenes:
        return scenes
    total = sum(max(1, len(scene.body)) for scene in scenes)
    runtime_sec = (runtime_minutes or 24) * 60
    cursor = 0
    for scene in scenes:
        portion = max(1, len(scene.body)) / total
        duration = max(10, int(runtime_sec * portion))
        scene.estimated_start_sec = cursor
        scene.estimated_end_sec = cursor + duration
        cursor += duration
    return scenes


def parse_scenes(script_text: str, runtime_minutes: int | None = None, max_scene_chars: int = 4200) -> tuple[list[Scene], list[str]]:
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    warnings: list[str] = []
    scenes: list[Scene] = []

    current_heading: str | None = None
    current_lines: list[str] = []
    saw_heading = False

    def flush() -> None:
        if not current_lines:
            return
        body = "\n".join(current_lines).strip()
        if not body:
            return
        scenes.append(
            Scene(
                index=len(scenes) + 1,
                heading=current_heading,
                body=body[:max_scene_chars],
                characters=_extract_characters(current_lines),
            )
        )

    for line in lines:
        if SCENE_HEADING_RE.match(line):
            saw_heading = True
            flush()
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)
    flush()

    if not saw_heading:
        warnings.append("SCENE_PARSE_NO_HEADINGS")
        scenes = []
        chunk: list[str] = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 1400:
                scenes.append(Scene(index=len(scenes) + 1, heading=None, body="\n".join(chunk), characters=_extract_characters(chunk)))
                chunk = []
        if chunk:
            scenes.append(Scene(index=len(scenes) + 1, heading=None, body="\n".join(chunk), characters=_extract_characters(chunk)))

    merged: list[Scene] = []
    for scene in scenes:
        if merged and len(scene.body) < 120 and scene.heading is None:
            prior = merged[-1]
            prior.body = f"{prior.body}\n{scene.body}"[:max_scene_chars]
            for character in scene.characters:
                if character not in prior.characters:
                    prior.characters.append(character)
            continue
        merged.append(scene)

    for index, scene in enumerate(merged, start=1):
        scene.index = index

    return _estimate_scene_times(merged, runtime_minutes), warnings


def _trigger_for_scene(scene: Scene, last_scene: bool) -> str:
    text = scene.body.lower()
    if any(token in text for token in ["dies", "dead", "killed", "funeral", "shot", "death"]):
        return "character_death"
    if any(token in text for token in ["actually", "reveals", "twist", "secret", "it was", "betray"]):
        return "plot_twist"
    if any(token in text for token in ["confesses", "proposal", "goodbye", "breaks down", "i love you"]):
        return "significant_character_moment"
    if any(token in text for token in ["laugh", "joke", "hilarious", "awkward", "comedic"]):
        return "surprising_or_funny"
    if last_scene:
        return "act_or_episode_end"
    return "none"


def react_to_scene(scene: Scene, last_scene: bool) -> SceneReaction:
    trigger = _trigger_for_scene(scene, last_scene)
    heading = scene.heading or f"Scene {scene.index}"

    if trigger == "character_death":
        text = f"Oh damn, that was brutal in {heading}. Huge character loss moment."
    elif trigger == "plot_twist":
        text = f"This is the scene where everything flips in {heading}. That reveal changes the whole read."
    elif trigger == "significant_character_moment":
        text = f"Big emotional swing in {heading}. This is a defining character beat."
    elif trigger == "act_or_episode_end":
        text = f"End beat hit in {heading}. Clear act/episode closing momentum."
    elif trigger == "surprising_or_funny":
        text = f"That was unexpectedly funny/surprising in {heading}."
    else:
        text = None

    return SceneReaction(scene_index=scene.index, trigger=trigger, text=text, surfaced=(trigger != "none"))


def append_watch_log(path: str, result: WatchResult) -> None:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    target = result.target
    metadata = result.metadata

    lines: list[str] = []
    lines.append(f"## {timestamp} - {target.title}")
    lines.append("")
    lines.append(f"- Type: `{target.content_type}`")
    if target.content_type == "episode":
        lines.append(f"- Episode: `S{target.season or 1:02d}E{target.episode or 1:02d}`")
    lines.append(f"- Source: `{result.source.provider if result.source else 'none'}`")
    lines.append(f"- Source URL: {result.source.url if result.source and result.source.url else 'n/a'}")
    lines.append(f"- Metadata title: {metadata.title if metadata and metadata.title else 'n/a'}")
    lines.append(f"- Air date: {metadata.air_date if metadata and metadata.air_date else 'n/a'}")
    lines.append(f"- Rating: {metadata.rating if metadata and metadata.rating is not None else 'n/a'}")
    lines.append(f"- Scenes processed: {result.scenes_processed}")
    lines.append("")
    lines.append("### Surfaced Reactions")
    if result.surfaced_reactions:
        for reaction in result.surfaced_reactions:
            lines.append(f"- Scene {reaction.scene_index} [{reaction.trigger}]: {reaction.text}")
    else:
        lines.append("- None")
    lines.append("")

    if result.warnings:
        lines.append("### Warnings")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    with log_path.open("a", encoding="utf-8") as handle:
        if not log_path.exists() or log_path.stat().st_size == 0:
            handle.write("# WATCH_LOG\n\n")
        handle.write("\n".join(lines))
        handle.write("\n")


def _acquire_lock(cache_dir: str) -> Path:
    lock_path = Path(cache_dir) / ".watch_session.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        raise SessionLockError("SESSION_IN_PROGRESS", "A watch session is already running")
    lock_path.write_text("locked", encoding="utf-8")
    return lock_path


def _release_lock(lock_path: Path) -> None:
    if lock_path.exists():
        lock_path.unlink()


def run_watch_session(
    query: str,
    movie: bool,
    season: int | None,
    episode: int | None,
    source_url: str | None,
    tmdb_api_key: str | None,
    watch_log: str,
    cache_dir: str,
    source_timeout_sec: int,
    tmdb_timeout_sec: int,
    max_scene_chars: int,
) -> WatchResult:
    target = _parse_target(query, movie=movie, season=season, episode=episode)
    result = WatchResult(target=target)

    lock_path = _acquire_lock(cache_dir)
    try:
        try:
            source, trace, warnings = fetch_script_text(target, timeout_sec=source_timeout_sec, source_url=source_url)
            result.source = source
            result.fallback_trace.extend(trace)
            result.warnings.extend(warnings)
        except SourceError as exc:
            result.errors.append({"code": exc.code, "message": exc.message})
            return result

        metadata = enrich_from_tmdb(target, tmdb_api_key=tmdb_api_key, timeout_sec=tmdb_timeout_sec)
        result.metadata = metadata
        result.warnings.extend(metadata.warnings)

        scenes, parse_warnings = parse_scenes(
            source.script_text or "",
            runtime_minutes=metadata.runtime_minutes,
            max_scene_chars=max_scene_chars,
        )
        result.warnings.extend(parse_warnings)

        for index, scene in enumerate(scenes):
            reaction = react_to_scene(scene, last_scene=(index == len(scenes) - 1))
            if reaction.surfaced:
                result.surfaced_reactions.append(reaction)

        result.scenes_processed = len(scenes)
        append_watch_log(watch_log, result)
        result.cache["watch_log_path"] = watch_log
        return result
    finally:
        _release_lock(lock_path)


def _model_dump(value):
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        dumped = asdict(value)
        return {key: _model_dump(val) for key, val in dumped.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch one movie or one TV episode from script text")
    parser.add_argument("query", help="Title query, e.g. 'Breaking Bad S01E01' or 'Spirited Away'")
    parser.add_argument("--movie", action="store_true", help="Treat query as movie")
    parser.add_argument("--season", type=int, default=None, help="Season number for TV episodes")
    parser.add_argument("--episode", type=int, default=None, help="Episode number for TV episodes")
    parser.add_argument("--source-url", default=None, help="Optional fallback transcript URL")
    parser.add_argument("--tmdb-api-key", default=None, help="Optional TMDB API key override (else TMDB_API_KEY env)")
    parser.add_argument("--watch-log", default=str(DEFAULT_WATCH_LOG_PATH), help="Path to markdown watch log")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Path to cache/lock directory")
    parser.add_argument("--source-timeout-sec", type=int, default=15, help="Script source HTTP timeout")
    parser.add_argument("--tmdb-timeout-sec", type=int, default=10, help="TMDB HTTP timeout")
    parser.add_argument("--max-scene-chars", type=int, default=4200, help="Max chars stored per scene")
    args = parser.parse_args()

    result = run_watch_session(
        query=args.query,
        movie=args.movie,
        season=args.season,
        episode=args.episode,
        source_url=args.source_url,
        tmdb_api_key=args.tmdb_api_key,
        watch_log=args.watch_log,
        cache_dir=args.cache_dir,
        source_timeout_sec=args.source_timeout_sec,
        tmdb_timeout_sec=args.tmdb_timeout_sec,
        max_scene_chars=args.max_scene_chars,
    )
    print(json.dumps(_model_dump(result), indent=2))


if __name__ == "__main__":
    main()
