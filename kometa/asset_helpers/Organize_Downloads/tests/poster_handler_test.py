from pathlib import Path

from poster_handler import PosterOrganizer


def make_organizer(tmp_path: Path, **kwargs) -> PosterOrganizer:
    source = tmp_path / "source"
    target = tmp_path / "target"
    exception_file = tmp_path / "exceptions.json"
    exception_file.write_text("{}", encoding="utf-8")
    return PosterOrganizer(
        source, target, exception_file, force_png=True, dry_run=True, **kwargs
    )


def test_is_collection_poster_exact_match(tmp_path):
    organizer = make_organizer(tmp_path)

    assert organizer._is_collection_poster("Blue Sky Studios", "Blue Sky Studios")


def test_is_collection_poster_matches_collection_suffix_pair(tmp_path):
    organizer = make_organizer(tmp_path)

    assert organizer._is_collection_poster("Atlantis Collection", "Atlantis Collection")
    assert organizer._is_collection_poster("Atlantis", "Atlantis Collection")


def test_is_collection_poster_does_not_match_other_collection_name(tmp_path):
    organizer = make_organizer(tmp_path)

    assert not organizer._is_collection_poster("Rio Collection", "Blue Sky Studios")


def test_normalize_kometa_collection_folder_name_strips_franchise_suffix(tmp_path):
    organizer = make_organizer(tmp_path)

    assert organizer.normalize_kometa_collection_folder_name("Cars Collection") == "Cars"
    assert (
        organizer.normalize_kometa_collection_folder_name(
            "Pirates of the Caribbean Collection"
        )
        == "Pirates of the Caribbean"
    )


def test_normalize_kometa_collection_folder_name_preserves_when_suffix_disabled(
    tmp_path,
):
    organizer = make_organizer(tmp_path, strip_collection_suffix=False)

    assert (
        organizer.normalize_kometa_collection_folder_name("Cars Collection")
        == "Cars Collection"
    )


def test_normalize_kometa_collection_folder_name_movie_titles_untouched(tmp_path):
    organizer = make_organizer(tmp_path)

    assert (
        organizer.normalize_kometa_collection_folder_name("Cars (2006)")
        == "Cars (2006)"
    )
