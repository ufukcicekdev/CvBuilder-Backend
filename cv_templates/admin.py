from django.contrib import admin
from .models import CustomTemplate

@admin.register(CustomTemplate)
class CustomTemplateAdmin(admin.ModelAdmin):
    """
    Özel şablonlar için admin panel yapılandırması
    """
    list_display = ('name', 'user', 'created_at', 'updated_at')
    list_filter = ('user',)
    search_fields = ('name', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'name')
        }),
        ('Şablon Verileri', {
            'fields': ('template_data',),
            'classes': ('collapse',)
        }),
        ('Zaman Bilgisi', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    ) 