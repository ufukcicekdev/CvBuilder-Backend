from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CVViewSet, cv_view
from django.views.generic import TemplateView

router = DefaultRouter()
router.register(r'cvs', CVViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    # CV görüntüleme URL'i - eski format
    path('cv/<int:cv_id>/<str:translation_key>/<str:language>/', cv_view, name='cv_view'),
    # CV görüntüleme URL'i - yeni format (template_id ile)
    path('cv/<str:template_id>/<int:cv_id>/<str:translation_key>/<str:language>/', cv_view, name='cv_view_with_template'),
] 