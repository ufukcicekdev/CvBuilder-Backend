
from rest_framework import generics
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.db.models import F
from .models import BlogPost, BlogTranslation
from .serializers import BlogPostSerializer, BlogPostDetailSerializer, BlogPostCreateSerializer

class BlogListView(generics.ListAPIView):
    """
    Lists all published blog posts. Each post will include all its translations.
    This can be used for a blog index page that might show titles in multiple languages.
    """
    queryset = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).prefetch_related('translations')
    serializer_class = BlogPostSerializer
    permission_classes = [AllowAny]

class BlogDetailView(generics.RetrieveAPIView):
    """
    Retrieves a single blog post, but returns the content for a specific language.
    The language is determined by the 'lang' query parameter.
    e.g., /api/blog/my-awesome-post/?lang=tr
    """
    queryset = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED)
    serializer_class = BlogPostDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_object(self):
        # Get the parent BlogPost object using the slug
        post = super().get_object()

        # Increment the view count atomically
        post.view_count = F('view_count') + 1
        post.save(update_fields=['view_count'])
        post.refresh_from_db()

        # Get the requested language from query params, default to 'en'
        lang_code = self.request.query_params.get('lang', 'en')

        # Get the specific translation for the post
        try:
            translation = post.translations.get(language=lang_code)
        except BlogTranslation.DoesNotExist:
            # If the requested language doesn't exist, try to get the first available one
            translation = post.translations.first()
            if not translation:
                # This would happen if a post has no translations at all
                # We can return a custom object or raise a 404
                # For simplicity, we attach a dummy translation object
                translation = BlogTranslation(title="No Translation Found", content="", language="")

        # Attach the found translation to the post object for the serializer
        post.translation = translation
        return post



# ... diğer view'larınızın altına ekleyin ...

class BlogPostCreateView(generics.CreateAPIView):
    """
    POST isteklerini kabul ederek yeni bir blog gönderisi ve çevirilerini oluşturur.
    """
    queryset = BlogPost.objects.all()
    serializer_class = BlogPostCreateSerializer
    # Production'da burayı IsAuthenticated gibi bir yetkiyle değiştirin
    permission_classes = [AllowAny] 
