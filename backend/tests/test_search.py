import pytest

from services.search import iso_date, normalize_channel, parse_flat_entries, search_args


class TestSearchArgs:
    def test_query_mode(self):
        args = search_args("yt-dlp", [], query="cats", limit=5)
        assert args == [
            "yt-dlp",
            "--dump-single-json",
            "--flat-playlist",
            "--no-warnings",
            "ytsearch5:cats",
        ]
        assert "--playlist-end" not in args

    def test_query_mode_with_cookies(self):
        args = search_args("yt-dlp", ["--cookies", "/data/cookies.txt"], query="cats", limit=3)
        assert args == [
            "yt-dlp",
            "--dump-single-json",
            "--flat-playlist",
            "--no-warnings",
            "--cookies",
            "/data/cookies.txt",
            "ytsearch3:cats",
        ]

    def test_channel_mode_appends_videos_tab(self):
        args = search_args(
            "yt-dlp", [], channel_url="https://www.youtube.com/@GarandThumb", limit=5
        )
        assert args[-1] == "https://www.youtube.com/@GarandThumb/videos"
        assert "--playlist-end" in args
        assert args[args.index("--playlist-end") + 1] == "5"

    def test_channel_mode_does_not_double_append_videos(self):
        args = search_args(
            "yt-dlp", [], channel_url="https://www.youtube.com/@GarandThumb/videos", limit=5
        )
        assert args[-1] == "https://www.youtube.com/@GarandThumb/videos"
        assert args[-1].count("/videos") == 1

    def test_channel_mode_strips_trailing_slash_before_appending(self):
        args = search_args(
            "yt-dlp", [], channel_url="https://www.youtube.com/@GarandThumb/", limit=5
        )
        assert args[-1] == "https://www.youtube.com/@GarandThumb/videos"

    def test_channel_mode_has_playlist_end_only_for_channels(self):
        query_args = search_args("yt-dlp", [], query="cats", limit=5)
        channel_args = search_args(
            "yt-dlp", [], channel_url="https://www.youtube.com/@GarandThumb", limit=5
        )
        assert "--playlist-end" not in query_args
        assert "--playlist-end" in channel_args


class TestParseFlatEntries:
    def test_skips_entries_without_id(self):
        raw = {"entries": [{"title": "no id here"}, {"id": "abc123", "title": "has id"}]}
        rows = parse_flat_entries(raw)
        assert len(rows) == 1
        assert rows[0]["id"] == "abc123"

    def test_missing_entries_key(self):
        assert parse_flat_entries({}) == []

    def test_url_fallback_built_from_id(self):
        raw = {"entries": [{"id": "abc123", "title": "t"}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["url"] == "https://www.youtube.com/watch?v=abc123"

    def test_url_kept_when_already_http(self):
        raw = {
            "entries": [
                {"id": "abc123", "url": "https://youtu.be/abc123", "title": "t"}
            ]
        }
        rows = parse_flat_entries(raw)
        assert rows[0]["url"] == "https://youtu.be/abc123"

    def test_url_fallback_when_url_is_not_http(self):
        # --flat-playlist sometimes puts the bare id in "url"
        raw = {"entries": [{"id": "abc123", "url": "abc123", "title": "t"}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["url"] == "https://www.youtube.com/watch?v=abc123"

    def test_uploader_fallback_to_channel(self):
        raw = {"entries": [{"id": "abc123", "channel": "Some Channel"}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["uploader"] == "Some Channel"

    def test_uploader_prefers_uploader_field(self):
        raw = {
            "entries": [
                {"id": "abc123", "uploader": "Uploader Name", "channel": "Channel Name"}
            ]
        }
        rows = parse_flat_entries(raw)
        assert rows[0]["uploader"] == "Uploader Name"

    def test_channel_url_fallback_to_uploader_url(self):
        raw = {"entries": [{"id": "abc123", "uploader_url": "https://x/uploader"}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["channel_url"] == "https://x/uploader"

    def test_channel_url_prefers_channel_url_field(self):
        raw = {
            "entries": [
                {
                    "id": "abc123",
                    "channel_url": "https://x/channel",
                    "uploader_url": "https://x/uploader",
                }
            ]
        }
        rows = parse_flat_entries(raw)
        assert rows[0]["channel_url"] == "https://x/channel"

    def test_upload_date_usually_absent_in_flat_results(self):
        raw = {"entries": [{"id": "abc123"}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["upload_date"] is None

    def test_carries_duration_and_view_count(self):
        raw = {"entries": [{"id": "abc123", "duration": 120, "view_count": 999}]}
        rows = parse_flat_entries(raw)
        assert rows[0]["duration"] == 120
        assert rows[0]["view_count"] == 999


class TestNormalizeChannel:
    def test_handle_with_at(self):
        assert normalize_channel("@GarandThumb") == "https://www.youtube.com/@GarandThumb"

    def test_handle_without_at(self):
        assert normalize_channel("GarandThumb") == "https://www.youtube.com/@GarandThumb"

    def test_full_handle_url(self):
        url = "https://www.youtube.com/@GarandThumb"
        assert normalize_channel(url) == url

    def test_channel_id_url(self):
        url = "https://www.youtube.com/channel/UCabc123"
        assert normalize_channel(url) == url

    def test_legacy_c_url(self):
        url = "https://www.youtube.com/c/SomeChannel"
        assert normalize_channel(url) == url

    def test_legacy_user_url(self):
        url = "https://www.youtube.com/user/SomeUser"
        assert normalize_channel(url) == url

    def test_strips_trailing_slash(self):
        assert normalize_channel("https://www.youtube.com/@GarandThumb/") == (
            "https://www.youtube.com/@GarandThumb"
        )

    def test_rejects_non_youtube_url(self):
        with pytest.raises(ValueError):
            normalize_channel("https://example.com/x")

    def test_rejects_malformed_handle(self):
        with pytest.raises(ValueError):
            normalize_channel("not a handle!")

    @pytest.mark.parametrize(
        "lookalike",
        [
            "https://example.com/?youtube.com",
            "https://notyoutube.com/@x",
            "https://youtube.com.evil.example/@x",
        ],
    )
    def test_rejects_lookalike_hosts(self, lookalike):
        with pytest.raises(ValueError):
            normalize_channel(lookalike)

    def test_accepts_youtube_subdomains(self):
        assert (
            normalize_channel("https://m.youtube.com/@GarandThumb")
            == "https://m.youtube.com/@GarandThumb"
        )
        assert (
            normalize_channel("https://youtube.com/@GarandThumb")
            == "https://youtube.com/@GarandThumb"
        )


class TestIsoDate:
    def test_valid_date(self):
        assert iso_date("20260904") == "2026-09-04"

    def test_none_input(self):
        assert iso_date(None) is None

    def test_empty_string(self):
        assert iso_date("") is None

    def test_malformed_wrong_length(self):
        assert iso_date("2026090") is None
        assert iso_date("202609044") is None

    def test_malformed_non_digit(self):
        assert iso_date("2026090x") is None
