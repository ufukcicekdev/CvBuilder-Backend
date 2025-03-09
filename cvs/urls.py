from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CVViewSet, get_cv_by_translation

router = DefaultRouter()
router.register('cvs', CVViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('cvs/<int:id>/<str:translation_key>/<str:lang>/', get_cv_by_translation, name='cv-by-translation'),
] 