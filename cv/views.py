from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import CV
from .serializers import CVSerializer
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
import json

def cv_view(request, cv_id, translation_key, language, template_id=None):
    """CV görüntüleme view'i"""
    cv = get_object_or_404(CV, id=cv_id, translation_key=translation_key)
    
    # Template ID'yi URL'den al veya query parameter'dan al
    if not template_id:
        template_id = request.GET.get('template', 'web-template1')
    
    # CV verilerini JSON olarak hazırla
    cv_data = CVSerializer(cv).data
    
    # Template'i render et
    template_name = f'cv/templates/{template_id}.html'  # Template ID'ye göre template seç
    html_content = render_to_string(template_name, {'cv': cv_data})
    
    return HttpResponse(html_content)

class CVViewSet(viewsets.ModelViewSet):
    queryset = CV.objects.all()
    serializer_class = CVSerializer

    def get_queryset(self):
        return CV.objects.prefetch_related('certificates').all()

    @action(detail=True, methods=['POST'], url_path='upload-video')
    def upload_video(self, request, pk=None):
        try:
            cv = self.get_object()
            
            if 'video' in request.FILES:
                # Eski videoyu sil
                if cv.video:
                    cv.video.delete()
                
                cv.video = request.FILES['video']
            
            cv.video_description = request.data.get('video_description', '')
            cv.save()
            
            return Response({'status': 'success'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def generate_web(self, request, pk=None):
        cv = self.get_object()
        template_id = request.data.get('template_id')
        language = request.data.get('language', 'en')  # Default language is English
        
        if not template_id:
            return Response(
                {'error': 'Template ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # CV verilerini JSON olarak hazırla
            cv_data = self.get_serializer(cv).data
            
            # Template'i render et
            template_name = f'cv/templates/{template_id}.html'
            html_content = render_to_string(template_name, {'cv': cv_data})
            
            # HTML dosyasını kaydet - translation_key ve language kullanarak
            file_name = f'cv_{cv.id}_{cv.translation_key}_{language}_{template_id}.html'
            file_path = f'media/cv_templates/{file_name}'
            
            with open(file_path, 'w') as f:
                f.write(html_content)
            
            # URL'i döndür - yeni format ile (template_id dahil)
            web_url = f'/cv/{template_id}/{cv.id}/{cv.translation_key}/{language}/'
            return Response({
                'web_url': web_url,
                'translation_key': cv.translation_key,
                'lang': language
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 