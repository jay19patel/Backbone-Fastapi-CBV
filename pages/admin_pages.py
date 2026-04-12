from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from backbone.generic.views import GenericTemplateView, GenericFormView
from backbone.core.permissions import IsSuperUser
from backbone.core.repository import BeanieRepository
from backbone import db_store
from schemas.shop import Product, Order, Payment
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
        orders = await Order.find_all().fetch_links().sort("-created_at").to_list()
        # Attach payment info to each order for the template
        for order in orders:
            if order.payment:
                try:
                    payment = await order.payment.fetch() if hasattr(order.payment, "fetch") else order.payment
                    order._payment_doc = payment
                except Exception:
                    order._payment_doc = None
            else:
                order._payment_doc = None
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
            return {"success": True, "message_text": f"Order #{order_id[-8:]} status updated to '{order.status}'."}

        if action == "mark_payment_received":
            # Update Order payment status
            order.payment_status = "received"
            await order.save()
            # Update linked Payment document
            if order.payment:
                from beanie import Link
                payment = await order.payment.fetch() if isinstance(order.payment, Link) else order.payment
                if payment:
                    payment.status = "received"
                    payment.received_at = datetime.now(timezone.utc)
                    await payment.save()
            return {"success": True, "message_text": f"Payment for Order #{order_id[-8:]} marked as RECEIVED."}

        if action == "confirm_payment":
            # Update Order payment status
            order.payment_status = "verified"
            await order.save()
            # Update linked Payment document
            if order.payment:
                from beanie import Link
                payment = await order.payment.fetch() if isinstance(order.payment, Link) else order.payment
                if payment:
                    payment.status = "verified"
                    payment.confirmed_at = datetime.now(timezone.utc)
                    await payment.save()
            return {"success": True, "message_text": f"Payment for Order #{order_id[-8:]} VERIFIED & CONFIRMED."}

        if action == "reject_payment":
            order.payment_status = "failed"
            await order.save()
            if order.payment:
                from beanie import Link
                payment = await order.payment.fetch() if isinstance(order.payment, Link) else order.payment
                if payment:
                    payment.status = "failed"
                    await payment.save()
            return {"success": True, "message_text": f"Payment for Order #{order_id[-8:]} rejected."}

        return {"error": "Invalid action"}
