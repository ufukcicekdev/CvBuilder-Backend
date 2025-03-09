from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
import logging

logger = logging.getLogger(__name__)

class TokenAuthentication(JWTAuthentication):
    def __init__(self):
        super().__init__()
        self.user_model = None

    def authenticate_credentials(self, email, password):
        """Email ve şifre ile kullanıcıyı doğrula ve token üret"""
        try:
            user = authenticate(email=email, password=password)
            if user is None:
                return {
                    'error': 'Invalid credentials',
                    'status': status.HTTP_401_UNAUTHORIZED
                }

            refresh = RefreshToken.for_user(user)
            return {
                'user': {
                    'id': user.id,
                    'email': user.email,
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return {
                'error': 'Authentication failed',
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR
            }

    def refresh_token(self, refresh_token):
        """Refresh token ile yeni access token üret"""
        try:
            refresh = RefreshToken(refresh_token)
            return {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        except TokenError as e:
            logger.error(f"Token refresh error: {str(e)}")
            return {
                'error': 'Invalid refresh token',
                'status': status.HTTP_401_UNAUTHORIZED
            }
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return {
                'error': 'Token refresh failed',
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR
            }

    def blacklist_token(self, refresh_token):
        """Refresh token'ı blacklist'e ekle (logout için)"""
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return {
                'message': 'Successfully logged out',
                'status': status.HTTP_200_OK
            }
        except Exception as e:
            logger.error(f"Token blacklist error: {str(e)}")
            return {
                'error': 'Logout failed',
                'status': status.HTTP_400_BAD_REQUEST
            }

    def verify_token(self, token):
        """Token'ın geçerliliğini kontrol et"""
        try:
            return self.get_validated_token(token)
        except TokenError as e:
            logger.error(f"Token verification error: {str(e)}")
            return None 