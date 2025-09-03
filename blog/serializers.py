from rest_framework import serializers
from .models import BlogPost, BlogTranslation

class BlogTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogTranslation
        fields = ['language', 'title', 'content']

class BlogPostSerializer(serializers.ModelSerializer):
    translations = BlogTranslationSerializer(many=True, read_only=True)

    class Meta:
        model = BlogPost
        fields = ['id', 'slug', 'status', 'created_at', 'updated_at', 'translations']

class BlogPostDetailSerializer(serializers.ModelSerializer):
    # This serializer is for the detail view, showing only one translation
    title = serializers.CharField(source='translation.title')
    content = serializers.CharField(source='translation.content')
    language = serializers.CharField(source='translation.language')

    class Meta:
        model = BlogPost
        fields = ['id', 'slug', 'status', 'created_at', 'updated_at', 'language', 'title', 'content']