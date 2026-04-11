from typing import Any, Dict, List
from fastapi import Request
from backbone.generic.views import GenericTemplateView
from backbone.core.permissions import AllowAny

class UserGuideView(GenericTemplateView):
    template_name = "pages/user_guide.html"
    page_name = "Backbone User Guide"
    page_description = "A comprehensive guide for developers using the Backbone library."
    permission_classes = [AllowAny]
    admin_category = "Documentation"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        return {
            "backbone_features": [
                {
                    "name": "🚀 Generic CRUD Views",
                    "description": "Standardize your APIs. Inherit from GenericCrudView to get List, Retrieve, Create, Update, and Delete endpoints out of the box with built-in permission handling and automated Link population.",
                    "usage": "class ProductView(GenericCrudView):\n    schema = Product\n    search_fields = ['name']\n    fetch_links = True"
                },
                {
                    "name": "📧 Advanced Emailing & PDFs",
                    "description": "Powerful email engine that handles HTML rendering, file attachments, and dynamic PDF generation using Jinja2 templates. Perfect for invoices and receipts.",
                    "usage": "await email_sender.queue_email(\n    to_email=order.customer_email,\n    subject='Invoiced',\n    pdf_attachments=[{\n        'template_name': 'email/pdf/invoice.html',\n        'filename': 'invoice.pdf'\n    }]\n)"
                },
                {
                    "name": "💾 Smart Snapshots & Relations",
                    "description": "For E-commerce, we store relational CartItems and OrderItems. OrderItems include automatic snapshots of price and name at the time of order, ensuring historical data integrity.",
                    "usage": "# In schemas/shop.py\nitems: List[Link[OrderItem]]\n\n# In api/shop.py\norder_item = OrderItem(..., price=product.price_value)"
                },
                {
                    "name": "📝 Database-Backed Logging",
                    "description": "Never miss a production error. Use the DatabaseLoggingHandler or @log_exceptions decorator to stream all application logs directly into the MongoDB 'logs' collection.",
                    "usage": "@log_exceptions\nasync def process_payment(data):\n    # Any error inside here will be logged to DB\n    ..."
                }
            ]
        }

router = UserGuideView.as_router("/user-guide", tags=["Pages — Guide"])
