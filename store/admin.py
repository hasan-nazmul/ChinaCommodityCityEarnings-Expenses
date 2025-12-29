from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Product, Sale, Customer, Payout, ProductChangeRequest

# 1. Custom User Admin
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'date_joined')
    list_filter = ('role', 'is_staff', 'is_superuser')
    # Add 'role' to the editable fields in admin
    fieldsets = UserAdmin.fieldsets + (
        ('Role Configuration', {'fields': ('role',)}),
    )

# 2. Product Admin
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'name', 'investor', 'quantity', 'buying_price', 'selling_price', 'stock_status')
    list_filter = ('investor', 'created_at')
    search_fields = ('name', 'product_id', 'investor__username')
    readonly_fields = ('product_id', 'created_at')

    # Custom column to show Low Stock warning
    def stock_status(self, obj):
        if obj.quantity <= obj.low_stock_threshold:
            return "⚠️ LOW"
        return "✅ OK"
    stock_status.short_description = 'Stock Level'

# 3. Sale Admin (The Ledger)
@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'date', 'product', 'sold_by', 'quantity', 'total_amount', 'payment_method')
    list_filter = ('date', 'payment_method', 'product__investor')
    search_fields = ('transaction_id', 'product__name', 'customer__name', 'customer__mobile')
    date_hierarchy = 'date' # Adds a date drill-down bar at the top

# 4. Customer Admin
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'mobile', 'email', 'created_at')
    search_fields = ('name', 'mobile', 'email')
    ordering = ('-created_at',)

# 5. Payout Admin
@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('investor', 'amount', 'date')
    list_filter = ('investor', 'date')

# 6. Change Request Admin (The Waiting Room)
@admin.register(ProductChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('request_type', 'requester', 'name', 'status', 'created_at')
    list_filter = ('status', 'request_type', 'requester')
    search_fields = ('name', 'requester__username')
    readonly_fields = ('created_at',)