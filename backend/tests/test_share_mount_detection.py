"""Tests for share mount detection with special characters in mount paths."""

import builtins
import io
import re
from unittest.mock import patch

import pytest

# We need to test the is_mounted function from share_manager
from backend.services.share_manager import is_mounted


class TestIsMounted:
    """Tests for is_mounted function with escaped paths."""

    # Fake /proc/mounts content with escaped special characters
    FAKE_PROC_MOUNTS = (
        "nas:/music /mnt/shares/My\\040Music nfs rw 0 0\n"
        "nas:/v /mnt/shares/video nfs rw 0 0\n"
    )

    # Additional test case for backslash escape
    FAKE_PROC_MOUNTS_BACKSLASH = (
        "nas:/data /mnt/shares/a\\134b nfs rw 0 0\n"
    )

    def _mock_open(self, path, *args, **kwargs):
        """Mock open that returns fake /proc/mounts for /proc/mounts path."""
        if path == "/proc/mounts":
            return io.StringIO(self.fake_mounts)
        return builtins.open(path, *args, **kwargs)

    def test_is_mounted_with_space_in_path(self):
        """Test is_mounted correctly handles space (\\040) in mount path."""
        self.fake_mounts = self.FAKE_PROC_MOUNTS
        with patch("builtins.open", side_effect=self._mock_open):
            # Space in path should match escaped \\040
            assert is_mounted("/mnt/shares/My Music") is True
            # Normal path without special chars should still work
            assert is_mounted("/mnt/shares/video") is True
            # Non-existent path should return False
            assert is_mounted("/mnt/shares/other") is False

    def test_is_mounted_with_tab_in_path(self):
        """Test is_mounted correctly handles tab (\\011) in mount path."""
        self.fake_mounts = "nas:/tab /mnt/shares/My\\011Tab nfs rw 0 0\n"
        with patch("builtins.open", side_effect=self._mock_open):
            assert is_mounted("/mnt/shares/My\tTab") is True

    def test_is_mounted_with_newline_in_path(self):
        """Test is_mounted correctly handles newline (\\012) in mount path."""
        self.fake_mounts = "nas:/nl /mnt/shares/My\\012NL nfs rw 0 0\n"
        with patch("builtins.open", side_effect=self._mock_open):
            assert is_mounted("/mnt/shares/My\nNL") is True

    def test_is_mounted_with_backslash_in_path(self):
        """Test is_mounted correctly handles backslash (\\134) in mount path."""
        self.fake_mounts = self.FAKE_PROC_MOUNTS_BACKSLASH
        with patch("builtins.open", side_effect=self._mock_open):
            # Single backslash in real path should match escaped \\134
            assert is_mounted(r"/mnt/shares/a\b") is True

    def test_is_mounted_proc_mounts_not_found(self):
        """Test is_mounted returns False when /proc/mounts doesn't exist."""
        def mock_open_not_found(path, *args, **kwargs):
            if path == "/proc/mounts":
                raise FileNotFoundError
            return builtins.open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_not_found):
            assert is_mounted("/mnt/shares/anything") is False

    def test_decode_octal_escapes(self):
        """Test the octal escape decoding regex works correctly."""
        # This tests the decoding logic directly
        test_cases = [
            ("/mnt/shares/My\\040Music", "/mnt/shares/My Music"),
            ("/mnt/shares/My\\011Tab", "/mnt/shares/My\tTab"),
            ("/mnt/shares/My\\012NL", "/mnt/shares/My\nNL"),
            ("/mnt/shares/a\\134b", r"/mnt/shares/a\b"),
            # Multiple escapes in one path
            ("/mnt/path\\040with\\011\\134slash", "/mnt/path with\t\\slash"),
        ]
        for escaped, expected in test_cases:
            decoded = re.sub(
                r"\\([0-7]{3})",
                lambda m: chr(int(m.group(1), 8)),
                escaped
            )
            assert decoded == expected, f"Failed for {escaped}: got {decoded!r}, expected {expected!r}"