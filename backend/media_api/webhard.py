from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from django.conf import settings

from .auth import CurrentUser
from .mongo import media_collection


def sync_from_webhard(current_user: CurrentUser, limit: int | None = None) -> dict[str, Any]:
    rows = fetch_webhard_media(current_user, limit or settings.MEDIA_CONFIG["MEDIA_SYNC_LIMIT"])
    collection = media_collection()
    now = datetime.now(timezone.utc)
    upserted = 0
    for row in rows:
        doc = media_document(row, now)
        result = collection.update_one(
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
        if result.upserted_id is not None or result.modified_count > 0:
            upserted += 1
    return {"scanned_count": len(rows), "upserted_count": upserted}


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


def media_document(row: dict[str, Any], synced_at: datetime) -> dict[str, Any]:
    file_id = int(row["file_id"])
    base_url = settings.MEDIA_CONFIG["WEBHARD_PUBLIC_BASE_URL"]
    return {
        "webhard_file_id": file_id,
        "owner_user_id": str(row["owner_user_id"]),
        "file_name": row.get("file_name") or "",
        "display_name": row.get("display_name") or row.get("file_name") or "",
        "file_size": int(row.get("file_size") or 0),
        "content_type": row.get("content_type") or "application/octet-stream",
        "content_kind": row.get("content_kind") or "OTHER",
        "thumbnail_url": f"{base_url}/file/thumbnail/{file_id}" if row.get("thumbnail_path") else f"{base_url}/file/content/{file_id}",
        "content_url": f"{base_url}/file/content/{file_id}",
        "download_url": f"{base_url}/file/download/{file_id}",
        "original_created_at": row.get("original_created_at"),
        "uploaded_at": row.get("created_at"),
        "webhard_updated_at": row.get("updated_at"),
        "synced_at": synced_at,
    }
