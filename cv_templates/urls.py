from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomTemplateViewSet

router = DefaultRouter()
router.register(r'templates', CustomTemplateViewSet, basename='custom-template')

urlpatterns = [
    path('', include(router.urls)),
]

# Bu URL yapılandırması şu endpointleri sağlar:
# GET /api/templates/ - Kullanıcının tüm özel şablonlarını getirir
# POST /api/templates/ - Yeni bir özel şablon oluşturur
# GET /api/templates/{id}/ - Belirli bir şablonun detaylarını getirir 
# PUT /api/templates/{id}/ - Bir şablonu günceller
# PATCH /api/templates/{id}/ - Bir şablonu kısmen günceller
# DELETE /api/templates/{id}/ - Bir şablonu siler
# GET /api/templates/for_current_user/ - Mevcut kullanıcının şablonlarını özel endpoint ile getirir 