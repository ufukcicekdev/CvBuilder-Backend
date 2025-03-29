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
        Verify that a webhook was sent by Paddle
        
        Args:
            headers: Request headers with Paddle-Signature
            payload_json: Raw JSON payload as string
            
        Returns:
            Boolean indicating if the signature is valid
        """
        # Get the signature from headers
        signature_header = headers.get('Paddle-Signature')
        if not signature_header:
            print("❌ Missing Paddle-Signature header")
            return False
        
        # Get webhook secret key from settings
        webhook_secret = getattr(settings, 'PADDLE_WEBHOOK_SECRET', None)
        
        # Check if we're in sandbox mode
        sandbox_mode = getattr(settings, 'PADDLE_SANDBOX', False)
        
        # Print full signature header for debugging
        print(f"📝 Received signature header: {signature_header}")
        
        # For testing in development/sandbox environment
        if sandbox_mode:
            print("⚠️ SANDBOX MODE: Bypassing signature verification")
            return True
            
        # For production, validate the signature
        if not webhook_secret:
            print("❌ Missing Paddle webhook secret in settings")
            return False
        
        try:
            # Parse the signature header - should be in format 'ts=timestamp;h1=hash'
            signature_parts = {}
            for part in signature_header.split(';'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    signature_parts[key] = value
            
            print(f"📝 Parsed signature parts: {signature_parts}")
            
            # Get timestamp and signature
            timestamp = signature_parts.get('ts')
            # Check for h1 first (newest format), then h (older format)
            signature = signature_parts.get('h1') or signature_parts.get('h')
            
            if not timestamp or not signature:
                print(f"❌ Missing timestamp or hash in header: {signature_header}")
                return False
            
            # Create the string to verify: timestamp + payload
            data_to_verify = f"{timestamp}:{payload_json}"
            print(f"📝 Data to verify (preview): {data_to_verify[:50]}...")
            
            # Extract the actual key if needed
            if webhook_secret.startswith('pdl_ntfset_'):
                # Format: pdl_ntfset_ID_SECRET_KEY
                parts = webhook_secret.split('_', 3)
                if len(parts) >= 4:
                    actual_secret = parts[3]
                else:
                    actual_secret = webhook_secret
            else:
                actual_secret = webhook_secret
                
            # Calculate expected signature using HMAC and SHA-256
            expected_signature = hmac.new(
                actual_secret.encode('utf-8'),
                data_to_verify.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            print(f"📝 Expected signature: {expected_signature}")
            print(f"📝 Received signature: {signature}")
            
            # Compare signatures using a constant-time comparison
            is_valid = hmac.compare_digest(signature, expected_signature)
            
            if is_valid:
                print("✅ Signature verification successful")
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
            subscription_id = subscription.get('id')
            subscription_status = subscription.get('status')
            
            # Log the data for debugging
            print(f"Processing subscription.created - ID: {subscription_id}, Status: {subscription_status}")
            print(f"Subscription data: {subscription}")
            
            # Try to get customer information
            customer_id = subscription.get('customer_id')
            customer_email = None
            
            # Try to get customer email from the event data
            # There are different possible paths in Paddle's webhook structure
            if 'customer' in event_data:
                customer = event_data.get('customer', {})
                customer_email = customer.get('email')
            elif 'customer' in subscription:
                customer = subscription.get('customer', {})
                customer_email = customer.get('email')
            
            # If we found an email, try to find the user
            user_id = None
            if customer_email:
                print(f"Found customer email: {customer_email}")
                # Get the user model
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                try:
                    # Try to find the user by email
                    user = User.objects.get(email=customer_email)
                    user_id = user.id
                    print(f"Found user by email: {user_id}")
                except User.DoesNotExist:
                    print(f"No user found with email: {customer_email}")
            
            # Try to get product/price information to determine the plan
            plan_id = None
            period = None
            
            # Check if there are items in the subscription
            items = subscription.get('items', [])
            if items and len(items) > 0:
                first_item = items[0]
                price = first_item.get('price', {})
                
                # Extract price ID which can help identify the plan
                price_id = price.get('id')
                
                # Try to find the corresponding plan in our database
                if price_id:
                    print(f"Found price ID: {price_id}")
                    
                    # Try to find plan based on the price ID
                    # This assumes you have a way to map Paddle price IDs to your plans
                    # For example, you might store price IDs in the plan metadata
                    try:
                        plan = get_subscription_plan_by_price_id(price_id)
                        if plan:
                            plan_id = plan.plan_id
                    except:
                        # Fallback if the utility function doesn't exist
                        try:
                            from .models import SubscriptionPlan
                            for sp in SubscriptionPlan.objects.filter(is_active=True):
                                # This is a basic example - you'd need to implement your own
                                # mapping between Paddle price IDs and your plans
                                # For example, you might store price IDs in the plan metadata
                                if hasattr(sp, 'paddle_price_id') and sp.paddle_price_id == price_id:
                                    plan_id = sp.plan_id
                                    break
                        except Exception as e:
                            print(f"Error finding plan by price ID: {str(e)}")
                
                # Try to determine the billing period
                billing_cycle = price.get('billing_cycle', {})
                interval = billing_cycle.get('interval')
                
                if interval == 'month':
                    period = 'monthly'
                elif interval == 'year':
                    period = 'yearly'
                else:
                    # Default to monthly if we can't determine
                    period = 'monthly'
            
            # If we still don't have user_id, plan_id, or period
            # Check if we're in sandbox mode and use fallbacks
            if settings.PADDLE_SANDBOX:
                if not user_id:
                    print("⚠️ No user_id found. Using first user as fallback in sandbox mode")
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    first_user = User.objects.first()
                    if first_user:
                        user_id = first_user.id
                
                if not plan_id:
                    print("⚠️ No plan_id found. Using first active plan as fallback in sandbox mode")
                    from .models import SubscriptionPlan
                    first_plan = SubscriptionPlan.objects.filter(is_active=True).first()
                    if first_plan:
                        plan_id = first_plan.plan_id
                
                if not period:
                    print("⚠️ No period found. Using 'monthly' as fallback in sandbox mode")
                    period = 'monthly'
            
            # At this point, we need to have all the necessary information
            if not user_id or not plan_id or not period:
                print(f"Missing required fields: user_id={user_id}, plan_id={plan_id}, period={period}")
                return Response(
                    {"status": "error", "detail": "Missing required information to create subscription"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the plan
            try:
                from .models import SubscriptionPlan
                plan = SubscriptionPlan.objects.get(plan_id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                print(f"Plan not found with ID: {plan_id}")
                if settings.PADDLE_SANDBOX:
                    plan = SubscriptionPlan.objects.filter(is_active=True).first()
                    if not plan:
                        return Response(
                            {"status": "error", "detail": "No active plans found"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
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
                        'status': 'pending'
                    }
                )
                
                # Update the subscription with Paddle details
                user_subscription.paddle_subscription_id = subscription_id
                user_subscription.paddle_customer_id = customer_id
                
                # Set status based on Paddle subscription status
                if subscription_status == 'active':
                    user_subscription.status = 'active'
                    user_subscription.start_date = timezone.now()
                    
                    # Set the end date based on the period and current billing period
                    # Try different possible formats for the end date
                    current_period_end = None
                    
                    # Format 1: current_billing_period.ends_at
                    if 'current_billing_period' in subscription:
                        current_period_end = subscription.get('current_billing_period', {}).get('ends_at')
                    
                    # Format 2: next_billed_at
                    if not current_period_end and 'next_billed_at' in subscription:
                        current_period_end = subscription.get('next_billed_at')
                    
                    # Format 3: current_period_end directly
                    if not current_period_end and 'current_period_end' in subscription:
                        current_period_end = subscription.get('current_period_end')
                    
                    if current_period_end:
                        user_subscription.end_date = current_period_end
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
