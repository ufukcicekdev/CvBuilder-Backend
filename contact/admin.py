from django.contrib import admin
from .models import Contact

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'status', 'created_at')
    list_filter = ('status', 'subject', 'created_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('created_at', 'updated_at', 'ip_address', 'user_agent')
    fieldsets = (
        (None, {
            'fields': ('name', 'email', 'subject', 'message')
        }),
        ('Status', {
            'fields': ('status', 'admin_notes')
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    ) 