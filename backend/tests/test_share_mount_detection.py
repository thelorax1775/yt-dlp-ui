"""Tests for share mount detection with special characters in mount paths."""

import builtins
import io
from unittest.mock import patch

import pytest


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

    def test_is_mounted_with_space_in_path(self, backend):
        """Test is_mounted correctly handles space (\040) in mount path."""
        fake_mounts = self.FAKE_PROC_MOUNTS
        real_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if path == "/proc/mounts":
                return io.StringIO(fake_mounts)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            # Space in path should match escaped \040
            assert backend.share_manager.is_mounted("/mnt/shares/My Music") is True
            # Normal path without special chars should still work
            assert backend.share_manager.is_mounted("/mnt/shares/video") is True
            # Non-existent path should return False
            assert backend.share_manager.is_mounted("/mnt/shares/other") is False

    def test_is_mounted_with_tab_in_path(self, backend):
        """Test is_mounted correctly handles tab (\011) in mount path."""
        fake_mounts = "nas:/tab /mnt/shares/My\\011Tab nfs rw 0 0\n"
        real_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if path == "/proc/mounts":
                return io.StringIO(fake_mounts)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            assert backend.share_manager.is_mounted("/mnt/shares/My\tTab") is True

    def test_is_mounted_with_newline_in_path(self, backend):
        """Test is_mounted correctly handles newline (\012) in mount path."""
        fake_mounts = "nas:/nl /mnt/shares/My\\012NL nfs rw 0 0\n"
        real_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if path == "/proc/mounts":
                return io.StringIO(fake_mounts)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            assert backend.share_manager.is_mounted("/mnt/shares/My\nNL") is True

    def test_is_mounted_with_backslash_in_path(self, backend):
        """Test is_mounted correctly handles backslash (\134) in mount path."""
        fake_mounts = self.FAKE_PROC_MOUNTS_BACKSLASH
        real_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if path == "/proc/mounts":
                return io.StringIO(fake_mounts)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            # Single backslash in real path should match escaped \134
            assert backend.share_manager.is_mounted(r"/mnt/shares/a\b") is True

    def test_is_mounted_proc_mounts_not_found(self, backend):
        """Test is_mounted returns False when /proc/mounts doesn't exist."""
        real_open = builtins.open

        def mock_open_not_found(path, *args, **kwargs):
            if path == "/proc/mounts":
                raise FileNotFoundError
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_not_found):
            assert backend.share_manager.is_mounted("/mnt/shares/anything") is False

    def test_is_mounted_with_multiple_escapes_in_path(self, backend):
        """Test is_mounted handles multiple escapes in one path."""
        # Path with space, tab, and backslash: /mnt/path with\t\slash
        fake_mounts = "nas:/multi /mnt/path\\040with\\011\\134slash nfs rw 0 0\n"
        real_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if path == "/proc/mounts":
                return io.StringIO(fake_mounts)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            assert backend.share_manager.is_mounted("/mnt/path with\t\\slash") is True