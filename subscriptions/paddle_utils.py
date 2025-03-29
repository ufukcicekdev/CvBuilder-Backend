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
        
        # Paddle Billing API endpoint for customer creation
        endpoint = f"{options['api_url']}/customers"
        
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
            f"{options['api_url']}/checkout",
            json=payload,
            headers=get_paddle_headers()
        )
        
        response_data = response.json()
        
        if response.status_code == 201 and 'data' in response_data:
            checkout_url = response_data['data']['url']
            checkout_id = response_data['data']['id']
            
            return {
                'checkout_url': checkout_url,
                'checkout_id': checkout_id,
                'custom_data': custom_data
            }
        else:
            # Log error details
            error_message = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"Error creating Paddle checkout: {error_message}")
            
            # Fallback to client-side checkout for development/testing
            # In production, you should handle errors more gracefully
            fallback_url = f"{options['checkout_url']}?price_id={price_id}&customer_email={user.email}&passthrough={json.dumps(custom_data)}"
            return {
                'checkout_url': fallback_url,
                'custom_data': custom_data
            }
            
    except Exception as e:
        # Log exception
        print(f"Exception creating Paddle checkout: {str(e)}")
        
        # Fallback checkout URL for development
        fallback_url = f"{options['checkout_url']}?price_id={price_id}&customer_email={user.email}&passthrough={json.dumps(custom_data)}"
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
        
        # For debugging
        print(f"Timestamp: {timestamp}")
        print(f"Signature: {signature}")
        
        # Create the string to verify
        # Format: timestamp + payload
        data_to_verify = f"{timestamp}:{payload_json}"
        
        # In Paddle v2, the public key needs to be properly decoded
        # The key format is: pdl_ntfset_XXXXX_YYYYY
        # We only need the YYYYY part
        # If key doesn't contain underscore, use as is (for backwards compatibility)
        if '_' in public_key:
            key_parts = public_key.split('_')
            if len(key_parts) >= 4:
                public_key = key_parts[3]
        
        # Replace problematic characters in the key
        public_key = public_key.replace(' ', '').replace('+', '+').replace('/', '/')
        
        # For debugging
        print(f"Using public key: {public_key}")
        
        # Try to base64 decode the key for HMAC
        try:
            # Try to decode if it looks like base64
            decoded_key = base64.b64decode(public_key)
        except:
            # If not decodable, use as is
            decoded_key = public_key.encode('utf-8')
        
        # Calculate expected signature
        expected_signature = hmac.new(
            decoded_key,
            data_to_verify.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # For debugging
        print(f"Expected signature: {expected_signature}")
        
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
    Cancel a subscription in Paddle
    
    Args:
        paddle_subscription_id: Paddle subscription ID
    
    Returns:
        Boolean indicating success
    """
    try:
        # The API endpoint for cancellation
        endpoint = f"{options['api_url']}/subscriptions/{paddle_subscription_id}/cancel"
        
        # Make request to Paddle API
        response = requests.post(
            endpoint,
            headers=get_paddle_headers()
        )
        
        # Check if the request was successful
        if response.status_code in [200, 201, 202, 204]:
            print(f"Successfully cancelled Paddle subscription: {paddle_subscription_id}")
            return True
        else:
            # Log error details
            response_data = response.json()
            error_message = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"Error cancelling Paddle subscription: {error_message}")
            return False
            
    except Exception as e:
        print(f"Exception cancelling Paddle subscription: {str(e)}")
        return False


def get_subscription_details(paddle_subscription_id):
    """
    Get subscription details from Paddle
    
    Args:
        paddle_subscription_id: Paddle subscription ID
    
    Returns:
        Subscription details
    """
    try:
        # The API endpoint for getting subscription details
        endpoint = f"{options['api_url']}/subscriptions/{paddle_subscription_id}"
        
        # Make request to Paddle API
        response = requests.get(
            endpoint,
            headers=get_paddle_headers()
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            response_data = response.json()
            
            if 'data' in response_data:
                subscription_data = response_data['data']
                
                # Map the subscription data to your format
                return {
                    'id': subscription_data.get('id'),
                    'status': subscription_data.get('status'),
                    'customer_id': subscription_data.get('customer_id'),
                    'next_billed_at': subscription_data.get('next_billed_at'),
                    'current_period_end': subscription_data.get('current_period_end'),
                    'created_at': subscription_data.get('created_at'),
                    'updated_at': subscription_data.get('updated_at')
                }
            else:
                print(f"Invalid response format from Paddle API: {response_data}")
                return None
        else:
            # Log error details
            response_data = response.json()
            error_message = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"Error getting Paddle subscription details: {error_message}")
            return None
            
    except Exception as e:
        print(f"Exception getting Paddle subscription details: {str(e)}")
        
        # Return None on error
        return None


def update_payment_method(paddle_subscription_id, return_url=None):
    """
    Generate a URL for the customer to update their payment method
    
    Args:
        paddle_subscription_id: Paddle subscription ID
        return_url: Optional URL to return to after updating payment method
    
    Returns:
        Update URL
    """
    try:
        # In the new Paddle API, updating payment method is done through a hosted page
        # We need to generate a checkout URL for this purpose
        
        # The API endpoint for creating a management link
        endpoint = f"{options['api_url']}/payment-methods/update"
        
        # Prepare the request payload
        payload = {
            "subscription_id": paddle_subscription_id
        }
        
        # Add return URL if provided
        if return_url:
            payload["return_url"] = return_url
        else:
            payload["return_url"] = f"{settings.FRONTEND_URL}/account"
        
        # Make request to Paddle API
        response = requests.post(
            endpoint,
            json=payload,
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