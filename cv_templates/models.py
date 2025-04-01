from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomTemplate(models.Model):
    """
    Kullanıcıya özel CV şablonları için model
    
    Kullanıcıların kendi oluşturdukları özel CV şablonlarını saklar.
    template_data alanı, şablonun tüm özelliklerini (layout, renkler, fontlar, vb.) içeren JSON veriyi tutar.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='custom_templates')
    name = models.CharField(max_length=255)
    template_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Özel Şablon'
        verbose_name_plural = 'Özel Şablonlar'
        
    def __str__(self):
        return f"{self.name} - {self.user.username}" 