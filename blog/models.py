
from django.db import models
from django.utils.text import slugify
from django_ckeditor_5.fields import CKEditor5Field

class BlogPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DF', 'Draft'
        PUBLISHED = 'PB', 'Published'

    slug = models.SlugField(max_length=200, unique=True, help_text="The unique identifier for a post, shared across all translations.")
    status = models.CharField(max_length=2, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.slug

class BlogTranslation(models.Model):
    class Language(models.TextChoices):
        TURKISH = 'tr', 'Türkçe'
        ENGLISH = 'en', 'English'
        GERMAN = 'de', 'Deutsch'
        SPANISH = 'es', 'Español'
        CHINESE = 'zh', '中文'
        ARABIC = 'ar', 'العربية'
        HINDI = 'hi', 'हिन्दी'

    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='translations')
    language = models.CharField(max_length=2, choices=Language.choices)
    title = models.CharField(max_length=200)
    content = CKEditor5Field('Content', config_name='extends')

    class Meta:
        unique_together = ('post', 'language')

    def __str__(self):
        return f"{self.post.slug} ({self.get_language_display()})"
