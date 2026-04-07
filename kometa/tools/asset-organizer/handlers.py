"""Asset organizer base protocol and utilities."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import unicodedata
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tmdb_resolver import TmdbResolver

logger = logging.getLogger(__name__)

HASH_SIDECAR = ".poster_source_hash"


def compute_file_hash(path: Path) -> str:
    """Return a SHA-256 hex digest of the file at ``path``."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_hash_sidecar(dest_dir: Path) -> str | None:
    """Return the stored source hash for ``dest_dir``, or None if absent/unreadable."""
    sidecar = dest_dir / HASH_SIDECAR
    try:
        return sidecar.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def write_hash_sidecar(dest_dir: Path, hash_str: str) -> None:
    """Persist ``hash_str`` as the source hash for ``dest_dir``."""
    sidecar = dest_dir / HASH_SIDECAR
    try:
        sidecar.write_text(hash_str + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write hash sidecar %s: %s", sidecar, e)


def _file_hash_sidecar_path(dest_file: Path) -> Path:
    """Return the per-file hash sidecar path for ``dest_file``.

    E.g. ``overlays/Awards/Oscars.png`` → ``overlays/Awards/.Oscars.png.source_hash``
    """
    return dest_file.parent / f".{dest_file.name}.source_hash"


def read_file_hash_sidecar(dest_file: Path) -> str | None:
    """Return the stored source hash for ``dest_file``, or None if absent/unreadable."""
    sidecar = _file_hash_sidecar_path(dest_file)
    try:
        return sidecar.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def write_file_hash_sidecar(dest_file: Path, hash_str: str) -> None:
    """Persist ``hash_str`` as the source hash for ``dest_file``."""
    sidecar = _file_hash_sidecar_path(dest_file)
    try:
        sidecar.write_text(hash_str + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write file hash sidecar %s: %s", sidecar, e)


# Plex / Kometa reject custom posters larger than this (see plex.py "Image too large" in Kometa).
PLEX_POSTER_MAX_BYTES = 10_480_000


def effective_max_poster_bytes() -> int:
    """Upper bound for poster.png size; override with env ASSET_MAX_POSTER_BYTES."""
    return int(os.getenv("ASSET_MAX_POSTER_BYTES", str(PLEX_POSTER_MAX_BYTES)))


class Organizer(ABC):
    """Base class for asset organizers."""

    # Category tracking: (processed_count, [errors_list])
    ASSET_CATEGORIES = {
        "Companies": (0, []),
        "Genres": (0, []),
        "Movies_Shows": (0, []),
        "People": (0, []),
    }

    def __init__(
        self,
        source_dir: Path,
        target_dir: Path,
        exception_file: Path,
        force_png: bool,
        dry_run: bool,
        incremental: bool = False,
        tmdb_resolver: TmdbResolver | None = None,
    ) -> None:
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.force_png = force_png
        self.dry_run = dry_run
        self.incremental = incremental
        self.tmdb_resolver = tmdb_resolver

        if exception_file.exists():
            try:
                with open(exception_file, "r") as f:
                    self.exception_mappings = json.load(f)
            except Exception as e:
                msg = f"Failed to load exception mappings {exception_file}: {e}"
                logger.warning(msg)
                self.exception_mappings = {}
        else:
            logger.debug("Exception mappings file not found: %s", exception_file)
            self.exception_mappings = {}

        # Initialize tracking
        for category in self.ASSET_CATEGORIES:
            self.ASSET_CATEGORIES[category] = (0, [])

    def _iter_image_files(self, folder_path: Path):
        """Iterate over image files in folder."""
        for item in sorted(folder_path.iterdir()):
            if not item.is_file() or item.name.startswith("."):
                continue
            yield item

    def _ensure_target_dir(self, dir_path: Path) -> None:
        """Create target directory if it doesn't exist (respects dry_run)."""
        if not dir_path.exists():
            if self.dry_run:
                logger.debug("DRY-RUN: would create directory %s", dir_path)
            else:
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.debug("created directory %s", dir_path)

    def clear_existing(self, dir_path: Path, clear: str) -> None:
        """Remove existing files matching pattern."""
        try:
            for p in sorted(dir_path.glob(clear)):
                if p.exists():
                    if self.dry_run:
                        logger.info(
                            "DRY-RUN: would remove existing %s",
                            p.relative_to(self.target_dir),
                        )
                    else:
                        try:
                            p.unlink()
                            logger.debug(
                                "removed existing %s", p.relative_to(self.target_dir)
                            )
                        except Exception as e:
                            logger.error("Error removing %s: %s", p.name, e)
        except Exception as e:
            logger.error("Error scanning for existing files in %s: %s", dir_path, e)

    def save_as_png(self, src: Path, dest: Path) -> bool:
        """Convert image to PNG and save."""
        if self.dry_run:
            logger.info(
                "DRY-RUN: would convert %s -> %s",
                src.name,
                dest.relative_to(self.target_dir),
            )
            return True

        if self.force_png:
            try:
                from PIL import Image  # local import to avoid global import sort issues

                with Image.open(src) as img:
                    if img.mode in ("RGBA", "LA") or (
                        img.mode == "P" and "transparency" in img.info
                    ):
                        out = img.convert("RGBA")
                    else:
                        out = img.convert("RGB")
                save_png_under_plex_limit(out, dest, max_bytes=effective_max_poster_bytes())
                logger.debug("saved PNG %s (%d bytes)", dest, dest.stat().st_size)
                return True
            except Exception as e:
                logger.error("Error converting %s to PNG: %s", src.name, e)
                return False
        else:
            logger.warning("Copying %s without conversion", src.name)
            try:
                shutil.copy2(src, dest)
                return True
            except Exception as e:
                logger.error("Error copying %s: %s", src.name, e)
                return False

    def process_file(self, src: Path, dest: Path) -> bool:
        """Process and save file (copy or convert)."""
        if self.force_png:
            return self.save_as_png(src, dest)
        else:
            if self.dry_run:
                logger.info(
                    "DRY-RUN: would copy %s -> %s",
                    src.name,
                    dest.relative_to(self.target_dir),
                )
                return True
            try:
                shutil.copy2(src, dest)
                logger.debug("copied %s", dest)
                return True
            except Exception as e:
                logger.error("Error copying %s: %s", src.name, e)
                return False

    def update_category_tracking(
        self, category: str, processed: int = 0, error: str | None = None
    ) -> None:
        """Update category tracking with processed count and/or error."""
        if category not in self.ASSET_CATEGORIES:
            return

        count, errs = self.ASSET_CATEGORIES[category]
        if processed > 0:
            count += processed
        if error:
            errs.append(error)
        self.ASSET_CATEGORIES[category] = (count, errs)

    def normalize_name(self, name: str) -> str:
        """Normalize asset names to match expected naming conventions.

        Lookup order:
          1. ``exception_mappings.json`` — manual/auto-written overrides (fastest).
          2. Standard rules — colon→dash, asterisk→dash, double-space→&, unicode.
          3. TMDb API — last resort, only when a year is present in *name* and
             ``TMDB_API_KEY`` is set.  Results are cached and written back to
             ``exception_mappings.json`` so subsequent runs skip the network call.
        """
        import re

        # 1. Exception mappings (exact key match)
        mapped = self.exception_mappings.get(name)
        if mapped:
            return mapped

        # 2. Standard normalization rules
        result = unicodedata.normalize("NFKC", name).strip()
        result = (
            result.replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u00a0", " ")
            .replace("\u00b7", "")
        )
        # Colon between digits → plain dash (e.g. "4:30" → "4-30")
        result = re.sub(r"(\d):(\d)", r"\1-\2", result)
        # Remaining colons → " -" (e.g. "Foo: Bar" → "Foo - Bar")
        result = result.replace(":", " -")
        # "word- word" → "word - word" (e.g. "Rogue One- A Star Wars Story")
        # Must run before asterisk substitution to avoid "Foo -" becoming "Foo  -"
        result = re.sub(r"(\w)- ", r"\1 - ", result)
        # Asterisks → "-" (e.g. "Thunderbolts*" → "Thunderbolts-")
        result = result.replace("*", "-")
        # Double space → " & " (e.g. "Lilo  Stitch" → "Lilo & Stitch")
        result = re.sub(r"  +", " & ", result)
        result = re.sub(r"\s+", " ", result).strip()

        # 3. TMDb last-resort (only for "Title (YYYY)" items, only when resolver active)
        if self.tmdb_resolver is not None and re.search(r"\(\d{4}\)", name):
            tmdb_result = self.tmdb_resolver.resolve(name)
            if tmdb_result:
                # Reload mappings so this run benefits from the write-back too
                self.exception_mappings[name] = tmdb_result
                return tmdb_result

        return result

    def get_category_summary(self, category: str) -> tuple[int, list[str]]:
        """Get (processed_count, [errors_list]) for a category."""
        return self.ASSET_CATEGORIES.get(category, (0, []))

    def log_category_summary(self, category: str) -> bool:
        """Log summary for a category. Returns True if no errors."""
        processed_count, errors = self.get_category_summary(category)
        logger.info(
            "Summary: Category=%s Processed=%d Errors=%d",
            category,
            processed_count,
            len(errors),
        )
        if errors:
            for err in errors:
                logger.error("  - %s", err)
        return len(errors) == 0

    @abstractmethod
    def organize(self, category: str) -> bool:
        """Organize assets for category."""
        ...

    @abstractmethod
    def process_companies(self, source_dir: Path) -> None:
        """Process company assets."""
        ...

    @abstractmethod
    def process_people(self, source_dir: Path) -> None:
        """Process people assets."""
        ...

    @abstractmethod
    def process_genres(self, source_dir: Path) -> None:
        """Process genre assets."""
        ...

    @abstractmethod
    def process_movies_and_shows(self, source_dir: Path) -> None:
        """Process movie and show assets."""
        ...


def _encode_png(img: "Image.Image", *, optimize: bool = True, compress_level: int = 9) -> bytes:
    """Serialize a PIL image to PNG bytes."""
    buf = BytesIO()
    img.save(
        buf,
        format="PNG",
        optimize=optimize,
        compress_level=compress_level,
    )
    return buf.getvalue()


def save_png_under_plex_limit(
    img: "Image.Image",
    dest: Path,
    *,
    max_bytes: int | None = None,
) -> None:
    """Write PNG to ``dest``, scaling down if needed so file size is under ``max_bytes``."""
    from PIL import Image

    if max_bytes is None:
        max_bytes = effective_max_poster_bytes()

    data = _encode_png(img)
    if len(data) <= max_bytes:
        dest.write_bytes(data)
        return

    scale = 0.92
    current = img
    while scale >= 0.3:
        w, h = current.size
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        current = current.resize((nw, nh), Image.Resampling.LANCZOS)
        data = _encode_png(current)
        if len(data) <= max_bytes:
            dest.write_bytes(data)
            logger.info(
                "Poster scaled to %dx%d (%s bytes) to stay under Plex limit: %s",
                nw,
                nh,
                f"{len(data):,}",
                dest,
            )
            return
        scale -= 0.04

    dest.write_bytes(data)
    logger.warning(
        "Could not shrink poster under %s bytes (final %s): %s",
        f"{max_bytes:,}",
        f"{len(data):,}",
        dest,
    )


def shrink_poster_file_if_needed(
    path: Path,
    *,
    max_bytes: int | None = None,
    dry_run: bool = False,
) -> bool:
    """If ``path`` is larger than ``max_bytes``, re-encode and optionally scale down. Returns True if changed."""
    if max_bytes is None:
        max_bytes = effective_max_poster_bytes()
    try:
        if not path.is_file() or path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False

    if dry_run:
        logger.info(
            "DRY-RUN: would shrink %s (%d bytes)",
            path,
            path.stat().st_size,
        )
        return True

    try:
        from PIL import Image

        with Image.open(path) as img:
            if img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            ):
                out = img.convert("RGBA")
            else:
                out = img.convert("RGB")
        save_png_under_plex_limit(out, path, max_bytes=max_bytes)
        return True
    except Exception as e:
        logger.error("Failed to shrink %s: %s", path, e)
        return False


def shrink_all_posters_under_limit(
    root: Path,
    *,
    max_bytes: int | None = None,
    dry_run: bool = False,
    pattern: str = "poster.png",
) -> int:
    """Walk ``root`` for ``**/pattern`` and shrink any file over ``max_bytes``. Returns count shrunk."""
    if max_bytes is None:
        max_bytes = effective_max_poster_bytes()
    count = 0
    if not root.is_dir():
        logger.warning("Not a directory: %s", root)
        return 0
    for path in sorted(root.rglob(pattern)):
        if shrink_poster_file_if_needed(path, max_bytes=max_bytes, dry_run=dry_run):
            count += 1
    return count
