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
import json

from .models import SubscriptionPlan, UserSubscription, SubscriptionPaymentHistory
from .serializers import (
    SubscriptionPlanSerializer, 
    UserSubscriptionSerializer, 
    SubscriptionPaymentHistorySerializer,
    CreateSubscriptionSerializer,
    CancelSubscriptionSerializer,
    UpdateCardSerializer
)
from .paddle_utils import (
    generate_checkout_url,
    cancel_subscription, 
    get_subscription_details,
    update_payment_method,
    verify_webhook_signature,
    get_subscription_plan
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
                    existing_subscription.status = 'pending'
                    existing_subscription.save()
                    
                    subscription = existing_subscription
                except UserSubscription.DoesNotExist:
                    # Create a new subscription
                    subscription = UserSubscription.objects.create(
                        user=request.user,
                        plan=plan,
                        period=period,
                        status='pending'
                    )
                
                # Generate a Paddle checkout URL
                checkout_data = generate_checkout_url(request.user, plan, period)
                
                # Get the price_id for Paddle.js v2 API
                price_id = get_subscription_plan(plan, period)
                
                # Return the checkout data needed for Paddle.js
                response_data = {
                    'subscription_id': subscription.id,
                    'checkout_url': checkout_data['checkout_url'],
                    'price_id': price_id,  # Price ID for Paddle.js v2
                    'custom_data': checkout_data.get('custom_data'),  # Include custom data
                }
                
                # Include checkout_id if available
                if 'checkout_id' in checkout_data:
                    response_data['checkout_id'] = checkout_data['checkout_id']
                    
                # Include passthrough for backward compatibility
                if 'passthrough' in checkout_data:
                    response_data['passthrough'] = checkout_data['passthrough']
                
                return Response(response_data, status=status.HTTP_200_OK)
                
            except SubscriptionPlan.DoesNotExist:
                return Response(
                    {"detail": "Plan not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def cancel_subscription(self, request):
        """Cancel a subscription"""
        serializer = CancelSubscriptionSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Get the subscription
                subscription = UserSubscription.objects.get(user=request.user)
                
                # Cancel the subscription in Paddle
                if subscription.paddle_subscription_id:
                    cancel_subscription(subscription.paddle_subscription_id)
                
                # Update the subscription status
                subscription.status = 'canceled'
                subscription.save()
                
                # Return the updated subscription
                serializer = UserSubscriptionSerializer(subscription)
                return Response(serializer.data)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"detail": "No subscription found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def update_payment_method(self, request):
        """Get a URL to update payment method"""
        try:
            # Get the subscription
            subscription = UserSubscription.objects.get(user=request.user)
            
            # Get the update URL from Paddle
            if not subscription.paddle_subscription_id:
                return Response(
                    {"detail": "No active Paddle subscription found"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            update_url = update_payment_method(subscription.paddle_subscription_id)
            
            # Return the URL
            return Response({
                'update_url': update_url
            })
        except UserSubscription.DoesNotExist:
            return Response(
                {"detail": "No subscription found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SubscriptionPaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for subscription payment history"""
    serializer_class = SubscriptionPaymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return the user's payment history"""
        try:
            subscription = UserSubscription.objects.get(user=self.request.user)
            return SubscriptionPaymentHistory.objects.filter(subscription=subscription)
        except UserSubscription.DoesNotExist:
            return SubscriptionPaymentHistory.objects.none()


class PaddleWebhookView(APIView):
    """View for handling Paddle Billing webhooks"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        """Handle Paddle Billing webhook events"""
        # Store the raw request body for signature verification
        raw_body = request.body.decode('utf-8')
        
        # Verify the webhook signature
        if not verify_webhook_signature(request.headers, raw_body):
            return Response(
                {"detail": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get the event type and data
        try:
            # Parse the webhook payload
            webhook_data = json.loads(raw_body)
            event_type = webhook_data.get('event_type')
            event_data = webhook_data.get('data', {})
            
            print(f"Received Paddle webhook: {event_type}")
            
            # Handle different types of webhook events
            if event_type == 'subscription.created':
                return self._handle_subscription_created(event_data)
            elif event_type == 'subscription.updated':
                return self._handle_subscription_updated(event_data)
            elif event_type == 'subscription.canceled':
                return self._handle_subscription_canceled(event_data)
            elif event_type == 'subscription.payment.succeeded':
                return self._handle_payment_succeeded(event_data)
            elif event_type == 'subscription.payment.failed':
                return self._handle_payment_failed(event_data)
            else:
                # Log unhandled event type
                print(f"Unhandled Paddle webhook event type: {event_type}")
                # Default response for unhandled events
                return Response({"status": "ignored"}, status=status.HTTP_200_OK)
                
        except Exception as e:
            print(f"Error processing Paddle webhook: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_subscription_created(self, event_data):
        """Handle subscription.created webhook"""
        try:
            # Get the subscription data
            subscription = event_data.get('subscription', {})
            subscription_id = subscription.get('id')
            status = subscription.get('status')
            
            # Get the custom data
            custom_data = {}
            try:
                custom_data_str = subscription.get('custom_data', '{}')
                custom_data = json.loads(custom_data_str)
            except Exception as e:
                print(f"Error parsing custom_data: {str(e)}")
            
            user_id = custom_data.get('user_id')
            plan_id = custom_data.get('plan_id')
            period = custom_data.get('period')
            
            if not user_id or not plan_id or not period:
                print("Missing required custom data fields")
                return Response(
                    {"status": "error", "detail": "Missing required custom data"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the plan
            try:
                plan = SubscriptionPlan.objects.get(plan_id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response(
                    {"status": "error", "detail": "Plan not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get or create the subscription
            try:
                user_subscription, created = UserSubscription.objects.get_or_create(
                    user_id=user_id,
                    defaults={
                        'plan': plan,
                        'period': period,
                        'status': 'pending'
                    }
                )
                
                # Update the subscription with Paddle details
                user_subscription.paddle_subscription_id = subscription_id
                user_subscription.paddle_customer_id = subscription.get('customer_id')
                
                # Set status based on Paddle subscription status
                if status == 'active':
                    user_subscription.status = 'active'
                    user_subscription.start_date = timezone.now()
                    
                    # Set the end date based on the period and current billing period
                    current_period_end = subscription.get('current_billing_period', {}).get('ends_at')
                    if current_period_end:
                        user_subscription.end_date = current_period_end
                    else:
                        # Fallback if no period end date is provided
                        if period == 'monthly':
                            user_subscription.end_date = timezone.now() + timedelta(days=30)
                        else:
                            user_subscription.end_date = timezone.now() + timedelta(days=365)
                
                user_subscription.save()
                
                return Response({"status": "success"}, status=status.HTTP_200_OK)
                
            except Exception as e:
                print(f"Error updating subscription: {str(e)}")
                return Response(
                    {"status": "error", "detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            print(f"Error handling subscription.created: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_subscription_updated(self, event_data):
        """Handle subscription.updated webhook"""
        try:
            # Get the subscription data
            subscription = event_data.get('subscription', {})
            subscription_id = subscription.get('id')
            status = subscription.get('status')
            
            if not subscription_id:
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status
            if status:
                if status == 'active':
                    user_subscription.status = 'active'
                elif status == 'paused':
                    user_subscription.status = 'paused'
                elif status == 'canceled':
                    user_subscription.status = 'canceled'
                elif status == 'past_due':
                    user_subscription.status = 'past_due'
            
            # Update end date if present
            current_period_end = subscription.get('current_billing_period', {}).get('ends_at')
            if current_period_end:
                user_subscription.end_date = current_period_end
            
            user_subscription.save()
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.updated: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_subscription_canceled(self, event_data):
        """Handle subscription.canceled webhook"""
        try:
            # Get the subscription ID
            subscription = event_data.get('subscription', {})
            subscription_id = subscription.get('id')
            
            if not subscription_id:
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status
            user_subscription.status = 'canceled'
            user_subscription.save()
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.canceled: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_payment_succeeded(self, event_data):
        """Handle subscription.payment.succeeded webhook"""
        try:
            # Get the transaction data
            transaction = event_data.get('transaction', {})
            subscription = event_data.get('subscription', {})
            
            subscription_id = subscription.get('id')
            transaction_id = transaction.get('id')
            
            if not subscription_id or not transaction_id:
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Create a payment record
            amount = transaction.get('amount', 0)
            currency = transaction.get('currency_code', 'USD')
            
            payment = SubscriptionPaymentHistory.objects.create(
                subscription=user_subscription,
                payment_id=f"paddle_payment_{transaction_id}",
                amount=amount,
                currency=currency,
                status='success',
                paddle_payment_id=transaction_id,
                paddle_checkout_id=transaction.get('checkout', {}).get('id')
            )
            
            # Update subscription end date
            current_period_end = subscription.get('current_billing_period', {}).get('ends_at')
            if current_period_end:
                user_subscription.end_date = current_period_end
            else:
                # Fallback if no period end date
                if user_subscription.period == 'monthly':
                    user_subscription.end_date = timezone.now() + timedelta(days=30)
                else:
                    user_subscription.end_date = timezone.now() + timedelta(days=365)
            
            # Ensure subscription is marked as active
            user_subscription.status = 'active'
            user_subscription.save()
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling payment.succeeded: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_payment_failed(self, event_data):
        """Handle subscription.payment.failed webhook"""
        try:
            # Get the transaction data
            transaction = event_data.get('transaction', {})
            subscription = event_data.get('subscription', {})
            
            subscription_id = subscription.get('id')
            transaction_id = transaction.get('id')
            
            if not subscription_id or not transaction_id:
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Create a failed payment record
            amount = transaction.get('amount', 0)
            currency = transaction.get('currency_code', 'USD')
            
            payment = SubscriptionPaymentHistory.objects.create(
                subscription=user_subscription,
                payment_id=f"paddle_payment_{transaction_id}",
                amount=amount,
                currency=currency,
                status='failed',
                paddle_payment_id=transaction_id,
                paddle_checkout_id=transaction.get('checkout', {}).get('id')
            )
            
            # Don't update the subscription status yet, Paddle will try again
            # If needed, you could update to 'past_due' or similar status
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling payment.failed: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
