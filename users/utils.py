import json
import requests
from typing import Union, List
from django.conf import settings
from django.template.loader import render_to_string
import uuid
from django.utils import timezone
from django.core.mail import send_mail
from django.utils.html import strip_tags
import jwt
from datetime import datetime, timedelta
import logging
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

logger = logging.getLogger(__name__)

def send_email_via_smtp2go(
    to_list: Union[List[str], str],
    subject: str,
    html_body: str,
    text_body: str = None
) -> dict:
    """
    SMTP2GO API kullanarak email gönderir
    
    Args:
        to_list: Tek bir email adresi string olarak veya email adresleri listesi
        subject: Email konusu
        html_body: HTML formatında email içeriği
        text_body: Düz metin formatında email içeriği (opsiyonel)
    
    Returns:
        dict: API yanıtı
    """
    url = "https://api.smtp2go.com/v3/email/send"
    
    headers = {
        'Content-Type': 'application/json',
        'X-Smtp2go-Api-Key': settings.SMTP2GO_API_KEY,
        'Accept': 'application/json'
    }
    
    # to_list'i her zaman liste formatına çevir
    if isinstance(to_list, str):
        to_list = [to_list]
    
    payload = {
        "sender": settings.SMTP2GO_FROM_EMAIL,
        "to": to_list,
        "subject": subject,
        "html_body": html_body
    }
    
    # Eğer düz metin body varsa ekle
    if text_body:
        payload["text_body"] = text_body
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # 4xx, 5xx hataları için exception fırlat
        return response.json()
    except requests.exceptions.RequestException as e:
        # Hata durumunda loglama yapabilir veya exception fırlatabilirsiniz
        raise Exception(f"Email gönderilemedi: {str(e)}")

def send_verification_email(user, language='en'):
    """
    Kullanıcıya seçilen dilde doğrulama emaili gönderir
    
    Args:
        user: Doğrulama maili gönderilecek kullanıcı
        language: Email dilini belirten string (varsayılan: 'en')
    
    Returns:
        bool: Email gönderildi mi?
    """
    # Yeni bir doğrulama token'ı oluştur
    user.email_verification_token = uuid.uuid4()
    user.email_verification_token_created_at = timezone.now()
    user.save()
    
    # Doğrulama URL'ini oluştur
    verification_url = f"{settings.FRONTEND_URL}/verify-email/{user.email_verification_token}"
    
    # Dile göre email başlıklarını ayarla
    subject_by_lang = {
        'tr': 'Email Adresinizi Doğrulayın - CV Builder',
        'en': 'Verify Your Email - CV Builder',
        'fr': 'Vérifiez votre email - CV Builder',
        'de': 'Bestätigen Sie Ihre E-Mail - CV Builder',
        'es': 'Verifique su correo electrónico - CV Builder',
        'it': 'Verifica la tua email - CV Builder',
        'ru': 'Подтвердите ваш email - CV Builder',
        'ar': 'تأكيد البريد الإلكتروني - CV Builder',
        'zh': '验证您的电子邮件 - CV Builder',
        'hi': 'अपना ईमेल सत्यापित करें - CV Builder'
    }
    
    # Template context'i hazırla
    context = {
        'user': user,
        'username': user.username,
        'verification_url': verification_url,
        'language': language
    }
    
    # Email şablonunu render et
    html_content = render_to_string('emails/email_verification.html', context)
    text_content = strip_tags(html_content)  # HTML'i düz metne çevir
    
    # Email'i gönder
    try:
        send_email_via_smtp2go(
            to_list=user.email,
            subject=subject_by_lang.get(language, subject_by_lang['en']),  # Dil yoksa İngilizce kullan
            html_body=html_content,
            text_body=text_content
        )
        return True
    except Exception as e:
        # Hata durumunda False döndür ve logla
        # print(f"Doğrulama emaili gönderilemedi: {str(e)}")
        return False 

def send_password_reset_email(user, token, language='en'):
    """
    Kullanıcıya şifre sıfırlama e-postası gönderir
    
    Args:
        user: Şifre sıfırlama maili gönderilecek kullanıcı
        token: Şifre sıfırlama token'ı
        language: Email dilini belirten string (varsayılan: 'en')
    
    Returns:
        bool: Email gönderildi mi?
    """
    try:
        # Frontend URL'sini oluştur
        # print("*****************")
        # print(settings.FRONTEND_URL)
        # print("*****************")
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        
        # Dile göre email başlıklarını ayarla
        subject_by_lang = {
            'tr': 'Şifre Sıfırlama Talebi - CV Builder',
            'en': 'Password Reset Request - CV Builder',
            'fr': 'Demande de réinitialisation de mot de passe - CV Builder',
            'de': 'Anfrage zum Zurücksetzen des Passworts - CV Builder',
            'es': 'Solicitud de restablecimiento de contraseña - CV Builder',
            'it': 'Richiesta di reimpostazione della password - CV Builder',
            'ru': 'Запрос на сброс пароля - CV Builder',
            'ar': 'طلب إعادة تعيين كلمة المرور - CV Builder',
            'zh': '密码重置请求 - CV Builder',
            'hi': 'पासवर्ड रीसेट अनुरोध - CV Builder'
        }
        
        # E-posta şablonunu hazırla
        context = {
            'user': user,
            'reset_url': reset_url,
            'valid_hours': 24,  # Token geçerlilik süresi (saat)
            'language': language
        }
        html_message = render_to_string('emails/password_reset_email.html', context)
        plain_message = strip_tags(html_message)
        
        # SMTP2GO kullanarak e-postayı gönder
        send_email_via_smtp2go(
            to_list=user.email,
            subject=subject_by_lang.get(language, subject_by_lang['en']),  # Dil yoksa İngilizce kullan
            html_body=html_message,
            text_body=plain_message
        )
        
        logger.info(f"Password reset email sent to {user.email}")
        return True
    except Exception as e:
        logger.error(f"Error sending password reset email to {user.email}: {str(e)}")
        return False 