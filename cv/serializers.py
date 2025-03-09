from rest_framework import serializers
from .models import CV, Certificate

class CertificateSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id', 
            'name', 
            'issuer', 
            'date', 
            'description', 
            'url',
            'document',
            'document_type',
            'document_url'
        ]

    def get_document_url(self, obj):
        if obj.document:
            return self.context['request'].build_absolute_uri(obj.document.url)
        return None

class CVSerializer(serializers.ModelSerializer):
    certificates = CertificateSerializer(many=True, required=False)

    class Meta:
        model = CV
        fields = [
            # ... mevcut alanlar ...
            'video_url',
            'video_description',
            'certificates',
        ]

    def update(self, instance, validated_data):
        certificates_data = validated_data.pop('certificates', [])
        
        # Mevcut sertifikaları sil
        instance.certificates.all().delete()
        
        # Yeni sertifikaları ekle
        for cert_data in certificates_data:
            document = cert_data.pop('document', None)
            certificate = Certificate.objects.create(cv=instance, **cert_data)
            if document:
                certificate.document = document
                certificate.save()
        
        return super().update(instance, validated_data) 