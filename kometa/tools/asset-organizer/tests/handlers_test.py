from pathlib import Path

from handlers import Organizer


class DummyOrganizer(Organizer):
    """Test implementation of Organizer."""

    def organize(self, category: str) -> bool:
        return True

    def process_companies(self, source_dir: Path) -> None:
        pass

    def process_people(self, source_dir: Path) -> None:
        pass

    def process_genres(self, source_dir: Path) -> None:
        pass

    def process_movies_and_shows(self, source_dir: Path) -> None:
        pass


def test_organizer_init(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    exception_file = tmp_path / "exceptions.json"
    exception_file.write_text("{}")
    org = DummyOrganizer(source, target, exception_file, force_png=True, dry_run=False)
    assert org.source_dir == source
    assert org.target_dir == target
    assert org.force_png is True
    assert org.dry_run is False
    assert isinstance(org.exception_mappings, dict)


def test_organizer_categories():
    assert set(Organizer.ASSET_CATEGORIES.keys()) == {
        "Companies",
        "Genres",
        "Movies_Shows",
        "People",
    }


def test_normalize_name_colon_and_dash(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    exception_file = tmp_path / "exceptions.json"
    exception_file.write_text("{}")
    org = DummyOrganizer(source, target, exception_file, force_png=True, dry_run=False)

    assert org.normalize_name("The 4:30 Movie") == "The 4-30 Movie"
    assert org.normalize_name("Kill Bill: Vol. 1") == "Kill Bill - Vol. 1"


def test_normalize_name_unicode_and_symbols(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    exception_file = tmp_path / "exceptions.json"
    exception_file.write_text("{}")
    org = DummyOrganizer(source, target, exception_file, force_png=True, dry_run=False)

    assert org.normalize_name("Thunderbolts*") == "Thunderbolts-"
    assert org.normalize_name("WALL·E") == "WALLE"
    assert org.normalize_name("Lilo  Stitch") == "Lilo & Stitch"


def test_normalize_name_uses_exception_mapping(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    exception_file = tmp_path / "exceptions.json"
    exception_file.write_text('{"Custom Name": "Mapped Name"}')
    org = DummyOrganizer(source, target, exception_file, force_png=True, dry_run=False)

    assert org.normalize_name("Custom Name") == "Mapped Name"
