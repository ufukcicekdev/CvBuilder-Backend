from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Contact
from .serializers import ContactSerializer

@api_view(['POST'])
@permission_classes([AllowAny])  # İsteği herkesin yapabilmesine izin ver
def contact_view(request):
    try:
        serializer = ContactSerializer(data=request.data)
        if serializer.is_valid():
            # Önce contact nesnesini oluştur
            contact = serializer.save()
            
            # IP adresini al
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            # User Agent bilgisini al
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # IP ve User Agent bilgilerini kaydet
            contact.ip_address = ip_address
            contact.user_agent = user_agent
            contact.save()

            return Response(
                {"message": "Mesajınız başarıyla gönderildi"},
                status=status.HTTP_201_CREATED
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        print(f"Contact error: {str(e)}")  # Debug için
        return Response(
            {"error": "Mesaj gönderilirken bir hata oluştu"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 