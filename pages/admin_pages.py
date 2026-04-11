from typing import Any, Dict, List, Optional
from fastapi import Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from backbone.generic.views import GenericTemplateView, GenericFormView
from backbone.core.permissions import IsSuperUser
from backbone.core.repository import BeanieRepository
from backbone import db_store
from schemas.shop import Product, Order
from backbone.common.utils import logger

class AdminProductListView(GenericTemplateView):
    template_name = "pages/admin_products.html"
    page_name = "Products Inventory"
    page_description = "Quick view of all products and stock levels."
    admin_category = "Project Management"
    permission_classes = [IsSuperUser]

    async def get_context_data(self, request: Request, **kwargs) -> Dict[str, Any]:
        products = await Product.find_all().to_list()
        return {"products": products}

class AdminOrderManagementView(GenericFormView):
    template_name = "pages/admin_orders.html"
    page_name = "Manage Orders"
    page_description = "Track orders, update shipping status, and verify payments."
    admin_category = "Project Management"
    permission_classes = [IsSuperUser]

    async def get_context_data(self, request: Request, **kwargs) -> Dict[str, Any]:
        orders = await Order.find_all().sort("-created_at").to_list()
        return {"orders": orders}

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        order_id = form_data.get("order_id")
        action = form_data.get("action")
        
        if not order_id:
            return {"error": "Order ID is missing"}

        order = await Order.get(order_id)
        if not order:
            return {"error": "Order not found"}

        if action == "update_status":
            order.status = form_data.get("status", order.status)
            await order.save()
            return {"success": True, "message_text": f"Order #{order_id} status updated to {order.status}."}
        
        if action == "update_payment":
            order.payment_status = form_data.get("payment_status", order.payment_status)
            await order.save()
            return {"success": True, "message_text": f"Order #{order_id} payment marked as {order.payment_status}."}

        return {"error": "Invalid action"}
