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


def test_delete_share_keeps_row_when_unmount_fails(client, backend, monkeypatch):
    share = _post(client, backend).json()
    backend.subprocess.mount_returncode = 32
    backend.subprocess.mount_output = b"umount: target is busy"
    monkeypatch.setattr(backend.share_manager, "is_mounted", lambda _mp: True)

    response = client.delete(f"/api/shares/{share['id']}")

    assert response.status_code == 409
    assert "target is busy" in response.json()["detail"]
    assert [row["id"] for row in client.get("/api/shares").json()] == [share["id"]]


def test_duplicate_mount_point_rejected(client, backend):
    mount_point = str(backend.tmp_path / "mnt" / "media")
    first = _post(client, backend, mount_point=mount_point)
    duplicate = _post(client, backend, mount_point=mount_point)
    duplicate_with_slash = _post(client, backend, mount_point=mount_point + "/")
    different = _post(client, backend, mount_point=str(backend.tmp_path / "mnt" / "other"))

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Another share already uses this mount point"
    assert duplicate_with_slash.status_code == 409
    assert different.status_code == 200
    assert len(client.get("/api/shares").json()) == 2


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


# --- unsafe input -----------------------------------------------------------

import pytest


def _post(client, backend, **overrides):
    body = {
        "name": "Media",
        "type": "nfs",
        "remote": "nas.example.invalid:/export/media",
        "mount_point": str(backend.tmp_path / "mnt" / "media"),
    }
    body.update(overrides)
    return client.post("/api/shares", json=body)


@pytest.mark.parametrize(
    "overrides",
    [
        {"remote": "--bind"},
        {"remote": "-o:/x"},
        {"remote": "host:/a b"},
        {"remote": "host:/a\nb"},
        {"remote": "nas.example.invalid"},
        {"type": "smb", "remote": "host:/export"},
        {"type": "smb", "remote": "//host"},
        {"mount_point": "/app/data"},
        {"mount_point": "../x"},
        {"mount_point": "relative/dir"},
        {"mount_point": "/etc"},
        {"mount_point": "BASE/../../etc"},
        {"mount_point": "BASE"},
        {"mount_point": "DATA/inner"},
        {"username": "a\npassword=x"},
        {"username": "a,b"},
        {"password": "p\0w"},
        {"domain": "d\r\nx"},
        {"options": "credentials=/etc/passwd"},
        {"options": "ro,credentials=/etc/passwd"},
        {"options": "uid=0,credentials=/etc/passwd"},
        {"options": "suid"},
        {"options": "dev"},
        {"options": "exec"},
        {"options": "bogus"},
        {"options": "ro=1"},
        {"options": "vers="},
        {"options": "uid=0 -o x"},
    ],
)
def test_unsafe_share_input_is_refused(client, backend, overrides):
    overrides = dict(overrides)
    mp = overrides.get("mount_point")
    if mp:
        overrides["mount_point"] = mp.replace("BASE", str(backend.tmp_path / "mnt")).replace(
            "DATA", str(backend.data_dir)
        )
    response = _post(client, backend, **overrides)

    assert response.status_code == 422, response.text
    assert client.get("/api/shares").json() == []


def test_mount_point_outside_the_base_is_refused(client, backend):
    response = _post(client, backend, mount_point=str(backend.tmp_path / "elsewhere"))

    assert response.status_code == 422


def test_mount_point_may_not_be_a_download_folder(client, backend, downloads_dir):
    (backend.tmp_path / "mnt").mkdir()
    client.post("/api/settings", json={"download_folder": str(backend.tmp_path / "mnt" / "dl")})

    response = _post(client, backend, mount_point=str(backend.tmp_path / "mnt" / "dl"))
    inside = _post(client, backend, mount_point=str(backend.tmp_path / "mnt" / "dl" / "x"))

    assert response.status_code == 422
    assert inside.status_code == 422


def test_allowed_options_are_accepted(client, backend):
    response = _post(client, backend, options="ro,vers=4.1,nfsvers=4,soft,timeo=30,retrans=2")

    assert response.status_code == 200


def test_valid_nfs_and_smb_shares_produce_the_expected_argv(client, backend):
    mnt = backend.tmp_path / "mnt"
    nfs = _post(client, backend, options="ro,vers=4", mount_point=str(mnt / "n")).json()
    smb = _post(
        client, backend, name="S", type="smb", remote="//nas.example.invalid/media",
        mount_point=str(mnt / "s"), username="alice", password="test-only-pass",
        domain="WORKGROUP", options="vers=3.0,file_mode=0644",
    ).json()

    assert client.post(f"/api/shares/{nfs['id']}/mount").json()["mounted"] is True
    assert client.post(f"/api/shares/{smb['id']}/mount").json()["mounted"] is True

    nfs_call, smb_call = backend.subprocess.calls_to("mount")
    assert nfs_call == [
        "mount", "-t", "nfs", "nas.example.invalid:/export/media", str(mnt / "n"),
        "-o", "ro,vers=4",
    ]
    creds = smb_call[-1].split(",")[2].split("=", 1)[1]
    assert smb_call == [
        "mount", "-t", "cifs", "//nas.example.invalid/media", str(mnt / "s"),
        "-o", f"rw,iocharset=utf8,credentials={creds},vers=3.0,file_mode=0644",
    ]


@pytest.mark.parametrize("returncode", [0, 32])
def test_no_credentials_file_is_left_behind(client, backend, returncode):
    backend.subprocess.mount_returncode = returncode
    share = _post(
        client, backend, type="smb", remote="//nas.example.invalid/media",
        username="alice", password="test-only-pass",
    ).json()

    client.post(f"/api/shares/{share['id']}/mount")

    assert len(backend.subprocess.calls_to("mount")) == 1
    assert "credentials=" in backend.subprocess.calls_to("mount")[0][-1]
    assert not backend.creds_dir.exists() or list(backend.creds_dir.iterdir()) == []


def _insert_share(backend, mount_point):
    import sqlite3

    with sqlite3.connect(backend.db_path) as conn:
        conn.execute(
            "INSERT INTO shares (name, type, remote, mount_point, auto_mount) "
            "VALUES ('x', 'nfs', 'h:/x', ?, 0)",
            (mount_point,),
        )
        return conn.execute("SELECT max(id) FROM shares").fetchone()[0]


def test_unmount_and_delete_never_run_umount_outside_the_base(client, backend, monkeypatch):
    # Pretend everything is mounted so only the validation can stop umount.
    monkeypatch.setattr(backend.share_manager, "is_mounted", lambda _mp: True)
    sid = _insert_share(backend, str(backend.data_dir))
    sid2 = _insert_share(backend, "/etc")

    unmounted = client.post(f"/api/shares/{sid}/unmount")
    deleted = client.delete(f"/api/shares/{sid2}")

    assert unmounted.status_code == 200
    assert "Refusing" in unmounted.json()["message"]
    assert deleted.status_code == 200
    assert backend.subprocess.calls_to("umount") == []


def test_unmount_still_works_for_a_share_inside_the_base(client, backend, monkeypatch):
    monkeypatch.setattr(backend.share_manager, "is_mounted", lambda _mp: True)
    mp = str(backend.tmp_path / "mnt" / "ok")
    sid = _insert_share(backend, mp)

    client.post(f"/api/shares/{sid}/unmount")

    assert backend.subprocess.calls_to("umount") == [["umount", mp]]


def test_mounting_a_stored_unsafe_share_is_refused(client, backend):
    sid = _insert_share(backend, "/etc")

    response = client.post(f"/api/shares/{sid}/mount")

    assert response.json()["mounted"] is False
    assert backend.subprocess.calls_to("mount") == []


# --- mount point guards that the base rule alone would not catch -------------


def test_mount_point_may_not_overlap_the_data_dir_inside_the_base(client, backend, monkeypatch):
    # Base is the folder holding the data dir, so only the data-dir rule applies.
    monkeypatch.setenv("SHARES_BASE", str(backend.tmp_path))
    (backend.data_dir / "x").mkdir()
    (backend.tmp_path / "up" / "data2").mkdir(parents=True)

    for mp in (backend.data_dir, backend.data_dir / "x"):
        assert _post(client, backend, mount_point=str(mp)).status_code == 422, mp

    # A folder above the data dir (still below the base) contains it.
    monkeypatch.setenv("SHARES_BASE", str(backend.tmp_path.parent))
    assert _post(client, backend, mount_point=str(backend.tmp_path)).status_code == 422

    # A sibling of the data dir is fine.
    monkeypatch.setenv("SHARES_BASE", str(backend.tmp_path))
    assert _post(client, backend, mount_point=str(backend.tmp_path / "up")).status_code == 200
    assert client.get("/api/shares").json()[0]["mount_point"] == str(backend.tmp_path / "up")


def test_mount_point_may_not_escape_the_base_through_a_symlink(client, backend):
    base = backend.tmp_path / "mnt"
    base.mkdir()
    outside = backend.tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)

    assert _post(client, backend, mount_point=str(base / "link")).status_code == 422
    assert _post(client, backend, mount_point=str(base / "link" / "sub")).status_code == 422
    assert client.get("/api/shares").json() == []
    assert not (outside / "sub").exists()


def test_mount_point_may_not_contain_a_download_folder(client, backend):
    base = backend.tmp_path / "mnt"
    (base / "a").mkdir(parents=True)
    client.post("/api/settings", json={"download_folder": str(base / "a" / "dl")})

    assert _post(client, backend, mount_point=str(base / "a")).status_code == 422
    assert _post(client, backend, mount_point=str(base / "b")).status_code == 200
