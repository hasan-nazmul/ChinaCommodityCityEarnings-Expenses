import pandas as pd
from .models import Sale
from django.utils import timezone
from datetime import timedelta

def get_predicted_top_product(investor_user):
    # 1. Get sales data for this investor from the last 30 days
    last_month = timezone.now() - timedelta(days=30)
    sales = Sale.objects.filter(
        product__investor=investor_user, 
        date__gte=last_month
    ).values('product__name', 'quantity', 'date')

    if not sales:
        return "Not enough data"

    # 2. Convert to Pandas DataFrame
    df = pd.DataFrame(list(sales))

    # 3. Group by Product Name and Sum the Quantity
    # This finds the most popular item based on recent history
    top_products = df.groupby('product__name')['quantity'].sum().sort_values(ascending=False)

    # 4. Return the name of the top product
    if not top_products.empty:
        return top_products.index[0] # Returns name of #1 product
    return "Unknown"