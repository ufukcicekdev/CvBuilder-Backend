import os
import uuid
import json
import requests
import hashlib
import base64
import hmac
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.utils.translation import get_language

from .models import UserSubscription

# Initialize PAYTR options
options = settings.PAYTR_SETTINGS if hasattr(settings, 'PAYTR_SETTINGS') else {
    'merchant_id': settings.PAYTR_MERCHANT_ID,
    'merchant_key': settings.PAYTR_MERCHANT_KEY,
    'merchant_salt': settings.PAYTR_MERCHANT_SALT,
    'api_url': 'https://www.paytr.com/odeme/api',
    'test_mode': settings.PAYTR_TEST_MODE if hasattr(settings, 'PAYTR_TEST_MODE') else False,
}

def generate_paytr_token(params):
    """
    Generate PAYTR hash token
    
    Args:
        params: Dictionary of parameters
    
    Returns:
        Hash token for PAYTR API
    """
    # Create parameter string
    param_str = ''
    # Sort parameters by key
    for key in sorted(params.keys()):
        param_str += str(params[key])
    
    # Add merchant salt
    param_str += options['merchant_salt']
    
    # Create hash
    hash_obj = hashlib.sha256(param_str.encode('utf-8'))
    hash_str = base64.b64encode(hash_obj.digest()).decode('utf-8')
    
    return hash_str

def create_paytr_hash(merchant_id, user_ip, merchant_oid, email, payment_amount, user_basket, test_mode):
    """
    Create PayTR hash for iframe
    """
    hash_str = merchant_id + user_ip + merchant_oid + email + str(payment_amount) + user_basket + str(test_mode)
    hash_str += options['merchant_salt']
    
    # Create hash
    hash_obj = hashlib.sha256(hash_str.encode('utf-8'))
    paytr_hash = base64.b64encode(hash_obj.digest()).decode('utf-8')
    
    return paytr_hash

def create_payment_form(user, merchant_oid, plan, amount, period, user_ip=None):
    """
    Creates a PAYTR payment form for Virtual POS
    
    Args:
        user: User model instance
        merchant_oid: Merchant order ID to reference later
        plan: SubscriptionPlan instance
        amount: Amount to charge
        period: Subscription period ('monthly' or 'yearly')
        user_ip: User IP address (optional)
    
    Returns:
        Dictionary with payment form data including token and url
    """
    try:
        # Get user info
        user_ip = user_ip or "127.0.0.1"
        email = user.email
        
        # Get or create user name
        if user.first_name and user.last_name:
            user_name = f"{user.first_name} {user.last_name}"
        elif hasattr(user, 'username') and user.username:
            user_name = user.username
        else:
            user_name = email.split('@')[0]
            
        # Convert amount to integer (PAYTR requires amount in cents)
        # Multiply by 100 and convert to integer as per documentation
        payment_amount = int(float(amount) * 100)
        
        # Create basket item as JSON string
        basket_items = [
            [plan.name, str(amount), 1]  # Format as per PayTR documentation: [item_name, price, quantity]
        ]
        user_basket = base64.b64encode(json.dumps(basket_items).encode('utf-8')).decode('utf-8')
        
        # Currency - PAYTR default is TL
        currency = plan.currency
        if currency.upper() not in ['TL', 'USD', 'EUR', 'GBP']:
            currency = 'TL'
        
        # Test mode setting
        test_mode = 1 if options['test_mode'] else 0
        
        # Merchant ID, Key and Salt from settings
        merchant_id = options['merchant_id']
        merchant_key = options['merchant_key']
        merchant_salt = options['merchant_salt']
        
        # Get user language
        lang = get_language() or 'tr'
        
        # Lang parametresi için sadece ilk iki karakteri al (en-us -> en)
        # PayTR sadece basit dil kodlarını kabul ediyor: tr, en, vb.
        if lang and len(lang) >= 2:
            lang = lang[:2].lower()
        else:
            lang = 'tr'  # Varsayılan olarak Türkçe
        
        # Create callback URLs
        no_inst = 0  # No installment
        max_inst = 0  # Maximum installment (0 = use default)
        
        # Success and fail URLs
        merchant_ok_url = f"{settings.FRONTEND_URL}/payment/success"
        merchant_fail_url = f"{settings.FRONTEND_URL}/payment/fail"
        
        # Create hash for token - must follow specific order per documentation
        hash_str = f"{merchant_id}{user_ip}{merchant_oid}{email}{payment_amount}{user_basket}{no_inst}{max_inst}{'TL'}{test_mode}{merchant_salt}"
        
        # Create hash
        hash_obj = hmac.new(merchant_key.encode('utf-8'), hash_str.encode('utf-8'), hashlib.sha256)
        paytr_token = base64.b64encode(hash_obj.digest()).decode('utf-8')
        
        # Create post data for PAYTR
        post_data = {
            'merchant_id': merchant_id,
            'user_ip': user_ip,
            'merchant_oid': merchant_oid,
            'email': email,
            'payment_amount': payment_amount,
            'paytr_token': paytr_token,
            'user_basket': user_basket,
            'debug_on': 1 if settings.DEBUG else 0,
            'no_installment': no_inst,
            'max_installment': max_inst,
            'user_name': user_name,
            'user_address': user.address if user.address else 'Adres girilmemiş',
            'user_phone': user.phone if user.phone else 'Telefon girilmemiş',
            'merchant_ok_url': merchant_ok_url,
            'merchant_fail_url': merchant_fail_url,
            'timeout_limit': 30,  # 30 minutes timeout
            'currency': 'TL',
            'test_mode': test_mode,
            'lang': lang,
        }
        
        print("PayTR API post data:", post_data)  # Debug için
        
        # Get the iframe token from PayTR
        response = requests.post(
            "https://www.paytr.com/odeme/api/get-token",
            data=post_data
        )
        
        # Parse the response
        try:
            response_data = response.json()
            print("PayTR API response:", response_data)  # Debug için
            
            if response_data.get('status') == 'success':
                token = response_data.get('token')
                iframe_url = f"https://www.paytr.com/odeme/guvenli/{token}"
                
                # Return the data
                return {
                    'status': 'success',
                    'iframe_url': iframe_url,
                    'token': token,
                    'merchant_oid': merchant_oid,
                }
            else:
                # Log the error
                print(f"PayTR Error: {response_data.get('reason')}")
                
                return {
                    'status': 'error',
                    'message': response_data.get('reason', 'Unknown error'),
                }
        except Exception as e:
            # Log any exceptions
            print(f"Error parsing PayTR response: {str(e)}")
            
            return {
                'status': 'error',
                'message': str(e),
            }
            
    except Exception as e:
        # Log any exceptions
        print(f"Error creating PayTR payment form: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
        }

def verify_webhook_signature(request_data, merchant_oid, status, total_amount, hash_key):
    """
    Verify PayTR webhook signature
    
    Args:
        request_data: Dict containing the whole request data
        merchant_oid: Merchant order ID
        status: Payment status
        total_amount: Total amount
        hash_key: Hash key from the request
    
    Returns:
        Boolean indicating if the signature is valid
    """
    try:
        # Get merchant key and salt from settings
        merchant_key = options['merchant_key']
        merchant_salt = options['merchant_salt']
        
        # Create the hash string
        hash_str = merchant_oid + merchant_salt + status + total_amount + merchant_key
        
        # Compute hash
        calculated_hash = base64.b64encode(hashlib.sha256(hash_str.encode('utf-8')).digest()).decode('utf-8')
        
        # Compare hashes
        return calculated_hash == hash_key
        
    except Exception as e:
        print(f"Error verifying PayTR webhook signature: {str(e)}")
        return False
        
def process_successful_payment(merchant_oid, payment_amount):
    """
    Process a successful payment
    
    Args:
        merchant_oid: Merchant order ID
        payment_amount: Payment amount
    
    Returns:
        Boolean indicating success
    """
    try:
        # Merchant OID formatı: cvb + SUBSCRIPTION_ID + RANDOM
        # Önce 'cvb' ön ekini kontrol edelim
        if merchant_oid.startswith('cvb'):
            # 'cvb' sonrasındaki kısmı alalım
            remaining = merchant_oid[3:]
            
            # Subscription ID'yi çıkarmak için sayısal karakterleri bulalım
            import re
            subscription_id_match = re.match(r'^(\d+)', remaining)
            
            if subscription_id_match:
                subscription_id = subscription_id_match.group(1)
                print(f"Extracted subscription ID: {subscription_id}")
                
                # Find the subscription
                try:
                    subscription = UserSubscription.objects.get(id=subscription_id)
                    
                    # Update subscription status and dates
                    if subscription.status in ['pending', 'expired']:
                        subscription.status = 'active'
                        
                        # Start date bugün, end date period'a göre belirlenir
                        subscription.start_date = timezone.now()
                        
                        # Set end date based on payment date + 1 month or 1 year
                        if subscription.period == 'yearly':
                            subscription.end_date = timezone.now() + timedelta(days=365)  # Approximately 1 year
                        else:
                            subscription.end_date = timezone.now() + timedelta(days=30)  # Approximately 1 month
                            
                        subscription.save()
                        
                        # Create payment history record
                        from .models import SubscriptionPaymentHistory
                        payment = SubscriptionPaymentHistory.objects.create(
                            subscription=subscription,
                            amount=payment_amount / 100,  # Convert back from cents
                            currency=subscription.plan.currency,
                            status='success',
                            payment_provider='paytr',
                            paytr_merchant_oid=merchant_oid,
                            paytr_amount=payment_amount / 100  # Convert back from cents
                        )
                        
                        return True
                    else:
                        print(f"Subscription is already active or has unexpected status: {subscription.status}")
                        return True  # Still return true to acknowledge the payment
                    
                except UserSubscription.DoesNotExist:
                    print(f"No subscription found with ID: {subscription_id}")
                    return False
            else:
                print(f"Could not extract subscription ID from merchant_oid: {merchant_oid}")
                return False
        else:
            print(f"Invalid merchant_oid format (doesn't start with 'cvb'): {merchant_oid}")
            return False
        
    except Exception as e:
        print(f"Error processing successful payment: {str(e)}")
        return False 