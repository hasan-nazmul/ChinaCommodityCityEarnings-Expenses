from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('add/', views.add_product, name='add_product'),
    path('sell/', views.sell_product, name='sell_product'),
    path('login/', auth_views.LoginView.as_view(template_name='store/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('pay/<int:investor_id>/', views.pay_investor, name='pay_investor'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:customer_id>/', views.customer_profile, name='customer_profile'),
    path('sales-history/', views.sales_history, name='sales_history'),
    path('api/product-lookup/', views.api_get_product, name='api_product_lookup'),
    path('profile/', views.profile, name='profile'),
    path('sales-history/export/', views.export_sales_csv, name='export_sales_csv'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/export/', views.export_inventory_csv, name='export_inventory_csv'), 
    path('inventory/edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('approvals/', views.admin_approval_list, name='admin_approval_list'),
    path('approvals/approve/<int:request_id>/', views.approve_request, name='approve_request'),
    path('approvals/reject/<int:request_id>/', views.reject_request, name='reject_request'),
    path('approvals/approve-all/', views.approve_all_requests, name='approve_all_requests'),
    path('approvals/reject-all/', views.reject_all_requests, name='reject_all_requests'),

    # NEW INVESTOR PATH
    path('my-requests/', views.my_requests, name='my_requests'),
]