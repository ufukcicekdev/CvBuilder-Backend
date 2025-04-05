from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from google.oauth2 import id_token
from cv_builder import settings
from google.auth.transport import requests
from users.models import User
from users.serializers import UserSerializer
import jwt
import requests as http_requests
import logging
import traceback
import json
import os
from dotenv import load_dotenv
from rest_framework_simplejwt.tokens import RefreshToken

load_dotenv()

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv('GOOGLE_CLIENT_ID')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth(request):
    print("Google auth endpoint called")
    print(f"Request data: {request.data}")
    
    token = request.data.get('token')
    if not token:
        print("No token provided")
        return Response({'error': 'No token provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        print(f"Verifying Google token with client ID: {SOCIAL_AUTH_GOOGLE_OAUTH2_KEY}")
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), SOCIAL_AUTH_GOOGLE_OAUTH2_KEY)

        print(f"Token verified, idinfo: {json.dumps(idinfo, indent=2)}")
        
        # Token doğrulama kontrolü
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            print(f"Invalid issuer: {idinfo['iss']}")
            return Response({'error': 'Wrong issuer'}, status=status.HTTP_400_BAD_REQUEST)

        email = idinfo['email']
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')
        
        print(f"User email: {email}")

        # Kullanıcı oluşturma veya güncelleme
        is_new_user = False
        try:
            user = User.objects.get(email=email)
            print(f"Existing user found: {user.id}")
            
            # Kullanıcı varsa ve email doğrulanmamışsa, doğrula
            if not user.is_email_verified:
                user.is_email_verified = True
                user.save()
                print(f"User email verified: {user.id}")
            
            # Paddle customer ID kontrolü yap - eğer yoksa oluştur
            if not user.paddle_customer_id:
                try:
                    from subscriptions.paddle_utils import create_customer
                    customer_id = create_customer(user)
                    if customer_id:
                        user.paddle_customer_id = customer_id
                        user.save(update_fields=['paddle_customer_id'])
                        print(f"Created Paddle customer for existing user {user.email}: {customer_id}")
                except Exception as e:
                    print(f"Error creating Paddle customer for existing user {user.email}: {str(e)}")
                
        except User.DoesNotExist:
            is_new_user = True
            print(f"Creating new user with email: {email}")
            user = User.objects.create(
                email=email,
                username=email,
                first_name=name.split()[0] if name and len(name.split()) > 0 else '',
                last_name=name.split()[1] if name and len(name.split()) > 1 else '',
                social_id=idinfo['sub'],
                social_provider='google',
                profile_picture=picture,
                user_type='jobseeker',
                is_active=True,
                is_email_verified=True  # Google ile giriş yapan kullanıcılar otomatik olarak doğrulanmış kabul edilir
            )
            print(f"New user created: {user.id}")
            
            # Kullanıcı için Paddle müşteri oluştur
            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
                    print(f"Created Paddle customer for {user.email}: {customer_id}")
            except Exception as e:
                print(f"Error creating Paddle customer for {user.email}: {str(e)}")

        # Deneme süresi kontrolü - 7 günlük deneme aboneliği oluştur
        try:
            from subscriptions.models import UserSubscription, SubscriptionPlan
            from django.utils import timezone
            from datetime import timedelta
            
            # Kullanıcının zaten aboneliği var mı kontrol et
            subscription_exists = hasattr(user, 'subscription')
            
            if not subscription_exists:
                # Free plan bulunması
                free_plan = SubscriptionPlan.objects.filter(plan_type='free', is_active=True).first()
                
                if free_plan:
                    # Tarih ayarları
                    current_time = timezone.now()
                    trial_end = current_time + timedelta(days=7)  # 7 günlük deneme süresi
                    
                    # Deneme aboneliği oluşturma
                    UserSubscription.objects.create(
                        user=user,
                        plan=free_plan,
                        status='trial',
                        period='monthly',
                        start_date=current_time,
                        end_date=trial_end,
                        trial_end_date=trial_end,
                        is_active=True
                    )
                    print(f"Created 7-day trial subscription for user {user.email}")
        except Exception as e:
            print(f"Error creating trial subscription: {str(e)}")
            # Hata olsa bile login işlemine devam et - kritik değil

        serializer = UserSerializer(user)
        # JWT token oluştur
        refresh = RefreshToken.for_user(user)
        
        print(f"Authentication successful for user {user.id}")
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'user_type': user.user_type,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'profile_picture': user.profile_picture.url if user.profile_picture else None,
                'social_provider': user.social_provider,
                'social_id': user.social_id
            }
        })

    except ValueError as e:
        print(f"Invalid token: {str(e)}")
        print(traceback.format_exc())
        return Response({'error': f'Invalid token: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        print(traceback.format_exc())
        return Response({'error': f'Authentication failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        
        # Paddle müşteri kontrolü yap
        if created:
            # Yeni kullanıcı için Paddle müşteri oluştur
            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
                    print(f"Created Paddle customer for new LinkedIn user {user.email}: {customer_id}")
            except Exception as e:
                print(f"Error creating Paddle customer for new LinkedIn user {user.email}: {str(e)}")
        elif not user.paddle_customer_id:
            # Var olan kullanıcının paddle_customer_id'si yoksa oluştur
            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
                    print(f"Created Paddle customer for existing LinkedIn user {user.email}: {customer_id}")
            except Exception as e:
                print(f"Error creating Paddle customer for existing LinkedIn user {user.email}: {str(e)}")

        # Deneme süresi kontrolü - 7 günlük deneme aboneliği oluştur
        try:
            from subscriptions.models import UserSubscription, SubscriptionPlan
            from django.utils import timezone
            from datetime import timedelta
            
            # Kullanıcının zaten aboneliği var mı kontrol et
            subscription_exists = hasattr(user, 'subscription')
            
            if not subscription_exists:
                # Free plan bulunması
                free_plan = SubscriptionPlan.objects.filter(plan_type='free', is_active=True).first()
                
                if free_plan:
                    # Tarih ayarları
                    current_time = timezone.now()
                    trial_end = current_time + timedelta(days=7)  # 7 günlük deneme süresi
                    
                    # Deneme aboneliği oluşturma
                    UserSubscription.objects.create(
                        user=user,
                        plan=free_plan,
                        status='trial',
                        period='monthly',
                        start_date=current_time,
                        end_date=trial_end,
                        trial_end_date=trial_end,
                        is_active=True
                    )
                    print(f"Created 7-day trial subscription for LinkedIn user {user.email}")
        except Exception as e:
            print(f"Error creating trial subscription for LinkedIn user: {str(e)}")
            # Hata olsa bile login işlemine devam et - kritik değil

        serializer = UserSerializer(user)
        # JWT token oluştur
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'user_type': user.user_type,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'profile_picture': user.profile_picture.url if user.profile_picture else None,
                'social_provider': user.social_provider,
                'social_id': user.social_id
            }
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 