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
    try:
        token = request.data.get('token')
        if not token:
            return Response({'error': 'No token provided'}, status=status.HTTP_400_BAD_REQUEST)

        idinfo = id_token.verify_oauth2_token(token, requests.Request(), SOCIAL_AUTH_GOOGLE_OAUTH2_KEY)

        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        email = idinfo['email']
        first_name = idinfo.get('given_name', '')
        last_name = idinfo.get('family_name', '')

        try:
            user = User.objects.get(email=email)

            if not user.email_verified:
                user.email_verified = True
                user.save()

            if not user.paddle_customer_id:
                try:
                    from subscriptions.paddle_utils import create_customer
                    customer_id = create_customer(user)
                    if customer_id:
                        user.paddle_customer_id = customer_id
                        user.save(update_fields=['paddle_customer_id'])
                except Exception as e:
                    pass

        except User.DoesNotExist:
            user = User.objects.create(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                email_verified=True,
                auth_provider='google'
            )

            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
            except Exception as e:
                pass

            from users.models import Profile
            Profile.objects.create(
                user=user,
                language='en'
            )

            try:
                from subscriptions.models import UserSubscription, SubscriptionPlan
                from django.utils import timezone
                from datetime import timedelta
                
                subscription_exists = hasattr(user, 'subscription')
                
                if not subscription_exists:
                    free_plan = SubscriptionPlan.objects.filter(plan_type='free', is_active=True).first()
                    
                    if free_plan:
                        current_time = timezone.now()
                        trial_end = current_time + timedelta(days=7)
                        
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
            except Exception as e:
                pass

        serializer = UserSerializer(user)
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

    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def linkedin_auth(request):
    code = request.data.get('code')
    try:
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
        
        if created:
            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
            except Exception as e:
                pass
        elif not user.paddle_customer_id:
            try:
                from subscriptions.paddle_utils import create_customer
                customer_id = create_customer(user)
                if customer_id:
                    user.paddle_customer_id = customer_id
                    user.save(update_fields=['paddle_customer_id'])
            except Exception as e:
                pass

        try:
            from subscriptions.models import UserSubscription, SubscriptionPlan
            from django.utils import timezone
            from datetime import timedelta
            
            subscription_exists = hasattr(user, 'subscription')
            
            if not subscription_exists:
                free_plan = SubscriptionPlan.objects.filter(plan_type='free', is_active=True).first()
                
                if free_plan:
                    current_time = timezone.now()
                    trial_end = current_time + timedelta(days=7)
                    
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
        except Exception as e:
            pass

        serializer = UserSerializer(user)
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