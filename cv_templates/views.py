from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from .models import CustomTemplate
from .serializers import CustomTemplateSerializer

class CustomTemplateViewSet(viewsets.ModelViewSet):
    """
    Özel şablonlar için API endpoints
    
    list:
        Tüm özel şablonları listeler (sadece kullanıcının kendisi)
        
    create:
        Yeni bir özel şablon oluşturur
        
    retrieve:
        Bir şablonun detaylarını getirir
        
    update:
        Bir şablonu tam günceller
        
    partial_update:
        Bir şablonu kısmen günceller
        
    destroy:
        Bir şablonu siler
    """
    serializer_class = CustomTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Bu görünüm, sadece istekte bulunan kullanıcının kendi şablonlarını döndürür
        """
        return CustomTemplate.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Şablon oluşturulurken mevcut kullanıcıyı otomatik ekler
        """
        serializer.save(user=self.request.user)
        
    def create(self, request, *args, **kwargs):
        """
        Yeni bir özel şablon oluşturur
        """
        # Eğer template_data kısmı yoksa, tüm request.data'yı template_data olarak kullan
        data = request.data.copy()
        
        if 'template_data' not in data:
            # name field'ı template_data içinden çıkart
            name = data.pop('name', 'Untitled Template')
            # request.data'yı template_data olarak kullan
            data = {'name': name, 'template_data': data}
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        
    def update(self, request, *args, **kwargs):
        """
        Mevcut bir şablonu günceller
        """
        # Eğer template_data kısmı yoksa, tüm request.data'yı template_data olarak kullan
        data = request.data.copy()
        
        if 'template_data' not in data:
            # name field'ı template_data içinden çıkart
            name = data.pop('name', None)
            # request.data'yı template_data olarak kullan
            update_data = {'template_data': data}
            if name:
                update_data['name'] = name
        else:
            update_data = data
        
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=update_data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        if getattr(instance, '_prefetched_objects_cache', None):
            # Prefetch önbelleğini temizle
            instance._prefetched_objects_cache = {}
            
        return Response(serializer.data)
        
    @action(detail=False, methods=['get'])
    def for_current_user(self, request):
        """
        Sadece mevcut kullanıcının şablonlarını listeler
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data) 