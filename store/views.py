from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Product, Sale
from .forms import ProductForm, SaleForm
from django.db.models import Sum, F
from .analytics import get_predicted_top_product
from .models import *

@login_required
def dashboard(request):
    user = request.user
    
    if user.role == 'OWNER':
        products = Product.objects.all()
        sales_history = Sale.objects.all().order_by('-date')[:20]
        
        investors = User.objects.filter(role='INVESTOR')
        financials = []
        
        for inv in investors:
            total_earned = Sale.objects.filter(product__investor=inv).aggregate(
                total=Sum('investor_profit_amount')
            )['total'] or 0
            
            total_paid = inv.payouts.aggregate(total=Sum('amount'))['total'] or 0
            
            due = total_earned - total_paid
            
            financials.append({
                'investor': inv,
                # ROUND NUMBERS HERE IN PYTHON
                'earned': round(total_earned, 2),
                'paid': round(total_paid, 2),
                'due': round(due, 2)
            })
            
        context = {
            'products': products,
            'recent_sales': sales_history,
            'financials': financials,
            'is_owner': True
        }

    else:
        products = Product.objects.filter(investor=user)
        sales_history = Sale.objects.filter(product__investor=user).order_by('-date')[:20]
        
        predicted_product = get_predicted_top_product(user)
        
        total_earned = Sale.objects.filter(product__investor=user).aggregate(
            total=Sum('investor_profit_amount')
        )['total'] or 0
        
        total_paid = user.payouts.aggregate(total=Sum('amount'))['total'] or 0
        due = total_earned - total_paid

        context = {
            'products': products,
            'recent_sales': sales_history,
            'predicted_product': predicted_product,
            # ROUND NUMBERS HERE IN PYTHON
            'total_earned': round(total_earned, 2),
            'total_paid': round(total_paid, 2),
            'due': round(due, 2),
            'is_owner': False
        }

    return render(request, 'store/dashboard.html', context)

@login_required
def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.investor = request.user  # Assign current user as owner
            product.save()
            messages.success(request, f"Product {product.product_id} added successfully!")
            return redirect('dashboard')
    else:
        form = ProductForm()
    return render(request, 'store/add_product.html', {'form': form})

@login_required
def sell_product(request):
    if request.method == 'POST':
        form = SaleForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['product_id_search']
            qty = form.cleaned_data['quantity']
            method = form.cleaned_data['payment_method']
            
            # Find product by Custom ID OR Name
            product = Product.objects.filter(
                Q(product_id__iexact=query) | Q(name__icontains=query)
            ).first()

            if product:
                if product.quantity >= qty:
                    # Create Sale
                    Sale.objects.create(
                        product=product,
                        sold_by=request.user,
                        quantity=qty,
                        payment_method=method
                    )
                    messages.success(request, f"Sold {qty} x {product.name}!")
                    return redirect('sell_product') # Refresh page for next sale
                else:
                    messages.error(request, f"Not enough stock! Only {product.quantity} left.")
            else:
                messages.error(request, "Product not found.")
    else:
        form = SaleForm()
        
    return render(request, 'store/sell.html', {'form': form})

@login_required
def dashboard(request):
    user = request.user
    
    # --- 1. DATA FOR OWNER ---
    if user.role == 'OWNER':
        products = Product.objects.all()
        sales_history = Sale.objects.all().order_by('-date')[:20]
        
        # Calculate Payables (How much Owner owes Investors)
        # We get all investors
        investors = User.objects.filter(role='INVESTOR')
        financials = []
        
        for inv in investors:
            # Total money this investor *should* have received from sales
            total_earned = Sale.objects.filter(product__investor=inv).aggregate(
                total=Sum('investor_profit_amount')
            )['total'] or 0
            
            # Total money owner has *actually* paid them
            total_paid = inv.payouts.aggregate(total=Sum('amount'))['total'] or 0
            
            due = total_earned - total_paid
            
            financials.append({
                'investor': inv,
                'earned': total_earned,
                'paid': total_paid,
                'due': due
            })
            
        context = {
            'products': products,
            'recent_sales': sales_history,
            'financials': financials, # Pass financial data to template
            'is_owner': True
        }

    # --- 2. DATA FOR INVESTOR ---
    else:
        products = Product.objects.filter(investor=user)
        sales_history = Sale.objects.filter(product__investor=user).order_by('-date')[:20]
        
        # Get ML Prediction
        predicted_product = get_predicted_top_product(user)
        
        # Get Financials for this specific user
        total_earned = Sale.objects.filter(product__investor=user).aggregate(
            total=Sum('investor_profit_amount')
        )['total'] or 0
        
        total_paid = user.payouts.aggregate(total=Sum('amount'))['total'] or 0
        due = total_earned - total_paid

        context = {
            'products': products,
            'recent_sales': sales_history,
            'predicted_product': predicted_product, # Pass ML result
            'total_earned': total_earned,
            'total_paid': total_paid,
            'due': due,
            'is_owner': False
        }

    return render(request, 'store/dashboard.html', context)

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