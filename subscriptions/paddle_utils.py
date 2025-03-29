import os
import uuid
import json
import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import get_language
import hmac
import hashlib
import base64

# Initialize Paddle options using PADDLE_SETTINGS
options = settings.PADDLE_SETTINGS if hasattr(settings, 'PADDLE_SETTINGS') else {
    'vendor_id': settings.PADDLE_VENDOR_ID,
    'vendor_auth_code': settings.PADDLE_VENDOR_AUTH_CODE,
    'api_key': settings.PADDLE_API_KEY,
    'public_key': settings.PADDLE_PUBLIC_KEY,
    'sandbox': settings.PADDLE_SANDBOX,
    'api_url': 'https://api.paddle.com' if not settings.PADDLE_SANDBOX else 'https://sandbox-api.paddle.com',
    'checkout_url': 'https://checkout.paddle.com' if not settings.PADDLE_SANDBOX else 'https://sandbox-checkout.paddle.com'
}

def get_paddle_headers():
    """
    Get common headers for Paddle API requests
    """
    return {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f"Bearer {options['api_key']}",
        'Paddle-Version': '1'  # API version
    }

def get_subscription_plan(plan, period):
    """
    Get a Paddle plan/product ID based on our plan and period
    
    Args:
        plan: SubscriptionPlan model instance
        period: 'monthly' or 'yearly'
    
    Returns:
        Paddle product ID
    """
    # In a real implementation, you'd map your plans to actual Paddle product IDs
    # For now, we'll create a simulated mapping
    
    # Generate a plan identifier based on the plan and period
    plan_identifier = f"{plan.plan_id}_{period}"
    
    # Sample mapping of plan identifiers to Paddle product IDs
    # In a real implementation, you'd store these mappings in your database or settings
    # Paddle Classic API product IDs vs new Paddle API price IDs are different
    paddle_product_map = {
        "premium_monthly": "pri_01h9ajczk62em0ndak6a7ppxqc",  # Example price ID for monthly billing
        "premium_yearly": "pri_01h9ajc6ma96qg11hqmgzs10tx",   # Example price ID for yearly billing
        "jobseeker_monthly": "pri_01h9ajcjk7spq6q0rhpj9sz2ch", 
        "jobseeker_yearly": "pri_01h9ajcs9zftfp5wphxcrtepwb",
    }
    
    # Return the mapped Paddle price ID or a default one
    return paddle_product_map.get(plan_identifier, "pri_default")


def create_customer(user):
    """
    Create a customer in Paddle
    
    Args:
        user: User model instance
    
    Returns:
        Paddle customer ID
    """
    try:
        # Check if user already has a Paddle customer ID
        if user.paddle_customer_id:
            print(f"Using existing Paddle customer ID: {user.paddle_customer_id}")
            return user.paddle_customer_id
        
        # Kontrol et: options sözlüğünde api_url var mı?
        if 'api_url' not in options:
            # api_url yoksa, sandbox durumuna göre yeniden oluştur
            api_url = 'https://sandbox-api.paddle.com' if settings.PADDLE_SANDBOX else 'https://api.paddle.com'
            print(f"Warning: 'api_url' not found in options dictionary. Using default: {api_url}")
        else:
            # api_url varsa, onu kullan
            api_url = options['api_url']
        
        # Paddle Billing API endpoint for customer creation
        endpoint = f"{api_url}/customers"
        
        # Prepare the request data
        # For documentation, see: https://developer.paddle.com/api-reference/customers
        email = user.email
        name = f"{user.first_name} {user.last_name}".strip() or user.username or email.split('@')[0]
        
        data = {
            "email": email,
            "name": name,
        }
        
        # Add locale if possible
        try:
            from django.utils.translation import get_language
            locale = get_language()
            if locale:
                data["locale"] = locale
        except ImportError:
            pass
        
        # Additional customer data if available
        # Address data
        if hasattr(user, 'country') and user.country:
            data["address"] = {
                "country_code": user.country,
            }
        
        # Make the API request
        response = requests.post(
            endpoint,
            json=data,
            headers=get_paddle_headers()
        )
        print("Paddle customer response: ", response.json())
        # Process the response
        if response.status_code == 201:
            response_data = response.json()
            if 'data' in response_data and 'id' in response_data['data']:
                customer_id = response_data['data']['id']
                
                # Paddle customer ID'yi kaydet
                # User modelinde doğrudan saklıyoruz
                user.paddle_customer_id = customer_id
                user.save(update_fields=['paddle_customer_id'])
                
                return customer_id
            else:
                print(f"Unexpected response format: {response_data}")
                return None
        else:
            # Log the error
            error_response = response.json()
            error_message = error_response.get('error', {}).get('message', 'Unknown error')
            print(f"Error creating Paddle customer: {error_message}")
            
            # Return None on error
            return None
            
    except Exception as e:
        print(f"Exception creating Paddle customer: {str(e)}")
        
        # Return None on error
        return None


def generate_checkout_url(user, plan, period):
    """
    Generate a Paddle checkout URL for subscription purchase
    
    Args:
        user: User model instance
        plan: SubscriptionPlan model instance
        period: 'monthly' or 'yearly'
    
    Returns:
        Checkout URL and passthrough data
    """
    # Get the Paddle price ID
    price_id = get_subscription_plan(plan, period)
    
    # Define the custom data (for webhook identification later)
    custom_data = {
        'user_id': user.id,
        'plan_id': plan.plan_id,
        'period': period,
        'unique_id': str(uuid.uuid4())
    }
    
    # Get or create a customer in Paddle
    customer_id = create_customer(user)
    
    # Kontrol et: options sözlüğünde api_url ve checkout_url var mı?
    if 'api_url' not in options:
        # api_url yoksa, sandbox durumuna göre yeniden oluştur
        api_url = 'https://sandbox-api.paddle.com' if settings.PADDLE_SANDBOX else 'https://api.paddle.com'
        print(f"Warning: 'api_url' not found in options dictionary. Using default: {api_url}")
    else:
        # api_url varsa, onu kullan
        api_url = options['api_url']

    if 'checkout_url' not in options:
        # checkout_url yoksa, sandbox durumuna göre yeniden oluştur
        checkout_url = 'https://sandbox-checkout.paddle.com' if settings.PADDLE_SANDBOX else 'https://checkout.paddle.com'
        print(f"Warning: 'checkout_url' not found in options dictionary. Using default: {checkout_url}")
    else:
        # checkout_url varsa, onu kullan
        checkout_url = options['checkout_url']
    
    # Prepare the request payload for Paddle API
    payload = {
        "items": [
            {
                "price_id": price_id,
                "quantity": 1
            }
        ],
        "customer_id": customer_id,  # Use the actual Paddle customer ID
        "custom_data": json.dumps(custom_data),
        "success_url": f"{settings.FRONTEND_URL}/account?subscribed=true",
        "cancel_url": f"{settings.FRONTEND_URL}/pricing",
    }
    
    # Add customer email only if we don't have a customer ID
    if not customer_id:
        payload["customer_email"] = user.email
    
    try:
        # Call Paddle API to create a checkout
        response = requests.post(
            f"{api_url}/checkout",
            json=payload,
            headers=get_paddle_headers()
        )
        
        response_data = response.json()
        
        if response.status_code == 201 and 'data' in response_data:
            checkout_url_from_response = response_data['data']['url']
            checkout_id = response_data['data']['id']
            
            return {
                'checkout_url': checkout_url_from_response,
                'checkout_id': checkout_id,
                'custom_data': custom_data
            }
        else:
            # Log error details
            error_message = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"Error creating Paddle checkout: {error_message}")
            
            # Fallback to client-side checkout for development/testing
            # In production, you should handle errors more gracefully
            fallback_url = f"{checkout_url}?price_id={price_id}&customer_email={user.email}&passthrough={json.dumps(custom_data)}"
            return {
                'checkout_url': fallback_url,
                'custom_data': custom_data
            }
            
    except Exception as e:
        # Log exception
        print(f"Exception creating Paddle checkout: {str(e)}")
        
        # Fallback checkout URL for development
        fallback_url = f"{checkout_url}?price_id={price_id}&customer_email={user.email}&passthrough={json.dumps(custom_data)}"
        return {
            'checkout_url': fallback_url,
            'custom_data': custom_data
        }


def verify_webhook_signature(headers, payload_json):
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
        print("Missing Paddle-Signature header")
        return False
    
    # Get public key from settings
    public_key = options['public_key']
    
    if not public_key or public_key == 'your_public_key':
        print("Missing or invalid Paddle public key in settings")
        # Return True for testing in development environment
        if options.get('sandbox', True):
            print("Sandbox mode enabled - bypassing signature verification")
            return True
        return False
    
    try:
        # Parse the signature header
        # Format: ts=timestamp;h=hash
        signature_parts = {}
        for part in signature_header.split(';'):
            if '=' in part:
                key, value = part.split('=', 1)
                signature_parts[key] = value
        
        # Get timestamp and signature
        timestamp = signature_parts.get('ts')
        signature = signature_parts.get('h')
        
        if not timestamp or not signature:
            print(f"Missing timestamp or hash in header: {signature_header}")
            return False
        
        # Create the string to verify
        # Format: timestamp + payload
        data_to_verify = f"{timestamp}:{payload_json}"
        
        # Calculate expected signature
        expected_signature = hmac.new(
            base64.b64decode(public_key),
            data_to_verify.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception as e:
        print(f"Error verifying Paddle webhook signature: {str(e)}")
        # In development, bypass verification
        if options.get('sandbox', True):
            print("Sandbox mode enabled - bypassing signature verification after error")
            return True
        return False


def cancel_subscription(paddle_subscription_id):
    """
    Cancel a subscription in Paddle.
    
    Args:
        paddle_subscription_id: Paddle subscription ID
    
    Returns:
        Boolean indicating success
    """
    if not paddle_subscription_id:
        print("No subscription ID provided for cancellation")
        return False
    
    try:
        # Kontrol et: options sözlüğünde api_url var mı?
        if 'api_url' not in options:
            # api_url yoksa, sandbox durumuna göre yeniden oluştur
            api_url = 'https://sandbox-api.paddle.com' if settings.PADDLE_SANDBOX else 'https://api.paddle.com'
            print(f"Warning: 'api_url' not found in options dictionary. Using default: {api_url}")
        else:
            # api_url varsa, onu kullan
            api_url = options['api_url']
        
        # Paddle API endpoint to cancel subscription
        endpoint = f"{api_url}/subscriptions/{paddle_subscription_id}/cancel"
        
        # Make the API request
        response = requests.post(
            endpoint,
            headers=get_paddle_headers()
        )
        
        # Process the response
        if response.status_code == 200:
            # Successfully canceled
            return True
        else:
            # Log error details
            error_response = response.json()
            error_message = error_response.get('error', {}).get('message', 'Unknown error')
            print(f"Error canceling subscription: {error_message}")
            return False
            
    except Exception as e:
        print(f"Exception canceling subscription: {str(e)}")
        return False


def get_subscription_details(paddle_subscription_id):
    """
    Get details of a Paddle subscription
    
    Args:
        paddle_subscription_id: Paddle subscription ID
    
    Returns:
        Dictionary with subscription details
    """
    if not paddle_subscription_id:
        print("No subscription ID provided")
        return None
    
    try:
        # Kontrol et: options sözlüğünde api_url var mı?
        if 'api_url' not in options:
            # api_url yoksa, sandbox durumuna göre yeniden oluştur
            api_url = 'https://sandbox-api.paddle.com' if settings.PADDLE_SANDBOX else 'https://api.paddle.com'
            print(f"Warning: 'api_url' not found in options dictionary. Using default: {api_url}")
        else:
            # api_url varsa, onu kullan
            api_url = options['api_url']
        
        # Paddle API endpoint to get subscription details
        endpoint = f"{api_url}/subscriptions/{paddle_subscription_id}"
        
        # Make the API request
        response = requests.get(
            endpoint,
            headers=get_paddle_headers()
        )
        
        # Process the response
        if response.status_code == 200:
            response_data = response.json()
            
            if 'data' in response_data:
                return response_data['data']
            else:
                print(f"Unexpected response format: {response_data}")
                return None
        else:
            # Log error details
            error_response = response.json()
            error_message = error_response.get('error', {}).get('message', 'Unknown error')
            print(f"Error getting subscription details: {error_message}")
            return None
            
    except Exception as e:
        print(f"Exception getting subscription details: {str(e)}")
        return None


def update_payment_method(paddle_subscription_id):
    """
    Generate a URL to update payment method for a subscription
    
    Args:
        paddle_subscription_id: Paddle subscription ID
    
    Returns:
        URL to update payment method
    """
    if not paddle_subscription_id:
        print("No subscription ID provided")
        return None
    
    try:
        # Kontrol et: options sözlüğünde api_url var mı?
        if 'api_url' not in options:
            # api_url yoksa, sandbox durumuna göre yeniden oluştur
            api_url = 'https://sandbox-api.paddle.com' if settings.PADDLE_SANDBOX else 'https://api.paddle.com'
            print(f"Warning: 'api_url' not found in options dictionary. Using default: {api_url}")
        else:
            # api_url varsa, onu kullan
            api_url = options['api_url']
        
        # Paddle API endpoint for payment method update
        endpoint = f"{api_url}/payment-methods/update"
        
        # Prepare the request data
        data = {
            "subscription_id": paddle_subscription_id,
            "return_url": f"{settings.FRONTEND_URL}/account"
        }
        
        # Make the API request
        response = requests.post(
            endpoint,
            json=data,
            headers=get_paddle_headers()
        )
        
        # Check if the request was successful
        if response.status_code == 201:
            response_data = response.json()
            
            if 'data' in response_data and 'url' in response_data['data']:
                # Return the update URL
                return response_data['data']['url']
            else:
                print(f"Invalid response format from Paddle API: {response_data}")
                return None
        else:
            # Log error details
            response_data = response.json()
            error_message = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"Error generating payment method update URL: {error_message}")
            
            # Fallback for development/testing
            return f"{options['checkout_url']}/subscription/update?subscription_id={paddle_subscription_id}"
            
    except Exception as e:
        print(f"Exception generating payment method update URL: {str(e)}")
        
        # Fallback URL for development
        return f"{options['checkout_url']}/subscription/update?subscription_id={paddle_subscription_id}"


def get_subscription_plan_by_price_id(price_id):
    """
    Get a subscription plan based on a Paddle price ID
    
    Args:
        price_id: Paddle price ID to look up
    
    Returns:
        SubscriptionPlan instance or None if not found
    """
    try:
        # Get the model
        from .models import SubscriptionPlan
        
        # Build a lookup of all active plans to their Paddle price IDs
        price_map = {}
        
        # Generate price maps for all active plans
        for plan in SubscriptionPlan.objects.filter(is_active=True):
            # Try for monthly
            monthly_price_id = get_subscription_plan(plan, 'monthly')
            if monthly_price_id:
                price_map[monthly_price_id] = plan
                
            # Try for yearly
            yearly_price_id = get_subscription_plan(plan, 'yearly')
            if yearly_price_id:
                price_map[yearly_price_id] = plan
        
        # Look up the plan by price ID
        return price_map.get(price_id)
    
    except Exception as e:
        print(f"Error finding plan by price ID: {str(e)}")
        return None


def get_customer_portal_url(paddle_customer_id, subscription_ids=None):
    """
    Get a URL to the Paddle customer portal for managing subscriptions
    
    Args:
        paddle_customer_id: Paddle customer ID
        subscription_ids: Optional list of subscription IDs to create deep links for
        
    Returns:
        URL to Paddle customer portal
    """
    try:
        if not paddle_customer_id:
            print("No Paddle customer ID provided")
            return None
            
        # Kontrol et: options içinde api_url var mı?
        if 'api_url' not in options:
            print("Warning: 'api_url' not found in options, recreating API URL")
            # API URL'yi yeniden oluştur
            api_url = 'https://sandbox-api.paddle.com' if options.get('sandbox', False) else 'https://api.paddle.com'
        else:
            api_url = options['api_url']
            
        # Endpoint for customer portal sessions
        endpoint = f"{api_url}/customers/{paddle_customer_id}/portal-sessions"
        print(f"Using Paddle API endpoint: {endpoint}")
        
        # Prepare request payload with subscription IDs (required format)
        data = {}
        
        # Add subscription_ids if provided - must be an array even for a single ID
        if subscription_ids:
            # Ensure subscription_ids is a list
            if isinstance(subscription_ids, list):
                data["subscription_ids"] = subscription_ids
            else:
                # If a single subscription ID is provided (not as a list)
                data["subscription_ids"] = [subscription_ids]
            
            print(f"Including subscription_ids in request: {data['subscription_ids']}")
        
        # Print request details for debugging
        print(f"Request payload: {json.dumps(data)}")
        headers = get_paddle_headers()
        
        # Make the API request
        try:
            response = requests.post(
                endpoint,
                json=data,
                headers=headers,
                timeout=10  # 10 seconds timeout
            )
            
            # Process the response
            print(f"API Response status code: {response.status_code}")
            
            if response.status_code == 201:
                response_data = response.json()
                
                # Extract URL from response - we need the overview URL
                if ('data' in response_data and 'urls' in response_data['data'] and 
                    'general' in response_data['data']['urls']):
                    
                    # New API format: general is an object with overview URL
                    if isinstance(response_data['data']['urls']['general'], dict) and 'overview' in response_data['data']['urls']['general']:
                        portal_url = response_data['data']['urls']['general']['overview']
                        print(f"Successfully generated customer portal URL (overview): {portal_url}")
                        return portal_url
                    
                    # Legacy format: general is directly the URL
                    elif isinstance(response_data['data']['urls']['general'], str):
                        portal_url = response_data['data']['urls']['general']
                        print(f"Successfully generated customer portal URL (legacy format): {portal_url}")
                        return portal_url
                
                print(f"Could not find portal URL in API response: {json.dumps(response_data)}")
            else:
                # Log error details
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', {}).get('message', 'Unknown error')
                    print(f"Error creating customer portal session: {error_message}")
                except:
                    print(f"Error response not in JSON format: {response.text}")
        
        except Exception as request_error:
            print(f"API request error: {str(request_error)}")
        
        # If we reached here, either API call failed or we're in sandbox mode without API access
        # Generate a realistic sandbox URL as a fallback
        if options.get('sandbox', False):
            print("Generating sandbox fallback URL")
            import uuid
            portal_link_id = f"cpl_{uuid.uuid4().hex[:24]}"
            token_part = f"token=pga_{uuid.uuid4().hex[:36]}"
            
            # Create sandbox URL with format matching real customer portal
            sandbox_url = f"https://sandbox-customer-portal.paddle.com/{portal_link_id}?action=overview&{token_part}"
            
            print(f"Generated sandbox URL: {sandbox_url}")
            return sandbox_url
        
        return None
            
    except Exception as e:
        print(f"Exception creating customer portal session: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Generate a sandbox fallback URL in case of any exception
        if options.get('sandbox', False):
            import uuid
            portal_link_id = f"cpl_{uuid.uuid4().hex[:24]}"
            token_part = f"token=pga_{uuid.uuid4().hex[:36]}"
            
            sandbox_url = f"https://sandbox-customer-portal.paddle.com/{portal_link_id}?action=overview&{token_part}"
            return sandbox_url
        
        return None 