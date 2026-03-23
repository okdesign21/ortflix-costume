"""Poster organization handler for Kometa.

This module contains the PosterOrganizer class that processes poster images
from various folder structures and organizes them into Kometa's expected
layout.
"""

import importlib.util
import logging
import re
from pathlib import Path

from handlers import Organizer

# Detect if Pillow is available without importing it (avoid unused import warnings)
HAS_PIL = importlib.util.find_spec("PIL") is not None

logger = logging.getLogger(__name__)


class PosterOrganizer(Organizer):
    """Organizes downloaded poster images into Kometa-compatible structure."""

    # Regex patterns for people name normalization
    ROLE_PATTERN = r"(directing|writing|acting|producing)"
    # Matches: (Role), - Role, Role at end
    ROLE_REGEX = re.compile(
        r"\s*(?:\(|[-–—]\s*|\b)" + ROLE_PATTERN + r"(?:\)|\s*)?\s*$", re.IGNORECASE
    )

    # Collection poster identification patterns
    COLLECTION_SUFFIXES = (" Collection", "Collection")

    def __init__(
        self,
        source_dir: Path,
        target_dir: Path,
        exception_file: Path,
        force_png: bool,
        dry_run: bool,
    ) -> None:
        """Initialize PosterOrganizer."""
        super().__init__(source_dir, target_dir, exception_file, force_png, dry_run)

    # --- Naming helpers (poster-specific) ------------------------------------------
    def normalize_people_name(self, stem: str) -> str:
        """Return the person's name with role in parentheses when present."""
        s = stem.strip()
        if re.search(r"\(.*\)", s):
            return self.normalize_name(s)
        m = re.search(self.ROLE_REGEX, s)
        if m:
            name = s[: m.start()].strip()
            role = m.group(1).capitalize()
            return self.normalize_name(f"{name} ({role})")
        return self.normalize_name(s)

    def extract_people_name(self, stem: str) -> str:
        """Return the person's name without any role suffix (Directing/Writing/Acting)."""
        s = stem.strip()
        s = re.sub(self.ROLE_REGEX, "", s)
        return self.normalize_name(s.strip())

    def extract_collection_name(self, folder_name: str) -> str:
        """Extract a clean collection name from dated/suffixed folders.

        Removes trailing dates (YYYY-MM-DD) and "set by Creator" suffix.
        """
        name = re.sub(r"\s*-\s*\d{4}-\d{2}-\d{2}$", "", folder_name)
        name = re.sub(r"\s+set by\s+[\w\-]+$", "", name, flags=re.IGNORECASE)
        return name.strip()

    # --- Filesystem helpers --------------------------------------------------------
    def get_target_poster_path(self, dir_path: Path, src: Path) -> Path:
        """Return the target poster path.

        If Pillow is available, normalize to ``poster.png``; otherwise
        preserve the original file extension.
        """
        if HAS_PIL:
            return dir_path / "poster.png"
        return dir_path / f"poster{src.suffix.lower()}"

    def clear_existing(self, dir_path: Path) -> None:
        """Clear existing poster files."""
        super().clear_existing(dir_path, "poster.*")

    def _is_collection_poster(self, filename: str, collection_name: str) -> bool:
        """Check if filename is the current collection's own poster.

        Avoid broad matching of any ``* Collection`` filename, which can
        incorrectly overwrite the parent collection poster when a studio folder
        contains multiple sub-collection posters (e.g. "Rio Collection" inside
        "Blue Sky Studios").
        """
        if filename == collection_name:
            return True

        filename_base = re.sub(r"\s+Collection$", "", filename, flags=re.IGNORECASE)
        collection_base = re.sub(
            r"\s+Collection$", "", collection_name, flags=re.IGNORECASE
        )

        return filename_base == collection_base and (
            filename.endswith(" Collection") or collection_name.endswith(" Collection")
        )

    def process_poster(
        self, src: Path, dest_dir: Path, category: str, collection: bool = False
    ) -> bool:
        """Process a single poster file."""
        self._ensure_target_dir(dest_dir)
        self.clear_existing(dest_dir)

        target_path = self.get_target_poster_path(dest_dir, src)

        if self.dry_run:
            logger.info(
                "DRY-RUN: %s/%s %s",
                dest_dir.name,
                target_path.name,
                "(collection poster)" if collection else "",
            )
            return True

        ok = self.save_as_png(src, target_path)
        if ok:
            self.update_category_tracking(category, processed=1)
            logger.info("Processed poster: %s -> %s", src.name, target_path)
            return True
        return False

    def _process_images_to_subfolders(
        self,
        folder_path: Path,
        target_base: Path,
        name_mapper,
        category: str,
    ) -> None:
        """Process images from folder into subfolders."""
        super()._ensure_target_dir(target_base)

        for item in self._iter_image_files(folder_path):
            item_name = name_mapper(item.stem)
            dest_dir = target_base / item_name
            self.process_poster(item, dest_dir, category)

    def process_collection_folder(
        self, folder_path: Path, target_base: Path, category: str
    ) -> None:
        collection_name = self.normalize_name(
            self.extract_collection_name(folder_path.name)
        )
        if not collection_name:
            logger.warning(
                "Could not extract collection name from %s", folder_path.name
            )
            return

        collection_dir = target_base / collection_name
        super()._ensure_target_dir(collection_dir)

        logger.info("Processing collection: %s", collection_name)

        try:
            for item in self._iter_image_files(folder_path):
                fname = item.stem
                norm_stem = self.normalize_name(fname)

                if self._is_collection_poster(norm_stem, collection_name):
                    self.process_poster(item, collection_dir, category, collection=True)
                else:
                    item_name = self.normalize_name(fname)
                    item_dir = target_base / item_name
                    self.process_poster(item, item_dir, category)
        except Exception as e:
            logger.error("Error reading folder %s: %s", folder_path.name, e)
            self.update_category_tracking(category, error=str(e))

    # --- Public folder processors ---------------------------------------------------
    def _process_folder_with_error_handling(
        self, folder_path: Path, target_subfolder: str, name_mapper, category: str
    ) -> None:
        """Generic folder processor with error handling."""
        target_base = self.target_dir / target_subfolder
        super()._ensure_target_dir(target_base)
        logger.info("Processing %s folder", target_subfolder)

        try:
            self._process_images_to_subfolders(
                folder_path, target_base, name_mapper, category
            )
        except Exception as e:
            logger.error("Error reading folder %s: %s", folder_path.name, e)
            self.update_category_tracking(category, error=str(e))

    def process_generic_image_folder(
        self, folder_path: Path, asset_subfolder: str, category: str
    ) -> None:
        self._process_folder_with_error_handling(
            folder_path, asset_subfolder, self.normalize_name, category
        )

    def process_people_folder(self, folder_path: Path, category: str) -> None:
        self._process_folder_with_error_handling(
            folder_path, "People", self.extract_people_name, category
        )

    def process_movies_and_shows_folder(self, folder_path: Path, category: str) -> None:
        target_base = self.target_dir / "Movies_Shows"
        super()._ensure_target_dir(target_base)
        logger.info("Processing Movies and Shows folder")

        try:
            # First process any sub-collections
            for item in sorted(folder_path.iterdir()):
                if item.is_dir():
                    self.process_collection_folder(item, target_base, category)

            # Then process any top-level poster files
            self._process_images_to_subfolders(
                folder_path, target_base, self.normalize_name, category
            )
        except Exception as e:
            logger.error(
                "Error reading Movies and Shows folder %s: %s", folder_path.name, e
            )
            self.update_category_tracking(category, error=str(e))

    def process_folder(self, folder_path: Path, category: str | None = None) -> None:
        """Process a single folder (helper method)."""
        if category is None:
            return None  # cannot process without category
        self.process_collection_folder(folder_path, self.target_dir, category)

    def process_file(self, file_path: Path, category: str | None = None) -> None:
        """Process a single file (helper method)."""
        if category is None:
            return None  # cannot process without category
        item_name = self.normalize_name(file_path.stem)
        item_dir = self.target_dir / item_name
        self.process_poster(file_path, item_dir, category)

    # --- Category processors (abstract method implementations) ---------------------
    def _process_category_if_exists(
        self, source_dir: Path, processor_method, category: str
    ) -> None:
        """Process category folder if it exists."""
        if not source_dir.exists():
            logger.warning("%s folder not found: %s", category, source_dir)
            return
        processor_method(source_dir, category)

    def process_companies(self, source_dir: Path) -> None:
        """Process company posters."""
        self._process_category_if_exists(
            source_dir,
            lambda s, c: self.process_generic_image_folder(s, "Companies", c),
            "Companies",
        )

    def process_genres(self, source_dir: Path) -> None:
        """Process genre posters."""
        self._process_category_if_exists(
            source_dir,
            lambda s, c: self.process_generic_image_folder(s, "Genres", c),
            "Genres",
        )

    def process_people(self, source_dir: Path) -> None:
        """Process people posters."""
        self._process_category_if_exists(
            source_dir, self.process_people_folder, "People"
        )

    def process_movies_and_shows(self, source_dir: Path) -> None:
        """Process movie and show posters."""
        self._process_category_if_exists(
            source_dir, self.process_movies_and_shows_folder, "Movies_Shows"
        )

    def validate_dirs(self) -> bool:
        """Validate source and target directories."""
        if not self.source_dir.exists():
            logger.error("Source directory not found: %s", self.source_dir)
            return False
        if not self.source_dir.is_dir():
            logger.error("Source is not a directory: %s", self.source_dir)
            return False
        super()._ensure_target_dir(self.target_dir)
        return True

    def organize(self, category: str) -> bool:
        """Organize assets for given category."""
        if category not in Organizer.ASSET_CATEGORIES:
            logger.error("Unknown category: %s", category)
            return False

        if not self.validate_dirs():
            return False

        logger.info("%sOrganizing assets...", "[DRY RUN] " if self.dry_run else "")

        cat_source = self.source_dir / category

        logger.info("Source: %s", cat_source)
        logger.info("Target: %s", self.target_dir)

        # Route to category-specific handler
        category_handlers = {
            "Companies": self.process_companies,
            "Genres": self.process_genres,
            "People": self.process_people,
            "Movies_Shows": self.process_movies_and_shows,
        }

        handler = category_handlers.get(category)
        if handler:
            logger.info("Processing %s posters", category)
            handler(cat_source)

        return self.log_category_summary(category)
