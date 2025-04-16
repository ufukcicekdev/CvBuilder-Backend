from django.db import models
from django.conf import settings
from users.models import User
from django.contrib.auth import get_user_model
from django.utils import timezone
import random
import string
from django.db import IntegrityError

User = get_user_model()

class CV(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Taslak'),
        ('completed', 'Tamamlandı'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    translation_key = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_step = models.IntegerField(default=0)
    
    # Form verileri için JSON alanları
    personal_info = models.JSONField(default=dict)
    education = models.JSONField(default=list)
    experience = models.JSONField(default=list)
    skills = models.JSONField(default=list)
    languages = models.JSONField(default=list)
    certificates = models.JSONField(default=list)  # Her sertifika için: {id, name, issuer, date, description, document_url, document_type}
    video_info = models.JSONField(default=dict)  # Video bilgileri: {url, description, type, uploaded_at}
    
    # Video alanları
    video = models.FileField(
        upload_to='cv_videos/',
        blank=True,
        null=True,
        help_text='Video dosyası yükleyebilirsiniz'
    )
    video_description = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'CV'
        verbose_name_plural = 'CVs'

    def __str__(self):
        return f"{self.user.email}'s CV - {self.title}"

    def delete(self, *args, **kwargs):
        # Video dosyasını S3'ten sil
        if self.video:
            self.video.delete()
        super().delete(*args, **kwargs)

    def generate_translation_key(self):
        """Generate a random 30-character string for URL"""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(30))

    def save(self, *args, **kwargs):
        if not self.translation_key:
            max_attempts = 5
            attempt = 0
            while attempt < max_attempts:
                try:
                    self.translation_key = self.generate_translation_key()
                    super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    attempt += 1
                    if attempt == max_attempts:
                        raise Exception("Could not generate unique translation key after multiple attempts")
        else:
            super().save(*args, **kwargs)

    @property
    def video_url(self):
        """Video URL'ini döndürür"""
        if self.video:
            return self.video.url
        return None

class CVTranslation(models.Model):
    LANGUAGE_CHOICES = [
        ('tr', 'Türkçe'),
        ('en', 'English'),
        ('es', 'Español'),
        ('zh', '中文'),
        ('ar', 'العربية'),
        ('hi', 'हिन्दी'),
        ('de', 'Deutsch')
    ]

    cv = models.ForeignKey(CV, on_delete=models.CASCADE, related_name='translations')
    language_code = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default='en'
    )
    
    # Çevrilen içerikler - Her alan için varsayılan boş değerler
    personal_info = models.JSONField(default=dict)
    education = models.JSONField(default=list)
    experience = models.JSONField(default=list)
    skills = models.JSONField(default=list)
    languages = models.JSONField(default=list)
    certificates = models.JSONField(default=list)  # Her sertifika için: {id, name, issuer, date, description, document_url, document_type}
    video_info = models.JSONField(default=dict)  # Video bilgileri: {url, description, type, uploaded_at}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cv', 'language_code')
        indexes = [
            models.Index(fields=['cv', 'language_code'])
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.cv.title} - {self.get_language_code_display()}"

    @property
    def content(self):
        """Tüm çevrilmiş içeriği tek bir dict olarak döndürür"""
        return {
            'personal_info': self.personal_info,
            'education': self.education,
            'experience': self.experience,
            'skills': self.skills,
            'languages': self.languages,
            'certificates': self.certificates,
            'video_info': self.video_info,
        }

    def update_content(self, translated_content):
        """Çevrilmiş içeriği ilgili alanlara dağıtır"""
        self.personal_info = translated_content.get('personal_info', {})
        self.education = translated_content.get('education', [])
        self.experience = translated_content.get('experience', [])
        self.skills = translated_content.get('skills', [])
        self.languages = translated_content.get('languages', [])
        self.certificates = translated_content.get('certificates', [])
        self.video_info = translated_content.get('video_info', {})
        self.save() 