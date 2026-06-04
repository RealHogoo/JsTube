from django.urls import path

from . import views


urlpatterns = [
    path("health/", views.health),
    path("version/", views.version),
    path("me/", views.me),
    path("sync/", lambda request: views.options_or_view(request, views.sync)),
    path("youtube/tools/check/", views.youtube_tools_check),
    path("youtube/preview/", views.youtube_preview),
    path("youtube/import/status/", views.youtube_import_status),
    path("youtube/import/", views.youtube_import_view),
    path("media/", views.media_list),
    path("media/<int:webhard_file_id>/", views.media_detail),
    path("media/<int:webhard_file_id>/delete/", views.media_delete),
    path("media/<int:webhard_file_id>/thumbnail/", views.media_thumbnail),
    path("media/<int:webhard_file_id>/content-file/", lambda request, webhard_file_id: views.media_file_proxy(request, webhard_file_id, "content")),
    path("media/<int:webhard_file_id>/thumbnail-file/", lambda request, webhard_file_id: views.media_file_proxy(request, webhard_file_id, "thumbnail")),
    path("media/<int:webhard_file_id>/download-file/", lambda request, webhard_file_id: views.media_file_proxy(request, webhard_file_id, "download")),
    path("albums/", views.albums),
]
