"""share_manager._build_mount_args (never runs mount)."""

import os
import stat

from models.database import ShareModel
from services import share_manager


def _share(tmp_path, **kw):
    values = dict(
        id=7,
        name="s",
        type="nfs",
        remote="nas:/export/media",
        mount_point=str(tmp_path / "mnt"),
        username=None,
        password=None,
        domain=None,
        options=None,
        auto_mount=0,
    )
    values.update(kw)
    return ShareModel(**values)


def test_nfs_default_options(tmp_path):
    share = _share(tmp_path)
    args = share_manager._build_mount_args(share)
    assert args == [
        "mount", "-t", "nfs", "nas:/export/media", share.mount_point,
        "-o", "rw,soft,timeo=30",
    ]
    assert os.path.isdir(share.mount_point)


def test_nfs_custom_options(tmp_path):
    args = share_manager._build_mount_args(_share(tmp_path, options="ro,vers=4"))
    assert args[-2:] == ["-o", "ro,vers=4"]


def test_smb_with_username_uses_0600_credentials_file(tmp_path):
    share = _share(
        tmp_path, type="smb", remote="//nas/media",
        username="alice", password="pw", domain="HOME", options="vers=3.0",
    )
    args = share_manager._build_mount_args(share)
    assert args[:5] == ["mount", "-t", "cifs", "//nas/media", share.mount_point]
    opts = args[6].split(",")
    assert opts[:2] == ["rw", "iocharset=utf8"]
    assert opts[-1] == "vers=3.0"
    cred_opts = [o for o in opts if o.startswith("credentials=")]
    assert len(cred_opts) == 1
    path = cred_opts[0].split("=", 1)[1]
    assert path.startswith(share_manager._CREDS_DIR)
    assert str(tmp_path) in path
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(share_manager._CREDS_DIR).st_mode) == 0o700
    with open(path) as fh:
        assert fh.read() == "username=alice\npassword=pw\ndomain=HOME\n"
    assert "guest" not in opts
    # the password never appears on the command line
    assert "pw" not in " ".join(args)


def test_smb_without_username_is_guest(tmp_path):
    share = _share(tmp_path, type="smb", remote="//nas/media")
    args = share_manager._build_mount_args(share)
    opts = args[6].split(",")
    assert "guest" in opts
    assert not any(o.startswith("credentials=") for o in opts)
    assert not os.path.exists(share_manager._CREDS_DIR)
