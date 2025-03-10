from django.urls import path, re_path
from . import views

urlpatterns = [
    # Slash olan ve olmayan URL'leri destekle
    path('google/', views.google_auth, name='google_auth'),
    re_path(r'^google$', views.google_auth, name='google_auth_no_slash'),
    
    path('linkedin/', views.linkedin_auth, name='linkedin_auth'),
    re_path(r'^linkedin$', views.linkedin_auth, name='linkedin_auth_no_slash'),
] 