from typing import Any, Dict, List, Optional
from fastapi import Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from backbone.generic.views import GenericTemplateView, GenericFormView
from backbone.core.permissions import IsSuperUser
from backbone.core.repository import BeanieRepository
from backbone import db_store
from schemas.shop import Product, Order
from backbone.common.utils import logger

class StoreTestView(GenericFormView):
    template_name = "pages/store_test.html"
    page_name = "Store Demo Tool"
    page_description = "Test and manage singleton store values."
    admin_category = "Project Tools"
    permission_classes = [IsSuperUser]

    async def get_context_data(self, request: Request, **kwargs) -> Dict[str, Any]:
        all_stores = await db_store.get_all()
        active_key = request.query_params.get("key", "active_store_key")
        return {
            "all_values": all_stores,
            "active_key": active_key,
            "active_value": await db_store.get(active_key),
            "form_values": {"key": active_key, "value": ""}
        }

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        key = form_data.get("key")
        value = form_data.get("value")
        if not key:
            return {"error": "Key is required", "success": False}
        
        await db_store.set(key, value)
        return {
            "success": True,
            "message_text": f"Successfully updated '{key}' in store.",
            "form_values": {"key": key, "value": value}
        }

class ContactFormTestView(GenericFormView):
    template_name = "pages/contact_form.html"
    page_name = "Contact Form Demo"
    page_description = "A playground for testing contact form submissions."
    admin_category = "Project Tools"
    permission_classes = [IsSuperUser]

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # In a real app, you'd save this to a 'Contact' model
        from schemas.content import Contact
        try:
            contact = Contact(**form_data)
            await contact.insert()
            return {"success": True, "message_text": "Contact message recorded successfully!"}
        except Exception as e:
            return {"success": False, "error": f"Failed to save contact: {str(e)}"}

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
