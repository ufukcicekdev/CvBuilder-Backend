# authentication.py
from django.conf import settings
from rest_framework import authentication
from rest_framework import exceptions
import secrets

class StaticAPIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        # İstek başlığından (header) bizim belirlediğimiz anahtarı al
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return None # Anahtar yoksa, başka authentication metodları denensin

        # Ayarlardaki anahtarla gelen anahtarı güvenli bir şekilde karşılaştır
        if not secrets.compare_digest(api_key, settings.N8N_API_KEY):
            raise exceptions.AuthenticationFailed('Invalid API Key.')

        # Başarılı olursa, bir kullanıcıya bağlamadan anonim olarak yetkilendir
        # (veya isterseniz burada sabit bir kullanıcıya bağlayabilirsiniz)
        return (None, None)
