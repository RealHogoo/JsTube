from django.urls import path

from . import views


urlpatterns = [
    path("health/", views.health),
    path("me/", views.me),
    path("sync/", lambda request: views.options_or_view(request, views.sync)),
    path("media/", views.media_list),
    path("media/<int:webhard_file_id>/", views.media_detail),
    path("albums/", views.albums),
]

