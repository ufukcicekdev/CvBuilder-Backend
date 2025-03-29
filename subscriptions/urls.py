from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet,
    UserSubscriptionViewSet,
    SubscriptionPaymentHistoryViewSet,
    PaddleWebhookView
)

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet, basename='subscription-plans')
router.register(r'subscriptions', UserSubscriptionViewSet, basename='user-subscriptions')
router.register(r'payment-history', SubscriptionPaymentHistoryViewSet, basename='payment-history')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/', PaddleWebhookView.as_view(), name='paddle-webhook'),
] 