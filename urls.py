from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # CV Templates uygulaması için API URL yönlendirmeleri
    path('api/', include('cv_templates.urls')),
    
    # API dokümentasyonu için URL (isteğe bağlı)
    path('api-auth/', include('rest_framework.urls')),
]

# Statik ve medya dosyaları için URL yapılandırması (geliştirme ortamında)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 