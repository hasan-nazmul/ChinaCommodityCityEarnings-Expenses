from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid
from decimal import Decimal

# 1. Custom User Model
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

# 2. Product Model
class Product(models.Model):
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    
    product_id = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    
    quantity = models.IntegerField(default=0)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    owner_split_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=30.00, 
        help_text="Percentage going to Business Owner"
    )
    investor_split_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=70.00, 
        help_text="Percentage kept by Investor"
    )
    
    low_stock_threshold = models.IntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.product_id:
            prefix = self.investor.username[:3].upper()
            suffix = str(uuid.uuid4().int)[:4]
            self.product_id = f"{prefix}{suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.product_id})"

# 3. Customer Model
class Customer(models.Model):
    name = models.CharField(max_length=100)
    mobile = models.CharField(max_length=20, unique=True) 
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.mobile})"

# 4. Sale Model (Updated with Discount)
class Sale(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('ONLINE', 'Online Transfer'),
    ]

    # Group multiple items in one receipt using this ID
    transaction_id = models.CharField(max_length=50, blank=True, null=True)

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    customer_name_text = models.CharField(max_length=100, blank=True, null=True) 
    customer_contact = models.CharField(max_length=100, blank=True, null=True)
    
    quantity = models.IntegerField()
    
    # CHANGED: Now storing percentage
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0) 

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='CASH')
    date = models.DateTimeField(auto_now_add=True)
    
    owner_profit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    investor_profit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if self.product:
            # 1. Calculate Gross for this item
            gross_total = self.product.selling_price * self.quantity
            
            # 2. Apply Percentage Discount (e.g., 10%)
            # Formula: Price - (Price * (10/100))
            discount_amount = gross_total * (self.discount_percent / Decimal(100))
            self.total_amount = gross_total - discount_amount
            
            # 3. Calculate Net Profit based on DISCOUNTED amount
            total_cost = self.product.buying_price * self.quantity
            total_net_profit = self.total_amount - total_cost
            
            # 4. Split Profit
            owner_percent = Decimal(self.product.owner_split_percent) / Decimal(100)
            investor_percent = Decimal(self.product.investor_split_percent) / Decimal(100)
            
            self.owner_profit_amount = total_net_profit * owner_percent
            
            # Investor gets profit share + original capital
            investor_share = total_net_profit * investor_percent
            self.investor_profit_amount = investor_share + total_cost
            
            # Reduce Stock (Only on new sale)
            if not self.pk: 
                self.product.quantity -= self.quantity
                self.product.save()
            
        super().save(*args, **kwargs)
        
# 5. Payout History
class Payout(models.Model):
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    proof_image = models.ImageField(upload_to='payout_proofs/', blank=True, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Paid {self.amount} to {self.investor.username}"