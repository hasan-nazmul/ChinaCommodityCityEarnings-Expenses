from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid
from datetime import datetime

# 1. Custom User Model to distinguish Owner vs Investor
class User(AbstractUser):
    IS_OWNER = 'OWNER'
    IS_INVESTOR = 'INVESTOR'
    IS_STAFF = 'STAFF'
    
    ROLE_CHOICES = [
        (IS_OWNER, 'Business Owner'),
        (IS_INVESTOR, 'Investor'),
        (IS_STAFF, 'Staff/Seller'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=IS_STAFF)

# 2. Product Model with Automated ID Logic
class Product(models.Model):
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    
    # The Automated ID (e.g., "ALI1234")
    product_id = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    
    quantity = models.IntegerField(default=0)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Profit Splits (%)
    owner_split_percent = models.IntegerField(default=30, help_text="Percentage going to Business Owner")
    investor_split_percent = models.IntegerField(default=70, help_text="Percentage kept by Investor")
    
    low_stock_threshold = models.IntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automated ID Logic
        if not self.product_id:
            # Take first 3 letters of investor's username, uppercase them
            prefix = self.investor.username[:3].upper()
            # Generate a random 4 digit number
            suffix = str(uuid.uuid4().int)[:4]
            self.product_id = f"{prefix}{suffix}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.product_id})"

# 3. Sale Model (The Transaction)
class Sale(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('ONLINE', 'Online Transfer'),
    ]

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='CASH')
    date = models.DateTimeField(auto_now_add=True)
    
    # We store the calculated profit at the moment of sale
    # This prevents data issues if profit % changes later
    owner_profit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    investor_profit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # Calculate totals and splits automatically
        if self.product:
            self.total_amount = self.product.selling_price * self.quantity
            
            # Calculate Net Profit per unit
            net_profit_per_unit = self.product.selling_price - self.product.buying_price
            total_net_profit = net_profit_per_unit * self.quantity
            
            # Split the profit
            self.owner_profit_amount = total_net_profit * (self.product.owner_split_percent / 100)
            
            # Investor gets their share of profit + the original capital (buying price)
            investor_share = total_net_profit * (self.product.investor_split_percent / 100)
            capital_back = self.product.buying_price * self.quantity
            self.investor_profit_amount = investor_share + capital_back
            
            # Reduce Stock
            self.product.quantity -= self.quantity
            self.product.save()
            
        super().save(*args, **kwargs)

# 4. Payout History (Owner paying Investor)
class Payout(models.Model):
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    proof_image = models.ImageField(upload_to='payout_proofs/', blank=True, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Paid {self.amount} to {self.investor.username}"