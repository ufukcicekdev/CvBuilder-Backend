from rest_framework import serializers
from .models import CustomTemplate

class CustomTemplateSerializer(serializers.ModelSerializer):
    """
    Özel şablonlar için serializer
    
    CustomTemplate modelini API üzerinden sunmak için kullanılır.
    """
    class Meta:
        model = CustomTemplate
        fields = ['id', 'name', 'template_data', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
        
    def to_representation(self, instance):
        """
        Şablon verilerini kullanıcı dostu bir formatta döndürür
        """
        data = super().to_representation(instance)
        
        # template_data field içinde hem JSON veri hem de id, name gibi meta bilgileri varsa
        # bunları düzgün şekilde birleştir
        if isinstance(data['template_data'], dict):
            template_data = data['template_data']
            
            # Temel alanları üst seviyeye taşı ve her zaman id'yi dahil et!
            # ÖNEMLİ: Frontend'de silme işlemi için ID'yi daima ekle
            template_data['id'] = data['id']
                
            if 'name' not in template_data and 'name' in data:
                template_data['name'] = data['name']
                
            if 'createdAt' not in template_data and 'created_at' in data:
                template_data['createdAt'] = data['created_at']
                
            if 'updatedAt' not in template_data and 'updated_at' in data:
                template_data['updatedAt'] = data['updated_at']
                
            return template_data
            
        # ID her zaman dönsün - eğer template_data bir dict değilse bile
        else:
            # Orijinal data içinde ID yoksa (olmaması beklenmez ama kontrol edelim)
            if 'id' not in data:
                data['id'] = str(instance.pk)
                
        return data 