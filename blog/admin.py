
from django.contrib import admin
from .models import BlogPost, BlogTranslation

class BlogTranslationInline(admin.StackedInline):
    """
    Allows editing of BlogTranslation models directly within the BlogPost admin page.
    """
    model = BlogTranslation
    extra = 1  # Show one extra empty form for a new translation by default
    fields = ('language', 'title', 'content')

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    """
    Admin configuration for the main BlogPost model.
    """
    list_display = ('slug', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('slug', 'translations__title', 'translations__content')
    inlines = [BlogTranslationInline]
