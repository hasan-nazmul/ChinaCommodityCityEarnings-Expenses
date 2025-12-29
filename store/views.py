import json
import uuid
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, Max
from django.db import transaction
from django.http import JsonResponse

from .models import Product, Sale, User, Payout, Customer
from .forms import ProductForm
from .analytics import get_predicted_top_product
import csv
from django.http import HttpResponse

# ==========================================
# 1. DASHBOARD & ANALYTICS
# ==========================================
@login_required
def dashboard(request):
    user = request.user
    
    # 1. Handle Filters
    filter_investor_id = request.GET.get('investor')
    
    # 2. Base Queries (Prepare them, but DO NOT slice yet)
    products_query = Product.objects.all()
    sales_query = Sale.objects.all().order_by('-date')
    
    # 3. Apply Filter (BEFORE slicing)
    if filter_investor_id and filter_investor_id != 'all':
        products_query = products_query.filter(investor_id=filter_investor_id)
        sales_query = sales_query.filter(product__investor_id=filter_investor_id)

    # 4. Now execute the queries and Slice
    products = products_query
    sales_history = sales_query[:50] # <--- Slice happens LAST

    # 5. Global Stats
    cash_income = Sale.objects.filter(payment_method='CASH').aggregate(t=Sum('total_amount'))['t'] or 0
    card_income = Sale.objects.filter(payment_method='CARD').aggregate(t=Sum('total_amount'))['t'] or 0
    online_income = Sale.objects.filter(payment_method='ONLINE').aggregate(t=Sum('total_amount'))['t'] or 0

    payment_stats = {
        'cash': round(cash_income, 2),
        'card': round(card_income, 2),
        'online': round(online_income, 2),
        'total': round(cash_income + card_income + online_income, 2)
    }

    # 6. Financials
    investors_only = User.objects.filter(role='INVESTOR')
    financials = []
    
    for inv in investors_only:
        t_earned = Sale.objects.filter(product__investor=inv).aggregate(total=Sum('investor_profit_amount'))['total'] or 0
        t_paid = inv.payouts.aggregate(total=Sum('amount'))['total'] or 0
        t_due = t_earned - t_paid
        
        financials.append({
            'investor': inv,
            'earned': round(t_earned, 2),
            'paid': round(t_paid, 2),
            'due': round(t_due, 2)
        })

    # 7. Dropdown List
    all_sellers = User.objects.filter(role__in=['OWNER', 'INVESTOR']).order_by('username')

    # 8. Owner Income
    owner_net_income = Sale.objects.aggregate(total=Sum('owner_profit_amount'))['total'] or 0

    # 9. Personal Wallet
    my_earned = 0
    my_paid = 0
    my_due = 0
    my_predicted_product = "N/A"

    if user.role == 'INVESTOR':
        my_earned = Sale.objects.filter(product__investor=user).aggregate(total=Sum('investor_profit_amount'))['total'] or 0
        my_paid = user.payouts.aggregate(total=Sum('amount'))['total'] or 0
        my_due = my_earned - my_paid
        my_predicted_product = get_predicted_top_product(user)

    context = {
        'products': products,
        'recent_sales': sales_history,
        'financials': financials,
        'owner_net_income': round(owner_net_income, 2),
        'payment_stats': payment_stats,
        'sellers_list': all_sellers,
        'current_filter': int(filter_investor_id) if filter_investor_id and filter_investor_id != 'all' else 'all',
        'is_owner': user.role == 'OWNER',
        'total_earned': round(my_earned, 2),
        'total_paid': round(my_paid, 2),
        'due': round(my_due, 2),
        'predicted_product': my_predicted_product
    }

    return render(request, 'store/dashboard.html', context)

# ==========================================
# 2. INVENTORY MANAGEMENT
# ==========================================
@login_required
def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.investor = request.user
            
            if request.user.role == 'OWNER':
                product.owner_split_percent = Decimal(100)
                product.investor_split_percent = Decimal(0)
            else:
                if product.owner_split_percent > 100:
                    product.owner_split_percent = Decimal(100)
                product.investor_split_percent = Decimal(100) - product.owner_split_percent
            
            product.save()
            messages.success(request, f"Product {product.product_id} added successfully!")
            return redirect('dashboard')
    else:
        form = ProductForm()
    return render(request, 'store/add_product.html', {'form': form})


# ==========================================
# 3. SALES & CART SYSTEM
# ==========================================
@login_required
def api_get_product(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'error': 'Empty query'}, status=400)
        
    product = Product.objects.filter(
        Q(product_id__iexact=query) | Q(name__iexact=query)
    ).first()
    
    if product:
        return JsonResponse({
            'found': True,
            'id': product.id,
            'name': product.name,
            'price': float(product.selling_price),
            'stock': product.quantity,
            'custom_id': product.product_id
        })
    return JsonResponse({'found': False})

@login_required
def sell_product(request):
    recent_sales = Sale.objects.order_by('-date')[:5]

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cart_items = data.get('items', [])
            customer_info = data.get('customer', {})
            payment_method = data.get('payment_method', 'CASH')
            discount_percent = Decimal(data.get('discount_percent', 0))

            if not cart_items:
                return JsonResponse({'success': False, 'message': 'Cart is empty'})

            trans_id = str(uuid.uuid4())[:8].upper()

            customer_obj = None
            c_contact = customer_info.get('contact')
            c_name = customer_info.get('name')
            
            if c_contact:
                customer_obj, created = Customer.objects.get_or_create(
                    mobile=c_contact,
                    defaults={'name': c_name or "Unknown"}
                )
                if not created and c_name:
                    customer_obj.name = c_name
                    customer_obj.save()

            with transaction.atomic():
                total_sale_val = 0
                for item in cart_items:
                    product = Product.objects.get(id=item['product_id'])
                    qty = int(item['quantity'])
                    
                    if product.quantity < qty:
                        raise ValueError(f"Not enough stock for {product.name}")

                    sale = Sale.objects.create(
                        transaction_id=trans_id,
                        product=product,
                        sold_by=request.user,
                        quantity=qty,
                        discount_percent=discount_percent,
                        payment_method=payment_method,
                        customer=customer_obj,
                        customer_name_text=c_name or "Walk-in",
                        customer_contact=c_contact
                    )
                    total_sale_val += sale.total_amount

                messages.success(request, f"✅ Transaction {trans_id} Complete! Total: ${round(total_sale_val, 2)}")
                return JsonResponse({'success': True})

        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)})
        except Exception as e:
            return JsonResponse({'success': False, 'message': "Server Error: " + str(e)})

    return render(request, 'store/sell.html', {'recent_sales': recent_sales})


# ==========================================
# 4. SALES HISTORY & LEDGER
# ==========================================
@login_required
def sales_history(request):
    # Open Visibility: Everyone starts with all sales
    sales = Sale.objects.all().select_related('product', 'sold_by', 'customer').order_by('-date')

    # Apply Investor Filter
    filter_investor_id = request.GET.get('investor')
    if filter_investor_id and filter_investor_id != 'all':
        sales = sales.filter(product__investor_id=filter_investor_id)

    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    if filter_type == 'today':
        sales = sales.filter(date__date=today)
    elif filter_type == 'week':
        start_date = today - timedelta(days=7)
        sales = sales.filter(date__date__gte=start_date)
    elif filter_type == 'month':
        start_date = today - timedelta(days=30)
        sales = sales.filter(date__date__gte=start_date)
    elif filter_type == 'year':
        start_date = today - timedelta(days=365)
        sales = sales.filter(date__date__gte=start_date)
    
    total_revenue = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_count = sales.count()
    
    # Dropdown List (Owner + Investors)
    all_sellers = User.objects.filter(role__in=['OWNER', 'INVESTOR']).order_by('username')

    return render(request, 'store/sales_history.html', {
        'sales': sales,
        'total_revenue': round(total_revenue, 2),
        'total_count': total_count,
        'filter_type': filter_type,
        'sellers_list': all_sellers, # <--- NEW LIST
        'current_filter': int(filter_investor_id) if filter_investor_id and filter_investor_id != 'all' else 'all',
    })


# ==========================================
# 5. USER PROFILE & CUSTOMERS
# ==========================================
@login_required
def profile(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
        
    return render(request, 'store/profile.html', {'form': form})

@login_required
def customer_list(request):
    sort_by = request.GET.get('sort', 'date') 
    customers = Customer.objects.annotate(
        total_spent=Sum('sales__total_amount'),
        visit_count=Count('sales'),
        last_visit=Max('sales__date')
    )

    if sort_by == 'spent':
        customers = customers.order_by('-total_spent')
    elif sort_by == 'visits':
        customers = customers.order_by('-visit_count')
    else:
        customers = customers.order_by('-last_visit')

    return render(request, 'store/customer_list.html', {
        'customers': customers,
        'current_sort': sort_by
    })

@login_required
def customer_profile(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    history = customer.sales.all().order_by('-date')
    total_spent = history.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    return render(request, 'store/customer_profile.html', {
        'customer': customer,
        'history': history,
        'total_spent': total_spent
    })

@login_required
def pay_investor(request, investor_id):
    if request.user.role != 'OWNER':
        return redirect('dashboard')
    investor = get_object_or_404(User, id=investor_id)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if amount:
            Payout.objects.create(investor=investor, amount=amount)
            messages.success(request, f"Recorded payment of ${amount} to {investor.username}")
            return redirect('dashboard')
    return render(request, 'store/pay_investor.html', {'investor': investor})

@login_required
def export_sales_csv(request):
    # 1. Setup the CSV file
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
    writer = csv.writer(response)
    
    # 2. Write the Header Row
    writer.writerow(['Date', 'Transaction ID', 'Product', 'Sold By', 'Customer', 'Qty', 'Total Amount', 'Payment Method'])

    # 3. Start with all sales
    sales = Sale.objects.all().select_related('product', 'sold_by', 'customer').order_by('-date')

    # --- APPLY FILTERS (Same logic as sales_history) ---
    
    # A. Filter by Investor/Seller
    filter_investor_id = request.GET.get('investor')
    if filter_investor_id and filter_investor_id != 'all':
        sales = sales.filter(product__investor_id=filter_investor_id)

    # B. Filter by Date Range
    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    if filter_type == 'today':
        sales = sales.filter(date__date=today)
    elif filter_type == 'week':
        start_date = today - timedelta(days=7)
        sales = sales.filter(date__date__gte=start_date)
    elif filter_type == 'month':
        start_date = today - timedelta(days=30)
        sales = sales.filter(date__date__gte=start_date)
    elif filter_type == 'year':
        start_date = today - timedelta(days=365)
        sales = sales.filter(date__date__gte=start_date)

    # 4. Write the Data Rows
    for sale in sales:
        # Handle customer name logic safely
        customer_name = sale.customer.name if sale.customer else (sale.customer_name_text or "Walk-in")
        
        writer.writerow([
            sale.date.strftime("%Y-%m-%d %H:%M:%S"),
            sale.transaction_id or "-",
            sale.product.name,
            sale.sold_by.username,
            customer_name,
            sale.quantity,
            sale.total_amount,
            sale.get_payment_method_display(),
        ])

    return response

@login_required
def inventory_list(request):
    # 1. Start with all products
    products = Product.objects.all().select_related('investor').order_by('-created_at')
    
    # 2. Get Parameters
    search_query = request.GET.get('search', '').strip()
    filter_investor = request.GET.get('investor', '')

    # 3. Apply Search (Checks Name OR Product ID)
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | 
            Q(product_id__icontains=search_query)
        )

    # 4. Apply Owner Filter
    if filter_investor and filter_investor != 'all':
        products = products.filter(investor_id=filter_investor)

    # 5. Calculate Total Value of visible inventory (Buying Price * Quantity)
    total_inventory_value = sum(p.buying_price * p.quantity for p in products)
    product_count = products.count()

    # 6. Get Sellers list for the dropdown
    sellers = User.objects.filter(role__in=['OWNER', 'INVESTOR']).order_by('username')

    context = {
        'products': products,
        'sellers': sellers,
        'search_query': search_query,
        'current_filter': int(filter_investor) if filter_investor and filter_investor != 'all' else 'all',
        'total_value': total_inventory_value,
        'product_count': product_count,
        'is_owner': request.user.role == 'OWNER'
    }
    
    return render(request, 'store/inventory_list.html', context)