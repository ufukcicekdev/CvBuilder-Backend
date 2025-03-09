from django.db import models
from django.conf import settings

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    headline = models.CharField(max_length=100)
    summary = models.TextField()
    video_intro = models.FileField(upload_to='video_intros/', null=True, blank=True)
    skills = models.ManyToManyField('Skill')
    languages = models.ManyToManyField('Language')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Skill(models.Model):
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name

class Language(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=2)
    
    def __str__(self):
        return self.name

class Experience(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='experiences')
    company = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField()
    
    class Meta:
        ordering = ['-start_date'] 