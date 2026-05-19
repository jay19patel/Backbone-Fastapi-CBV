"""
services.order_hooks
~~~~~~~~~~~~~~~~~~~~~

Order lifecycle event handlers.

These hooks are registered on the Order model via Backbone's signal system.
They are imported once in main.py to trigger registration — business logic
lives here, not in the entry point.

Architecture decision:
    Hooks are decoupled from the view layer (api/shop.py) intentionally.
    View hooks handle data integrity (stock, cart, payment).
    These hooks handle customer communication and audit trails.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("soul_craft.order_hooks")


def _order_payload(instance: Any) -> dict:
    """Minimal serialisable summary of an Order for logging."""
    return {
        "id": str(getattr(instance, "id", "") or ""),
        "customer": getattr(instance, "customer_name", None),
        "total": getattr(instance, "total_amount", None),
        "status": getattr(instance, "status", None),
        "items_count": len(getattr(instance, "items", [])),
    }


async def _send_order_confirmation(instance: Any) -> None:
    """Queue order confirmation email with PDF invoice."""
    try:
        from backbone.core.config import BackboneConfig
        from backbone.email_sender import email_sender

        settings = BackboneConfig.get_instance().config
        await instance.fetch_all_links()

        context = {
            "order": instance,
            "site_name": getattr(settings, "SITE_NAME", "Soul Craft Studio"),
            "current_year": datetime.now(UTC).year,
            "site_url": getattr(settings, "SITE_URL", "http://localhost:3000"),
        }

        await email_sender.queue_email(
            to_email=instance.customer_email,
            subject=f"Order Confirmation - {instance.id}",
            template_name="email/order_confirmation.html",
            context=context,
            pdf_attachments=[
                {
                    "template_name": "email/pdf/invoice.html",
                    "context": context,
                    "filename": f"invoice_{instance.id}.pdf",
                    "content_type": "application/pdf",
                }
            ],
        )
    except Exception:
        logger.exception(
            "Failed to send order confirmation email for order %s", getattr(instance, "id", "?")
        )


async def _send_order_status_email(instance: Any) -> None:
    """Queue order status update email when status field changes."""
    try:
        from backbone.core.config import BackboneConfig
        from backbone.email_sender import email_sender

        settings = BackboneConfig.get_instance().config
        await instance.fetch_all_links()

        context = {
            "order": instance,
            "new_status": instance.status,
            "site_name": getattr(settings, "SITE_NAME", "Soul Craft Studio"),
            "current_year": datetime.now(UTC).year,
            "site_url": getattr(settings, "SITE_URL", "http://localhost:3000"),
        }

        await email_sender.queue_email(
            to_email=instance.customer_email,
            subject=f"Order Status Updated: {instance.status.upper()}",
            template_name="email/order_status_update.html",
            context=context,
        )
    except Exception:
        logger.exception(
            "Failed to send order status email for order %s", getattr(instance, "id", "?")
        )


def register_order_hooks() -> None:
    """
    Register all Order signal hooks.

    Call this once at application startup (from main.py).
    Idempotent — safe to call multiple times due to _connect_unique in signals.
    """
    from backbone import log as backbone_log
    from backbone.hooks import on_create, on_delete, on_field_change, on_update
    from ecommerce.schemas.shop import Order

    @on_create(Order)
    async def order_on_create_hook(instance: Any, **kwargs) -> None:
        backbone_log(
            "Order placed: on_create",
            hook="on_create",
            model="Order",
            payload=_order_payload(instance),
        )
        await _send_order_confirmation(instance)

    @on_update(Order)
    async def order_on_update_hook(instance: Any, changed_fields=None, **kwargs) -> None:
        backbone_log(
            "Order updated: on_update",
            hook="on_update",
            model="Order",
            payload=_order_payload(instance),
            changed_fields=list((changed_fields or {}).keys()),
        )

    @on_delete(Order)
    async def order_on_delete_hook(instance: Any, **kwargs) -> None:
        backbone_log(
            "Order deleted: on_delete",
            hook="on_delete",
            model="Order",
            payload=_order_payload(instance),
        )

    @on_field_change(Order, fields=["status"])
    async def order_on_status_change_hook(
        instance: Any,
        changed_fields=None,
        matched_fields=None,
        **kwargs,
    ) -> None:
        backbone_log(
            "Order status changed: on_field_change",
            hook="on_field_change",
            model="Order",
            payload=_order_payload(instance),
            matched_fields=matched_fields or [],
            changed_fields=list((changed_fields or {}).keys()),
        )
        await _send_order_status_email(instance)

    logger.info("Order signal hooks registered.")
