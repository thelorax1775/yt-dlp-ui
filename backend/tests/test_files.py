"""File manager: every path must stay inside the download folder."""

import os

import pytest


@pytest.fixture
def tree(downloads_dir):
    """downloads/ with a few entries, plus a sibling folder that is off limits."""
    (downloads_dir / "clip.mp4").write_bytes(b"video-bytes")
    (downloads_dir / "Music").mkdir()
    (downloads_dir / "Music" / "song.mp3").write_bytes(b"audio")
    outside = downloads_dir.parent / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not serve")
    return downloads_dir


# ---- _safe_join (the guard itself) ----


def test_safe_join_accepts_paths_inside_root(backend, tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    safe_join = backend.files_manager._safe_join

    assert safe_join(str(root), "") == os.path.realpath(root)
    assert safe_join(str(root), "sub/file.mp4") == os.path.join(
        os.path.realpath(root), "sub", "file.mp4"
    )


@pytest.mark.parametrize("rel", ["..", "../outside", "sub/../../outside", "../root-sibling"])
def test_safe_join_rejects_parent_traversal(backend, tmp_path, rel):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)

    with pytest.raises(ValueError):
        backend.files_manager._safe_join(str(root), rel)


def test_safe_join_never_returns_an_absolute_path_outside_root(backend, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    root_real = os.path.realpath(root)

    # Either refusing or confining the path is acceptable; escaping is not.
    try:
        resolved = backend.files_manager._safe_join(str(root), "/etc/passwd")
    except ValueError:
        return
    assert resolved.startswith(root_real + os.sep)


def test_safe_join_rejects_symlink_pointing_outside_root(backend, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside)

    with pytest.raises(ValueError):
        backend.files_manager._safe_join(str(root), "escape/secret.txt")


# ---- HTTP API ----


def test_list_root_shows_folders_first(client, tree):
    response = client.get("/api/files")

    assert response.status_code == 200
    body = response.json()
    assert body["root"] == os.path.realpath(tree)
    assert body["path"] == ""
    assert [(e["name"], e["is_dir"]) for e in body["entries"]] == [
        ("Music", True),
        ("clip.mp4", False),
    ]
    assert body["entries"][1]["size"] == len(b"video-bytes")


def test_list_subfolder(client, tree):
    response = client.get("/api/files", params={"path": "Music"})

    assert response.status_code == 200
    assert [e["path"] for e in response.json()["entries"]] == ["Music/song.mp3"]


@pytest.mark.parametrize("path", ["..", "../outside", "Music/../../outside"])
def test_list_rejects_parent_traversal(client, tree, path):
    response = client.get("/api/files", params={"path": path})

    assert response.status_code == 400
    assert "outside" in response.json()["detail"]


def test_download_serves_file_inside_root(client, tree):
    response = client.get("/api/files/download", params={"path": "clip.mp4"})

    assert response.status_code == 200
    assert response.content == b"video-bytes"


def test_download_rejects_parent_traversal(client, tree):
    response = client.get("/api/files/download", params={"path": "../outside/secret.txt"})

    assert response.status_code == 400
    assert b"do not serve" not in response.content


def test_download_never_serves_an_absolute_path(client, tree):
    secret = tree.parent / "outside" / "secret.txt"

    response = client.get("/api/files/download", params={"path": str(secret)})

    assert response.status_code in (400, 404)
    assert b"do not serve" not in response.content


def test_delete_removes_file_inside_root(client, tree):
    response = client.delete("/api/files", params={"path": "clip.mp4"})

    assert response.status_code == 200
    assert not (tree / "clip.mp4").exists()


def test_delete_rejects_parent_traversal_and_leaves_target_alone(client, tree):
    outside = tree.parent / "outside"

    response = client.delete("/api/files", params={"path": "../outside"})

    assert response.status_code == 400
    assert (outside / "secret.txt").exists()


def test_delete_with_absolute_path_leaves_target_alone(client, tree):
    outside = tree.parent / "outside"

    response = client.delete("/api/files", params={"path": str(outside)})

    assert response.status_code in (400, 404)
    assert (outside / "secret.txt").exists()


def test_delete_refuses_the_download_root(client, tree):
    response = client.delete("/api/files", params={"path": ""})

    assert response.status_code == 400
    assert (tree / "clip.mp4").exists()


def test_delete_missing_file_is_404(client, tree):
    assert client.delete("/api/files", params={"path": "nope.mp4"}).status_code == 404


def test_rename_inside_root(client, tree):
    response = client.post(
        "/api/files/rename", json={"path": "clip.mp4", "new_name": "renamed.mp4"}
    )

    assert response.status_code == 200
    assert response.json()["path"] == "renamed.mp4"
    assert (tree / "renamed.mp4").read_bytes() == b"video-bytes"
    assert not (tree / "clip.mp4").exists()


def test_rename_rejects_source_outside_root(client, tree):
    outside = tree.parent / "outside"

    response = client.post(
        "/api/files/rename", json={"path": "../outside/secret.txt", "new_name": "x.txt"}
    )

    assert response.status_code == 400
    assert (outside / "secret.txt").exists()


@pytest.mark.parametrize("new_name", ["../escaped.mp4", "a/b.mp4", "..", "", "back\\slash"])
def test_rename_rejects_names_with_path_parts(client, tree, new_name):
    response = client.post("/api/files/rename", json={"path": "clip.mp4", "new_name": new_name})

    assert response.status_code == 422
    assert (tree / "clip.mp4").exists()
    assert not (tree.parent / "escaped.mp4").exists()


def test_rename_refuses_to_overwrite(client, tree):
    (tree / "other.mp4").write_bytes(b"other")

    response = client.post("/api/files/rename", json={"path": "clip.mp4", "new_name": "other.mp4"})

    assert response.status_code == 400
    assert (tree / "other.mp4").read_bytes() == b"other"


def test_mkdir_inside_root_and_duplicate(client, tree):
    first = client.post("/api/files/mkdir", json={"path": "Music", "name": "Album"})
    second = client.post("/api/files/mkdir", json={"path": "Music", "name": "Album"})

    assert first.status_code == 200
    assert (tree / "Music" / "Album").is_dir()
    assert second.status_code == 400


def test_mkdir_rejects_parent_outside_root(client, tree):
    response = client.post("/api/files/mkdir", json={"path": "../outside", "name": "new"})

    assert response.status_code == 400
    assert not (tree.parent / "outside" / "new").exists()
