from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, SubscriptionPaymentHistory

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_id', 'plan_type', 'price_monthly', 'price_yearly', 'currency', 'is_active')
    list_filter = ('plan_type', 'is_active', 'currency')
    search_fields = ('name', 'plan_id', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'period', 'start_date', 'end_date')
    list_filter = ('status', 'period', 'plan')
    search_fields = ('user__email', 'user__username', 'iyzico_subscription_reference_code')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'plan')

@admin.register(SubscriptionPaymentHistory)
class SubscriptionPaymentHistoryAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'payment_id', 'amount', 'currency', 'status', 'payment_date')
    list_filter = ('status', 'currency', 'payment_date')
    search_fields = ('payment_id', 'iyzico_payment_id', 'subscription__user__email')
    readonly_fields = ('payment_date',)
    raw_id_fields = ('subscription',)
