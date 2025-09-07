
from django.db import models
from django.utils.text import slugify
from django_ckeditor_5.fields import CKEditor5Field

class BlogPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DF', 'Draft'
        PUBLISHED = 'PB', 'Published'

    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        blank=True, 
        null=True, 
        help_text="The unique identifier for a post. Generated automatically from the title of the first translation."
    )
    status = models.CharField(max_length=2, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    view_count = models.PositiveIntegerField(default=0, help_text="The number of times the post has been viewed.")

    def __str__(self):
        return self.slug or f"Post (ID: {self.id})"

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
        display_slug = self.post.slug or f"Post (ID: {self.post.id})"
        return f"{display_slug} ({self.get_language_display()})"

    def save(self, *args, **kwargs):
        if not self.post.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while BlogPost.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.post.slug = slug
            self.post.save()
        
        super(BlogTranslation, self).save(*args, **kwargs)
