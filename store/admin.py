from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Product, Sale, Payout

# We define a custom Admin setup for our User
class CustomUserAdmin(UserAdmin):
    model = User
    # This adds the 'role' field to the "Edit User" page in Admin
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role',)}),
    )
    # This adds the 'role' field to the "Add User" page
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),
    )

# Register the User using this special Admin class
admin.site.register(User, CustomUserAdmin)

admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(Payout)