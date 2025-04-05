from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.conf import settings
from django.urls import reverse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta, datetime
import json
import logging
import secrets
import string
import requests
import time
import uuid
import base64
import hmac
import hashlib
from decimal import Decimal
import re

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.decorators import action

from .models import (
    SubscriptionPlan, UserSubscription, PaymentGateway
)
from .serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer, PaymentGatewaySerializer
)
from .paddle_utils import (
    create_customer, get_subscription_plan, generate_checkout_url, 
    cancel_subscription, get_subscription_details, update_payment_method,
    get_subscription_plan_by_price_id, verify_webhook_signature, 
    get_customer_portal_url
)
from users.models import User

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
    
    @action(detail=False, methods=['post'])
    def create_subscription(self, request):
        """Create a subscription with Paddle or PayTR
        """
        user = request.user
        subscription_id = None
        
        # Check if user is authenticated
        if not user.is_authenticated:
            return Response(
                {"detail": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get request data
        plan_id = request.data.get('plan_id')
        period = request.data.get('period')
        payment_provider = request.data.get('payment_provider', 'paddle')  # Default to paddle
        user_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1'))
        
        # Validate data
        if not plan_id or not period:
            return Response(
                {"detail": "Missing required fields"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if period is valid
        if period not in ['monthly', 'yearly']:
            return Response(
                {"detail": "Invalid period. Must be 'monthly' or 'yearly'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the subscription plan
        try:
            plan = SubscriptionPlan.objects.get(plan_id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {"detail": "Subscription plan not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Tüm ödeme sağlayıcıları için geçerli olacak şekilde abonelik oluştur
        # Ancak durum 'pending' olarak ayarla, start_date ve end_date alanlarını doldur
        # Böylece null hatası almayız
        from django.utils import timezone
        
        # Get or create the user subscription
        current_time = timezone.now()
        subscription, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={
                "plan": plan,
                "period": period,
                "status": "pending",
                "payment_provider": payment_provider,
                "start_date": current_time,  # Geçici başlangıç tarihi
                "end_date": current_time + timedelta(days=30)  # Geçici bitiş tarihi
            }
        )
        
        # If subscription exists, update it
        if not created:
            subscription.plan = plan
            subscription.period = period
            subscription.status = "pending"
            subscription.payment_provider = payment_provider
            subscription.start_date = current_time
            subscription.end_date = current_time + timedelta(days=30 if period == 'monthly' else 365)
            subscription.save()
        
        subscription_id = subscription.id
        print(f"🔔 Subscription created/updated with ID: {subscription_id}")
        
        # Ödeme sağlayıcısına göre farklı işlemler yap
        if payment_provider == 'paddle':
            # Get paddle price ID based on plan and period  
            paddle_price_id = plan.paddle_price_id
            
            # Return the checkout data
            return Response({
                "checkout_url": settings.PADDLE_CHECKOUT_URL,
                "subscription_id": subscription_id,
                "passthrough": f"{user.id}:{subscription_id}",
                "checkout_id": str(uuid.uuid4()),
                "price_id": paddle_price_id
            })
            
        elif payment_provider == 'paytr':
            # PayTR için merchant_oid'ye abonelik id'sini ekleyelim
            # NOT: PayTR, merchant_oid için alfanumerik değer gerektiriyor, alt çizgi (_) kullanılamaz!
            # Subscription ID ve random karakterlerini ayırmak için bir separator ekleyelim
            # Böylece daha sonra ID'yi regex ile daha güvenilir şekilde ayıklayabiliriz
            merchant_oid = f"cvb{subscription_id}x{uuid.uuid4().hex[:8]}"
            
            # Get the amount based on period
            amount = plan.price_yearly if period == 'yearly' else plan.price_monthly
            
            # Merchant OID'yi subscription'a kaydet
            subscription.paddle_checkout_id = merchant_oid
            subscription.save()
            
            print(f"💰 PayTR merchant_oid created: {merchant_oid} for subscription: {subscription_id}")
            
            # Use the PayTR utility to create payment form
            from .paytr_utils import create_payment_form
            payment_data = create_payment_form(
                user=user,
                merchant_oid=merchant_oid,
                plan=plan,
                amount=amount,
                period=period,
                user_ip=user_ip
            )
            
            print("PayTR payment form data:", payment_data)
            
            if payment_data.get('status') == 'success':
                response_data = {
                    "iframe_url": payment_data.get('iframe_url'),
                    "merchant_oid": payment_data.get('merchant_oid'),
                    "subscription_id": subscription_id
                }
                
                print("Sending PayTR response:", response_data)
                return Response(response_data)
            else:
                print("PayTR error:", payment_data.get('message', 'Unknown error'))
                return Response({
                    "detail": payment_data.get('message', 'Error creating PayTR payment')
                }, status=status.HTTP_400_BAD_REQUEST)
    
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
    
    @action(detail=False, methods=['get'])
    def customer_portal(self, request):
        """Get a URL to the Paddle customer portal"""
        try:
            # Get the subscription
            subscription = UserSubscription.objects.get(user=request.user)
            
            # Log customer and subscription info for debugging
            print(f"Customer portal request - User ID: {request.user.id}, Email: {request.user.email}")
            print(f"Subscription info - ID: {subscription.id}, Status: {subscription.status}")
            
            # Debug customer ID
            customer_id = None
            subscription_id = None
            
            # Make sure we have a customer ID
            if subscription.paddle_customer_id:
                customer_id = subscription.paddle_customer_id
                print(f"Using subscription paddle_customer_id: {customer_id}")
            elif hasattr(request.user, 'paddle_customer_id') and request.user.paddle_customer_id:
                customer_id = request.user.paddle_customer_id
                print(f"Using user paddle_customer_id: {customer_id}")
            else:
                print("No paddle_customer_id found in subscription or user")
                
                # In sandbox mode, we can provide a fallback URL
                if settings.PADDLE_SANDBOX:
                    print("Sandbox mode: No Paddle customer ID found, returning to frontend account page")
                    # Return the user to the frontend account page
                    frontend_account_url = f"{settings.FRONTEND_URL}/account?sandbox_mode=true"
                    return Response({
                        'portal_url': frontend_account_url,
                        'sandbox_mode': True,
                        'message': "Sandbox mode active - Customer portal is simulated in sandbox mode"
                    })
                
                return Response(
                    {"detail": "No Paddle customer ID found"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get subscription_id if available
            subscription_ids = None
            if subscription.paddle_subscription_id:
                subscription_ids = [subscription.paddle_subscription_id]
                print(f"Including paddle_subscription_id in portal request: {subscription.paddle_subscription_id}")
            
            # Get the customer portal URL from Paddle
            portal_url = get_customer_portal_url(customer_id, subscription_ids)
            
            if not portal_url:
                # In sandbox mode, provide a fallback URL
                if settings.PADDLE_SANDBOX:
                    print("Sandbox mode: Could not generate customer portal URL, returning to frontend account page")
                    # Return the user to the frontend account page
                    frontend_account_url = f"{settings.FRONTEND_URL}/account?sandbox_mode=true"
                    if subscription_ids and len(subscription_ids) > 0:
                        frontend_account_url += f"&subscription_id={subscription_ids[0]}"
                    
                    return Response({
                        'portal_url': frontend_account_url,
                        'sandbox_mode': True,
                        'message': "Sandbox mode active - Customer portal is simulated in sandbox mode"
                    })
                    
                return Response(
                    {"detail": "Could not generate customer portal URL"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Check if this is a frontend account URL (sandbox fallback)
            if portal_url.startswith(settings.FRONTEND_URL):
                return Response({
                    'portal_url': portal_url,
                    'sandbox_mode': True,
                    'message': "Sandbox mode active - Customer portal is simulated in sandbox mode"
                })
            
            # Return the real Paddle portal URL
            return Response({
                'portal_url': portal_url
            })
        except UserSubscription.DoesNotExist:
            print(f"No subscription found for user ID: {request.user.id}")
            return Response(
                {"detail": "No subscription found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error in customer_portal: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # In sandbox mode, provide a fallback URL even for exceptions
            if settings.PADDLE_SANDBOX:
                print("Sandbox mode: Error during customer portal URL generation, returning to frontend account page")
                # Return the user to the frontend account page
                frontend_account_url = f"{settings.FRONTEND_URL}/account?sandbox_mode=true&error=true"
                
                # Add subscription ID if we have it in the exception context
                if 'subscription' in locals() and hasattr(subscription, 'paddle_subscription_id') and subscription.paddle_subscription_id:
                    frontend_account_url += f"&subscription_id={subscription.paddle_subscription_id}"
                
                return Response({
                    'portal_url': frontend_account_url,
                    'sandbox_mode': True,
                    'error': str(e),
                    'message': "Error occurred while accessing Paddle customer portal"
                })
                
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CurrentSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for getting the current user subscription"""
    serializer_class = UserSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return the user's current subscription"""
        return UserSubscription.objects.filter(user=self.request.user)
        
    def list(self, request):
        """Return the user's current subscription"""
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            serializer = self.get_serializer(subscription)
            
            # Serializerdan gelen veriyi bir dict'e dönüştürelim
            response_data = dict(serializer.data)
            
            # Trial için kalan gün sayısını hesapla
            if subscription.status == 'trial' and subscription.trial_end_date:
                from django.utils import timezone
                from datetime import timedelta
                
                # Eğer deneme süresi varsa, kalan günü hesapla
                current_time = timezone.now()
                
                # Eğer deneme süresi daha bitmemişse
                if subscription.trial_end_date > current_time:
                    # Kalan zamanı timedelta olarak hesapla
                    remaining_time = subscription.trial_end_date - current_time
                    # Gün sayısına çevir (tam sayı olarak yuvarla)
                    trial_days_left = max(0, remaining_time.days)
                    
                    # Saat bazında hassasiyet için
                    if remaining_time.seconds > 0 and trial_days_left == 0:
                        trial_days_left = 1  # Son günde bile en az 1 gün göster
                else:
                    trial_days_left = 0
                    
                # Response verisine ekle
                response_data['trial_days_left'] = trial_days_left
                print(f"User {request.user.email} has {trial_days_left} trial days left")
            
            return Response(response_data)
        except UserSubscription.DoesNotExist:
            # Return an empty response with 200 OK instead of 404
            return Response(
                {
                    "status": "no_subscription",
                    "detail": "No active subscription found",
                    "has_subscription": False,
                    "user_id": request.user.id,
                    "user_email": request.user.email
                },
                status=status.HTTP_200_OK
            )
    
    # Liste görünümünü varsayılan yap
    def retrieve(self, request, pk=None):
        return self.list(request)


@method_decorator(csrf_exempt, name='dispatch')
class PaddleWebhookView(APIView):
    """View for handling Paddle Billing webhooks"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        """Handle Paddle Billing webhook events"""
        try:
            # Store the raw request body for signature verification
            raw_body = request.body.decode('utf-8')
            
            # Debug logging to help with troubleshooting
            print("=== Webhook Headers ===")
            for key, value in request.headers.items():
                if key.lower() in ['paddle-signature', 'content-type']:
                    print(f"{key}: {value}")
            
            print(f"=== Webhook Body Preview ===\n{raw_body[:500]}...\n")
            
            # Just for testing in sandbox/development mode - accept all webhooks
            if settings.PADDLE_SANDBOX:
                print("⚠️ SANDBOX MODE: Processing webhook without signature verification")
                # The rest of the code will continue normally
            else:
                # Only verify signature in production mode
                if not self.verify_webhook_signature(request.headers, raw_body):
                    print("❌ Webhook signature verification failed")
                    return Response(
                        {"detail": "Invalid signature"},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
                print("✅ Webhook signature verification passed")
            
            # Get the event type and data
            try:
                # Parse the webhook payload
                webhook_data = json.loads(raw_body)
                
                # Log the webhook data structure for debugging
                print(f"Webhook data keys: {webhook_data.keys()}")
                
                event_type = webhook_data.get('event_type')
                event_id = webhook_data.get('event_id')
                event_data = webhook_data.get('data', {})
                
                print(f"📥 Received Paddle webhook: {event_type} (Event ID: {event_id})")
                
                # Pass the entire webhook_data to handlers to support different structures
                if event_type == 'subscription.created':
                    return self._handle_subscription_created(webhook_data)
                elif event_type == 'subscription.updated':
                    return self._handle_subscription_updated(webhook_data)
                elif event_type == 'subscription.canceled':
                    return self._handle_subscription_canceled(webhook_data)
                elif event_type == 'subscription.payment.succeeded':
                    return self._handle_payment_succeeded(webhook_data)
                elif event_type == 'subscription.payment.failed':
                    return self._handle_payment_failed(webhook_data)
                elif event_type == 'transaction.paid' or event_type == 'transaction.created':
                    # Treat transaction.paid similar to payment.succeeded
                    return self._handle_transaction_paid(webhook_data)
                elif event_type == 'transaction.updated':
                    # Handle transaction updates
                    return self._handle_transaction_updated(webhook_data)
                # Yeni eklenen webhook event handler'ları 
                elif event_type == 'subscription.activated':
                    return self._handle_subscription_activated(webhook_data)
                elif event_type == 'subscription.paused':
                    return self._handle_subscription_paused(webhook_data)
                elif event_type == 'subscription.resumed':
                    return self._handle_subscription_resumed(webhook_data)
                elif event_type == 'subscription.trialing':
                    return self._handle_subscription_trialing(webhook_data)
                elif event_type == 'subscription.imported':
                    return self._handle_subscription_imported(webhook_data)
                elif event_type == 'subscription.past_due':
                    return self._handle_subscription_past_due(webhook_data)
                elif event_type == 'transaction.billed':
                    return self._handle_transaction_billed(webhook_data)
                elif event_type == 'transaction.canceled':
                    return self._handle_transaction_canceled(webhook_data)
                elif event_type == 'transaction.completed':
                    return self._handle_transaction_completed(webhook_data)
                elif event_type == 'transaction.ready':
                    return self._handle_transaction_ready(webhook_data)
                elif event_type == 'transaction.revised':
                    return self._handle_transaction_revised(webhook_data)
                elif event_type == 'transaction.past_due':
                    return self._handle_transaction_past_due(webhook_data)
                elif event_type == 'transaction.payment_failed':
                    return self._handle_transaction_payment_failed(webhook_data)
                elif event_type == 'payment_method.saved':
                    return self._handle_payment_method_saved(webhook_data)
                elif event_type == 'payment_method.deleted':
                    return self._handle_payment_method_deleted(webhook_data)
                else:
                    # Log unhandled event type
                    print(f"⚠️ Unhandled Paddle webhook event type: {event_type}")
                    # Default response for unhandled events
                    return Response({"status": "acknowledged"}, status=status.HTTP_200_OK)
                    
            except json.JSONDecodeError as e:
                print(f"❌ Error decoding webhook JSON: {str(e)}")
                return Response(
                    {"status": "error", "detail": "Invalid JSON payload"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            print(f"❌ Error processing Paddle webhook: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def verify_webhook_signature(self, headers, payload_json):
        """
        Verify that a webhook was sent by Paddle using signature verification
        
        Args:
            headers: Request headers with Paddle-Signature
            payload_json: Raw JSON payload as string
            
        Returns:
            Boolean indicating if the signature is valid
        """
        # Debug: Print settings to see if they're loaded correctly
        print(f"🔍 PADDLE_SANDBOX setting: {settings.PADDLE_SANDBOX}")
        print(f"🔍 PADDLE_WEBHOOK_SECRET: {settings.PADDLE_WEBHOOK_SECRET[:10]}...")
        
        # First check if we're in sandbox mode
        sandbox_mode = getattr(settings, 'PADDLE_SANDBOX', False)
        if sandbox_mode:
            print("⚠️ SANDBOX MODE: Bypassing signature verification")
            return True
            
        # 1. Get the Paddle-Signature header
        signature_header = headers.get('Paddle-Signature')
        if not signature_header:
            print("❌ Missing Paddle-Signature header")
            return False
        
        # Get webhook secret key from settings
        webhook_secret = getattr(settings, 'PADDLE_WEBHOOK_SECRET', None)
        
        # Print full signature header for debugging
        print(f"📝 Received signature header: {signature_header}")
            
        # For production, validate the signature
        if not webhook_secret:
            print("❌ Missing Paddle webhook secret in settings")
            return False
        
        try:
            # 2. Extract timestamp and signature from the header
            # Parse signature header in format: 'ts=timestamp;h1=hash'
            signature_parts = {}
            for part in signature_header.split(';'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    signature_parts[key] = value
            
            print(f"📝 Parsed signature parts: {signature_parts}")
            
            # Get timestamp and signature
            timestamp = signature_parts.get('ts')
            # Get h1 signature (current Paddle format)
            signature = signature_parts.get('h1')
            
            if not timestamp or not signature:
                print(f"❌ Missing timestamp or signature in header: {signature_header}")
                return False
            
            # 3. Build the signed payload: timestamp:payload_json
            data_to_verify = f"{timestamp}:{payload_json}"
            print(f"📝 Data to verify (preview): {data_to_verify[:50]}...")
            
            # 4. Hash the signed payload using HMAC-SHA256 with secret key
            # First try with the full webhook_secret
            expected_signature_full = hmac.new(
                webhook_secret.encode('utf-8'),
                data_to_verify.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Try with just the part after the last underscore if it contains pdl_ntfset
            if webhook_secret.startswith('pdl_ntfset_'):
                parts = webhook_secret.split('_', 3)
                if len(parts) >= 4:
                    key_part = parts[3]
                    expected_signature_part = hmac.new(
                        key_part.encode('utf-8'),
                        data_to_verify.encode('utf-8'),
                        hashlib.sha256
                    ).hexdigest()
                    print(f"📝 Expected signature (using key part): {expected_signature_part}")
            
            print(f"📝 Expected signature (using full key): {expected_signature_full}")
            print(f"📝 Received signature: {signature}")
            
            # 5. Compare signatures using constant-time comparison
            is_valid = hmac.compare_digest(signature, expected_signature_full)
            
            if webhook_secret.startswith('pdl_ntfset_') and not is_valid:
                # Try with just the key part
                is_valid = hmac.compare_digest(signature, expected_signature_part)
                if is_valid:
                    print("✅ Signature verification successful with key part")
            else:
                if is_valid:
                    print("✅ Signature verification successful with full key")
                else:
                    print("❌ Signature verification failed")
            
            return is_valid
            
        except Exception as e:
            print(f"❌ Error verifying webhook signature: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _handle_subscription_created(self, event_data):
        """Handle subscription.created webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            if not subscription_data:
                # In case the event data structure is flat (older format)
                subscription_data = event_data
                
            # Log the data structure for debugging
            print(f"Processing subscription.created webhook - Raw data structure: {subscription_data.keys()}")
            
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            
            # Log the data for debugging
            print(f"Processing subscription.created - ID: {subscription_id}, Status: {subscription_status}")
            
            # Get customer_id
            customer_id = subscription_data.get('customer_id')
            if not customer_id:
                print("❌ No customer_id found in the webhook")
                return Response(
                    {"status": "error", "detail": "Missing customer_id in webhook data"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            print(f"Found customer_id: {customer_id}")
            
            # Import User model first
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Try to find user by customer_id first (if we've stored it before)
            user_id = None
            try:
                user = User.objects.get(paddle_customer_id=customer_id)
                user_id = user.id
                print(f"Found user by customer_id: {user_id}")
            except User.DoesNotExist:
                print("User not found by paddle_customer_id, will try other methods")
            except Exception as e:
                print(f"Error finding user by paddle_customer_id: {str(e)}")
            
            # Option 1: Try to find user by paddle_customer_id in UserSubscription
            if not user_id:
                try:
                    from .models import UserSubscription
                    existing_subscription = UserSubscription.objects.filter(paddle_customer_id=customer_id).first()
                    if existing_subscription:
                        user_id = existing_subscription.user_id
                        print(f"Found existing user by subscription customer_id: {user_id}")
                except Exception as e:
                    print(f"Error finding user by subscription customer_id: {str(e)}")
            
            # Option 2: If we can't find by customer_id, try to get customer email
            if not user_id:
                # Attempt to get customer details from Paddle
                # This would require a Paddle API call, which we might implement later
                # For now, we'll rely on sandbox mode fallback if needed
                
                if settings.PADDLE_SANDBOX:
                    print("⚠️ No user found by customer_id. Using first user as fallback in sandbox mode")
                    first_user = User.objects.first()
                    if first_user:
                        user_id = first_user.id
                    else:
                        return Response(
                            {"status": "error", "detail": "No users found in the system"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    return Response(
                        {"status": "error", "detail": "Could not identify user for this subscription"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Get plan information from the items array
            plan_id = None
            period = None
            
            items = subscription_data.get('items', [])
            if items and len(items) > 0:
                first_item = items[0]
                
                # Get product information
                product = first_item.get('product', {})
                if not product and 'product' in first_item:
                    product = first_item.get('product', {})
                
                product_id = product.get('id') if product else None
                
                # Get price information
                price = first_item.get('price', {})
                price_id = price.get('id') if price else None
                
                # Try to get billing period information
                billing_cycle = price.get('billing_cycle', {}) if price else {}
                if not billing_cycle:
                    # Try to get from subscription level
                    billing_cycle = subscription_data.get('billing_cycle', {})
                    
                interval = billing_cycle.get('interval')
                
                print(f"Found product_id: {product_id}, price_id: {price_id}, interval: {interval}")
                
                # Determine period based on interval
                if interval == 'month':
                    period = 'monthly'
                elif interval == 'year':
                    period = 'yearly'
                else:
                    period = 'monthly'  # Default to monthly
                
                # Try to find plan by price_id 
                if price_id:
                    try:
                        plan = get_subscription_plan_by_price_id(price_id)
                        if plan:
                            plan_id = plan.plan_id
                            print(f"Found plan by price_id: {plan_id}")
                    except Exception as e:
                        print(f"Error finding plan by price_id: {str(e)}")
                
                # If not found by price_id, try by product_id
                if not plan_id and product_id:
                    try:
                        from .models import SubscriptionPlan
                        plan = SubscriptionPlan.objects.filter(paddle_product_id=product_id).first()
                        if plan:
                            plan_id = plan.plan_id
                            print(f"Found plan by product_id: {plan_id}")
                    except Exception as e:
                        print(f"Error finding plan by product_id: {str(e)}")
            
            # If still no plan_id, use fallback in sandbox mode
            if not plan_id:
                if settings.PADDLE_SANDBOX:
                    print("⚠️ No plan_id found. Using first active plan as fallback in sandbox mode")
                    from .models import SubscriptionPlan
                    first_plan = SubscriptionPlan.objects.filter(is_active=True).first()
                    if first_plan:
                        plan_id = first_plan.plan_id
                    else:
                        return Response(
                            {"status": "error", "detail": "No active plans found"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    return Response(
                        {"status": "error", "detail": "Could not identify plan for this subscription"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # At this point, we should have user_id, plan_id, and period
            print(f"Final values: user_id={user_id}, plan_id={plan_id}, period={period}")
            
            # Get the plan
            try:
                from .models import SubscriptionPlan
                plan = SubscriptionPlan.objects.get(plan_id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                print(f"Plan not found with ID: {plan_id}")
                return Response(
                    {"status": "error", "detail": "Plan not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get or create the subscription
            try:
                from .models import UserSubscription
                user_subscription, created = UserSubscription.objects.get_or_create(
                    user_id=user_id,
                    defaults={
                        'plan': plan,
                        'period': period,
                        'status': 'pending',
                        'start_date': timezone.now(),  # Will be updated with actual data if available
                        'payment_provider': 'paddle',
                        'is_active': True,
                        'cancel_at_period_end': False
                    }
                )
                
                # Update the subscription with Paddle details
                user_subscription.paddle_subscription_id = subscription_id
                user_subscription.paddle_customer_id = customer_id
                
                # Set status based on Paddle subscription status
                if subscription_status == 'active':
                    user_subscription.status = 'active'
                    
                    # Get start date from various possible locations
                    start_date = None
                    if 'started_at' in subscription_data:
                        start_date = subscription_data.get('started_at')
                    elif 'first_billed_at' in subscription_data:
                        start_date = subscription_data.get('first_billed_at')
                    elif 'current_billing_period' in subscription_data:
                        start_date = subscription_data.get('current_billing_period', {}).get('starts_at')
                    
                    if start_date:
                        user_subscription.start_date = start_date
                        print(f"Set start_date to: {start_date}")
                    
                    # Get end date from various possible locations
                    end_date = None
                    if 'current_billing_period' in subscription_data:
                        end_date = subscription_data.get('current_billing_period', {}).get('ends_at')
                    elif 'next_billed_at' in subscription_data:
                        end_date = subscription_data.get('next_billed_at')
                    
                    if end_date:
                        user_subscription.end_date = end_date
                        print(f"Set end_date to: {end_date}")
                    else:
                        # Fallback if no period end date is provided
                        if period == 'monthly':
                            user_subscription.end_date = timezone.now() + timedelta(days=30)
                        else:
                            user_subscription.end_date = timezone.now() + timedelta(days=365)
                
                user_subscription.save()
                
                print(f"✅ Successfully processed subscription.created - User ID: {user_id}, Plan: {plan.name}")
                return Response({"status": "success"}, status=status.HTTP_200_OK)
                
            except Exception as e:
                print(f"Error updating subscription: {str(e)}")
                import traceback
                traceback.print_exc()
                return Response(
                    {"status": "error", "detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            print(f"Error handling subscription.created: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_subscription_updated(self, event_data):
        """Handle subscription.updated webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.updated webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.updated - ID: {subscription_id}, Status: {subscription_status}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status
            if subscription_status:
                print(f"Updating subscription status to: {subscription_status}")
                if subscription_status == 'active':
                    user_subscription.status = 'active'
                elif subscription_status == 'paused':
                    user_subscription.status = 'paused'
                elif subscription_status == 'canceled':
                    user_subscription.status = 'canceled'
                elif subscription_status == 'past_due':
                    user_subscription.status = 'past_due'
            
            # Check for scheduled changes (cancellation)
            scheduled_change = subscription_data.get('scheduled_change', {})
            if scheduled_change and scheduled_change.get('action') == 'cancel':
                print(f"Detected scheduled cancellation, setting cancel_at_period_end to True")
                user_subscription.cancel_at_period_end = True
            
            # Update end date if present
            current_period = subscription_data.get('current_billing_period', {})
            current_period_end = current_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
                user_subscription.end_date = current_period_end
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.updated for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.updated: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_subscription_canceled(self, event_data):
        """Handle subscription.canceled webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.canceled webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            canceled_at = subscription_data.get('canceled_at')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.canceled - ID: {subscription_id}, Status: {subscription_status}, Canceled at: {canceled_at}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status to canceled
            user_subscription.status = 'canceled'
            
            # Dokümantasyona göre, canceled abonelikler için end_date'i belirleyelim
            # 1. canceled_at varsa, bunu end_date olarak kullan (en doğru yaklaşım)
            if canceled_at:
                print(f"Setting end date to canceled_at timestamp: {canceled_at}")
                user_subscription.end_date = canceled_at
            else:
                # 2. current_billing_period varsa, ends_at'i al
                # current_billing_period null olabilir canceled abonelikler için
                current_period = subscription_data.get('current_billing_period')
                if current_period is not None and isinstance(current_period, dict):
                    current_period_end = current_period.get('ends_at')
                    if current_period_end:
                        print(f"Setting end date to current_billing_period.ends_at: {current_period_end}")
                        user_subscription.end_date = current_period_end
                else:
                    # 3. next_billed_at var mı?
                    next_billed_at = subscription_data.get('next_billed_at')
                    if next_billed_at:
                        print(f"Setting end date to next_billed_at: {next_billed_at}")
                        user_subscription.end_date = next_billed_at
                    else:
                        # 4. Hiçbir tarih bilgisi yoksa, şimdiki zamanı kullan
                        print("No date information found in webhook. Setting end date to current time")
                        user_subscription.end_date = timezone.now()
            
            # Mark subscription as canceled
            user_subscription.cancel_at_period_end = True
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.canceled for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.canceled: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_payment_succeeded(self, event_data):
        """Handle subscription.payment.succeeded webhook"""
        try:
            # Get the data from the 'data' field
            payment_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing payment.succeeded webhook - Raw data structure: {payment_data.keys()}")
            
            # Extract relevant data
            subscription_id = payment_data.get('subscription_id')
            transaction_id = payment_data.get('id')
            
            if not subscription_id or not transaction_id:
                print(f"❌ Missing required fields - transaction_id: {transaction_id}, subscription_id: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing payment.succeeded - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription end date if available
            billing_period = payment_data.get('billing_period', {})
            current_period_end = billing_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
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
            
            print(f"✅ Successfully processed payment.succeeded for transaction ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling payment.succeeded: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _handle_payment_failed(self, event_data):
        """Handle subscription.payment.failed webhook"""
        try:
            # Get the data from the 'data' field
            payment_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing payment.failed webhook - Raw data structure: {payment_data.keys()}")
            
            # Extract relevant data
            subscription_id = payment_data.get('subscription_id')
            transaction_id = payment_data.get('id')
            
            if not subscription_id or not transaction_id:
                print(f"❌ Missing required fields - transaction_id: {transaction_id}, subscription_id: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing payment.failed - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription status to past_due if needed
            user_subscription.status = 'past_due'
            user_subscription.save()
            
            print(f"✅ Successfully processed payment.failed for transaction ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling payment.failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_paid(self, event_data):
        """Handle transaction.paid webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.paid webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print("❌ Missing transaction ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log the transaction data
            print(f"Processing transaction.paid - ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription ID, this might be a one-time payment, we can acknowledge it
            if not subscription_id:
                print("No subscription ID associated with this transaction - treating as one-time payment")
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription details based on the transaction
            
            # 1. Billing period information
            billing_period = transaction_data.get('billing_period', {})
            if billing_period:
                ends_at = billing_period.get('ends_at')
                if ends_at:
                    print(f"Setting subscription end date to billing_period.ends_at: {ends_at}")
                    user_subscription.end_date = ends_at
                
                # Also check for starts_at
                starts_at = billing_period.get('starts_at')
                if starts_at and not user_subscription.start_date:
                    print(f"Setting subscription start date to billing_period.starts_at: {starts_at}")
                    user_subscription.start_date = starts_at
            else:
                # Fallback if no period end date - add time based on subscription period
                if user_subscription.end_date is None:
                    if user_subscription.period == 'monthly':
                        user_subscription.end_date = timezone.now() + timedelta(days=30)
                        print(f"No billing period found, setting fallback end date +30 days: {user_subscription.end_date}")
                    else:
                        user_subscription.end_date = timezone.now() + timedelta(days=365)
                        print(f"No billing period found, setting fallback end date +365 days: {user_subscription.end_date}")
            
            # 2. Status update - paid transaction generally means active subscription
            if transaction_status == 'paid':
                user_subscription.status = 'active'
                print("Transaction is paid, setting subscription status to 'active'")
            
            # 3. Reset cancel_at_period_end flag if applicable
            # This is a new payment, which might mean the subscription was renewed after cancellation
            if user_subscription.cancel_at_period_end and transaction_status == 'paid':
                scheduled_change = transaction_data.get('subscription', {}).get('scheduled_change')
                if not scheduled_change or scheduled_change.get('action') != 'cancel':
                    print("New paid transaction received - resetting cancel_at_period_end flag")
                    user_subscription.cancel_at_period_end = False
            
            user_subscription.save()
            
            print(f"✅ Successfully processed transaction.paid for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.paid: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_updated(self, event_data):
        """Handle transaction.updated webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.updated webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.updated - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction update without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status based on transaction status
            if transaction_status:
                print(f"Transaction status: {transaction_status}")
                if transaction_status == 'paid':
                    user_subscription.status = 'active'
                    print("Setting subscription status to 'active'")
                elif transaction_status == 'past_due':
                    user_subscription.status = 'past_due'
                    print("Setting subscription status to 'past_due'")
            
            # Update end date if present
            billing_period = transaction_data.get('billing_period', {})
            if billing_period:
                current_period_end = billing_period.get('ends_at')
                if current_period_end:
                    print(f"Updating subscription end date to: {current_period_end}")
                    user_subscription.end_date = current_period_end
            
            user_subscription.save()
            print(f"✅ Successfully processed transaction.updated for ID: {transaction_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.updated: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_subscription_activated(self, event_data):
        """Handle subscription.activated webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.activated webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.activated - ID: {subscription_id}, Status: {subscription_status}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status to active
            user_subscription.status = 'active'
            print(f"Setting subscription status to active")
            
            # Update dates from subscription data
            # 1. Start date
            started_at = subscription_data.get('started_at')
            if started_at:
                print(f"Setting subscription start date to: {started_at}")
                user_subscription.start_date = started_at
                
            # 2. End date from current_billing_period
            current_period = subscription_data.get('current_billing_period')
            if current_period and isinstance(current_period, dict):
                current_period_end = current_period.get('ends_at')
                if current_period_end:
                    print(f"Setting subscription end date to: {current_period_end}")
                    user_subscription.end_date = current_period_end
            # 3. Or from next_billed_at
            elif subscription_data.get('next_billed_at'):
                print(f"Setting subscription end date to next_billed_at: {subscription_data.get('next_billed_at')}")
                user_subscription.end_date = subscription_data.get('next_billed_at')
            
            # Reset cancel flags
            user_subscription.cancel_at_period_end = False
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.activated for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.activated: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_billed(self, event_data):
        """Handle transaction.billed webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.billed webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.billed - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription end date
            billing_period = transaction_data.get('billing_period', {})
            current_period_end = billing_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
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
            
            print(f"✅ Successfully processed transaction.billed for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.billed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_canceled(self, event_data):
        """Handle transaction.canceled webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.canceled webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.canceled - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription status
            user_subscription.status = 'canceled'
            user_subscription.save()
            
            print(f"✅ Successfully processed transaction.canceled for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.canceled: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_completed(self, event_data):
        """Handle transaction.completed webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.completed webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.completed - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription end date
            billing_period = transaction_data.get('billing_period', {})
            current_period_end = billing_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
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
            
            print(f"✅ Successfully processed transaction.completed for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.completed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_ready(self, event_data):
        """Handle transaction.ready webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.ready webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.ready - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Don't update subscription status for ready transactions
            
            print(f"✅ Successfully processed transaction.ready for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.ready: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_revised(self, event_data):
        """Handle transaction.revised webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.revised webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.revised - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            print(f"✅ Successfully processed transaction.revised for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.revised: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_past_due(self, event_data):
        """Handle transaction.past_due webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.past_due webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.past_due - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription status
            user_subscription.status = 'past_due'
            user_subscription.save()
            
            print(f"✅ Successfully processed transaction.past_due for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.past_due: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_payment_failed(self, event_data):
        """Handle transaction.payment_failed webhook"""
        try:
            # Get the transaction data from the 'data' field
            transaction_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing transaction.payment_failed webhook - Raw data structure: {transaction_data.keys()}")
            
            # Get transaction details from proper location
            transaction_id = transaction_data.get('id')
            subscription_id = transaction_data.get('subscription_id')
            transaction_status = transaction_data.get('status')
            
            if not transaction_id:
                print(f"❌ Missing transaction_id in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing transaction_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing transaction.payment_failed - Transaction ID: {transaction_id}, Subscription ID: {subscription_id}, Status: {transaction_status}")
            
            # If there's no subscription_id, this may be a one-time payment not tied to a subscription
            if not subscription_id:
                print(f"Transaction without subscription_id - possibly a one-time payment")
                # Just acknowledge receipt of the webhook for non-subscription transactions
                return Response({"status": "success"}, status=status.HTTP_200_OK)
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update subscription status to past_due
            user_subscription.status = 'past_due'
            user_subscription.save()
            
            print(f"✅ Successfully processed transaction.payment_failed for ID: {transaction_id}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.payment_failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_payment_method_saved(self, event_data):
        """Handle payment_method.saved webhook"""
        try:
            # Get the payment method data from the 'data' field
            payment_method_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing payment_method.saved webhook - Raw data structure: {payment_method_data.keys()}")
            
            # Get payment method details
            payment_method_id = payment_method_data.get('id')
            customer_id = payment_method_data.get('customer_id')
            
            if not payment_method_id or not customer_id:
                print(f"❌ Missing required fields - payment_method_id: {payment_method_id}, customer_id: {customer_id}")
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing payment_method.saved - ID: {payment_method_id}, Customer ID: {customer_id}")
            
            # Find the subscription by customer_id
            try:
                user_subscription = UserSubscription.objects.get(paddle_customer_id=customer_id)
                
                # No need to update anything, just acknowledge
                print(f"✅ Successfully processed payment_method.saved for Customer ID: {customer_id}")
                return Response({"status": "success"}, status=status.HTTP_200_OK)
                
            except UserSubscription.DoesNotExist:
                print(f"❌ No subscription found with customer ID: {customer_id}")
                
                # In sandbox mode, we accept this silently
                if settings.PADDLE_SANDBOX:
                    print("⚠️ Sandbox mode: No action taken for payment_method.saved event")
                    return Response({"status": "success"}, status=status.HTTP_200_OK)
                    
                return Response(
                    {"status": "error", "detail": "No subscription found with this customer ID"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Exception as e:
            print(f"Error handling payment_method.saved: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_payment_method_deleted(self, event_data):
        """Handle payment_method.deleted webhook"""
        try:
            # Get the payment method data from the 'data' field
            payment_method_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing payment_method.deleted webhook - Raw data structure: {payment_method_data.keys()}")
            
            # Get payment method details
            payment_method_id = payment_method_data.get('id')
            customer_id = payment_method_data.get('customer_id')
            
            if not payment_method_id or not customer_id:
                print(f"❌ Missing required fields - payment_method_id: {payment_method_id}, customer_id: {customer_id}")
                return Response(
                    {"status": "error", "detail": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing payment_method.deleted - ID: {payment_method_id}, Customer ID: {customer_id}")
            
            # Find the subscription by customer_id
            try:
                user_subscription = UserSubscription.objects.get(paddle_customer_id=customer_id)
                
                # No need to update anything, just acknowledge
                print(f"✅ Successfully processed payment_method.deleted for Customer ID: {customer_id}")
                return Response({"status": "success"}, status=status.HTTP_200_OK)
                
            except UserSubscription.DoesNotExist:
                print(f"❌ No subscription found with customer ID: {customer_id}")
                
                # In sandbox mode, we accept this silently
                if settings.PADDLE_SANDBOX:
                    print("⚠️ Sandbox mode: No action taken for payment_method.deleted event")
                    return Response({"status": "success"}, status=status.HTTP_200_OK)
                    
                return Response(
                    {"status": "error", "detail": "No subscription found with this customer ID"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Exception as e:
            print(f"Error handling payment_method.deleted: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_subscription_paused(self, event_data):
        """Handle subscription.paused webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.paused webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            paused_at = subscription_data.get('paused_at')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.paused - ID: {subscription_id}, Status: {subscription_status}, Paused at: {paused_at}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status to paused
            user_subscription.status = 'paused'
            print("Setting subscription status to 'paused'")
            
            # Update pause date if available
            if paused_at:
                print(f"Recorded pause date: {paused_at}")
                # Note: You might want to store this date in a separate field if tracking pause dates is important
                
            # Check for a scheduled resumption date
            scheduled_change = subscription_data.get('scheduled_change', {})
            if scheduled_change and scheduled_change.get('action') == 'resume':
                resume_at = scheduled_change.get('effective_at')
                if resume_at:
                    print(f"Subscription is scheduled to resume at: {resume_at}")
                    # Store scheduled resume date if needed
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.paused for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.paused: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_subscription_resumed(self, event_data):
        """Handle subscription.resumed webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.resumed webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.resumed - ID: {subscription_id}, Status: {subscription_status}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status
            if subscription_status:
                print(f"Updating subscription status to: {subscription_status}")
                user_subscription.status = 'active'
            
            # Update end date if present
            current_period = subscription_data.get('current_billing_period', {})
            current_period_end = current_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
                user_subscription.end_date = current_period_end
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.resumed for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.resumed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_subscription_trialing(self, event_data):
        """Handle subscription.trialing webhook"""
        try:
            # Get the subscription data from the 'data' field
            subscription_data = event_data.get('data', {})
            
            # Log for debugging
            print(f"Processing subscription.trialing webhook - Raw data structure: {subscription_data.keys()}")
            
            # Get subscription details from proper location
            subscription_id = subscription_data.get('id')
            subscription_status = subscription_data.get('status')
            
            if not subscription_id:
                print("❌ Missing subscription ID in webhook data")
                return Response(
                    {"status": "error", "detail": "Missing subscription ID"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Log for debugging
            print(f"Processing subscription.trialing - ID: {subscription_id}, Status: {subscription_status}")
            
            # Find the subscription in our database
            try:
                user_subscription = UserSubscription.objects.get(paddle_subscription_id=subscription_id)
            except UserSubscription.DoesNotExist:
                print(f"❌ Subscription not found with ID: {subscription_id}")
                return Response(
                    {"status": "error", "detail": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the subscription status
            if subscription_status:
                print(f"Updating subscription status to: {subscription_status}")
                user_subscription.status = 'active'
            
            # Update end date if present
            current_period = subscription_data.get('current_billing_period', {})
            current_period_end = current_period.get('ends_at')
            if current_period_end:
                print(f"Updating subscription end date to: {current_period_end}")
                user_subscription.end_date = current_period_end
            
            user_subscription.save()
            print(f"✅ Successfully processed subscription.trialing for ID: {subscription_id}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling subscription.trialing: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class PayTRWebhookView(APIView):
    """View for handling PayTR webhooks"""
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        """Handle PayTR webhook notification"""
        from django.http import HttpResponse
        
        try:
            # Log the received data
            print(f"🔔 Received PayTR webhook notification: {request.POST}")
            
            # Get required parameters
            merchant_oid = request.POST.get('merchant_oid')
            payment_status = request.POST.get('status')  # Renamed from 'status' to 'payment_status'
            total_amount = request.POST.get('total_amount')
            hash_key = request.POST.get('hash')
            
            # Validate required parameters
            if not merchant_oid or not payment_status or not total_amount or not hash_key:
                print("❌ Missing required parameters in PayTR webhook notification")
                # PayTR expects "OK" as plain text response
                return HttpResponse("OK")
            
            # Verify signature
            from .paytr_utils import verify_webhook_signature
            if not verify_webhook_signature(request.POST, merchant_oid, payment_status, total_amount, hash_key):
                print("❌ Invalid signature in PayTR webhook notification")
                # PayTR expects "OK" as plain text response
                return HttpResponse("OK")
            
            # Debug - List all active subscriptions
            from .models import UserSubscription
            active_subs = list(UserSubscription.objects.filter(status__in=['active', 'pending']).values('id', 'status', 'payment_provider', 'paddle_checkout_id'))
            print(f"🔎 Active subscriptions: {active_subs}")
            
            # Check if merchant_oid exists in any subscription
            matching_sub = UserSubscription.objects.filter(paddle_checkout_id=merchant_oid).first()
            if matching_sub:
                print(f"✅ Found subscription with merchant_oid: {merchant_oid}, ID: {matching_sub.id}")
            else:
                print(f"❌ No subscription found with merchant_oid: {merchant_oid}")
                
                # Extract ID from merchant_oid
                if merchant_oid.startswith('cvb'):
                    import re
                    # Önce yeni formata göre, 'x' separator ile
                    id_match = re.match(r'^cvb(\d+)x', merchant_oid)
                    
                    # Yeni formatta bulunamadıysa eski formata göre deneyelim
                    if not id_match:
                        print("📌 Trying legacy merchant_oid format without separator")
                        # Eski format: sadece rakamları al
                        id_match = re.match(r'^cvb(\d+)', merchant_oid)
                    
                    if id_match:
                        extracted_id = id_match.group(1)
                        print(f"🔍 Extracted ID from merchant_oid: {extracted_id}")
                        
                        # Check if this ID exists
                        sub_exists = UserSubscription.objects.filter(id=extracted_id).exists()
                        print(f"🔍 Subscription with ID {extracted_id} exists: {sub_exists}")
            
            # Handle the notification based on status
            if payment_status == "success":
                # Process successful payment
                from .paytr_utils import process_successful_payment
                if process_successful_payment(merchant_oid, total_amount):
                    print(f"✅ Successfully processed PayTR payment for {merchant_oid}")
                else:
                    print(f"❌ Failed to process PayTR payment for {merchant_oid}")
            else:
                # Payment failed
                print(f"⚠️ PayTR payment failed for {merchant_oid}")
                
                # Başarısız ödeme durumunda aboneliği iptal et veya güncelle
                if merchant_oid.startswith('cvb'):
                    import re
                    # Önce yeni formata göre, 'x' separator ile
                    subscription_id_match = re.match(r'^cvb(\d+)x', merchant_oid)
                    
                    # Yeni formatta bulunamadıysa eski formata göre deneyelim
                    if not subscription_id_match:
                        # Eski format: sadece rakamları al
                        subscription_id_match = re.match(r'^cvb(\d+)', merchant_oid)
                    
                    if subscription_id_match:
                        # Subscription ID'yi al
                        subscription_id = subscription_id_match.group(1)
                        print(f"💡 Extracted subscription ID from failed payment: {subscription_id}")
                        
                        # Subscription'ı bul ve güncelle
                        subscription = UserSubscription.objects.filter(id=subscription_id).first()
                        
                        if subscription and subscription.status == 'pending':
                            subscription.status = 'expired'
                            subscription.save()
                            print(f"💔 Abonelik durumu 'expired' olarak güncellendi: {subscription_id}")
                        else:
                            status_text = subscription.status if subscription else "not found"
                            print(f"📝 Subscription {subscription_id} not updated, status: {status_text}")
            
            # Her durumda PayTR'ye "OK" yanıtı döndür - dokümana göre düz string olmalı
            return HttpResponse("OK")
            
        except Exception as e:
            print(f"❌ Error processing PayTR webhook: {str(e)}")
            import traceback
            traceback.print_exc()
            # We still return OK to PayTR as they expect - Even on errors
            return HttpResponse("OK")


class PaymentGatewayViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for payment gateways"""
    queryset = PaymentGateway.objects.filter(is_active=True)
    serializer_class = PaymentGatewaySerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        """Return all payment gateways, active or not, but sort active ones first"""
        # Önce aktif olan, sonra diğerleri şeklinde göster
        print("Tüm ödeme yöntemleri:", list(PaymentGateway.objects.all().values()))
        print("Aktif ödeme yöntemleri:", list(PaymentGateway.objects.filter(is_active=True).values()))
        
        # Tüm payment gateway'leri verelim, UI tarafında filtreleme yapılsın
        return PaymentGateway.objects.all().order_by('-is_active', 'position')
