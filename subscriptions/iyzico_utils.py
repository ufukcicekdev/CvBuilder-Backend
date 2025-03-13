import iyzipay
import uuid
import json
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import get_language

# Initialize Iyzico options using IYZIPAY_SETTINGS
options = settings.IYZIPAY_SETTINGS if hasattr(settings, 'IYZIPAY_SETTINGS') else {
    'api_key': settings.IYZICO_API_KEY,
    'secret_key': settings.IYZICO_SECRET_KEY,
    'base_url': settings.IYZICO_BASE_URL
}

def get_subscription_pricing_plan(plan, period):
    """
    Create or get a subscription pricing plan in Iyzico
    
    Args:
        plan: SubscriptionPlan model instance
        period: 'monthly' or 'yearly'
    
    Returns:
        Iyzico pricing plan reference code
    """
    # Get the price based on period
    price = plan.price_monthly if period == 'monthly' else plan.price_yearly
    
    # Set the interval based on period
    interval = 'MONTHLY' if period == 'monthly' else 'YEARLY'
    
    # Create a unique reference code for the pricing plan
    reference_code = f"{plan.plan_id}_{period}_{uuid.uuid4().hex[:8]}"
    
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'name': f"{plan.name} ({period})",
        'price': str(price),
        'currencyCode': plan.currency,
        'paymentInterval': interval,
        'paymentIntervalCount': 1,
        'planPaymentType': 'RECURRING',
        'recurrenceCount': None,  # Unlimited
        'referenceCode': reference_code,
        'trialPeriodDays': 0  # No trial period
    }
    
    # Create the pricing plan in Iyzico using SubscriptionPlan
    result = iyzipay.SubscriptionPlan().create(request, options)
    
    # Check if the request was successful
    if result.status == 'success':
        response_data = json.loads(result.read().decode('utf-8'))
        return response_data.get('referenceCode')
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico pricing plan creation failed: {error_data.get('errorMessage')}")


def create_customer(user):
    """
    Create a customer in Iyzico
    
    Args:
        user: User model instance
    
    Returns:
        Iyzico customer reference code
    """
    # Create a unique reference code for the customer
    reference_code = f"customer_{user.id}_{uuid.uuid4().hex[:8]}"
    
    # Get the user's name
    name = user.first_name if hasattr(user, 'first_name') and user.first_name else user.username
    surname = user.last_name if hasattr(user, 'last_name') and user.last_name else ''
    
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'name': name,
        'surname': surname,
        'email': user.email,
        'identityNumber': f"ID_{user.id}",
        'gsmNumber': user.phone if hasattr(user, 'phone') and user.phone else '',
        'billingAddress': {
            'contactName': f"{name} {surname}",
            'city': 'Istanbul',
            'country': 'Turkey',
            'address': 'Default Address',
            'zipCode': '34000'
        },
        'shippingAddress': {
            'contactName': f"{name} {surname}",
            'city': 'Istanbul',
            'country': 'Turkey',
            'address': 'Default Address',
            'zipCode': '34000'
        },
        'referenceCode': reference_code
    }
    
    # Create the customer in Iyzico using SubscriptionCustomer
    result = iyzipay.SubscriptionCustomer().create(request, options)
    
    # Check if the request was successful
    if result.status == 'success':
        response_data = json.loads(result.read().decode('utf-8'))
        return response_data.get('referenceCode')
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico customer creation failed: {error_data.get('errorMessage')}")


def create_subscription(user, plan, period, card_token=None):
    """
    Create a subscription in Iyzico
    
    Args:
        user: User model instance
        plan: SubscriptionPlan model instance
        period: 'monthly' or 'yearly'
        card_token: Optional card token for payment
    
    Returns:
        Iyzico subscription reference code
    """
    # Get or create the customer in Iyzico
    try:
        # Check if the user already has a subscription
        if hasattr(user, 'subscription') and user.subscription.iyzico_customer_reference_code:
            customer_reference_code = user.subscription.iyzico_customer_reference_code
        else:
            customer_reference_code = create_customer(user)
    except Exception as e:
        raise Exception(f"Failed to create customer: {str(e)}")
    
    # Get or create the pricing plan in Iyzico
    try:
        pricing_plan_reference_code = get_subscription_pricing_plan(plan, period)
    except Exception as e:
        raise Exception(f"Failed to create pricing plan: {str(e)}")
    
    # Create a unique reference code for the subscription
    subscription_reference_code = f"sub_{user.id}_{plan.plan_id}_{period}_{uuid.uuid4().hex[:8]}"
    
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'pricingPlanReferenceCode': pricing_plan_reference_code,
        'customerReferenceCode': customer_reference_code,
        'subscriptionInitialStatus': 'ACTIVE',
        'referenceCode': subscription_reference_code
    }
    
    # If a card token is provided, add it to the request
    if card_token:
        request['paymentCard'] = {
            'cardToken': card_token,
            'cardUserKey': f"user_{user.id}"
        }
    
    # Create the subscription in Iyzico using SubscriptionCheckoutDirect
    result = iyzipay.SubscriptionCheckoutDirect().create(request, options)
    
    # Check if the request was successful
    if result.status == 'success':
        response_data = json.loads(result.read().decode('utf-8'))
        return response_data.get('referenceCode')
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico subscription creation failed: {error_data.get('errorMessage')}")


def cancel_subscription(subscription_reference_code):
    """
    Cancel a subscription in Iyzico
    
    Args:
        subscription_reference_code: Iyzico subscription reference code
    
    Returns:
        Boolean indicating success
    """
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'subscriptionReferenceCode': subscription_reference_code
    }
    
    # Cancel the subscription in Iyzico
    # Note: API endpoint may need to be updated based on new Iyzico API
    # This is a placeholder and may need adjustment
    result = iyzipay.HttpClient().delete('/v2/subscription/' + subscription_reference_code, options, request)
    
    # Check if the request was successful
    if result.status == 'success':
        return True
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico subscription cancellation failed: {error_data.get('errorMessage')}")


def get_subscription_details(subscription_reference_code):
    """
    Get subscription details from Iyzico
    
    Args:
        subscription_reference_code: Iyzico subscription reference code
    
    Returns:
        Subscription details
    """
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'subscriptionReferenceCode': subscription_reference_code
    }
    
    # Get the subscription details from Iyzico
    # Note: API endpoint may need to be updated based on new Iyzico API
    # This is a placeholder and may need adjustment
    result = iyzipay.HttpClient().get('/v2/subscription/' + subscription_reference_code, options, request)
    
    # Check if the request was successful
    if result.status == 'success':
        response_data = json.loads(result.read().decode('utf-8'))
        return response_data
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico subscription details failed: {error_data.get('errorMessage')}")


def update_subscription_card(subscription_reference_code, card_token):
    """
    Update the card used for a subscription in Iyzico
    
    Args:
        subscription_reference_code: Iyzico subscription reference code
        card_token: New card token
    
    Returns:
        Boolean indicating success
    """
    # Prepare the request
    request = {
        'locale': get_language() or 'en',
        'conversationId': str(uuid.uuid4()),
        'subscriptionReferenceCode': subscription_reference_code,
        'paymentCard': {
            'cardToken': card_token
        }
    }
    
    # Update the card in Iyzico
    # Note: API endpoint may need to be updated based on new Iyzico API
    # This is a placeholder and may need adjustment
    result = iyzipay.HttpClient().put('/v2/subscription/' + subscription_reference_code + '/card-update', options, request)
    
    # Check if the request was successful
    if result.status == 'success':
        return True
    else:
        # Log the error and raise an exception
        error_data = json.loads(result.read().decode('utf-8'))
        raise Exception(f"Iyzico subscription card update failed: {error_data.get('errorMessage')}") 