from django.urls import path
from . import views

urlpatterns = [
    path('google/', views.google_auth, name='google_auth'),
    path('linkedin/', views.linkedin_auth, name='linkedin_auth'),
] 