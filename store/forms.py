from django import forms
from .models import Product, Sale

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'quantity', 'buying_price', 'selling_price', 'low_stock_threshold', 'owner_split_percent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Winter Jacket'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'buying_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'owner_split_percent': forms.NumberInput(attrs={
                'class': 'form-control', 
                'id': 'owner_share_input', 
                'max': 100,
                'step': '0.01'
            }),
        }

    # --- THE FIX IS HERE ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We make this optional because the Owner's HTML form hides this field.
        # If it is required (default), the form validation fails for Owners.
        self.fields['owner_split_percent'].required = False

class SaleForm(forms.Form):
    product_id_search = forms.CharField(
        label="Product ID or Name", 
        widget=forms.TextInput(attrs={
            'class': 'form-control border-start-0 fs-4 fw-bold text-dark', 
            'placeholder': 'Scan or Type...',
            'autofocus': 'autofocus'
        })
    )
    
    customer_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Walk-in Customer'})
    )
    customer_contact = forms.CharField(
        required=False,
        label="Mobile / Email",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+880...'})
    )

    quantity = forms.IntegerField(
        min_value=1, 
        widget=forms.NumberInput(attrs={'class': 'form-control border-start-0 fw-bold', 'value': 1})
    )
    
    discount_amount = forms.DecimalField(
        required=False,
        min_value=0,
        label="Discount ($)",
        widget=forms.NumberInput(attrs={'class': 'form-control border-start-0 fw-bold text-danger', 'placeholder': '0.00'})
    )

    payment_method = forms.ChoiceField(
        choices=Sale.PAYMENT_METHODS, 
        widget=forms.Select(attrs={'class': 'form-select form-select-lg fw-bold'})
    )