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
import base64
import hmac
import hashlib
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

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
    get_subscription_plan,
    get_subscription_plan_by_price_id
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
                        status='pending',
                        payment_provider='paddle',      # Set payment provider
                        is_active=True,                # Set is_active to True
                        cancel_at_period_end=False,    # Set cancel_at_period_end to False
                        start_date=timezone.now()      # Set start_date to prevent NULL constraint
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
            
            print(f"=== Webhook Body Preview ===\n{raw_body[:200]}...\n")
            
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
                event_type = webhook_data.get('event_type')
                event_data = webhook_data.get('data', {})
                
                print(f"📥 Received Paddle webhook: {event_type}")
                
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
                elif event_type == 'transaction.paid' or event_type == 'transaction.created':
                    # Treat transaction.paid similar to payment.succeeded
                    return self._handle_transaction_paid(event_data)
                elif event_type == 'transaction.updated':
                    # Handle transaction updates
                    return self._handle_transaction_updated(event_data)
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
            # Get the subscription data
            subscription = event_data.get('subscription', {})
            if not subscription:
                # In some Paddle webhook formats, the subscription is directly in the event_data
                subscription = event_data
                
            subscription_id = subscription.get('id')
            subscription_status = subscription.get('status')
            
            # Log the data for debugging
            print(f"Processing subscription.created - ID: {subscription_id}, Status: {subscription_status}")
            
            # Get customer_id
            customer_id = subscription.get('customer_id')
            if not customer_id:
                print("❌ No customer_id found in the webhook")
                return Response(
                    {"status": "error", "detail": "Missing customer_id in webhook data"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            print(f"Found customer_id: {customer_id}")
            
            # Try to find user by customer_id first (if we've stored it before)
            user_id = None
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Option 1: Try to find user by paddle_customer_id
            try:
                existing_subscription = UserSubscription.objects.filter(paddle_customer_id=customer_id).first()
                if existing_subscription:
                    user_id = existing_subscription.user_id
                    print(f"Found existing user by customer_id: {user_id}")
            except Exception as e:
                print(f"Error finding user by customer_id: {str(e)}")
            
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
            
            items = subscription.get('items', [])
            if items and len(items) > 0:
                first_item = items[0]
                
                # Get product information
                product = first_item.get('product', {})
                product_id = product.get('id') if product else None
                
                # Get price information
                price = first_item.get('price', {})
                price_id = price.get('id') if price else None
                
                # Try to get billing period information
                billing_cycle = price.get('billing_cycle', {}) if price else {}
                if not billing_cycle:
                    # Try to get from subscription level
                    billing_cycle = subscription.get('billing_cycle', {})
                    
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
                
                # Check for a transaction ID
                transaction_id = subscription.get('transaction_id')
                if transaction_id:
                    print(f"Found transaction_id: {transaction_id}")
                
                # Set status based on Paddle subscription status
                if subscription_status == 'active':
                    user_subscription.status = 'active'
                    
                    # Get start date
                    start_date = None
                    if 'started_at' in subscription:
                        start_date = subscription.get('started_at')
                    elif 'first_billed_at' in subscription:
                        start_date = subscription.get('first_billed_at')
                    elif 'current_billing_period' in subscription:
                        start_date = subscription.get('current_billing_period', {}).get('starts_at')
                    
                    if start_date:
                        user_subscription.start_date = start_date
                        print(f"Set start_date to: {start_date}")
                    
                    # Get end date
                    end_date = None
                    if 'current_billing_period' in subscription:
                        end_date = subscription.get('current_billing_period', {}).get('ends_at')
                    elif 'next_billed_at' in subscription:
                        end_date = subscription.get('next_billed_at')
                    
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
                
                # If we have a transaction ID, create a payment record
                if transaction_id and subscription_status == 'active':
                    try:
                        # Try to get amount from the webhook
                        amount = "0"
                        currency = "USD"
                        
                        if items and len(items) > 0:
                            first_item = items[0]
                            price = first_item.get('price', {})
                            unit_price = price.get('unit_price', {})
                            amount = unit_price.get('amount', "0")
                            currency = unit_price.get('currency_code', "USD")
                        
                        # Create payment record
                        from .models import SubscriptionPaymentHistory
                        payment = SubscriptionPaymentHistory.objects.create(
                            subscription=user_subscription,
                            payment_id=f"paddle_payment_{transaction_id}",
                            amount=amount,
                            currency=currency,
                            status='success',
                            paddle_payment_id=transaction_id
                        )
                        print(f"Created payment record for transaction: {transaction_id}")
                    except Exception as e:
                        print(f"Error creating payment record: {str(e)}")
                
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
            # Get the subscription data
            subscription = event_data.get('subscription', {})
            subscription_id = subscription.get('id')
            subscription_status = subscription.get('status')
            
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
            if subscription_status:
                if subscription_status == 'active':
                    user_subscription.status = 'active'
                elif subscription_status == 'paused':
                    user_subscription.status = 'paused'
                elif subscription_status == 'canceled':
                    user_subscription.status = 'canceled'
                elif subscription_status == 'past_due':
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

    def _handle_transaction_paid(self, event_data):
        """Handle transaction.paid webhook"""
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
            print(f"Error handling transaction.paid: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_transaction_updated(self, event_data):
        """Handle transaction.updated webhook"""
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
            
            # Update the subscription status
            if transaction.get('status') == 'paid':
                user_subscription.status = 'active'
            elif transaction.get('status') == 'past_due':
                user_subscription.status = 'past_due'
            
            # Update end date if present
            current_period_end = transaction.get('current_billing_period', {}).get('ends_at')
            if current_period_end:
                user_subscription.end_date = current_period_end
            
            user_subscription.save()
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error handling transaction.updated: {str(e)}")
            return Response(
                {"status": "error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
