import json
from pathlib import Path

import httpx
import pytest
import respx

from forlabs_mcp.client.client import ForlabsClient
from forlabs_mcp.config import ForlabsConfig
from forlabs_mcp.errors import InvalidArgumentError, ProgrammingError

BASE_URL = "https://bki.forlabs.ru"
FIXTURES = Path(__file__).parent / "fixtures"
STUDY_ID = 10823
TASK_ID = 7001
ASSIGNMENT_ID = 8001


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _config(
    tmp_path: Path, *, enabled: bool = True, upload_root: Path | None = None
) -> ForlabsConfig:
    return ForlabsConfig(
        session_token="remember-cookie-value",
        base_url=BASE_URL,
        session_path=tmp_path / "session.json",
        assignment_submission_enabled=enabled,
        upload_root=upload_root,
    )


def _mock_xsrf_prime() -> None:
    respx.get(f"{BASE_URL}/app/login").mock(
        return_value=httpx.Response(200, headers=[("set-cookie", "XSRF-TOKEN=abc; Path=/")])
    )


def _mock_assignment_reads() -> None:
    _mock_xsrf_prime()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/sched/get_schedule").mock(
        return_value=httpx.Response(200, json=_load("sched_get_schedule.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_studies").mock(
        return_value=httpx.Response(200, json=_load("learning_get_studies.json"))
    )
    respx.post(f"{BASE_URL}/lm-vendor/repositories/learning/get_tasks").mock(
        return_value=httpx.Response(200, json=_load("learning_get_tasks_assignments.json"))
    )


def _comment(comment_id: int, message: str, attachments: list[dict] | None = None) -> dict:
    return {
        "id": comment_id,
        "user_id": 3210,
        "message": message,
        "created_at": "2026-04-02 12:30:00",
        "user": {"id": 3210, "name": "Synthetic Student"},
        "attachments": attachments or [],
    }


@respx.mock
def test_preview_returns_exact_response_and_safe_file_metadata(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    attachment = upload_root / "answer.txt"
    attachment.write_text("synthetic answer\n")
    _mock_assignment_reads()

    preview = ForlabsClient(_config(tmp_path, upload_root=upload_root)).preview_assignment_response(
        STUDY_ID, TASK_ID, "  reviewed text  ", ["answer.txt"]
    )

    assert preview["message"] == "reviewed text"
    assert preview["task_id"] == TASK_ID
    assert preview["assignment_id"] == ASSIGNMENT_ID
    assert preview["attachments"] == [
        {
            "name": "answer.txt",
            "size_bytes": len("synthetic answer\n"),
            "mime_type": "text/plain",
        }
    ]
    assert preview["expires_in_seconds"] == 600
    assert str(attachment) not in repr(preview)
    assert "sha256" not in repr(preview)


@respx.mock
def test_preview_rejects_path_outside_upload_root(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not allowed")
    _mock_assignment_reads()

    client = ForlabsClient(_config(tmp_path, upload_root=upload_root))
    with pytest.raises(InvalidArgumentError, match="non-symlink path"):
        client.preview_assignment_response(STUDY_ID, TASK_ID, "answer", [str(outside)])


@respx.mock
def test_submit_posts_once_and_confirms_new_thread_response(tmp_path: Path) -> None:
    _mock_assignment_reads()
    comments = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        side_effect=[
            httpx.Response(200, json={"comments": []}),
            httpx.Response(200, json={"comments": [_comment(9002, ".")]}),
        ]
    )
    post_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/post_comment").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = ForlabsClient(_config(tmp_path))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, ".")

    result = client.submit_assignment_response(preview["preparation_id"])

    assert result["submission_status"] == "confirmed"
    assert result["read_back_status"] == "confirmed"
    assert comments.call_count == 2
    assert post_route.call_count == 1
    body = json.loads(post_route.calls.last.request.content)
    assert body == {
        "study_id": str(STUDY_ID),
        "task_id": TASK_ID,
        "assignment_id": ASSIGNMENT_ID,
        "message": ".",
        "files": [],
        "mode": "student",
    }
    assert "id" not in body

    with pytest.raises(InvalidArgumentError, match="already used"):
        client.submit_assignment_response(preview["preparation_id"])
    assert post_route.call_count == 1


@respx.mock
def test_ambiguous_post_is_not_retried_and_requires_thread_inspection(
    tmp_path: Path,
) -> None:
    _mock_assignment_reads()
    comments = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json={"comments": []})
    )
    post_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/post_comment").mock(
        side_effect=httpx.ConnectTimeout("ambiguous timeout")
    )
    client = ForlabsClient(_config(tmp_path))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, ".")

    result = client.submit_assignment_response(preview["preparation_id"])

    assert result["submission_status"] == "uncertain"
    assert result["read_back_status"] == "not_visible"
    assert post_route.call_count == 1
    assert comments.call_count == 2
    assert "not retried" in result["note"]


@respx.mock
def test_changed_attachment_blocks_submission_before_upload_or_thread_read(
    tmp_path: Path,
) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    attachment = upload_root / "answer.txt"
    attachment.write_text("original")
    _mock_assignment_reads()
    comments = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json={"comments": []})
    )
    upload = respx.get(f"{BASE_URL}/lm-vendor/upload").mock(return_value=httpx.Response(204))
    client = ForlabsClient(_config(tmp_path, upload_root=upload_root))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, "answer", ["answer.txt"])
    attachment.write_text("modified after preview")

    with pytest.raises(InvalidArgumentError, match="changed after preview"):
        client.submit_assignment_response(preview["preparation_id"])

    assert comments.call_count == 0
    assert upload.call_count == 0
    assert not any("/assignments/post_comment" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_attachment_upload_uses_flow_chunk_protocol_then_finalizes(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    attachment = upload_root / "answer.txt"
    content = b"synthetic attachment\n"
    attachment.write_bytes(content)
    _mock_assignment_reads()
    respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        side_effect=[
            httpx.Response(200, json={"comments": []}),
            httpx.Response(
                200,
                json={
                    "comments": [
                        _comment(
                            9002,
                            "answer",
                            [
                                {
                                    "id": 9100,
                                    "filename": "answer.txt",
                                    "mime_type": "text/plain",
                                    "size": len(content),
                                }
                            ],
                        )
                    ]
                },
            ),
        ]
    )
    chunk_check = respx.get(f"{BASE_URL}/lm-vendor/upload").mock(return_value=httpx.Response(204))
    chunk_upload = respx.post(f"{BASE_URL}/lm-vendor/upload").mock(
        return_value=httpx.Response(200, json={"attachment": {"id": 9100}})
    )
    store_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/uploads/store").mock(
        return_value=httpx.Response(200, json={"stored": True})
    )
    post_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/post_comment").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = ForlabsClient(_config(tmp_path, upload_root=upload_root))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, "answer", ["answer.txt"])

    result = client.submit_assignment_response(preview["preparation_id"])

    assert result["submission_status"] == "confirmed"
    assert chunk_check.call_count == 1
    assert chunk_check.calls.last.request.url.params["flowChunkNumber"] == "1"
    assert chunk_upload.call_count == 1
    upload_request = chunk_upload.calls.last.request
    assert upload_request.headers["content-type"].startswith("multipart/form-data;")
    for field in (
        "flowChunkNumber",
        "flowChunkSize",
        "flowCurrentChunkSize",
        "flowTotalSize",
        "flowIdentifier",
        "flowFilename",
        "flowRelativePath",
        "flowTotalChunks",
    ):
        assert f'name="{field}"'.encode() in upload_request.content
    assert b'name="file"; filename="answer.txt"' in upload_request.content
    assert content in upload_request.content
    assert json.loads(store_route.calls.last.request.content) == {"files": [9100]}
    body = json.loads(post_route.calls.last.request.content)
    assert body["files"] == [9100]
    assert body["message"] == "answer"


@respx.mock
def test_existing_flow_chunk_fails_closed_without_post(tmp_path: Path) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    (upload_root / "answer.txt").write_text("synthetic attachment")
    _mock_assignment_reads()
    comments = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json={"comments": []})
    )
    respx.get(f"{BASE_URL}/lm-vendor/upload").mock(return_value=httpx.Response(200))
    client = ForlabsClient(_config(tmp_path, upload_root=upload_root))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, "answer", ["answer.txt"])

    result = client.submit_assignment_response(preview["preparation_id"])

    assert result["submission_status"] == "not_sent"
    assert result["upload_status"] == "failed"
    assert comments.call_count == 1
    assert not any("/assignments/post_comment" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_failed_later_attachment_cleans_up_earlier_upload_and_never_posts(
    tmp_path: Path,
) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    (upload_root / "first.txt").write_text("first")
    (upload_root / "second.txt").write_text("second")
    _mock_assignment_reads()
    comments = respx.post(f"{BASE_URL}/lm-vendor/repositories/assignments/get_comments").mock(
        return_value=httpx.Response(200, json={"comments": []})
    )
    chunk_checks = respx.get(f"{BASE_URL}/lm-vendor/upload").mock(
        side_effect=[httpx.Response(204), httpx.Response(200)]
    )
    chunk_uploads = respx.post(f"{BASE_URL}/lm-vendor/upload").mock(
        return_value=httpx.Response(200, json={"attachment": {"id": 9100}})
    )
    delete_route = respx.post(f"{BASE_URL}/lm-vendor/repositories/uploads/delete").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    client = ForlabsClient(_config(tmp_path, upload_root=upload_root))
    preview = client.preview_assignment_response(
        STUDY_ID, TASK_ID, "answer", ["first.txt", "second.txt"]
    )

    result = client.submit_assignment_response(preview["preparation_id"])

    assert result["submission_status"] == "not_sent"
    assert result["cleanup_status"] == "deleted"
    assert comments.call_count == 1
    assert chunk_checks.call_count == 2
    assert chunk_uploads.call_count == 1
    assert json.loads(delete_route.calls.last.request.content) == {"files": [9100]}
    assert not any("/assignments/post_comment" in str(call.request.url) for call in respx.calls)


@respx.mock
def test_direct_submission_call_is_disabled_without_the_feature_flag(
    tmp_path: Path,
) -> None:
    _mock_assignment_reads()
    client = ForlabsClient(_config(tmp_path, enabled=False))
    preview = client.preview_assignment_response(STUDY_ID, TASK_ID, "answer")
    request_count = len(respx.calls)

    with pytest.raises(ProgrammingError, match="disabled"):
        client.submit_assignment_response(preview["preparation_id"])

    assert len(respx.calls) == request_count
    assert not any("/assignments/post_comment" in str(call.request.url) for call in respx.calls)
