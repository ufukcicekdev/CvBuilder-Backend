from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class SubscriptionPlan(models.Model):
    """Model for subscription plans"""
    PLAN_TYPE_CHOICES = (
        ('free', _('Free')),
        ('jobseeker', _('Job Seeker')),
        ('premium', _('Premium')),
    )

    plan_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES)
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Store features as JSON
    features = models.JSONField(default=dict)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Subscription Plan')
        verbose_name_plural = _('Subscription Plans')


class UserSubscription(models.Model):
    """Model for user subscriptions"""
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('canceled', _('Canceled')),
        ('expired', _('Expired')),
        ('trial', _('Trial')),
        ('pending', _('Pending')),
    )

    PERIOD_CHOICES = (
        ('monthly', _('Monthly')),
        ('yearly', _('Yearly')),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default='monthly')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    
    # Iyzico specific fields
    iyzico_subscription_reference_code = models.CharField(max_length=100, blank=True, null=True)
    iyzico_customer_reference_code = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"
    
    class Meta:
        verbose_name = _('User Subscription')
        verbose_name_plural = _('User Subscriptions')


class SubscriptionPaymentHistory(models.Model):
    """Model for subscription payment history"""
    STATUS_CHOICES = (
        ('success', _('Success')),
        ('failed', _('Failed')),
        ('pending', _('Pending')),
    )

    subscription = models.ForeignKey(UserSubscription, on_delete=models.CASCADE, related_name='payments')
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(auto_now_add=True)
    
    # Iyzico specific fields
    iyzico_payment_id = models.CharField(max_length=100, blank=True, null=True)
    iyzico_payment_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.subscription.user.email} - {self.amount} {self.currency} ({self.status})"
    
    class Meta:
        verbose_name = _('Subscription Payment History')
        verbose_name_plural = _('Subscription Payment Histories')
