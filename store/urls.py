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
]