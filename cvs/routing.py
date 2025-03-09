from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Old URL pattern (without template_id)
    re_path(r'ws/cv/(?P<cv_id>\d+)/(?P<translation_key>[^/]+)/(?P<lang>[^/]+)/$', consumers.CVConsumer.as_asgi()),
    # New URL pattern (with template_id)
    re_path(r'ws/cv/(?P<template_id>[^/]+)/(?P<cv_id>\d+)/(?P<translation_key>[^/]+)/(?P<lang>[^/]+)/$', consumers.CVConsumer.as_asgi()),
] 