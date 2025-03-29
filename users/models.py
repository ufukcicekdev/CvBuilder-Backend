from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator
import uuid
from django.utils import timezone
from datetime import timedelta

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email field is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_email_verified', True)  # Superuser'lar için email doğrulaması otomatik olarak yapılmış kabul edilir
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    class UserType(models.TextChoices):
        JOBSEEKER = 'jobseeker', _('Job Seeker')
        EMPLOYER = 'employer', _('Employer')

    user_type = models.CharField(
        max_length=10,
        choices=UserType.choices,
        default=UserType.JOBSEEKER
    )
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    social_id = models.CharField(max_length=255, blank=True, null=True)
    social_provider = models.CharField(max_length=50, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])
        ],
        verbose_name='Profil Resmi'
    )
    
    # Paddle müşteri ID'si
    paddle_customer_id = models.CharField(max_length=255, blank=True, null=True, verbose_name='Paddle Customer ID')
    
    # Email doğrulama alanları
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    email_verification_token_created_at = models.DateTimeField(null=True, blank=True)
    
    # İş arayan için ek alanlar
    phone = models.CharField(max_length=15, blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)
    profession = models.CharField(max_length=100, blank=True, null=True)
    
    # İşveren için ek alanlar
    company_name = models.CharField(max_length=100, blank=True, null=True)
    company_website = models.URLField(blank=True, null=True)
    company_position = models.CharField(max_length=100, blank=True, null=True)
    company_size = models.CharField(max_length=50, blank=True, null=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email 

    def get_profile_picture_url(self):
        if self.profile_picture:
            return self.profile_picture.url
        return None

    def delete(self, *args, **kwargs):
        # Kullanıcı silindiğinde profil resmini de sil
        if self.profile_picture:
            self.profile_picture.delete(save=False)
        super().delete(*args, **kwargs)

class VerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_tokens')
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} - {self.token}"

class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} - {self.token}" 