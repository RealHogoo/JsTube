from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.http import HttpRequest, JsonResponse


WEBHARD_SERVICE = "WEBHARD_SERVICE"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    roles: list[str]
    service_permissions: dict[str, list[str]]

    @property
    def is_admin(self) -> bool:
        return "ROLE_ADMIN" in self.roles or "ROLE_SUPER_ADMIN" in self.roles

    def has_permission(self, permission: str) -> bool:
        if self.is_admin:
            return True
        permissions = self.service_permissions.get(WEBHARD_SERVICE) or self.service_permissions.get("WEBHARD-SERVICE") or []
        return normalize_code(permission) in permissions

    def has_any_webhard_permission(self) -> bool:
        if self.is_admin:
            return True
        permissions = self.service_permissions.get(WEBHARD_SERVICE) or self.service_permissions.get("WEBHARD-SERVICE") or []
        return len(permissions) > 0


def require_user(request: HttpRequest, permission: str | None = None) -> CurrentUser | JsonResponse:
    token = auth_token(request)
    if not token:
        return JsonResponse({"ok": False, "code": "UNAUTHORIZED", "message": "login is required"}, status=401)

    current_user = fetch_current_user(token)
    if current_user is None:
        return JsonResponse({"ok": False, "code": "UNAUTHORIZED", "message": "login is invalid"}, status=401)
    if not current_user.has_any_webhard_permission():
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "webhard permission is required"}, status=403)
    if permission and not current_user.has_permission(permission):
        return JsonResponse({"ok": False, "code": "FORBIDDEN", "message": "permission is required"}, status=403)
    return current_user


def auth_token(request: HttpRequest) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[len("Bearer ") :].strip()
    return request.COOKIES.get("ACCESS_TOKEN", "").strip()


def fetch_current_user(token: str) -> CurrentUser | None:
    url = f"{settings.MEDIA_CONFIG['ADMIN_SERVICE_BASE_URL']}/auth/me.json"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=5,
        )
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    body = response.json()
    if body.get("ok") is not True or not isinstance(body.get("data"), dict):
        return None
    data: dict[str, Any] = body["data"]
    user_id = str(data.get("user_id") or "")
    if not user_id:
        return None
    return CurrentUser(
        user_id=user_id,
        roles=[str(item) for item in data.get("roles") or []],
        service_permissions=normalize_permissions(data.get("service_permissions")),
    )


def normalize_permissions(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for service_code, permissions in raw.items():
        if not isinstance(permissions, list):
            continue
        result[normalize_code(str(service_code))] = [normalize_code(str(item)) for item in permissions]
    return result


def normalize_code(value: str) -> str:
    return value.strip().replace("-", "_").replace(" ", "_").upper()

