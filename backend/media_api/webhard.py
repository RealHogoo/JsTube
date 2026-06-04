from datetime import datetime, timezone
from typing import Any

import psycopg
from pymongo import UpdateOne
from psycopg.rows import dict_row
from django.conf import settings

from .auth import CurrentUser
from .mongo import media_collection


def sync_from_webhard(current_user: CurrentUser, limit: int | None = None) -> dict[str, Any]:
    rows = fetch_webhard_media(current_user, limit or settings.MEDIA_CONFIG["MEDIA_SYNC_LIMIT"])
    collection = media_collection()
    now = datetime.now(timezone.utc)
    operations = []
    for row in rows:
        doc = media_document(row, now, owner_is_admin=current_user.is_admin and str(row.get("owner_user_id") or "") == current_user.user_id)
        operations.append(
            UpdateOne(
                {"webhard_file_id": doc["webhard_file_id"]},
                {
                    "$set": doc,
                    "$setOnInsert": {
                        "tags": [],
                        "album": "",
                        "favorite": False,
                        "created_at": now,
                    },
                },
                upsert=True,
            )
        )
    deleted_count = purge_deleted_webhard_media(current_user)
    if not operations:
        return {"scanned_count": 0, "upserted_count": 0, "deleted_count": deleted_count}
    result = collection.bulk_write(operations, ordered=False)
    return {"scanned_count": len(rows), "upserted_count": result.upserted_count + result.modified_count, "deleted_count": deleted_count}


def sync_one_from_webhard(current_user: CurrentUser, file_id: int) -> dict[str, Any]:
    rows = fetch_webhard_media_by_file_id(current_user, file_id)
    collection = media_collection()
    now = datetime.now(timezone.utc)
    for row in rows:
        doc = media_document(row, now, owner_is_admin=current_user.is_admin and str(row.get("owner_user_id") or "") == current_user.user_id)
        collection.update_one(
            {"webhard_file_id": doc["webhard_file_id"]},
            {
                "$set": doc,
                "$setOnInsert": {
                    "tags": [],
                    "album": "",
                    "favorite": False,
                    "created_at": now,
                },
            },
            upsert=True,
        )
    return {"item": media_collection().find_one({"webhard_file_id": file_id})}


def fetch_webhard_media(current_user: CurrentUser, limit: int) -> list[dict[str, Any]]:
    sql = """
        SELECT file_id, owner_user_id, file_name, display_name, file_size, content_type,
               content_kind, thumbnail_path, original_created_at, created_at, updated_at
        FROM wh_file
        WHERE deleted_yn = 'N'
          AND content_kind IN ('IMAGE', 'VIDEO')
          AND (%s OR owner_user_id = %s)
        ORDER BY updated_at DESC, file_id DESC
        LIMIT %s
    """
    with psycopg.connect(
        host=settings.MEDIA_CONFIG["WEBHARD_DB_HOST"],
        port=settings.MEDIA_CONFIG["WEBHARD_DB_PORT"],
        dbname=settings.MEDIA_CONFIG["WEBHARD_DB_DATABASE"],
        user=settings.MEDIA_CONFIG["WEBHARD_DB_USERNAME"],
        password=settings.MEDIA_CONFIG["WEBHARD_DB_PASSWORD"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, [current_user.is_admin, current_user.user_id, limit])
            return list(cursor.fetchall())


def fetch_webhard_media_by_file_id(current_user: CurrentUser, file_id: int) -> list[dict[str, Any]]:
    sql = """
        SELECT file_id, owner_user_id, file_name, display_name, file_size, content_type,
               content_kind, thumbnail_path, original_created_at, created_at, updated_at
        FROM wh_file
        WHERE deleted_yn = 'N'
          AND content_kind IN ('IMAGE', 'VIDEO')
          AND file_id = %s
          AND (%s OR owner_user_id = %s)
    """
    with psycopg.connect(
        host=settings.MEDIA_CONFIG["WEBHARD_DB_HOST"],
        port=settings.MEDIA_CONFIG["WEBHARD_DB_PORT"],
        dbname=settings.MEDIA_CONFIG["WEBHARD_DB_DATABASE"],
        user=settings.MEDIA_CONFIG["WEBHARD_DB_USERNAME"],
        password=settings.MEDIA_CONFIG["WEBHARD_DB_PASSWORD"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, [file_id, current_user.is_admin, current_user.user_id])
            return list(cursor.fetchall())


def fetch_webhard_file(current_user: CurrentUser, file_id: int, allow_public: bool = False) -> dict[str, Any] | None:
    sql = """
        SELECT file_id, owner_user_id, file_name, storage_path, thumbnail_path, content_type
        FROM wh_file
        WHERE deleted_yn = 'N'
          AND file_id = %s
          AND (%s OR owner_user_id = %s OR %s)
    """
    with psycopg.connect(
        host=settings.MEDIA_CONFIG["WEBHARD_DB_HOST"],
        port=settings.MEDIA_CONFIG["WEBHARD_DB_PORT"],
        dbname=settings.MEDIA_CONFIG["WEBHARD_DB_DATABASE"],
        user=settings.MEDIA_CONFIG["WEBHARD_DB_USERNAME"],
        password=settings.MEDIA_CONFIG["WEBHARD_DB_PASSWORD"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, [file_id, current_user.is_admin, current_user.user_id, allow_public])
            return cursor.fetchone()


def purge_deleted_webhard_media(current_user: CurrentUser) -> int:
    collection = media_collection()
    query = {} if current_user.is_admin else {"owner_user_id": current_user.user_id}
    existing_ids = [int(item) for item in collection.distinct("webhard_file_id", query) if item]
    if not existing_ids:
        return 0
    active_ids: set[int] = set()
    for index in range(0, len(existing_ids), 500):
        active_ids.update(fetch_active_webhard_file_ids(current_user, existing_ids[index:index + 500]))
    stale_ids = [file_id for file_id in existing_ids if file_id not in active_ids]
    if not stale_ids:
        return 0
    return collection.delete_many({"webhard_file_id": {"$in": stale_ids}, **query}).deleted_count


def fetch_active_webhard_file_ids(current_user: CurrentUser, file_ids: list[int]) -> set[int]:
    if not file_ids:
        return set()
    sql = """
        SELECT file_id
        FROM wh_file
        WHERE deleted_yn = 'N'
          AND content_kind IN ('IMAGE', 'VIDEO')
          AND file_id = ANY(%s::bigint[])
          AND (%s OR owner_user_id = %s)
    """
    with psycopg.connect(
        host=settings.MEDIA_CONFIG["WEBHARD_DB_HOST"],
        port=settings.MEDIA_CONFIG["WEBHARD_DB_PORT"],
        dbname=settings.MEDIA_CONFIG["WEBHARD_DB_DATABASE"],
        user=settings.MEDIA_CONFIG["WEBHARD_DB_USERNAME"],
        password=settings.MEDIA_CONFIG["WEBHARD_DB_PASSWORD"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, [file_ids, current_user.is_admin, current_user.user_id])
            return {int(row["file_id"]) for row in cursor.fetchall()}


def media_document(row: dict[str, Any], synced_at: datetime, owner_is_admin: bool = False) -> dict[str, Any]:
    file_id = int(row["file_id"])
    content_kind = row.get("content_kind") or "OTHER"
    thumbnail_url = f"/api/media/{file_id}/thumbnail-file/" if row.get("thumbnail_path") else ""
    if not thumbnail_url and content_kind == "IMAGE":
        thumbnail_url = f"/api/media/{file_id}/content-file/"
    return {
        "webhard_file_id": file_id,
        "owner_user_id": str(row["owner_user_id"]),
        "owner_is_admin": owner_is_admin,
        "file_name": row.get("file_name") or "",
        "display_name": row.get("display_name") or row.get("file_name") or "",
        "file_size": int(row.get("file_size") or 0),
        "content_type": row.get("content_type") or "application/octet-stream",
        "content_kind": content_kind,
        "thumbnail_url": thumbnail_url,
        "content_url": f"/api/media/{file_id}/content-file/",
        "download_url": f"/api/media/{file_id}/download-file/",
        "original_created_at": row.get("original_created_at"),
        "uploaded_at": row.get("created_at"),
        "webhard_updated_at": row.get("updated_at"),
        "synced_at": synced_at,
    }
