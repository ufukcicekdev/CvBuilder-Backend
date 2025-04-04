from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet,
    UserSubscriptionViewSet,
    PaddleWebhookView,
    PayTRWebhookView,
    PaymentGatewayViewSet,
    CurrentSubscriptionViewSet
)

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet)
router.register(r'subscriptions', UserSubscriptionViewSet, basename='user-subscription')
router.register(r'current', CurrentSubscriptionViewSet, basename='current-subscription')
router.register(r'payment-gateways', PaymentGatewayViewSet, basename='payment-gateway')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/', PaddleWebhookView.as_view(), name='paddle-webhook'),
    path('paytr-webhook/', PayTRWebhookView.as_view(), name='paytr-webhook'),
] 