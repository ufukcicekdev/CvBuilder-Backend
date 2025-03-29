from rest_framework import viewsets, status, generics
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import authenticate
from .models import User, PasswordResetToken
from .serializers import UserSerializer, CustomTokenObtainPairSerializer, UserProfileSerializer, PasswordResetSerializer
import logging
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .authentication import TokenAuthentication
from .utils import send_verification_email, send_password_reset_email
from django.utils import timezone
import uuid
from django.shortcuts import get_object_or_404
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.hashers import make_password

logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = UserSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Email doğrulama maili serializer içinde gönderiliyor
            # send_verification_email(user)
            
            auth = TokenAuthentication()
            result = auth.authenticate_credentials(
                request.data.get('email'),
                request.data.get('password')
            )
            
            if 'error' in result:
                return Response({'error': result['error']}, status=result['status'])
            
            return Response({
                'user': serializer.data,
                'tokens': {
                    'access': result['access'],
                    'refresh': result['refresh']
                },
                'message': 'Kayıt başarılı. Lütfen email adresinizi doğrulayın.'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = UserSerializer

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({
                'email': ['field.required'] if not email else [],
                'password': ['field.required'] if not password else []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Kullanıcıyı bul
        try:
            user = User.objects.get(email=email)
            
            # Email doğrulaması yapılmış mı kontrol et
            if not user.is_email_verified and not user.social_provider:  # Sosyal giriş yapan kullanıcılar için doğrulama gerekmez
                return Response({
                    'email': ['email.not_verified']
                }, status=status.HTTP_400_BAD_REQUEST)
                
            # Kullanıcı aktif mi kontrol et
            if not user.is_active:
                return Response({
                    'email': ['account.inactive']
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except User.DoesNotExist:
            # Kullanıcı bulunamadı - kimlik bilgileri hatalı
            return Response({
                'email': ['credentials.invalid']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Kimlik doğrulama
        user = authenticate(email=email, password=password)
        if not user:
            return Response({
                'email': ['credentials.invalid']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Token oluştur
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'user_type': user.user_type,
                'paddle_customer_id': user.paddle_customer_id
            }
        })

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user 

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def get_user_profile(request):
    if request.method == 'GET':
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)
    elif request.method == 'PATCH':
        try:
            user = request.user
            data = request.data.copy()
            
            # Profil resmi yükleme işlemi artık ayrı bir endpoint'te
            if 'profile_picture' in request.FILES:
                return Response(
                    {'error': 'Profile picture upload should be done via /api/users/upload-profile-picture/ endpoint'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Content-Type'a göre işlem yap
            content_type = request.content_type if hasattr(request, 'content_type') else ''
            
            logger.info(f"Profile update request with Content-Type: {content_type}")
            logger.info(f"Request data: {data}")
            
            # Diğer alanları güncelle
            serializer = UserProfileSerializer(user, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            
            logger.error(f"Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Profile update error: {str(e)}")
            logger.error(f"Error type: {e.__class__.__name__}")
            return Response({
                'error': f'Failed to update profile: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_profile_picture(request):
    if 'profile_picture' not in request.FILES:
        return Response({
            'error': 'No picture provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = request.user
        logger.info(f"Uploading profile picture for user: {user.email}")
        
        # Eski resmi sil
        if user.profile_picture:
            logger.info(f"Deleting old profile picture: {user.profile_picture.name}")
            try:
                user.profile_picture.delete(save=False)
                logger.info("Old profile picture deleted successfully")
            except Exception as e:
                logger.error(f"Error deleting old profile picture: {str(e)}")
        
        # Yeni resmi kaydet
        file = request.FILES['profile_picture']
        logger.info(f"New file details - Name: {file.name}, Size: {file.size}, Content Type: {file.content_type}")
        
        # Dosya tipi kontrolü
        if not file.content_type.startswith('image/'):
            return Response({
                'error': 'Invalid file type. Only images are allowed.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Dosya boyutu kontrolü (5MB)
        if file.size > 5 * 1024 * 1024:
            return Response({
                'error': 'File size too large. Maximum size is 5MB.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Dosyayı kaydet
            user.profile_picture = file
            user.save()
            
            # Dosya yükleme sonrası bilgileri logla
            logger.info(f"Profile picture saved successfully. URL: {user.profile_picture.url}")
            logger.info(f"File path in storage: {user.profile_picture.name}")
        except Exception as e:
            logger.error(f"Error saving profile picture: {str(e)}")
            logger.error(f"Error type: {e.__class__.__name__}")
            raise
        
        return Response({
            'message': 'Profile picture uploaded successfully',
            'profile_picture_url': user.profile_picture.url
        })
    except Exception as e:
        logger.error(f"Profile picture upload error: {str(e)}")
        logger.error(f"Error details: {e.__class__.__name__}")
        return Response({
            'error': f'Failed to upload profile picture: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TokenRefreshView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        auth = TokenAuthentication()
        result = auth.refresh_token(refresh_token)
        
        if 'error' in result:
            return Response({'error': result['error']}, status=result['status'])
        
        return Response(result)

class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        auth = TokenAuthentication()
        result = auth.blacklist_token(refresh_token)
        
        return Response(
            {'message': result.get('message', 'Logged out')}, 
            status=result.get('status', status.HTTP_200_OK)
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def verify_email(request, token):
    """
    Email doğrulama token'ını kontrol eder ve kullanıcının hesabını doğrular
    """
    # Dil tercihini belirle:
    # 1. Önce request.query_params içindeki 'language' parametresini kontrol et
    # 2. Yoksa, 'Accept-Language' HTTP başlığını kontrol et
    # 3. Hiçbiri yoksa varsayılan olarak 'en' kullan
    language = request.query_params.get('language')
    
    if not language:
        # HTTP başlığından dil bilgisini al
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if accept_language:
            # İlk dil kodunu al (örn: 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7' -> 'tr')
            language = accept_language.split(',')[0].split('-')[0].lower()
        else:
            # Varsayılan dil
            language = 'en'
    
    # Desteklenen diller listesi
    supported_languages = ['tr', 'en', 'fr', 'de', 'es', 'it', 'ru', 'ar', 'zh', 'hi']
    
    # Eğer dil desteklenmiyorsa, varsayılan olarak İngilizce kullan
    if language not in supported_languages:
        language = 'en'
    
    try:
        # Token ile kullanıcıyı bul
        user = User.objects.get(email_verification_token=token)
        
        # Token'ın geçerlilik süresini kontrol et (24 saat)
        if user.email_verification_token_created_at:
            token_age = timezone.now() - user.email_verification_token_created_at
            if token_age.days > 1:  # 24 saatten fazla ise
                # Dile göre hata mesajı
                error_messages = {
                    'tr': 'Doğrulama bağlantısının süresi dolmuş. Lütfen yeni bir doğrulama maili talep edin.',
                    'en': 'Verification link has expired. Please request a new verification email.',
                    'fr': 'Le lien de vérification a expiré. Veuillez demander un nouvel e-mail de vérification.',
                    'de': 'Der Bestätigungslink ist abgelaufen. Bitte fordern Sie eine neue Bestätigungs-E-Mail an.',
                    'es': 'El enlace de verificación ha caducado. Solicite un nuevo correo electrónico de verificación.',
                    'it': 'Il link di verifica è scaduto. Richiedi una nuova email di verifica.',
                    'ru': 'Срок действия ссылки для подтверждения истек. Пожалуйста, запросите новое письмо с подтверждением.',
                    'ar': 'انتهت صلاحية رابط التحقق. يرجى طلب بريد إلكتروني جديد للتحقق.',
                    'zh': '验证链接已过期。请请求新的验证电子邮件。',
                    'hi': 'सत्यापन लिंक की समय सीमा समाप्त हो गई है। कृपया एक नया सत्यापन ईमेल अनुरोध करें।'
                }
                
                return Response({
                    'error': error_messages.get(language, error_messages['en'])
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Kullanıcıyı doğrulanmış olarak işaretle
        user.is_email_verified = True
        user.email_verification_token = None
        user.email_verification_token_created_at = None
        user.save()
        
        # Dile göre başarı mesajı
        success_messages = {
            'tr': 'Email adresiniz başarıyla doğrulandı. Şimdi giriş yapabilirsiniz.',
            'en': 'Your email has been successfully verified. You can now log in.',
            'fr': 'Votre e-mail a été vérifié avec succès. Vous pouvez maintenant vous connecter.',
            'de': 'Ihre E-Mail wurde erfolgreich verifiziert. Sie können sich jetzt anmelden.',
            'es': 'Su correo electrónico ha sido verificado con éxito. Ahora puede iniciar sesión.',
            'it': 'La tua email è stata verificata con successo. Ora puoi accedere.',
            'ru': 'Ваш адрес электронной почты успешно подтвержден. Теперь вы можете войти в систему.',
            'ar': 'تم التحقق من بريدك الإلكتروني بنجاح. يمكنك الآن تسجيل الدخول.',
            'zh': '您的电子邮件已成功验证。您现在可以登录。',
            'hi': 'आपका ईमेल सफलतापूर्वक सत्यापित किया गया है। अब आप लॉग इन कर सकते हैं।'
        }
        
        return Response({
            'message': success_messages.get(language, success_messages['en'])
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        # Dile göre hata mesajı
        error_messages = {
            'tr': 'Geçersiz doğrulama bağlantısı.',
            'en': 'Invalid verification link.',
            'fr': 'Lien de vérification invalide.',
            'de': 'Ungültiger Bestätigungslink.',
            'es': 'Enlace de verificación no válido.',
            'it': 'Link di verifica non valido.',
            'ru': 'Недействительная ссылка для подтверждения.',
            'ar': 'رابط التحقق غير صالح.',
            'zh': '无效的验证链接。',
            'hi': 'अमान्य सत्यापन लिंक।'
        }
        
        return Response({
            'error': error_messages.get(language, error_messages['en'])
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_email(request):
    """
    Kullanıcıya yeni bir doğrulama maili gönderir
    """
    email = request.data.get('email')
    
    # Dil tercihini belirle:
    # 1. Önce request.data içindeki 'language' parametresini kontrol et
    # 2. Yoksa, 'Accept-Language' HTTP başlığını kontrol et
    # 3. Hiçbiri yoksa varsayılan olarak 'en' kullan
    language = request.data.get('language')
    
    if not language:
        # HTTP başlığından dil bilgisini al
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if accept_language:
            # İlk dil kodunu al (örn: 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7' -> 'tr')
            language = accept_language.split(',')[0].split('-')[0].lower()
        else:
            # Varsayılan dil
            language = 'en'
    
    # Desteklenen diller listesi
    supported_languages = ['tr', 'en', 'fr', 'de', 'es', 'it', 'ru', 'ar', 'zh', 'hi']
    
    # Eğer dil desteklenmiyorsa, varsayılan olarak İngilizce kullan
    if language not in supported_languages:
        language = 'en'
    
    if not email:
        return Response({
            'error': 'Email adresi gereklidir.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(email=email)
        
        # Kullanıcı zaten doğrulanmış mı kontrol et
        if user.is_email_verified:
            return Response({
                'message': 'Email adresiniz zaten doğrulanmış.'
            }, status=status.HTTP_200_OK)
        
        # Yeni doğrulama maili gönder
        send_verification_email(user, language)
        
        return Response({
            'message': 'Doğrulama maili gönderildi. Lütfen email kutunuzu kontrol edin.'
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        # Güvenlik nedeniyle kullanıcı bulunamasa bile başarılı mesajı döndür
        return Response({
            'message': 'Eğer bu email adresi sistemimizde kayıtlıysa, doğrulama maili gönderilecektir.'
        }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    """
    Şifre sıfırlama e-postası gönderir
    """
    # print("DEBUG: forgot_password fonksiyonu çağrıldı")
    email = request.data.get('email')
    
    # Dil tercihini belirle:
    # 1. Önce request.data içindeki 'language' parametresini kontrol et
    # 2. Yoksa, 'Accept-Language' HTTP başlığını kontrol et
    # 3. Hiçbiri yoksa varsayılan olarak 'en' kullan
    language = request.data.get('language')
    
    if not language:
        # HTTP başlığından dil bilgisini al
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if accept_language:
            # İlk dil kodunu al (örn: 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7' -> 'tr')
            language = accept_language.split(',')[0].split('-')[0].lower()
        else:
            # Varsayılan dil
            language = 'en'
    
    # Desteklenen diller listesi
    supported_languages = ['tr', 'en', 'fr', 'de', 'es', 'it', 'ru', 'ar', 'zh', 'hi']
    
    # Eğer dil desteklenmiyorsa, varsayılan olarak İngilizce kullan
    if language not in supported_languages:
        language = 'en'
    
    # print(f"DEBUG: Gelen email: {email}")
    
    if not email:
        # print("DEBUG: Email adresi bulunamadı")
        return Response({'error': 'Email adresi gereklidir'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # print(f"DEBUG: Kullanıcı aranıyor: {email}")
        user = User.objects.get(email=email)
        # print(f"DEBUG: Kullanıcı bulundu: {user.username}")
    except User.DoesNotExist:
        # print(f"DEBUG: Kullanıcı bulunamadı: {email}")
        # Güvenlik nedeniyle kullanıcı bulunamasa bile başarılı yanıt döndür
        return Response({'message': 'Şifre sıfırlama bağlantısı gönderildi (eğer hesap varsa)'}, status=status.HTTP_200_OK)
    
    # Önceki sıfırlama tokenlarını iptal et
    # print(f"DEBUG: Önceki tokenlar siliniyor: {user.email}")
    PasswordResetToken.objects.filter(user=user).delete()
    
    # Yeni token oluştur
    # print("DEBUG: Yeni token oluşturuluyor")
    reset_token = PasswordResetToken.objects.create(
        user=user,
        token=str(uuid.uuid4()),
        expires_at=timezone.now() + timezone.timedelta(hours=24)
    )
    # print(f"DEBUG: Token oluşturuldu: {reset_token.token}")
    
    # E-posta gönder
    # print(f"DEBUG: E-posta gönderiliyor: {user.email}")
    result = send_password_reset_email(user, reset_token.token, language)
    # print(f"DEBUG: E-posta gönderme sonucu: {result}")
    
    return Response({'message': 'Şifre sıfırlama bağlantısı e-posta adresinize gönderildi'}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([AllowAny])
def validate_reset_token(request, token):
    """
    Şifre sıfırlama token'ını doğrular
    """
    try:
        reset_token = PasswordResetToken.objects.get(token=token)
        
        # Token süresi dolmuş mu kontrol et
        if reset_token.expires_at < timezone.now():
            reset_token.delete()
            return Response({'error': 'Token süresi dolmuş'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Token kullanılmış mı kontrol et
        if reset_token.used:
            return Response({'error': 'Token zaten kullanılmış'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'message': 'Token geçerli'}, status=status.HTTP_200_OK)
    
    except PasswordResetToken.DoesNotExist:
        return Response({'error': 'Geçersiz token'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    """
    Şifre sıfırlama işlemini gerçekleştirir
    """
    serializer = PasswordResetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    token = serializer.validated_data['token']
    password = serializer.validated_data['password']
    
    try:
        reset_token = PasswordResetToken.objects.get(token=token)
        
        # Token süresi dolmuş mu kontrol et
        if reset_token.expires_at < timezone.now():
            reset_token.delete()
            return Response({'error': 'Token süresi dolmuş'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Token kullanılmış mı kontrol et
        if reset_token.used:
            return Response({'error': 'Token zaten kullanılmış'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Şifreyi güncelle
        user = reset_token.user
        user.password = make_password(password)
        user.save()
        
        # Token'ı kullanıldı olarak işaretle
        reset_token.used = True
        reset_token.save()
        
        return Response({'message': 'Şifreniz başarıyla sıfırlandı'}, status=status.HTTP_200_OK)
    
    except PasswordResetToken.DoesNotExist:
        return Response({'error': 'Geçersiz token'}, status=status.HTTP_400_BAD_REQUEST) 