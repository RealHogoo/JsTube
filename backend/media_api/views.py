import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bson import ObjectId
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .auth import CurrentUser, auth_token, require_user
from .mongo import media_collection, mongo_client
from .webhard import fetch_webhard_file, sync_from_webhard, sync_one_from_webhard
from .youtube import check_download_tools, import_youtube, preview_youtube


def ok(data: dict[str, Any] | list[Any]) -> JsonResponse:
    return JsonResponse({"ok": True, "code": "OK", "message": "success", "data": data}, json_dumps_params={"ensure_ascii": False})


def bad_request(message: str) -> JsonResponse:
    return JsonResponse({"ok": False, "code": "BAD_REQUEST", "message": message}, status=400)


def health(_request: HttpRequest) -> JsonResponse:
    mongo_status = "UP"
    try:
        mongo_client().admin.command("ping")
    except Exception:
        mongo_status = "DOWN"
    return ok({"status": "UP" if mongo_status == "UP" else "DEGRADED", "service": "media-service", "mongo": mongo_status})


def version(_request: HttpRequest) -> JsonResponse:
    return ok({
        "service": "media-service",
        "git_commit": git_commit(),
    })


@csrf_exempt
def options_or_view(request: HttpRequest, view):
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    return view(request)


def me(request: HttpRequest) -> JsonResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    return ok({
        "user_id": user.user_id,
        "roles": user.roles,
        "is_admin": user.is_admin,
        "permissions": {
            "write": user.has_permission("WRITE"),
            "share": user.has_permission("SHARE"),
            "delete": user.has_permission("DELETE"),
        },
    })


def sync(request: HttpRequest) -> JsonResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    if not user.is_admin:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "admin permission is required"}, status=403)
    limit = int_param(request, "limit", 0)
    return ok(sync_from_webhard(user, limit if limit > 0 else None))


@csrf_exempt
def youtube_preview(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "POST":
        return bad_request("POST is required")
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    if not user.is_admin:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "admin permission is required"}, status=403)
    body = json_body(request)
    url = str(body.get("url") or "").strip()
    if not is_youtube_url(url):
        return bad_request("youtube url is required")
    try:
        return ok(preview_youtube(url))
    except Exception as exc:
        return JsonResponse({"ok": False, "code": "YOUTUBE_ANALYZE_FAILED", "message": str(exc)}, status=502)


@csrf_exempt
def youtube_tools_check(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "POST":
        return bad_request("POST is required")
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    if not user.is_admin:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "admin permission is required"}, status=403)
    return ok(check_download_tools())


@csrf_exempt
def youtube_import_status(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "POST":
        return bad_request("POST is required")
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    if not user.is_admin:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "admin permission is required"}, status=403)
    body = json_body(request)
    raw_ids = body.get("youtube_video_ids") or []
    if not isinstance(raw_ids, list):
        return bad_request("youtube_video_ids must be a list")
    video_ids = []
    for item in raw_ids:
        video_id = str(item or "").strip()
        if video_id and video_id not in video_ids:
            video_ids.append(video_id[:80])
    if not video_ids:
        return ok({"items": [], "saved_count": 0})
    query: dict[str, Any] = {
        "source_type": "YOUTUBE_DOWNLOAD",
        "youtube_video_id": {"$in": video_ids[:200]},
    }
    if not user.is_admin:
        query["owner_user_id"] = user.user_id
    items = [serialize_media(item) for item in media_collection().find(query, media_list_projection()).limit(200)]
    return ok({"items": items, "saved_count": len(items)})


@csrf_exempt
def youtube_import_view(request: HttpRequest) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "POST":
        return bad_request("POST is required")
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    if not user.is_admin:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "admin permission is required"}, status=403)
    if not user.has_permission("WRITE"):
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "write permission is required"}, status=403)
    body = json_body(request)
    url = str(body.get("url") or "").strip()
    if not is_youtube_url(url):
        return bad_request("youtube url is required")
    tool_status = check_download_tools()
    if not tool_status.get("ok_to_download"):
        return JsonResponse({"ok": False, "code": "YOUTUBE_TOOL_CHECK_FAILED", "message": "download environment or webhard check failed", "data": tool_status}, status=422)
    try:
        return ok(import_youtube(url, user, auth_token(request), normalize_tags(body.get("tags") or "")))
    except Exception as exc:
        return JsonResponse({"ok": False, "code": "YOUTUBE_IMPORT_FAILED", "message": str(exc)}, status=502)


def media_list(request: HttpRequest) -> JsonResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user

    limit = min(max(int_param(request, "limit", 40), 1), 100)
    offset = max(int_param(request, "offset", 0), 0)
    query: dict[str, Any] = {}
    if not user.is_admin:
        query["owner_user_id"] = user.user_id
    elif request.GET.get("owner_user_id"):
        query["owner_user_id"] = request.GET["owner_user_id"].strip()

    content_kind = request.GET.get("content_kind", "").strip().upper()
    if content_kind in {"IMAGE", "VIDEO"}:
        query["content_kind"] = content_kind
        if content_kind == "VIDEO" and request.GET.get("tag", "").strip() != "노래방":
            query["tags"] = {"$ne": "노래방"}
    elif content_kind == "KARAOKE":
        query["content_kind"] = "VIDEO"
        query["tags"] = "노래방"
    if request.GET.get("tag"):
        query["tags"] = request.GET["tag"].strip()
    if request.GET.get("album"):
        query["album"] = request.GET["album"].strip()
    if request.GET.get("favorite") in {"true", "1", "Y"}:
        query["favorite"] = True
    if request.GET.get("q"):
        keyword = request.GET["q"].strip()[:80]
        pattern = re.escape(keyword)
    if request.GET.get("q") and keyword:
        query["$or"] = [
            {"display_name": {"$regex": pattern, "$options": "i"}},
            {"file_name": {"$regex": pattern, "$options": "i"}},
            {"tags": {"$regex": pattern, "$options": "i"}},
            {"album": {"$regex": pattern, "$options": "i"}},
        ]

    sort_key = request.GET.get("sort", "recent").strip().lower()
    if sort_key == "popular":
        sort = [("view_count", -1), ("like_count", -1), ("original_created_at", -1), ("webhard_file_id", -1)]
    elif sort_key == "liked":
        sort = [("like_count", -1), ("view_count", -1), ("original_created_at", -1), ("webhard_file_id", -1)]
    else:
        sort = [("original_created_at", -1), ("webhard_file_id", -1)]

    collection = media_collection()
    count_base_query = dict(query)
    count_base_query.pop("content_kind", None)
    count_base_query.pop("tags", None)
    counts = None
    if offset == 0 or request.GET.get("include_counts") in {"true", "1", "Y"}:
        counts = media_counts(collection, count_base_query)
    cursor = collection.find(query, media_list_projection()).sort(sort).skip(offset).limit(limit + 1)
    fetched_items = [serialize_media(item) for item in cursor]
    has_more = len(fetched_items) > limit
    items = fetched_items[:limit]
    return ok({
        "items": items,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "counts": counts,
    })


@csrf_exempt
def media_detail(request: HttpRequest, webhard_file_id: int) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method not in {"GET", "PATCH"}:
        return bad_request("GET or PATCH is required")

    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user

    query: dict[str, Any] = {"webhard_file_id": webhard_file_id}
    if not user.is_admin:
        query["owner_user_id"] = user.user_id

    if request.method == "GET":
        item = media_collection().find_one(query)
        if not item:
            return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media not found"}, status=404)
        return ok({"item": serialize_media(item)})

    body = json_body(request)
    item = media_collection().find_one(query)
    if not item:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media not found"}, status=404)
    edit_fields = {"tags", "album", "title", "description", "channel_name", "subscribed"}
    if edit_fields.intersection(body.keys()) and not can_manage_media(user, item):
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "owner or admin permission is required"}, status=403)

    update: dict[str, Any] = {"updated_at": datetime.utcnow()}
    increments: dict[str, int] = {}
    if "tags" in body:
        update["tags"] = normalize_tags(body["tags"])
    if "album" in body:
        update["album"] = str(body.get("album") or "").strip()[:100]
    if "favorite" in body:
        update["favorite"] = bool(body.get("favorite"))
    if "title" in body:
        update["title"] = str(body.get("title") or "").strip()[:180]
    if "description" in body:
        update["description"] = str(body.get("description") or "").strip()[:2000]
    if "channel_name" in body:
        update["channel_name"] = str(body.get("channel_name") or "").strip()[:120]
    if "subscribed" in body:
        update["subscribed"] = bool(body.get("subscribed"))
    if "liked" in body:
        liked = bool(body.get("liked"))
        update["liked"] = liked
        increments["like_count"] = 1 if liked else -1
    if body.get("increment_view"):
        increments["view_count"] = 1

    patch: dict[str, Any] = {"$set": update}
    if increments:
        patch["$inc"] = increments
    result = media_collection().update_one(query, patch)
    if result.matched_count == 0:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media not found"}, status=404)
    item = media_collection().find_one(query)
    return ok({"item": serialize_media(item)})


@csrf_exempt
def media_thumbnail(request: HttpRequest, webhard_file_id: int) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "POST":
        return bad_request("POST is required")

    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    item = media_collection().find_one({"webhard_file_id": webhard_file_id})
    if not item:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media not found"}, status=404)
    if not can_manage_media(user, item):
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "owner or admin permission is required"}, status=403)

    token = auth_token(request)
    try:
        response = requests.post(
            f"{settings.MEDIA_CONFIG['WEBHARD_PUBLIC_BASE_URL']}/thumbnail/rebuild.json",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"file_id": webhard_file_id, "limit": 1},
            timeout=30,
        )
        body = response.json()
    except requests.RequestException:
        return JsonResponse({"ok": False, "code": "WEBHARD_UNAVAILABLE", "message": "webhard thumbnail request failed"}, status=502)
    except ValueError:
        return JsonResponse({"ok": False, "code": "WEBHARD_INVALID_RESPONSE", "message": "webhard thumbnail response is invalid"}, status=502)

    if not response.ok or body.get("ok") is not True:
        return JsonResponse(
            {
                "ok": False,
                "code": body.get("code") or "WEBHARD_THUMBNAIL_FAILED",
                "message": body.get("message") or "thumbnail creation failed",
            },
            status=response.status_code if response.status_code >= 400 else 502,
        )

    synced = sync_one_from_webhard(user, webhard_file_id)
    return ok({"thumbnail": body.get("data") or {}, "item": serialize_media(synced.get("item"))})


def media_file_proxy(request: HttpRequest, webhard_file_id: int, file_kind: str) -> JsonResponse | HttpResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user

    file = fetch_webhard_file(user, webhard_file_id)
    if not file:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media file not found"}, status=404)

    if file_kind == "thumbnail":
        path = file.get("thumbnail_path")
        content_type = "image/webp"
        as_attachment = False
    elif file_kind == "content":
        path = file.get("storage_path")
        content_type = file.get("content_type") or "application/octet-stream"
        as_attachment = False
    elif file_kind == "download":
        path = file.get("storage_path")
        content_type = "application/octet-stream"
        as_attachment = True
    else:
        return bad_request("invalid file kind")

    if not path:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "file path not found"}, status=404)
    try:
        file_path = safe_media_path(path)
    except ValueError:
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "file path is outside storage root"}, status=403)
    if not file_path.exists():
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "file path not found"}, status=404)

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=as_attachment,
        filename=str(file.get("file_name") or "download"),
        content_type=str(content_type),
    )


def albums(request: HttpRequest) -> JsonResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user
    query = {} if user.is_admin else {"owner_user_id": user.user_id}
    values = [item for item in media_collection().distinct("album", query) if item]
    values.sort()
    return ok({"items": values})


def serialize_media(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {}
    result = dict(item)
    result["_id"] = str(result.get("_id", ""))
    result["title"] = result.get("title") or result.get("display_name") or result.get("file_name") or "Untitled"
    result["description"] = result.get("description") or ""
    result["channel_name"] = result.get("channel_name") or channel_name(result)
    result["view_count"] = max(int(result.get("view_count") or 0), 0)
    result["like_count"] = max(int(result.get("like_count") or 0), 0)
    result["liked"] = bool(result.get("liked"))
    result["subscribed"] = bool(result.get("subscribed"))
    thumbnail_url = str(result.get("thumbnail_url") or "")
    content_url = str(result.get("content_url") or "")
    if result.get("content_kind") == "VIDEO" and (thumbnail_url == content_url or "/file/content/" in thumbnail_url):
        result["thumbnail_url"] = ""
    for key, value in list(result.items()):
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


def media_list_projection() -> dict[str, int]:
    return {
        "_id": 1,
        "webhard_file_id": 1,
        "owner_user_id": 1,
        "file_name": 1,
        "display_name": 1,
        "file_size": 1,
        "content_type": 1,
        "content_kind": 1,
        "thumbnail_url": 1,
        "content_url": 1,
        "download_url": 1,
        "original_created_at": 1,
        "uploaded_at": 1,
        "webhard_updated_at": 1,
        "source_type": 1,
        "youtube_video_id": 1,
        "youtube_url": 1,
        "youtube_playlist_id": 1,
        "youtube_playlist_title": 1,
        "title": 1,
        "description": 1,
        "channel_name": 1,
        "album": 1,
        "tags": 1,
        "favorite": 1,
        "view_count": 1,
        "like_count": 1,
        "liked": 1,
        "subscribed": 1,
    }


def media_counts(collection, query: dict[str, Any]) -> dict[str, int]:
    tags_array = {"$cond": [{"$isArray": "$tags"}, "$tags", []]}
    karaoke_tag = {"$in": ["노래방", tags_array]}
    rows = list(collection.aggregate([
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "image": {"$sum": {"$cond": [{"$eq": ["$content_kind", "IMAGE"]}, 1, 0]}},
                "video": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$content_kind", "VIDEO"]}, {"$not": [karaoke_tag]}]},
                            1,
                            0,
                        ]
                    }
                },
                "karaoke": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$content_kind", "VIDEO"]}, karaoke_tag]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
    ]))
    row = rows[0] if rows else {}
    return {
        "image": int(row.get("image") or 0),
        "video": int(row.get("video") or 0),
        "karaoke": int(row.get("karaoke") or 0),
    }


def can_manage_media(user: CurrentUser, item: dict[str, Any]) -> bool:
    return user.is_admin or str(item.get("owner_user_id") or "") == user.user_id


def channel_name(item: dict[str, Any]) -> str:
    owner = str(item.get("owner_user_id") or "creator").strip()
    return f"{owner} 채널"


def git_commit() -> str:
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("VITE_GIT_COMMIT")
    if env_commit:
        return env_commit[:12]

    repo_dir = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def int_param(request: HttpRequest, name: str, default: int) -> int:
    try:
        return int(request.GET.get(name) or default)
    except ValueError:
        return default


def json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


def normalize_tags(value: Any) -> list[str]:
    items = value if isinstance(value, list) else str(value or "").split(",")
    result = []
    for item in items:
        tag = str(item).strip()
        if tag and tag not in result:
            result.append(tag[:40])
    return result[:30]


def is_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    allowed_hosts = {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
    return parsed.scheme == "https" and parsed.hostname in allowed_hosts


def safe_media_path(value: Any) -> Path:
    configured = str(settings.MEDIA_CONFIG.get("WEBHARD_STORAGE_ROOT") or "").strip()
    if not configured:
        raise ValueError("webhard storage root is not configured")
    root = Path(configured).resolve()
    candidate = Path(str(value)).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("file path is outside storage root")
    return candidate
