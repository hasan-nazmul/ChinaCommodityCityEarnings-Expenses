import json
import uuid
import csv
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, F, Sum, Count, Max
from django.db import transaction
from django.http import JsonResponse, HttpResponse

from .models import *
from .forms import ProductForm
from .analytics import get_predicted_top_product

# ==========================================
# 1. DASHBOARD & ANALYTICS
# ==========================================
@login_required
def dashboard(request):
    user = request.user
    
    # ... [Keep lines 1-60 exactly the same (Filters, Basic Queries, Financials)] ...
    # (Copy from previous file or keep existing until 'owner_net_income' calculation)
    
    # 1. Handle Filters & Base Queries (Standard stuff)
    filter_investor_id = request.GET.get('investor')
    products_query = Product.objects.all()
    sales_query = Sale.objects.all().order_by('-date')
    
    if filter_investor_id and filter_investor_id != 'all':
        products_query = products_query.filter(investor_id=filter_investor_id)
        sales_query = sales_query.filter(product__investor_id=filter_investor_id)

    products = products_query
    sales_history = sales_query[:50]

    # Global Stats
    cash_income = Sale.objects.filter(payment_method='CASH').aggregate(t=Sum('total_amount'))['t'] or 0
    card_income = Sale.objects.filter(payment_method='CARD').aggregate(t=Sum('total_amount'))['t'] or 0
    online_income = Sale.objects.filter(payment_method='ONLINE').aggregate(t=Sum('total_amount'))['t'] or 0

    payment_stats = {
        'cash': round(cash_income, 2),
        'card': round(card_income, 2),
        'online': round(online_income, 2),
        'total': round(cash_income + card_income + online_income, 2)
    }

    # Financials (Owner View)
    investors_only = User.objects.filter(role='INVESTOR')
    financials = []
    for inv in investors_only:
        t_earned = Sale.objects.filter(product__investor=inv).aggregate(total=Sum('investor_profit_amount'))['total'] or 0
        t_paid = inv.payouts.aggregate(total=Sum('amount'))['total'] or 0
        financials.append({
            'investor': inv,
            'earned': round(t_earned, 2),
            'paid': round(t_paid, 2),
            'due': round(t_earned - t_paid, 2)
        })

    all_sellers = User.objects.filter(role__in=['OWNER', 'INVESTOR']).order_by('username')
    owner_net_income = Sale.objects.aggregate(total=Sum('owner_profit_amount'))['total'] or 0

    # --- NEW AI / CHAMPION LOGIC ---
    
    # 1. Calculate GLOBAL Champion (Store-wide best seller)
    global_stat = Sale.objects.values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    global_champion = global_stat['product__name'] if global_stat else "No Sales Yet"

    # 2. Calculate PERSONAL Champion (Logged-in user's best seller)
    my_stat = Sale.objects.filter(product__investor=user).values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    my_champion = my_stat['product__name'] if my_stat else "No Sales Yet"

    # Personal Wallet (Investor)
    my_earned = 0
    my_paid = 0
    my_due = 0
    
    if user.role == 'INVESTOR':
        my_earned = Sale.objects.filter(product__investor=user).aggregate(total=Sum('investor_profit_amount'))['total'] or 0
        my_paid = user.payouts.aggregate(total=Sum('amount'))['total'] or 0
        my_due = my_earned - my_paid
    
    pending_count = 0
    if user.role == 'OWNER':
        pending_count = ProductChangeRequest.objects.filter(status='PENDING').count()

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
        'pending_approvals': pending_count,
        
        # Pass the calculated stats
        'global_champion': global_champion,
        'my_champion': my_champion
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
            
            # CASE 1: OWNER (Direct Save)
            if request.user.role == 'OWNER':
                product = form.save(commit=False)
                product.investor = request.user
                product.owner_split_percent = Decimal(100)
                product.investor_split_percent = Decimal(0)
                product.save()
                messages.success(request, f"Product added directly to inventory.")
            
            # CASE 2: INVESTOR (Create Request)
            else:
                ProductChangeRequest.objects.create(
                    requester=request.user,
                    request_type='NEW',
                    name=form.cleaned_data['name'],
                    quantity=form.cleaned_data['quantity'],
                    buying_price=form.cleaned_data['buying_price'],
                    selling_price=form.cleaned_data['selling_price'],
                    low_stock_threshold=form.cleaned_data['low_stock_threshold']
                )
                messages.info(request, "Request submitted! The Owner must approve this before it appears in the store.")

            return redirect('inventory_list')
    else:
        form = ProductForm()
    return render(request, 'store/add_product.html', {'form': form})

@login_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    # Security: Users can only edit their own stuff
    if request.user.role != 'OWNER' and product.investor != request.user:
        messages.error(request, "Access Denied.")
        return redirect('inventory_list')

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            
            # CASE 1: OWNER (Direct Update)
            if request.user.role == 'OWNER':
                form.save()
                messages.success(request, "Product updated successfully.")
            
            # CASE 2: INVESTOR (Create Request)
            else:
                ProductChangeRequest.objects.create(
                    requester=request.user,
                    request_type='EDIT',
                    target_product=product, # Link to existing item
                    name=form.cleaned_data['name'],
                    quantity=form.cleaned_data['quantity'],
                    buying_price=form.cleaned_data['buying_price'],
                    selling_price=form.cleaned_data['selling_price'],
                    low_stock_threshold=form.cleaned_data['low_stock_threshold']
                )
                messages.info(request, "Changes submitted for approval.")
            
            return redirect('inventory_list')
    else:
        form = ProductForm(instance=product)

    return render(request, 'store/edit_product.html', {'form': form, 'product': product})

@login_required
def inventory_list(request):
    # 1. Base Query: Get all products + Calculate Margin
    products = Product.objects.all().select_related('investor').annotate(
        margin=F('selling_price') - F('buying_price')
    ).order_by('-created_at')
    
    # 2. Get Search & Filter Parameters
    search_query = request.GET.get('search', '').strip()
    filter_investor = request.GET.get('investor', '')

    # 3. Apply Search
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | 
            Q(product_id__icontains=search_query)
        )

    # 4. Apply Owner Filter
    if filter_investor and filter_investor != 'all':
        products = products.filter(investor_id=filter_investor)

    # 5. Calculate Total Inventory Value
    total_inventory_value = sum(p.buying_price * p.quantity for p in products)
    product_count = products.count()

    # 6. Get Sellers list
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

@login_required
def export_inventory_csv(request):
    current_time = timezone.localtime(timezone.now()).strftime("%Y-%m-%d_%H-%M")
    filename = f"inventory_report_{current_time}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    writer.writerow(['Product ID', 'Name', 'Owner', 'Cost Price', 'Selling Price', 'Quantity', 'Stock Status', 'Total Stock Value'])

    products = Product.objects.all().select_related('investor').order_by('-created_at')
    
    search_query = request.GET.get('search', '').strip()
    filter_investor = request.GET.get('investor', '')

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | 
            Q(product_id__icontains=search_query)
        )

    if filter_investor and filter_investor != 'all':
        products = products.filter(investor_id=filter_investor)

    for p in products:
        status = "Low Stock" if p.quantity <= p.low_stock_threshold else "In Stock"
        total_val = p.buying_price * p.quantity

        writer.writerow([
            p.product_id,
            p.name,
            p.investor.username,
            p.buying_price,
            p.selling_price,
            p.quantity,
            status,
            total_val
        ])

    return response

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
    sales = Sale.objects.all().select_related('product', 'sold_by', 'customer').order_by('-date')

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
    all_sellers = User.objects.filter(role__in=['OWNER', 'INVESTOR']).order_by('username')

    return render(request, 'store/sales_history.html', {
        'sales': sales,
        'total_revenue': round(total_revenue, 2),
        'total_count': total_count,
        'filter_type': filter_type,
        'sellers_list': all_sellers,
        'current_filter': int(filter_investor_id) if filter_investor_id and filter_investor_id != 'all' else 'all',
    })

@login_required
def export_sales_csv(request):
    current_time = timezone.localtime(timezone.now()).strftime("%Y-%m-%d_%H-%M")
    filename = f"sales_report_{current_time}.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    
    writer.writerow(['Date', 'Transaction ID', 'Product', 'Sold By', 'Customer', 'Qty', 'Total Amount', 'Payment Method'])

    sales = Sale.objects.all().select_related('product', 'sold_by', 'customer').order_by('-date')
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

    for sale in sales:
        customer_name = sale.customer.name if sale.customer else (sale.customer_name_text or "Walk-in")
        
        # Convert UTC to Local Time before writing
        local_date = timezone.localtime(sale.date)
        formatted_date = local_date.strftime("%Y-%m-%d %I:%M %p")

        writer.writerow([
            formatted_date,
            sale.transaction_id or "-",
            sale.product.name,
            sale.sold_by.username,
            customer_name,
            sale.quantity,
            sale.total_amount,
            sale.get_payment_method_display(),
        ])

    return response

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


# ==========================================
# 6. APPROVAL SYSTEM & REQUESTS
# ==========================================

@login_required
def admin_approval_list(request):
    if request.user.role != 'OWNER':
        return redirect('dashboard')
    
    # Only show PENDING requests in the main list
    pending_requests = ProductChangeRequest.objects.filter(status='PENDING').order_by('-created_at')
    return render(request, 'store/approval_list.html', {'requests': pending_requests})

def process_approval(req):
    """Applies the changes to the live Product table"""
    if req.request_type == 'NEW':
        Product.objects.create(
            investor=req.requester,
            name=req.name,
            quantity=req.quantity,
            buying_price=req.buying_price,
            selling_price=req.selling_price,
            low_stock_threshold=req.low_stock_threshold,
            owner_split_percent=30,
            investor_split_percent=70
        )
    elif req.request_type == 'EDIT' and req.target_product:
        p = req.target_product
        p.name = req.name
        p.quantity = req.quantity
        p.buying_price = req.buying_price
        p.selling_price = req.selling_price
        p.low_stock_threshold = req.low_stock_threshold
        p.save()

@login_required
def approve_request(request, request_id):
    if request.user.role != 'OWNER': return redirect('dashboard')
    
    req = get_object_or_404(ProductChangeRequest, id=request_id)
    if req.status == 'PENDING':
        process_approval(req) # Apply changes
        req.status = 'APPROVED' # Update Status
        req.save()
        messages.success(request, "Request Approved.")
        
    return redirect('admin_approval_list')

@login_required
def reject_request(request, request_id):
    if request.user.role != 'OWNER': return redirect('dashboard')
    
    req = get_object_or_404(ProductChangeRequest, id=request_id)
    if req.status == 'PENDING':
        req.status = 'REJECTED' # Update Status
        req.save()
        messages.warning(request, "Request Rejected.")
        
    return redirect('admin_approval_list')

@login_required
def approve_all_requests(request):
    if request.user.role != 'OWNER': return redirect('dashboard')
    
    pending = ProductChangeRequest.objects.filter(status='PENDING')
    count = pending.count()
    
    if count > 0:
        for req in pending:
            process_approval(req)
            req.status = 'APPROVED'
            req.save()
        messages.success(request, f"✅ Successfully approved all {count} pending requests.")
    else:
        messages.info(request, "No pending requests to approve.")
        
    return redirect('admin_approval_list')

@login_required
def reject_all_requests(request):
    if request.user.role != 'OWNER': return redirect('dashboard')
    
    pending = ProductChangeRequest.objects.filter(status='PENDING')
    count = pending.count()
    
    if count > 0:
        # We use update() for efficiency since we don't need to process logic
        pending.update(status='REJECTED')
        messages.warning(request, f"❌ Rejected all {count} pending requests.")
        
    return redirect('admin_approval_list')

@login_required
def my_requests(request):
    # Show user's history (All statuses)
    my_history = ProductChangeRequest.objects.filter(requester=request.user).order_by('-created_at')
    return render(request, 'store/request_history.html', {'history': my_history})