from rest_framework import serializers
from .models import CV, CVTranslation
from profiles.serializers import LanguageSerializer

class CVTranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(read_only=True)
    personal_info = serializers.JSONField(required=False)
    education = serializers.JSONField(required=False)
    experience = serializers.JSONField(required=False)
    skills = serializers.JSONField(required=False)
    languages = serializers.JSONField(required=False)
    certificates = serializers.JSONField(required=False)
    video_info = serializers.JSONField(required=False)
    
    class Meta:
        model = CVTranslation
        fields = [
            'id',
            'language_code',
            'personal_info',
            'education',
            'experience',
            'skills',
            'languages',
            'certificates',
            'video_info',
            'created_at',
            'updated_at'
        ]

class CVSerializer(serializers.ModelSerializer):
    translations = CVTranslationSerializer(many=True, read_only=True)
    personal_info = serializers.JSONField(required=False)
    education = serializers.JSONField(required=False, default=list)
    experience = serializers.JSONField(required=False, default=list)
    skills = serializers.JSONField(required=False, default=list)
    languages = serializers.JSONField(required=False, default=list)
    certificates = serializers.JSONField(required=False, default=list)
    video_info = serializers.JSONField(required=False)  
    class Meta:
        model = CV
        fields = [
            'id', 'title', 'status', 'current_step',
            'user', 'personal_info', 'experience',
            'education', 'skills', 'languages',
            'created_at', 'updated_at', 'translations',
            'certificates', 'video_info'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

    def get_video_url(self, obj):
        if obj.video:
            return self.context['request'].build_absolute_uri(obj.video.url)
        return None

    def to_representation(self, instance):
        # Önce orijinal veriyi al
        data = super().to_representation(instance)
        
        # Request'ten dil kodunu al
        request = self.context.get('request')
        if not request:
            return data
            
        # Accept-Language header'ından dil kodunu al
        lang_code = request.headers.get('Accept-Language', 'en')[:2].lower()
        
        try:
            # İstenen dildeki çeviriyi bul
            translation = instance.translations.filter(language_code=lang_code).first()
            
            if translation:
                # Çeviri varsa, ana veriyi çeviri ile değiştir
                data['language'] = lang_code
                personal_info = translation.personal_info
                # Kullanıcının profil resmini ekle
                if instance.user.profile_picture:
                    personal_info['photo'] = request.build_absolute_uri(instance.user.profile_picture.url)
                data['personal_info'] = personal_info
                data['education'] = translation.education
                data['experience'] = translation.experience
                data['skills'] = translation.skills
                data['languages'] = translation.languages
                data['certificates'] = translation.certificates
                
                # video_info alanını güncelle
                video_info = translation.video_info or {}
                if instance.video:
                    video_info['url'] = request.build_absolute_uri(instance.video.url)
                if instance.video_description:
                    video_info['description'] = instance.video_description
                data['video_info'] = video_info
              
            else:
                # İngilizce çeviriyi dene
                en_translation = instance.translations.filter(language_code='en').first()
                if en_translation:
                    data['language'] = 'en'
                    personal_info = en_translation.personal_info
                    # Kullanıcının profil resmini ekle
                    if instance.user.profile_picture:
                        personal_info['photo'] = request.build_absolute_uri(instance.user.profile_picture.url)
                    data['personal_info'] = personal_info
                    data['education'] = en_translation.education
                    data['experience'] = en_translation.experience
                    data['skills'] = en_translation.skills
                    data['languages'] = en_translation.languages
                    data['certificates'] = en_translation.certificates
                    
                    # video_info alanını güncelle
                    video_info = en_translation.video_info or {}
                    if instance.video:
                        video_info['url'] = request.build_absolute_uri(instance.video.url)
                    if instance.video_description:
                        video_info['description'] = instance.video_description
                    data['video_info'] = video_info
                
        except Exception as e:
            print(f"Error in to_representation: {str(e)}")
            # Hata durumunda orijinal veriyi dön
            data['language'] = 'en'
            data['video_info'] = {
                'url': self.get_video_url(instance),
                'description': instance.video_description,
                'type': None,
                'uploaded_at': None
            }
        
        return data

    def validate_personal_info(self, value):
        if value:
            required_fields = ['full_name', 'email', 'phone', 'address']
            missing_fields = [field for field in required_fields if not value.get(field)]
            if missing_fields:
                raise serializers.ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
        return value

    def validate_current_step(self, value):
        if value < 0 or value > 6:  # 6 yerine len(steps) kullanılabilir
            raise serializers.ValidationError("Invalid step value")
        return value

    def create(self, validated_data):
        validated_data.setdefault('personal_info', {})
        validated_data.setdefault('education', [])
        validated_data.setdefault('experience', [])
        validated_data.setdefault('skills', [])
        validated_data.setdefault('languages', [])
        validated_data.setdefault('certificates', [])
        validated_data.setdefault('video_info', {})
        
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Video işlemi
        if 'video' in validated_data:
            if instance.video:
                instance.video.delete()
            instance.video = validated_data.pop('video')
        
        if 'video_description' in validated_data:
            instance.video_description = validated_data.pop('video_description')

        return super().update(instance, validated_data) 