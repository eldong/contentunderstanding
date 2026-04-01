"""Tests for the local folder ingestion adapter."""

import json

import pytest

from src.ingestion.local_folder import LocalFolderAdapter


def _make_submission(tmp_path, name, meta=None, form_name="form.pdf", attachments=None):
    """Helper to create a submission directory structure."""
    sub_dir = tmp_path / name
    sub_dir.mkdir()
    if meta is not None:
        (sub_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    (sub_dir / form_name).write_bytes(b"%PDF-1.4 placeholder")
    for att in attachments or []:
        (sub_dir / att).write_bytes(b"%PDF-1.4 placeholder")
    return sub_dir


class TestLocalFolderAdapter:
    def test_list_single_submission(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Jane Employee"},
            attachments=["attachment.pdf"],
        )
        adapter = LocalFolderAdapter(tmp_path)
        results = adapter.list_submissions()

        assert len(results) == 1
        item = results[0]
        assert item.submission_id == "sub1"
        assert item.submitted_by == "Jane Employee"
        assert item.form_path.name == "form.pdf"
        assert len(item.attachment_paths) == 1
        assert item.attachment_paths[0].name == "attachment.pdf"

    def test_list_multiple_submissions(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
        )
        _make_submission(
            tmp_path,
            "sub2",
            {"submitted_by": "Bob"},
            attachments=["cert.pdf", "photo.jpg"],
        )
        adapter = LocalFolderAdapter(tmp_path)
        results = adapter.list_submissions()

        assert len(results) == 2
        ids = {r.submission_id for r in results}
        assert ids == {"sub1", "sub2"}

    def test_no_metadata_still_works(self, tmp_path):
        _make_submission(tmp_path, "sub1", attachments=["attachment.pdf"])
        adapter = LocalFolderAdapter(tmp_path)
        results = adapter.list_submissions()

        assert len(results) == 1
        assert results[0].submission_id == "sub1"
        assert results[0].submitted_by == ""

    def test_skips_directory_without_form(self, tmp_path):
        _make_submission(
            tmp_path,
            "valid",
            {"submitted_by": "Alice"},
        )
        # directory without a form file
        no_form = tmp_path / "invalid"
        no_form.mkdir()
        (no_form / "attachment.pdf").write_bytes(b"%PDF-1.4")

        adapter = LocalFolderAdapter(tmp_path)
        results = adapter.list_submissions()

        assert len(results) == 1
        assert results[0].submission_id == "valid"

    def test_form_path_is_absolute(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
        )
        adapter = LocalFolderAdapter(tmp_path)
        item = adapter.list_submissions()[0]

        assert item.form_path.is_absolute()

    def test_attachment_paths_are_absolute(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
            attachments=["att.pdf"],
        )
        adapter = LocalFolderAdapter(tmp_path)
        item = adapter.list_submissions()[0]

        for p in item.attachment_paths:
            assert p.is_absolute()

    def test_download_submission(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
        )
        adapter = LocalFolderAdapter(tmp_path)
        item = adapter.download_submission("sub1")

        assert item.submission_id == "sub1"

    def test_download_submission_not_found(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
        )
        adapter = LocalFolderAdapter(tmp_path)

        with pytest.raises(KeyError):
            adapter.download_submission("NONEXISTENT")

    def test_multiple_attachments(self, tmp_path):
        _make_submission(
            tmp_path,
            "sub1",
            {"submitted_by": "Alice"},
            attachments=["cert.pdf", "photo.png", "letter.docx"],
        )
        adapter = LocalFolderAdapter(tmp_path)
        item = adapter.list_submissions()[0]

        assert len(item.attachment_paths) == 3
