"""Network shares: the argument list handed to `mount`.

`mount` and `umount` are never run; see FakeSubprocess in conftest.py. Mount
points and the SMB credentials directory are temp folders.
"""

import os
import stat


def make_share(backend, **overrides):
    values = dict(
        id=7,
        name="NAS",
        type="nfs",
        remote="nas.example.invalid:/export/media",
        mount_point=str(backend.tmp_path / "mnt" / "media"),
        username=None,
        password=None,
        domain=None,
        options=None,
        auto_mount=0,
    )
    values.update(overrides)
    return backend.database.ShareModel(**values)


def test_nfs_mount_args(backend):
    share = make_share(backend)

    args = backend.share_manager._build_mount_args(share)

    assert args == [
        "mount", "-t", "nfs",
        "nas.example.invalid:/export/media", share.mount_point,
        "-o", "rw,soft,timeo=30",
    ]
    assert os.path.isdir(share.mount_point)
    # NFS needs no credentials file.
    assert not backend.creds_dir.exists()


def test_nfs_mount_args_with_custom_options(backend):
    share = make_share(backend, options=" ro,vers=4 ")

    args = backend.share_manager._build_mount_args(share)

    assert args[-2:] == ["-o", "ro,vers=4"]


def test_smb_guest_mount_args(backend):
    share = make_share(backend, type="smb", remote="//nas.example.invalid/media")

    args = backend.share_manager._build_mount_args(share)

    assert args == [
        "mount", "-t", "cifs",
        "//nas.example.invalid/media", share.mount_point,
        "-o", "rw,iocharset=utf8,guest",
    ]
    assert not backend.creds_dir.exists()


def test_smb_mount_args_keep_the_password_out_of_argv(backend):
    share = make_share(
        backend,
        type="smb",
        remote="//nas.example.invalid/media",
        username="alice",
        password="test-only-pass",
        domain="WORKGROUP",
    )

    args = backend.share_manager._build_mount_args(share)

    assert args[:5] == ["mount", "-t", "cifs", "//nas.example.invalid/media", share.mount_point]
    assert args[5] == "-o"
    options = args[6].split(",")
    assert options[:2] == ["rw", "iocharset=utf8"]
    assert "guest" not in options
    assert not any("test-only-pass" in arg for arg in args)

    (creds_option,) = [o for o in options if o.startswith("credentials=")]
    creds_file = creds_option.split("=", 1)[1]
    assert os.path.dirname(creds_file) == str(backend.creds_dir)
    with open(creds_file) as fh:
        assert fh.read() == "username=alice\npassword=test-only-pass\ndomain=WORKGROUP\n"
    assert stat.S_IMODE(os.stat(creds_file).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(backend.creds_dir).st_mode) == 0o700


def test_share_api_hides_password_and_mounts_through_the_fake(client, backend):
    mount_point = str(backend.tmp_path / "mnt" / "nfs")

    created = client.post(
        "/api/shares",
        json={
            "name": "Media",
            "type": "nfs",
            "remote": "nas.example.invalid:/export/media",
            "mount_point": mount_point,
            "password": "test-only-pass",
        },
    )

    assert created.status_code == 200
    share = created.json()
    assert "password" not in share
    assert share["mounted"] is False
    assert "test-only-pass" not in client.get("/api/shares").text
    # Saving a share must not mount it.
    assert backend.subprocess.calls_to("mount") == []

    mounted = client.post(f"/api/shares/{share['id']}/mount")

    assert mounted.status_code == 200
    assert mounted.json() == {"mounted": True, "message": "Mounted"}
    assert backend.subprocess.calls_to("mount") == [
        ["mount", "-t", "nfs", "nas.example.invalid:/export/media", mount_point,
         "-o", "rw,soft,timeo=30"]
    ]


def test_share_api_reports_mount_failure(client, backend):
    backend.subprocess.mount_returncode = 32
    backend.subprocess.mount_output = b"mount.nfs: access denied by server\n"
    share = client.post(
        "/api/shares",
        json={
            "name": "Media",
            "type": "nfs",
            "remote": "nas.example.invalid:/export/media",
            "mount_point": str(backend.tmp_path / "mnt" / "nfs"),
        },
    ).json()

    response = client.post(f"/api/shares/{share['id']}/mount")

    assert response.status_code == 200
    assert response.json() == {"mounted": False, "message": "mount.nfs: access denied by server"}


def test_share_api_rejects_unknown_type_and_unknown_id(client, backend):
    bad_type = client.post(
        "/api/shares",
        json={"name": "x", "type": "sshfs", "remote": "h:/x", "mount_point": "/mnt/x"},
    )

    assert bad_type.status_code == 422
    assert client.get("/api/shares").json() == []
    assert client.post("/api/shares/999/mount").status_code == 404
    assert client.post("/api/shares/999/unmount").status_code == 404
    assert client.delete("/api/shares/999").status_code == 404
    assert backend.subprocess.calls == []
