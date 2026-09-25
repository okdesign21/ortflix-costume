from plex_index import PlexIndex, normalize_key
from matcher import MatchReview, TitleMatcher


def make_index() -> PlexIndex:
    return PlexIndex(
        movies_shows={
            normalize_key("Friends"): "Friends",
            normalize_key("A Bug's Life (1998)"): "A Bug's Life (1998)",
        },
        collections={normalize_key("Cars"): "Cars"},
        people={normalize_key("Tom Hanks"): "Tom Hanks"},
        genres={},
        studios={},
        snapshot_at=1.0,
    )


def test_exception_mapping_always_wins():
    matcher = TitleMatcher(make_index(), exception_mappings={"Weird Name": "Correct Name"})
    result = matcher.match("movies_shows", "Weird Name")
    assert result.canonical == "Correct Name"
    assert result.method == "exception"
    assert result.confidence == 1.0


def test_exact_match_against_plex_index():
    matcher = TitleMatcher(make_index())
    result = matcher.match("movies_shows", "Friends")
    assert result.canonical == "Friends"
    assert result.method == "exact"
    assert result.confidence == 1.0


def test_fuzzy_match_within_cutoff():
    matcher = TitleMatcher(make_index())
    result = matcher.match("movies_shows", "A Bugs Life (1998)")
    assert result.matched
    assert result.canonical == "A Bug's Life (1998)"
    assert result.method == "fuzzy"
    assert 0.86 <= result.confidence < 1.0


def test_no_match_below_cutoff_is_unmatched():
    matcher = TitleMatcher(make_index(), fuzzy_cutoff=0.995)
    result = matcher.match("movies_shows", "A Bugs Life (1998)")
    assert not result.matched
    assert result.method == "unmatched"


def test_multi_category_prefers_exact_over_fuzzy():
    idx = make_index()
    matcher = TitleMatcher(idx)
    # "Cars" is exact in collections; nothing in movies_shows is close.
    result = matcher.match(("collections", "movies_shows"), "Cars")
    assert result.canonical == "Cars"
    assert result.method == "exact"


def test_disabled_when_index_is_none():
    matcher = TitleMatcher(None)
    assert not matcher.enabled
    result = matcher.match("movies_shows", "Friends")
    assert not result.matched
    assert result.method == "unmatched"


def test_disabled_when_index_is_empty():
    matcher = TitleMatcher(PlexIndex())
    assert not matcher.enabled


def test_match_review_only_records_low_confidence():
    review = MatchReview()
    matcher = TitleMatcher(make_index(), review=review)
    matcher.match("movies_shows", "Friends")  # exact -> not recorded
    matcher.match("movies_shows", "A Bugs Life (1998)")  # fuzzy -> recorded
    matcher.match("movies_shows", "Totally Unknown Title (2099)")  # unmatched -> recorded

    assert len(review.entries) == 2
    assert len(review.fuzzy()) == 1
    assert len(review.unmatched()) == 1
    assert review.is_clean() is False


def test_match_review_is_clean_when_no_low_confidence_entries():
    review = MatchReview()
    matcher = TitleMatcher(make_index(), review=review)
    matcher.match("movies_shows", "Friends")
    assert review.is_clean() is True
