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


# ---- a file in a subfolder: the whole round trip ----


def test_file_in_a_subfolder_can_be_listed_downloaded_and_deleted(client, tree):
    listed = client.get("/api/files", params={"path": "Music"})
    downloaded = client.get("/api/files/download", params={"path": "Music/song.mp3"})
    deleted = client.delete("/api/files", params={"path": "Music/song.mp3"})

    assert listed.status_code == 200
    assert [e["path"] for e in listed.json()["entries"]] == ["Music/song.mp3"]
    assert downloaded.status_code == 200
    assert downloaded.content == b"audio"
    assert deleted.status_code == 200
    assert not (tree / "Music" / "song.mp3").exists()
    assert (tree / "Music").is_dir()


@pytest.mark.parametrize("path", ["../x", "../outside/secret.txt", "Music/../../outside"])
def test_traversal_is_refused_by_every_file_operation(client, tree, path):
    outside = tree.parent / "outside"

    assert client.get("/api/files", params={"path": path}).status_code == 400
    assert client.get("/api/files/download", params={"path": path}).status_code == 400
    assert client.delete("/api/files", params={"path": path}).status_code == 400
    assert (
        client.post("/api/files/rename", json={"path": path, "new_name": "n"}).status_code == 400
    )
    assert client.post("/api/files/mkdir", json={"path": path, "name": "n"}).status_code == 400
    assert (outside / "secret.txt").read_text() == "do not serve"
    assert sorted(p.name for p in outside.iterdir()) == ["secret.txt"]


def test_absolute_paths_never_reach_outside_the_root(client, tree):
    outside = tree.parent / "outside"
    secret = str(outside / "secret.txt")

    assert client.get("/api/files", params={"path": str(outside)}).json().get("entries") in (
        None,
        [],
    )
    assert client.get("/api/files/download", params={"path": secret}).status_code in (400, 404)
    assert client.delete("/api/files", params={"path": secret}).status_code in (400, 404)
    assert (outside / "secret.txt").read_text() == "do not serve"


# ---- root folder "/" (subfolders used to be refused: "//" prefix bug) ----


def test_safe_join_accepts_subfolders_when_the_root_is_the_filesystem_root(backend, tmp_path):
    (tmp_path / "sub").mkdir()
    expected = os.path.realpath(tmp_path / "sub")

    assert backend.files_manager._safe_join("/", expected) == expected
    assert backend.files_manager._safe_join("/", "") == "/"


def test_subfolder_listing_and_download_work_when_the_root_is_the_filesystem_root(
    client, backend, tmp_path, monkeypatch
):
    # "/" can no longer be chosen in the settings, but an older setup may have
    # it stored. Read-only requests, and only for a temp folder.
    folder = tmp_path / "under-root"
    folder.mkdir()
    (folder / "clip.mp4").write_bytes(b"video-bytes")
    rel = os.path.realpath(folder).lstrip("/")

    async def filesystem_root():
        return "/"

    monkeypatch.setattr(backend.files_manager, "get_root", filesystem_root)

    listed = client.get("/api/files", params={"path": rel})
    downloaded = client.get("/api/files/download", params={"path": f"{rel}/clip.mp4"})

    assert listed.status_code == 200, listed.text
    assert [e["path"] for e in listed.json()["entries"]] == [f"{rel}/clip.mp4"]
    assert downloaded.status_code == 200
    assert downloaded.content == b"video-bytes"


# ---- symbolic links: delete and rename act on the link, not its target ----


def test_delete_of_a_link_removes_the_link_and_keeps_its_target(client, tree):
    (tree / "keep.mp4").write_bytes(b"keep me")
    (tree / "link.mp4").symlink_to(tree / "keep.mp4")

    response = client.delete("/api/files", params={"path": "link.mp4"})

    assert response.status_code == 200
    assert (tree / "keep.mp4").read_bytes() == b"keep me"
    assert not os.path.lexists(tree / "link.mp4")


@pytest.mark.parametrize("path", ["album-link", "album-link/"])
def test_delete_of_a_link_to_a_folder_keeps_the_folder(client, tree, path):
    (tree / "album-link").symlink_to(tree / "Music")

    response = client.delete("/api/files", params={"path": path})

    assert response.status_code == 200
    assert (tree / "Music" / "song.mp3").read_bytes() == b"audio"
    assert not os.path.lexists(tree / "album-link")


def test_link_pointing_outside_is_listed_in_place_and_can_be_removed(client, tree):
    outside = tree.parent / "outside"
    (tree / "escape.txt").symlink_to(outside / "secret.txt")
    (tree / "escape-dir").symlink_to(outside)

    entries = {e["name"]: e for e in client.get("/api/files").json()["entries"]}
    # Listed where the link is, not where it leads.
    assert entries["escape.txt"]["path"] == "escape.txt"
    assert entries["escape-dir"]["path"] == "escape-dir"

    # Following the link out of the root is still refused...
    assert client.get("/api/files/download", params={"path": "escape.txt"}).status_code == 400
    assert client.get("/api/files", params={"path": "escape-dir"}).status_code == 400
    through = client.delete("/api/files", params={"path": "escape-dir/secret.txt"})
    assert through.status_code == 400

    # ...but the links themselves can be cleaned up, and the targets stay.
    assert client.delete("/api/files", params={"path": "escape.txt"}).status_code == 200
    assert client.delete("/api/files", params={"path": "escape-dir"}).status_code == 200
    assert not os.path.lexists(tree / "escape.txt")
    assert not os.path.lexists(tree / "escape-dir")
    assert (outside / "secret.txt").read_text() == "do not serve"


def test_rename_of_a_link_renames_the_link_and_keeps_its_target(client, tree):
    (tree / "keep.mp4").write_bytes(b"keep me")
    (tree / "link.mp4").symlink_to(tree / "keep.mp4")

    response = client.post(
        "/api/files/rename", json={"path": "link.mp4", "new_name": "renamed-link.mp4"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["path"] == "renamed-link.mp4"
    assert (tree / "keep.mp4").read_bytes() == b"keep me"
    assert (tree / "renamed-link.mp4").is_symlink()
    assert not os.path.lexists(tree / "link.mp4")


def test_rename_does_not_replace_an_existing_link(client, tree):
    (tree / "dangling").symlink_to(tree / "gone.mp4")

    response = client.post("/api/files/rename", json={"path": "clip.mp4", "new_name": "dangling"})

    assert response.status_code == 400
    assert (tree / "clip.mp4").exists()
    assert (tree / "dangling").is_symlink()


def test_link_whose_target_is_gone_is_listed_and_can_be_deleted(client, tree):
    (tree / "dangling.mp4").symlink_to(tree / "gone.mp4")

    names = [e["name"] for e in client.get("/api/files").json()["entries"]]
    response = client.delete("/api/files", params={"path": "dangling.mp4"})

    assert "dangling.mp4" in names
    assert response.status_code == 200
    assert not os.path.lexists(tree / "dangling.mp4")


# ---- bad inputs get a clear 400/404, not a 500 or a silent success ----


def test_list_missing_folder_is_404(client, tree):
    response = client.get("/api/files", params={"path": "nope/nope"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found"


def test_list_of_an_existing_file_is_404(client, tree):
    response = client.get("/api/files", params={"path": "clip.mp4"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found"


def test_list_root_when_download_folder_does_not_exist_is_200_empty(client, tmp_path):
    missing = tmp_path / "fresh-downloads"
    response = client.post("/api/settings", json={"download_folder": str(missing)})
    assert response.status_code == 200, response.text

    listing = client.get("/api/files")

    assert listing.status_code == 200
    assert listing.json()["entries"] == []


def test_mkdir_with_missing_parent_is_404_and_creates_nothing(client, tree):
    response = client.post("/api/files/mkdir", json={"path": "no/such/parent", "name": "sub"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found"
    assert not (tree / "no").exists()


def test_mkdir_with_a_file_as_parent_is_400(client, tree):
    response = client.post("/api/files/mkdir", json={"path": "clip.mp4", "name": "sub"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Not a folder"
    assert (tree / "clip.mp4").is_file()


def test_rename_to_a_too_long_name_is_400_and_keeps_the_file(client, tree):
    response = client.post(
        "/api/files/rename", json={"path": "clip.mp4", "new_name": "n" * 300}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File name too long"
    assert (tree / "clip.mp4").read_bytes() == b"video-bytes"


def test_mkdir_with_a_too_long_name_is_400_and_creates_nothing(client, tree):
    response = client.post("/api/files/mkdir", json={"path": "", "name": "n" * 300})

    assert response.status_code == 400
    assert response.json()["detail"] == "File name too long"
    assert sorted(p.name for p in tree.iterdir()) == ["Music", "clip.mp4"]
