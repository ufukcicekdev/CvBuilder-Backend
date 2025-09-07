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
        fields = ['id', 'slug', 'status', 'created_at', 'updated_at', 'view_count', 'translations']

class BlogPostDetailSerializer(serializers.ModelSerializer):
    # This serializer is for the detail view, showing only one translation
    title = serializers.CharField(source='translation.title')
    content = serializers.CharField(source='translation.content')
    language = serializers.CharField(source='translation.language')

    class Meta:
        model = BlogPost
        fields = ['id', 'slug', 'status', 'created_at', 'updated_at', 'view_count', 'language', 'title', 'content']



# ... diğer serializer'larınızın altına ekleyin ...

class BlogPostCreateSerializer(serializers.ModelSerializer):
    translations = BlogTranslationSerializer(many=True)

    class Meta:
        model = BlogPost
        fields = ['slug', 'status', 'translations']

    def create(self, validated_data):
        translations_data = validated_data.pop('translations')
        blog_post = BlogPost.objects.create(**validated_data)
        for translation_data in translations_data:
            BlogTranslation.objects.create(post=blog_post, **translation_data)
        return blog_post
