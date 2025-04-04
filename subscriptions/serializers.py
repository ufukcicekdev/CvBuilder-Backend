from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, SubscriptionPaymentHistory, PaymentGateway
from django.utils.translation import gettext_lazy as _

class PaymentGatewaySerializer(serializers.ModelSerializer):
    """Serializer for payment gateways"""
    
    class Meta:
        model = PaymentGateway
        fields = [
            'id', 'name', 'gateway_type', 'is_active', 'is_default', 'position'
        ]
        read_only_fields = ['id']

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans"""
    
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'plan_id', 'name', 'description', 'price_monthly', 
         'plan_type', 'currency', 'features', 'is_active', "paddle_product_id", "paddle_price_id"
        ]
        read_only_fields = ['id']


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for user subscriptions"""
    plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'status', 'period', 'start_date', 
            'end_date', 'trial_end_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class SubscriptionPaymentHistorySerializer(serializers.ModelSerializer):
    """Serializer for subscription payment history"""
    
    class Meta:
        model = SubscriptionPaymentHistory
        fields = [
            'id', 'subscription', 'payment_id', 'amount', 'currency', 
            'status', 'payment_date', 'iyzico_payment_id', 'iyzico_payment_transaction_id'
        ]
        read_only_fields = ['id', 'subscription', 'payment_date']


class CreateSubscriptionSerializer(serializers.Serializer):
    """Serializer for creating a subscription"""
    plan_id = serializers.CharField(required=True)
    period = serializers.ChoiceField(choices=['monthly', 'yearly'], required=True)
    card_token = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    def validate_plan_id(self, value):
        """Validate that the plan exists and is active"""
        try:
            plan = SubscriptionPlan.objects.get(plan_id=value, is_active=True)
            return value
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError(_("Invalid or inactive subscription plan"))


class CancelSubscriptionSerializer(serializers.Serializer):
    """Serializer for canceling a subscription"""
    subscription_id = serializers.IntegerField(required=False)
    
    def validate_subscription_id(self, value):
        """Validate that the subscription exists"""
        try:
            subscription = UserSubscription.objects.get(id=value)
            return value
        except UserSubscription.DoesNotExist:
            raise serializers.ValidationError(_("Invalid subscription ID"))


class UpdateCardSerializer(serializers.Serializer):
    """Serializer for updating the card used for a subscription"""
    card_token = serializers.CharField(required=True)
    subscription_id = serializers.IntegerField(required=False)
    
    def validate_subscription_id(self, value):
        """Validate that the subscription exists"""
        try:
            subscription = UserSubscription.objects.get(id=value)
            return value
        except UserSubscription.DoesNotExist:
            raise serializers.ValidationError(_("Invalid subscription ID")) 