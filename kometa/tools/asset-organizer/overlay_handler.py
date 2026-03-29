"""Overlay organization handler for Kometa.

Organizes custom overlay images from a source ``Overlays/`` directory into
Kometa's ``config/overlays/`` directory, preserving the subdirectory structure
so overlays can be referenced by path in Kometa YAML configs.

Source layout (mirrors target structure):

    Overlays/
    ├── SomeOverlay.png          →  config/overlays/SomeOverlay.png
    ├── Awards/
    │   ├── Oscars.png           →  config/overlays/Awards/Oscars.png
    │   └── Emmy Winner.png      →  config/overlays/Awards/Emmy Winner.png
    └── Ratings/
        └── IMDb Top 250.png     →  config/overlays/Ratings/IMDb Top 250.png

File stems are normalized via ``normalize_name`` (same rules as poster handler).
Sub-directory names are also normalized.
"""

import logging
from pathlib import Path

from handlers import (
    Organizer,
    compute_file_hash,
    read_file_hash_sidecar,
    write_file_hash_sidecar,
)

logger = logging.getLogger(__name__)

# Image extensions recognised as overlay files
OVERLAY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class OverlayOrganizer(Organizer):
    """Organizes custom overlay images into Kometa's overlays directory."""

    def __init__(
        self,
        source_dir: Path,
        target_dir: Path,
        exception_file: Path,
        force_png: bool,
        dry_run: bool,
        incremental: bool = False,
    ) -> None:
        super().__init__(
            source_dir, target_dir, exception_file, force_png, dry_run, incremental
        )
        self._processed = 0
        self._skipped = 0
        self._errors: list[str] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_image_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in OVERLAY_EXTENSIONS

    def _dest_filename(self, src: Path) -> str:
        """Return the destination filename for ``src``.

        Normalizes the stem; forces ``.png`` extension when ``force_png`` is set,
        otherwise preserves the original (lowercased) extension.
        """
        stem = self.normalize_name(src.stem)
        ext = ".png" if self.force_png else src.suffix.lower()
        return f"{stem}{ext}"

    def _process_overlay_file(self, src: Path, dest: Path) -> bool:
        """Copy / convert a single overlay file to ``dest``."""
        self._ensure_target_dir(dest.parent)

        if self.incremental and dest.exists():
            src_hash = compute_file_hash(src)
            stored = read_file_hash_sidecar(dest)
            if src_hash == stored:
                logger.debug("Incremental: unchanged overlay, skipping %s", dest.name)
                self._skipped += 1
                return True
            logger.debug(
                "Incremental: overlay changed (hash mismatch), re-processing %s",
                dest.name,
            )

        if self.dry_run:
            logger.info(
                "DRY-RUN: would copy overlay %s -> %s",
                src.name,
                dest.relative_to(self.target_dir),
            )
            return True

        # Re-use base process_file: converts to PNG when force_png, else copies.
        ok = super().process_file(src, dest)
        if ok:
            write_file_hash_sidecar(dest, compute_file_hash(src))
            self._processed += 1
            logger.info(
                "Processed overlay: %s -> %s",
                src.name,
                dest.relative_to(self.target_dir),
            )
        return ok

    def _walk_and_process(self, source: Path, target: Path) -> None:
        """Recursively mirror ``source`` into ``target``, normalizing names."""
        try:
            items = sorted(source.iterdir())
        except OSError as e:
            logger.error("Cannot read overlay source directory %s: %s", source, e)
            self._errors.append(str(e))
            return

        for item in items:
            if item.name.startswith("."):
                continue

            if item.is_dir():
                sub_target = target / self.normalize_name(item.name)
                self._walk_and_process(item, sub_target)

            elif self._is_image_file(item):
                dest = target / self._dest_filename(item)
                if not self._process_overlay_file(item, dest):
                    self._errors.append(str(item))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def organize(self, category: str = "Overlays") -> bool:  # noqa: ARG002
        """Walk source and mirror overlay files into the target directory."""
        self._processed = 0
        self._skipped = 0
        self._errors = []

        if not self.source_dir.exists():
            logger.info(
                "Overlays source not found, skipping (%s)", self.source_dir
            )
            return True

        logger.info(
            "%sOrganizing overlays...", "[DRY RUN] " if self.dry_run else ""
        )
        logger.info("Overlays source: %s", self.source_dir)
        logger.info("Overlays target: %s", self.target_dir)

        self._walk_and_process(self.source_dir, self.target_dir)

        logger.info(
            "Summary: Overlays Processed=%d Skipped=%d Errors=%d",
            self._processed,
            self._skipped,
            len(self._errors),
        )
        for err in self._errors:
            logger.error("  - %s", err)
        return len(self._errors) == 0

    # ------------------------------------------------------------------
    # Abstract method stubs (poster-specific, not applicable for overlays)
    # ------------------------------------------------------------------

    def process_companies(self, source_dir: Path) -> None:
        pass

    def process_people(self, source_dir: Path) -> None:
        pass

    def process_genres(self, source_dir: Path) -> None:
        pass

    def process_movies_and_shows(self, source_dir: Path) -> None:
        pass
