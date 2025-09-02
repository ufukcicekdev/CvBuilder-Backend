from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('session/', views.session_view, name='session'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('me/', views.get_user_profile, name='user-profile'),
    path('upload-profile-picture/', views.upload_profile_picture, name='upload-profile-picture'),
    path('verify-email/<uuid:token>/', views.verify_email, name='verify-email'),
    path('resend-verification-email/', views.resend_verification_email, name='resend-verification-email'),
    
    # Şifre sıfırlama URL'leri
    path('forgot-password/', views.forgot_password, name='forgot-password'),
    path('reset-password/validate/<str:token>/', views.validate_reset_token, name='validate-reset-token'),
    path('reset-password/', views.reset_password, name='reset-password'),
] 