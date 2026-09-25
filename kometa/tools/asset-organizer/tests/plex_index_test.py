from pathlib import Path

from plex_index import PlexIndex, normalize_key


def test_normalize_key_strips_punctuation_and_case():
    assert normalize_key("Kill Bill: Vol. 1") == "kill bill vol 1"
    assert normalize_key("A Bug's Life") == "a bug s life"
    assert normalize_key("  Double   Space ") == "double space"


def test_normalize_key_strips_accents():
    assert normalize_key("Zoe Saldaña") == "zoe saldana"


def test_normalize_key_matches_regardless_of_colon_or_ampersand():
    assert normalize_key("Black Panther: Wakanda Forever (2022)") == normalize_key(
        "Black Panther Wakanda Forever (2022)"
    )


def test_index_roundtrip_json(tmp_path: Path):
    idx = PlexIndex(
        movies_shows={"friends": "Friends"},
        collections={"cars": "Cars"},
        people={"tom hanks": "Tom Hanks"},
        genres={"comedy": "Comedy"},
        studios={"pixar": "Pixar"},
        snapshot_at=123.0,
        libraries=("Films", "TV Programmes"),
    )
    path = tmp_path / "index.json"
    idx.save(path)

    loaded = PlexIndex.load(path)
    assert loaded is not None
    assert loaded.movies_shows == {"friends": "Friends"}
    assert loaded.collections == {"cars": "Cars"}
    assert loaded.people == {"tom hanks": "Tom Hanks"}
    assert loaded.genres == {"comedy": "Comedy"}
    assert loaded.studios == {"pixar": "Pixar"}
    assert loaded.snapshot_at == 123.0
    assert loaded.libraries == ("Films", "TV Programmes")


def test_index_load_missing_file_returns_none(tmp_path: Path):
    assert PlexIndex.load(tmp_path / "missing.json") is None


def test_index_is_empty():
    assert PlexIndex().is_empty()
    assert not PlexIndex(movies_shows={"a": "A"}).is_empty()


def test_index_age_hours_infinite_when_no_snapshot():
    assert PlexIndex().age_hours() == float("inf")
