from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/cv/(?P<cv_id>\d+)/(?P<translation_key>[^/]+)/(?P<lang>[^/]+)/$', consumers.CVConsumer.as_asgi()),
] 