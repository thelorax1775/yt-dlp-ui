"""File manager: confinement to the download root and basic operations."""

import pytest

ESCAPES = ["..", "../outside.txt", "sub/../../outside.txt", "a/../../.."]


@pytest.fixture
def root(client, download_root, tmp_path):
    from pathlib import Path

    (tmp_path / "outside.txt").write_text("secret")
    r = Path(download_root)
    (r / "sub").mkdir()
    (r / "sub" / "inner.txt").write_text("inner")
    (r / "video.mp4").write_text("video data")
    return r


@pytest.mark.parametrize("bad", ESCAPES)
def test_list_rejects_traversal(client, root, bad):
    assert client.get("/api/files", params={"path": bad}).status_code == 400


@pytest.mark.parametrize("bad", ESCAPES)
def test_download_rejects_traversal(client, root, bad):
    assert client.get("/api/files/download", params={"path": bad}).status_code == 400


@pytest.mark.parametrize("bad", ESCAPES)
def test_delete_rejects_traversal(client, root, tmp_path, bad):
    assert client.delete("/api/files", params={"path": bad}).status_code == 400
    assert (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize("bad", ESCAPES)
def test_rename_rejects_traversal_in_path(client, root, tmp_path, bad):
    resp = client.post("/api/files/rename", json={"path": bad, "new_name": "x"})
    assert resp.status_code == 400
    assert (tmp_path / "outside.txt").exists()


def test_rename_rejects_traversal_in_new_name(client, root, tmp_path):
    resp = client.post(
        "/api/files/rename", json={"path": "video.mp4", "new_name": "../moved.mp4"}
    )
    # rejected by request validation (422) before it reaches the file manager
    assert resp.status_code in (400, 422)
    assert (root / "video.mp4").exists()
    assert not (tmp_path / "moved.mp4").exists()


@pytest.mark.parametrize("bad", ESCAPES)
def test_mkdir_rejects_traversal_in_path(client, root, bad):
    resp = client.post("/api/files/mkdir", json={"path": bad, "name": "newdir"})
    assert resp.status_code == 400


def test_mkdir_rejects_traversal_in_name(client, root, tmp_path):
    resp = client.post("/api/files/mkdir", json={"path": "", "name": "../escaped"})
    assert resp.status_code in (400, 422)
    assert not (tmp_path / "escaped").exists()


def test_absolute_path_is_treated_as_inside_root(client, root, tmp_path):
    # Leading slashes are stripped, so "/etc" means <root>/etc, never the real /etc.
    resp = client.get("/api/files", params={"path": "/etc"})
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
    abs_outside = str(tmp_path / "outside.txt")
    assert client.get("/api/files/download", params={"path": abs_outside}).status_code == 404
    assert client.delete("/api/files", params={"path": abs_outside}).status_code == 404
    assert (tmp_path / "outside.txt").exists()


def test_symlink_pointing_outside_is_rejected(client, root, tmp_path):
    (root / "link").symlink_to(tmp_path)
    assert client.get("/api/files", params={"path": "link"}).status_code == 400
    assert client.get("/api/files/download", params={"path": "link/outside.txt"}).status_code == 400


def test_list_root_and_subdir(client, root):
    data = client.get("/api/files").json()
    assert data["path"] == ""
    assert [(e["name"], e["is_dir"]) for e in data["entries"]] == [
        ("sub", True),
        ("video.mp4", False),
    ]
    assert data["entries"][1]["size"] == len("video data")
    sub = client.get("/api/files", params={"path": "sub"}).json()
    assert sub["path"] == "sub"
    assert [e["path"] for e in sub["entries"]] == ["sub/inner.txt"]


def test_rename(client, root):
    resp = client.post("/api/files/rename", json={"path": "video.mp4", "new_name": "clip.mp4"})
    assert resp.status_code == 200
    assert resp.json()["path"] == "clip.mp4"
    assert not (root / "video.mp4").exists()
    assert (root / "clip.mp4").read_text() == "video data"


def test_rename_onto_existing_name_is_rejected(client, root):
    (root / "other.mp4").write_text("x")
    resp = client.post("/api/files/rename", json={"path": "video.mp4", "new_name": "other.mp4"})
    assert resp.status_code == 400
    assert (root / "video.mp4").exists()


def test_rename_missing_file_is_404(client, root):
    resp = client.post("/api/files/rename", json={"path": "nope", "new_name": "x"})
    assert resp.status_code == 404


def test_mkdir(client, root):
    resp = client.post("/api/files/mkdir", json={"path": "sub", "name": "deeper"})
    assert resp.status_code == 200
    assert resp.json()["path"] == "sub/deeper"
    assert (root / "sub" / "deeper").is_dir()
    again = client.post("/api/files/mkdir", json={"path": "sub", "name": "deeper"})
    assert again.status_code == 400


def test_delete_file_and_directory(client, root):
    assert client.delete("/api/files", params={"path": "video.mp4"}).status_code == 200
    assert not (root / "video.mp4").exists()
    assert client.delete("/api/files", params={"path": "sub"}).status_code == 200
    assert not (root / "sub").exists()
    assert client.delete("/api/files", params={"path": "sub"}).status_code == 404


def test_delete_root_is_rejected(client, root):
    assert client.delete("/api/files", params={"path": ""}).status_code == 400
    assert root.exists()


def test_download_file(client, root):
    resp = client.get("/api/files/download", params={"path": "sub/inner.txt"})
    assert resp.status_code == 200
    assert resp.content == b"inner"
    assert "inner.txt" in resp.headers["content-disposition"]
    assert client.get("/api/files/download", params={"path": "sub"}).status_code == 404
