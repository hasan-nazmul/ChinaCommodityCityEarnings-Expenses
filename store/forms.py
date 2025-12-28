from django import forms
from .models import Product, Sale

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'quantity', 'buying_price', 'selling_price', 'low_stock_threshold', 'owner_split_percent', 'investor_split_percent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'buying_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'owner_split_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'investor_split_percent': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class SaleForm(forms.Form):
    # We use a simple form here because we need custom logic to find products by ID
    product_id_search = forms.CharField(label="Product ID or Name", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter XXX1234'}))
    quantity = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control', 'value': 1}))
    payment_method = forms.ChoiceField(choices=Sale.PAYMENT_METHODS, widget=forms.Select(attrs={'class': 'form-select'}))