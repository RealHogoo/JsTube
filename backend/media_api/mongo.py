from pymongo import ASCENDING, DESCENDING, MongoClient
from django.conf import settings


_client: MongoClient | None = None


def mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MEDIA_CONFIG["MEDIA_MONGO_URI"], serverSelectionTimeoutMS=5000)
    return _client


def media_collection():
    db = mongo_client()[settings.MEDIA_CONFIG["MEDIA_MONGO_DATABASE"]]
    collection = db["media_items"]
    collection.create_index([("webhard_file_id", ASCENDING)], unique=True)
    collection.create_index([("owner_user_id", ASCENDING), ("original_created_at", DESCENDING), ("webhard_file_id", DESCENDING)])
    collection.create_index([("owner_user_id", ASCENDING), ("content_kind", ASCENDING), ("original_created_at", DESCENDING)])
    collection.create_index([("owner_user_id", ASCENDING), ("tags", ASCENDING)])
    collection.create_index([("owner_user_id", ASCENDING), ("album", ASCENDING)])
    return collection

