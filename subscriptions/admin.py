from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, SubscriptionPaymentHistory, PaymentGateway

@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'gateway_type', 'is_active', 'is_default', 'position')
    list_filter = ('gateway_type', 'is_active', 'is_default')
    search_fields = ('name',)
    ordering = ('position',)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_id', 'plan_type', 'price_monthly', 'price_yearly', 'currency', 'is_active')
    list_filter = ('plan_type', 'is_active', 'currency')
    search_fields = ('name', 'plan_id', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'period', 'payment_provider', 'start_date', 'end_date')
    list_filter = ('status', 'period', 'plan', 'payment_provider')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'plan')

@admin.register(SubscriptionPaymentHistory)
class SubscriptionPaymentHistoryAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'payment_id', 'amount', 'currency', 'status', 'payment_date', 'payment_provider')
    list_filter = ('status', 'currency', 'payment_date', 'payment_provider')
    search_fields = ('payment_id', 'subscription__user__email', 'paytr_merchant_oid', 'paytr_payment_id')
    readonly_fields = ('payment_date',)
    raw_id_fields = ('subscription',)
