from django.apps import AppConfig


class CvTemplatesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cv_templates'
    verbose_name = 'CV Şablonları'
    
    def ready(self):
        """
        Uygulama başlatıldığında çalışacak kodlar
        """
        pass 