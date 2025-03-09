from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from users.models import User
from users.serializers import UserSerializer
import jwt
import requests as http_requests

@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth(request):
    token = request.data.get('token')
    try:
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), settings.GOOGLE_CLIENT_ID)

        email = idinfo['email']
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': name.split()[0] if name else '',
                'last_name': name.split()[1] if name and len(name.split()) > 1 else '',
                'social_id': idinfo['sub'],
                'social_provider': 'google',
                'profile_picture': picture,
                'user_type': 'jobseeker'
            }
        )

        serializer = UserSerializer(user)
        token = jwt.encode(
            {'user_id': user.id}, settings.SECRET_KEY, algorithm='HS256')
        
        return Response({
            'token': token,
            'user': serializer.data
        })

    except ValueError:
        return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def linkedin_auth(request):
    code = request.data.get('code')
    try:
        # LinkedIn token alma
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
            'client_id': settings.LINKEDIN_CLIENT_ID,
            'client_secret': settings.LINKEDIN_CLIENT_SECRET,
        }
        token_response = http_requests.post(token_url, data=token_data)
        access_token = token_response.json()['access_token']

        # Kullanıcı bilgilerini alma
        user_url = 'https://api.linkedin.com/v2/me'
        email_url = 'https://api.linkedin.com/v2/emailAddress'
        headers = {'Authorization': f'Bearer {access_token}'}
        
        user_response = http_requests.get(user_url, headers=headers)
        email_response = http_requests.get(email_url, headers=headers)
        
        user_data = user_response.json()
        email = email_response.json()['elements'][0]['handle~']['emailAddress']

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': user_data.get('localizedFirstName', ''),
                'last_name': user_data.get('localizedLastName', ''),
                'social_id': user_data['id'],
                'social_provider': 'linkedin',
                'user_type': 'jobseeker'
            }
        )

        serializer = UserSerializer(user)
        token = jwt.encode(
            {'user_id': user.id}, settings.SECRET_KEY, algorithm='HS256')
        
        return Response({
            'token': token,
            'user': serializer.data
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 