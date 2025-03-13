from django.shortcuts import render
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.utils.translation import get_language
from django.db import transaction
from datetime import timedelta
import uuid

from .models import SubscriptionPlan, UserSubscription, SubscriptionPaymentHistory
from .serializers import (
    SubscriptionPlanSerializer, 
    UserSubscriptionSerializer, 
    SubscriptionPaymentHistorySerializer,
    CreateSubscriptionSerializer,
    CancelSubscriptionSerializer,
    UpdateCardSerializer
)
from .iyzico_utils import (
    create_subscription, 
    cancel_subscription, 
    get_subscription_details,
    update_subscription_card
)

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for subscription plans"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        """Return active subscription plans"""
        return SubscriptionPlan.objects.filter(is_active=True)
    
    def list(self, request, *args, **kwargs):
        """List all active subscription plans"""
        # Get the language from the request
        language = request.META.get('HTTP_ACCEPT_LANGUAGE', 'en')
        
        # Get the queryset and serialize it
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # Return the serialized data
        return Response(serializer.data)


class UserSubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for user subscriptions"""
    serializer_class = UserSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return the user's subscription"""
        return UserSubscription.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get the user's current subscription"""
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        except UserSubscription.DoesNotExist:
            return Response(
                {"detail": "No active subscription found"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def create_subscription(self, request):
        """Create a new subscription"""
        serializer = CreateSubscriptionSerializer(data=request.data)
        
        if serializer.is_valid():
            plan_id = serializer.validated_data['plan_id']
            period = serializer.validated_data['period']
            card_token = serializer.validated_data.get('card_token')
            
            try:
                # Get the plan
                plan = SubscriptionPlan.objects.get(plan_id=plan_id, is_active=True)
                
                # Check if the user already has a subscription
                try:
                    existing_subscription = UserSubscription.objects.get(user=request.user)
                    
                    # If the subscription is active, return an error
                    if existing_subscription.status == 'active':
                        return Response(
                            {"detail": "User already has an active subscription"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # If the subscription is not active, update it
                    existing_subscription.plan = plan
                    existing_subscription.period = period
                    existing_subscription.status = 'active'  # Changed from 'pending' to 'active' for demo
                    existing_subscription.save()
                    
                    subscription = existing_subscription
                except UserSubscription.DoesNotExist:
                    # Create a new subscription
                    subscription = UserSubscription.objects.create(
                        user=request.user,
                        plan=plan,
                        period=period,
                        status='active'  # Changed from 'pending' to 'active' for demo
                    )
                
                # Create the subscription in Iyzico (simulated for demo)
                with transaction.atomic():
                    try:
                        # Generate a fake subscription reference code instead of calling Iyzico
                        subscription_reference_code = f"demo_sub_{request.user.id}_{plan_id}_{period}_{str(uuid.uuid4())[:8]}"
                        
                        # Update the subscription with the reference code
                        subscription.iyzico_subscription_reference_code = subscription_reference_code
                        subscription.iyzico_customer_reference_code = f"demo_customer_{request.user.id}_{str(uuid.uuid4())[:8]}"
                        subscription.status = 'active'
                        subscription.start_date = timezone.now()
                        
                        # Set the end date based on the period
                        if period == 'monthly':
                            subscription.end_date = timezone.now() + timedelta(days=30)
                        else:
                            subscription.end_date = timezone.now() + timedelta(days=365)
                        
                        subscription.save()
                        
                        # Create a payment history record (for demo)
                        payment_amount = plan.price_monthly if period == 'monthly' else plan.price_yearly
                        
                        SubscriptionPaymentHistory.objects.create(
                            subscription=subscription,
                            payment_id=f"demo_payment_{subscription.id}_{str(uuid.uuid4())[:8]}",
                            amount=payment_amount,
                            currency=plan.currency,
                            status='success',
                            payment_date=timezone.now(),
                            iyzico_payment_id=f"demo_iyzico_payment_{str(uuid.uuid4())[:8]}",
                            iyzico_payment_transaction_id=f"demo_transaction_{str(uuid.uuid4())[:8]}"
                        )
                        
                        # Return the subscription
                        serializer = UserSubscriptionSerializer(subscription)
                        return Response(serializer.data, status=status.HTTP_201_CREATED)
                    except Exception as e:
                        # If there's an error, rollback the transaction
                        transaction.set_rollback(True)
                        return Response(
                            {"detail": str(e)},
                            status=status.HTTP_400_BAD_REQUEST
                        )
            except SubscriptionPlan.DoesNotExist:
                return Response(
                    {"detail": "Invalid or inactive subscription plan"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def cancel_subscription(self, request):
        """Cancel the user's subscription"""
        serializer = CancelSubscriptionSerializer(data=request.data)
        
        if serializer.is_valid():
            subscription_id = serializer.validated_data.get('subscription_id')
            
            try:
                # Get the subscription
                if subscription_id:
                    subscription = UserSubscription.objects.get(id=subscription_id, user=request.user)
                else:
                    subscription = UserSubscription.objects.get(user=request.user)
                
                # Check if the subscription is active
                if subscription.status != 'active':
                    return Response(
                        {"detail": "Subscription is not active"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Cancel the subscription in Iyzico
                try:
                    cancel_subscription(subscription.iyzico_subscription_reference_code)
                    
                    # Update the subscription status
                    subscription.status = 'canceled'
                    subscription.save()
                    
                    # Return the subscription
                    serializer = UserSubscriptionSerializer(subscription)
                    return Response(serializer.data)
                except Exception as e:
                    return Response(
                        {"detail": str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "No active subscription found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def update_card(self, request):
        """Update the card used for a subscription"""
        serializer = UpdateCardSerializer(data=request.data)
        
        if serializer.is_valid():
            card_token = serializer.validated_data['card_token']
            subscription_id = serializer.validated_data.get('subscription_id')
            
            try:
                # Get the subscription
                if subscription_id:
                    subscription = UserSubscription.objects.get(id=subscription_id, user=request.user)
                else:
                    subscription = UserSubscription.objects.get(user=request.user)
                
                # Check if the subscription is active
                if subscription.status != 'active':
                    return Response(
                        {"detail": "Subscription is not active"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Update the card in Iyzico
                try:
                    update_subscription_card(
                        subscription.iyzico_subscription_reference_code, card_token
                    )
                    
                    # Return the subscription
                    serializer = UserSubscriptionSerializer(subscription)
                    return Response(serializer.data)
                except Exception as e:
                    return Response(
                        {"detail": str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "No active subscription found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionPaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for subscription payment history"""
    serializer_class = SubscriptionPaymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return the user's subscription payment history"""
        try:
            subscription = UserSubscription.objects.get(user=self.request.user)
            return SubscriptionPaymentHistory.objects.filter(subscription=subscription)
        except UserSubscription.DoesNotExist:
            return SubscriptionPaymentHistory.objects.none()


class IyzicoWebhookView(APIView):
    """View for handling Iyzico webhooks"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        """Handle Iyzico webhook events"""
        # Get the event type from the request
        event_type = request.data.get('event_type')
        
        # Handle different event types
        if event_type == 'subscription.order.success':
            # Payment was successful
            subscription_reference_code = request.data.get('subscriptionReferenceCode')
            
            try:
                # Get the subscription
                subscription = UserSubscription.objects.get(
                    iyzico_subscription_reference_code=subscription_reference_code
                )
                
                # Create a payment history record
                SubscriptionPaymentHistory.objects.create(
                    subscription=subscription,
                    payment_id=request.data.get('paymentId'),
                    amount=request.data.get('price'),
                    currency=subscription.plan.currency,
                    status='success',
                    iyzico_payment_id=request.data.get('paymentId'),
                    iyzico_payment_transaction_id=request.data.get('paymentTransactionId')
                )
                
                # Update the subscription end date
                if subscription.period == 'monthly':
                    subscription.end_date = timezone.now() + timedelta(days=30)
                else:
                    subscription.end_date = timezone.now() + timedelta(days=365)
                
                subscription.save()
                
                return Response(status=status.HTTP_200_OK)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif event_type == 'subscription.order.failure':
            # Payment failed
            subscription_reference_code = request.data.get('subscriptionReferenceCode')
            
            try:
                # Get the subscription
                subscription = UserSubscription.objects.get(
                    iyzico_subscription_reference_code=subscription_reference_code
                )
                
                # Create a payment history record
                SubscriptionPaymentHistory.objects.create(
                    subscription=subscription,
                    payment_id=request.data.get('paymentId'),
                    amount=request.data.get('price'),
                    currency=subscription.plan.currency,
                    status='failed',
                    iyzico_payment_id=request.data.get('paymentId'),
                    iyzico_payment_transaction_id=request.data.get('paymentTransactionId')
                )
                
                return Response(status=status.HTTP_200_OK)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif event_type == 'subscription.canceled':
            # Subscription was canceled
            subscription_reference_code = request.data.get('subscriptionReferenceCode')
            
            try:
                # Get the subscription
                subscription = UserSubscription.objects.get(
                    iyzico_subscription_reference_code=subscription_reference_code
                )
                
                # Update the subscription status
                subscription.status = 'canceled'
                subscription.save()
                
                return Response(status=status.HTTP_200_OK)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Unknown event type
            return Response(
                {"detail": "Unknown event type"},
                status=status.HTTP_400_BAD_REQUEST
            )
