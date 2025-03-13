from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from users.views import UserViewSet, LoginView, TokenRefreshView, LogoutView
from profiles.views import ProfileViewSet, SkillViewSet, LanguageViewSet
from cvs.views import CVViewSet, get_cv_by_translation
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.generic import TemplateView

router = DefaultRouter()
router.register(r'profiles', ProfileViewSet, basename='profile')
router.register(r'skills', SkillViewSet)
router.register(r'languages', LanguageViewSet)
router.register(r'cvs', CVViewSet, basename='cv')

@api_view(['GET'])
def health_check(request):
    return Response({"status": "healthy"})

urlpatterns = [
    path('admin/', admin.site.urls),    
    path('api/', include(router.urls)),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/users/', include('users.urls')),
    path('api/auth/', include('social_auth.urls')),
    path('', include('social_django.urls', namespace='social')),
    path('api/contact/', include('contact.urls')),
    path('health/', health_check, name='health_check'),
    # WebSocket test sayfası
    path('websocket-test/', TemplateView.as_view(template_name='web/websocket_test.html'), name='websocket_test'),
    # CV translation endpoint
    path('cvs/<int:id>/<str:translation_key>/<str:lang>/', get_cv_by_translation, name='cv-by-translation'),
    path('api/subscriptions/', include('subscriptions.urls')),
] 

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
