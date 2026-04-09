from fastapi import APIRouter
from backbone.generic.views import GenericCrudView
from backbone.core.permissions import AllowAny
from schemas.shop import Category, Product, Order

class CategoryView(GenericCrudView):
    schema = Category
    search_fields = ["name"]
    list_fields = ["id", "name", "img", "color", "created_at"]
    permission_classes = [AllowAny]

class ProductView(GenericCrudView):
    schema = Product
    search_fields = ["name", "tag"]
    list_fields = ["id", "name", "price", "tag", "stock", "category_id", "created_at"]
    permission_classes = [AllowAny]

class OrderView(GenericCrudView):
    schema = Order
    search_fields = ["customer_name", "customer_email", "status"]
    list_fields = ["id", "customer_name", "customer_email", "total_amount", "status", "created_at"]
    permission_classes = [AllowAny]

router = APIRouter()
router.include_router(CategoryView.as_router("/categories", tags=["Shop Categories"]))
router.include_router(ProductView.as_router("/products", tags=["Shop Products"]))
router.include_router(OrderView.as_router("/orders", tags=["Shop Orders"]))
