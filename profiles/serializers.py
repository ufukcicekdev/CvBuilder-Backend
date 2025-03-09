from rest_framework import serializers
from .models import Profile, Skill, Language, Experience

class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ('id', 'name')

class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ('id', 'name', 'code')

class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = ('id', 'company', 'position', 'start_date', 'end_date', 'description')

class ProfileSerializer(serializers.ModelSerializer):
    skills = SkillSerializer(many=True)
    languages = LanguageSerializer(many=True)
    experiences = ExperienceSerializer(many=True, read_only=True)

    class Meta:
        model = Profile
        fields = ('id', 'headline', 'summary', 'video_intro', 'skills', 
                 'languages', 'experiences', 'created_at', 'updated_at')

    def create(self, validated_data):
        skills_data = validated_data.pop('skills')
        languages_data = validated_data.pop('languages')
        profile = Profile.objects.create(**validated_data)
        
        for skill_data in skills_data:
            skill, _ = Skill.objects.get_or_create(**skill_data)
            profile.skills.add(skill)
        
        for language_data in languages_data:
            language, _ = Language.objects.get_or_create(**language_data)
            profile.languages.add(language)
        
        return profile 