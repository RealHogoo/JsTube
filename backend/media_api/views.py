import json
from datetime import datetime
from typing import Any

from bson import ObjectId
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .auth import CurrentUser, require_user
from .mongo import media_collection, mongo_client
from .webhard import sync_from_webhard


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
    user = require_user(request, "WRITE")
    if not isinstance(user, CurrentUser):
        return user
    limit = int_param(request, "limit", 0)
    return ok(sync_from_webhard(user, limit if limit > 0 else None))


def media_list(request: HttpRequest) -> JsonResponse:
    user = require_user(request)
    if not isinstance(user, CurrentUser):
        return user

    limit = min(max(int_param(request, "limit", 40), 1), 100)
    query: dict[str, Any] = {}
    if not user.is_admin:
        query["owner_user_id"] = user.user_id
    elif request.GET.get("owner_user_id"):
        query["owner_user_id"] = request.GET["owner_user_id"].strip()

    content_kind = request.GET.get("content_kind", "").strip().upper()
    if content_kind in {"IMAGE", "VIDEO"}:
        query["content_kind"] = content_kind
    if request.GET.get("tag"):
        query["tags"] = request.GET["tag"].strip()
    if request.GET.get("album"):
        query["album"] = request.GET["album"].strip()
    if request.GET.get("favorite") in {"true", "1", "Y"}:
        query["favorite"] = True
    if request.GET.get("q"):
        keyword = request.GET["q"].strip()
        query["$or"] = [
            {"display_name": {"$regex": keyword, "$options": "i"}},
            {"file_name": {"$regex": keyword, "$options": "i"}},
            {"tags": {"$regex": keyword, "$options": "i"}},
            {"album": {"$regex": keyword, "$options": "i"}},
        ]

    cursor = media_collection().find(query).sort([("original_created_at", -1), ("webhard_file_id", -1)]).limit(limit)
    return ok({"items": [serialize_media(item) for item in cursor], "limit": limit})


@csrf_exempt
def media_detail(request: HttpRequest, webhard_file_id: int) -> JsonResponse | HttpResponse:
    if request.method == "OPTIONS":
        return HttpResponse(status=204)
    if request.method != "PATCH":
        return bad_request("PATCH is required")

    user = require_user(request, "WRITE")
    if not isinstance(user, CurrentUser):
        return user

    body = json_body(request)
    update: dict[str, Any] = {"updated_at": datetime.utcnow()}
    if "tags" in body:
        update["tags"] = normalize_tags(body["tags"])
    if "album" in body:
        update["album"] = str(body.get("album") or "").strip()[:100]
    if "favorite" in body:
        update["favorite"] = bool(body.get("favorite"))

    query: dict[str, Any] = {"webhard_file_id": webhard_file_id}
    if not user.is_admin:
        query["owner_user_id"] = user.user_id
    result = media_collection().update_one(query, {"$set": update})
    if result.matched_count == 0:
        return JsonResponse({"ok": False, "code": "NOT_FOUND", "message": "media not found"}, status=404)
    item = media_collection().find_one(query)
    return ok({"item": serialize_media(item)})


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
    for key, value in list(result.items()):
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


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

