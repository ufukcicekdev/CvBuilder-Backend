from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, PasswordResetToken
from django.contrib.auth.password_validation import validate_password
from .utils import send_verification_email
from django.contrib.auth.hashers import make_password
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    language = serializers.CharField(write_only=True, required=False, default='en')

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'password', 'password2', 'first_name', 'last_name', 
                 'user_type', 'social_id', 'social_provider', 'profile_picture', 'language')
        extra_kwargs = {
            'email': {'required': True},
            'user_type': {'required': True},
            'password': {'write_only': True},
            'password2': {'write_only': True},
            'language': {'write_only': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": ["password.mismatch"]})

        # Email ve username benzersizlik kontrolü
        email = attrs.get('email')
        username = attrs.get('username')

        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": ["exists"]})

        if username and User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": ["exists"]})

        return attrs

    def create(self, validated_data):
        # language alanını validated_data'dan çıkar
        language = validated_data.pop('language', 'en')
        validated_data.pop('password2')
        
        # Kullanıcıyı oluştur
        user = User.objects.create_user(**validated_data)
        
        # Dil tercihini kontrol et
        # Desteklenen diller listesi
        supported_languages = ['tr', 'en', 'fr', 'de', 'es', 'it', 'ru', 'ar', 'zh', 'hi']
        
        # Eğer dil desteklenmiyorsa, varsayılan olarak İngilizce kullan
        if language not in supported_languages:
            language = 'en'
        
        # Email doğrulama mailini seçilen dilde gönder
        send_verification_email(user, language)
        
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['user_type'] = user.user_type
        return token

    def validate(self, attrs):
        try:
            user = User.objects.get(email=attrs['email'])
            if not user.is_active:
                raise serializers.ValidationError({
                    "email": ["account.inactive"]
                })
            if not user.email_verified:
                raise serializers.ValidationError({
                    "email": ["email.not_verified"]
                })
        except User.DoesNotExist:
            raise serializers.ValidationError({
                "email": ["credentials.invalid"]
            })

        try:
            validated_data = super().validate(attrs)
            return validated_data
        except serializers.ValidationError:
            raise serializers.ValidationError({
                "password": ["credentials.invalid"]
            })

class UserProfileSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone', 'birth_date', 
                 'profession', 'company_name', 'company_website', 'company_position', 
                 'company_size', 'profile_picture_url', 'user_type']
        read_only_fields = ['id', 'email', 'username', 'profile_picture_url', 'user_type']
        extra_kwargs = {
            'profile_picture': {'write_only': True}
        }

    def get_profile_picture_url(self, obj):
        if obj.profile_picture:
            return obj.profile_picture.url
        return None 

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            # Güvenlik nedeniyle kullanıcı bulunamasa bile hata döndürmüyoruz
            pass
        return value

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Şifreler eşleşmiyor."})
        
        try:
            token_obj = PasswordResetToken.objects.get(token=data['token'])
            if not token_obj.is_valid():
                raise serializers.ValidationError({"token": "Geçersiz veya süresi dolmuş token."})
            self.token_obj = token_obj
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({"token": "Geçersiz token."})
        
        return data
    
    def save(self):
        user = self.token_obj.user
        user.set_password(self.validated_data['password'])
        user.save()
        
        # Token'ı kullanılmış olarak işaretle
        self.token_obj.is_used = True
        self.token_obj.save()
        
        return user 

class PasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    password_confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        # Şifrelerin eşleştiğini kontrol et
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Şifreler eşleşmiyor"})
        
        # Şifre doğrulaması yap
        try:
            validate_password(data['password'])
        except Exception as e:
            raise serializers.ValidationError({"password": list(e)})
        
        return data 