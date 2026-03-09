"""
Stripe Invoicing Module for Scope Tracker Change Orders

Handles invoice creation, payment link generation, and payment status tracking
for approved change orders.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

import stripe
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")


@dataclass
class InvoiceLineItem:
    """Represents a single line item on an invoice."""
    description: str
    quantity: Decimal
    unit_amount: int  # Amount in cents
    amount: int  # Total in cents


@dataclass
class InvoiceMetadata:
    """Metadata to attach to Stripe invoice."""
    engagement_id: str
    change_order_id: str
    client_id: str
    firm_id: str


class StripeInvoicingService:
    """Service for managing invoices and payments via Stripe."""

    def __init__(self, database_url: Optional[str] = None):
        self.stripe_client = stripe
        self.database_url = database_url or DATABASE_URL

    def create_invoice_from_change_order(
        self,
        change_order_id: str,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Stripe invoice from an approved change order.

        Args:
            change_order_id: UUID of the change order in Supabase
            customer_id: Optional existing Stripe customer ID (will create if not provided)

        Returns:
            Dictionary with invoice details and payment link
        """
        try:
            # Fetch change order from database
            change_order = self._fetch_change_order(change_order_id)
            if not change_order:
                raise ValueError(f"Change order {change_order_id} not found")

            # Fetch engagement and client
            engagement = self._fetch_engagement(change_order["engagement_id"])
            client = self._fetch_client(engagement["client_id"])

            # Get or create Stripe customer
            if not customer_id:
                customer_id = self._get_or_create_customer(client, engagement)

            # Prepare line items
            line_items = self._prepare_line_items(change_order)

            # Create Stripe invoice
            invoice_params = {
                "customer": customer_id,
                "description": f"Change Order for {engagement['matter_name']}",
                "auto_advance": False,  # Don't auto-finalize, allow review first
                "metadata": {
                    "change_order_id": change_order_id,
                    "engagement_id": change_order["engagement_id"],
                    "client_id": client["id"],
                },
            }

            invoice = self.stripe_client.Invoice.create(**invoice_params)

            # Add line items
            for item in line_items:
                self.stripe_client.InvoiceItem.create(
                    invoice=invoice.id,
                    description=item.description,
                    quantity=int(item.quantity),
                    unit_amount=item.unit_amount,
                    metadata={
                        "change_order_id": change_order_id,
                    },
                )

            # Finalize the invoice
            invoice = self.stripe_client.Invoice.finalize_invoice(invoice.id)

            logger.info(
                f"Invoice {invoice.id} created for change order {change_order_id}"
            )

            # Update change order with Stripe invoice ID
            self._update_change_order_invoice(change_order_id, invoice.id)

            return {
                "success": True,
                "stripe_invoice_id": invoice.id,
                "invoice_number": invoice.number,
                "invoice_pdf": invoice.invoice_pdf,
                "status": invoice.status,
                "amount_due": invoice.amount_due,
                "payment_link": self._create_payment_link(invoice, customer_id),
            }

        except Exception as e:
            logger.error(f"Failed to create invoice: {str(e)}")
            raise

    def create_payment_link(
        self,
        change_order_id: str,
        expiration_hours: int = 30,
    ) -> str:
        """
        Generate a payment link for a change order invoice.

        Args:
            change_order_id: UUID of the change order
            expiration_hours: How long the link remains valid

        Returns:
            Payment link URL
        """
        try:
            change_order = self._fetch_change_order(change_order_id)
            if not change_order or not change_order.get("stripe_invoice_id"):
                raise ValueError(
                    f"Change order {change_order_id} has no associated Stripe invoice"
                )

            invoice = self.stripe_client.Invoice.retrieve(
                change_order["stripe_invoice_id"]
            )

            # Create payment link (in Stripe, this is done via PaymentLink)
            payment_link = self.stripe_client.PaymentLink.create(
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": f"Change Order Invoice #{invoice.number}",
                            },
                            "unit_amount": invoice.amount_due,
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "change_order_id": change_order_id,
                    "invoice_id": invoice.id,
                },
                expires_at=int(
                    (datetime.utcnow() + timedelta(hours=expiration_hours)).timestamp()
                ),
            )

            logger.info(f"Payment link created: {payment_link.url}")

            return payment_link.url

        except Exception as e:
            logger.error(f"Failed to create payment link: {str(e)}")
            raise

    def handle_payment_webhook(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Stripe webhook events for payment status updates.

        Args:
            event: Stripe webhook event payload

        Returns:
            Webhook handling result
        """
        event_type = event.get("type")

        logger.info(f"Processing Stripe webhook: {event_type}")

        try:
            if event_type == "invoice.paid":
                return self._handle_invoice_paid(event["data"]["object"])
            elif event_type == "invoice.payment_failed":
                return self._handle_invoice_payment_failed(event["data"]["object"])
            elif event_type == "invoice.payment_action_required":
                return self._handle_payment_action_required(event["data"]["object"])
            elif event_type == "charge.refunded":
                return self._handle_charge_refunded(event["data"]["object"])
            else:
                logger.info(f"Ignoring event type: {event_type}")
                return {"status": "ignored", "event_type": event_type}

        except Exception as e:
            logger.error(f"Webhook handling failed: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _handle_invoice_paid(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Handle invoice.paid event."""
        change_order_id = invoice.get("metadata", {}).get("change_order_id")

        if not change_order_id:
            logger.warning(f"No change_order_id in invoice metadata: {invoice['id']}")
            return {"status": "no_change_order"}

        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor()

            # Update change order status
            cur.execute(
                """
                UPDATE change_orders
                SET payment_status = %s, updated_at = %s
                WHERE id = %s
                """,
                ("paid", datetime.utcnow().isoformat(), change_order_id),
            )

            logger.info(f"Updated change order {change_order_id} status to paid")

            # Log payment in email_logs for audit trail
            cur.execute(
                """
                INSERT INTO email_logs (change_order_id, email_type, subject, status, sent_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    change_order_id,
                    "payment_confirmation",
                    f"Payment Received - Change Order {change_order_id}",
                    "sent",
                    datetime.utcnow().isoformat(),
                ),
            )

            conn.commit()
            cur.close()
            conn.close()

            return {
                "status": "success",
                "change_order_id": change_order_id,
                "payment_status": "paid",
            }

        except Exception as e:
            logger.error(f"Failed to handle payment: {str(e)}")
            raise

    def _handle_invoice_payment_failed(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Handle invoice.payment_failed event."""
        change_order_id = invoice.get("metadata", {}).get("change_order_id")

        if not change_order_id:
            logger.warning(
                f"No change_order_id in invoice metadata: {invoice['id']}"
            )
            return {"status": "no_change_order"}

        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor()

            # Update change order status
            cur.execute(
                """
                UPDATE change_orders
                SET payment_status = %s, updated_at = %s
                WHERE id = %s
                """,
                ("failed", datetime.utcnow().isoformat(), change_order_id),
            )

            conn.commit()
            cur.close()
            conn.close()

            logger.warning(f"Payment failed for change order {change_order_id}")

            return {
                "status": "payment_failed",
                "change_order_id": change_order_id,
                "invoice_id": invoice["id"],
            }

        except Exception as e:
            logger.error(f"Failed to handle payment failure: {str(e)}")
            raise

    def _handle_payment_action_required(
        self, invoice: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle invoice.payment_action_required event (e.g., 3D Secure)."""
        change_order_id = invoice.get("metadata", {}).get("change_order_id")

        if not change_order_id:
            return {"status": "no_change_order"}

        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor()

            # Update status to indicate action needed
            cur.execute(
                """
                UPDATE change_orders
                SET payment_status = %s, updated_at = %s
                WHERE id = %s
                """,
                ("action_required", datetime.utcnow().isoformat(), change_order_id),
            )

            conn.commit()
            cur.close()
            conn.close()

            logger.info(f"Payment action required for change order {change_order_id}")

            return {
                "status": "action_required",
                "change_order_id": change_order_id,
                "hosting_invoice_id": invoice["hosted_invoice_url"],
            }

        except Exception as e:
            logger.error(f"Failed to handle payment action required: {str(e)}")
            raise

    def _handle_charge_refunded(self, charge: Dict[str, Any]) -> Dict[str, Any]:
        """Handle charge.refunded event."""
        invoice_id = charge.get("invoice")

        if not invoice_id:
            logger.warning("Refund with no associated invoice")
            return {"status": "no_invoice"}

        try:
            # Fetch invoice to get change order ID
            invoice = self.stripe_client.Invoice.retrieve(invoice_id)
            change_order_id = invoice.get("metadata", {}).get("change_order_id")

            if change_order_id:
                # Update change order
                conn = psycopg2.connect(self.database_url)
                cur = conn.cursor()

                cur.execute(
                    """
                    UPDATE change_orders
                    SET payment_status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    ("refunded", datetime.utcnow().isoformat(), change_order_id),
                )

                conn.commit()
                cur.close()
                conn.close()

                logger.info(f"Refund processed for change order {change_order_id}")

            return {
                "status": "refunded",
                "change_order_id": change_order_id,
                "amount": charge["amount_refunded"],
            }

        except Exception as e:
            logger.error(f"Failed to handle refund: {str(e)}")
            raise

    def get_invoice_status(self, change_order_id: str) -> Dict[str, Any]:
        """
        Get current payment status for a change order.

        Args:
            change_order_id: UUID of the change order

        Returns:
            Invoice and payment status information
        """
        try:
            change_order = self._fetch_change_order(change_order_id)

            if not change_order.get("stripe_invoice_id"):
                return {
                    "status": "no_invoice",
                    "payment_status": change_order.get("payment_status"),
                }

            invoice = self.stripe_client.Invoice.retrieve(
                change_order["stripe_invoice_id"]
            )

            return {
                "status": "found",
                "stripe_invoice_id": invoice.id,
                "invoice_number": invoice.number,
                "payment_status": invoice.status,
                "amount_due": invoice.amount_due,
                "paid_at": invoice.paid_at,
                "invoice_pdf": invoice.invoice_pdf,
                "hosted_invoice_url": invoice.hosted_invoice_url,
            }

        except Exception as e:
            logger.error(f"Failed to get invoice status: {str(e)}")
            return {"status": "error", "message": str(e)}

    # Private helper methods

    def _fetch_change_order(self, change_order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch change order from PostgreSQL."""
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM change_orders WHERE id = %s",
                (change_order_id,),
            )
            result = cur.fetchone()
            cur.close()
            conn.close()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to fetch change order: {str(e)}")
            return None

    def _fetch_engagement(self, engagement_id: str) -> Dict[str, Any]:
        """Fetch engagement from PostgreSQL."""
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM engagements WHERE id = %s",
                (engagement_id,),
            )
            result = cur.fetchone()
            cur.close()
            conn.close()
            return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Failed to fetch engagement: {str(e)}")
            return {}

    def _fetch_client(self, client_id: str) -> Dict[str, Any]:
        """Fetch client from PostgreSQL."""
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM clients WHERE id = %s",
                (client_id,),
            )
            result = cur.fetchone()
            cur.close()
            conn.close()
            return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Failed to fetch client: {str(e)}")
            return {}

    def _get_or_create_customer(
        self,
        client: Dict[str, Any],
        engagement: Dict[str, Any],
    ) -> str:
        """Get existing Stripe customer or create new one."""
        # Try to find existing customer by email
        customers = self.stripe_client.Customer.list(
            email=client.get("contact_email"),
            limit=1,
        )

        if customers.data:
            logger.info(f"Using existing customer: {customers.data[0].id}")
            return customers.data[0].id

        # Create new customer
        customer = self.stripe_client.Customer.create(
            name=client.get("name", ""),
            email=client.get("contact_email", ""),
            phone=client.get("contact_phone", ""),
            metadata={
                "client_id": client.get("id", ""),
                "engagement_id": engagement.get("id", ""),
            },
        )

        logger.info(f"Created new customer: {customer.id}")
        return customer.id

    def _prepare_line_items(
        self,
        change_order: Dict[str, Any],
    ) -> List[InvoiceLineItem]:
        """Prepare line items for invoice from change order."""
        items = []

        # Add main change order item
        amount_cents = int(
            Decimal(str(change_order["estimated_additional_cost"])) * 100
        )
        items.append(
            InvoiceLineItem(
                description=f"Change Order: {change_order['title']}",
                quantity=Decimal("1"),
                unit_amount=amount_cents,
                amount=amount_cents,
            )
        )

        # Fetch detailed line items from change_order_items table
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM change_order_items WHERE change_order_id = %s",
                (change_order["id"],),
            )
            line_items = cur.fetchall()
            cur.close()
            conn.close()

            if line_items:
                items = []  # Replace with detailed items
                for item in line_items:
                    unit_amount = int(Decimal(str(item["unit_cost"])) * 100)
                    items.append(
                        InvoiceLineItem(
                            description=item["description"],
                            quantity=Decimal(str(item["quantity"])),
                            unit_amount=unit_amount,
                            amount=int(Decimal(str(item["amount"])) * 100),
                        )
                    )

        except Exception as e:
            logger.error(f"Failed to fetch line items: {str(e)}")

        return items

    def _update_change_order_invoice(
        self,
        change_order_id: str,
        stripe_invoice_id: str,
    ) -> None:
        """Update change order with Stripe invoice ID."""
        try:
            conn = psycopg2.connect(self.database_url)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE change_orders
                SET stripe_invoice_id = %s, payment_status = %s, updated_at = %s
                WHERE id = %s
                """,
                (stripe_invoice_id, "draft", datetime.utcnow().isoformat(), change_order_id),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update change order invoice: {str(e)}")
            raise

    def _create_payment_link(
        self,
        invoice: Any,
        customer_id: str,
    ) -> str:
        """Create a payment link for the invoice."""
        # In production, use PaymentLink API or return hosted_invoice_url
        return invoice.hosted_invoice_url or f"https://pay.stripe.com/invoice/{invoice.id}"


# Standalone helper functions for API endpoints

def verify_stripe_webhook(request_body: str, signature: str) -> bool:
    """
    Verify Stripe webhook signature.

    Args:
        request_body: Raw request body
        signature: Stripe signature from header

    Returns:
        True if signature is valid
    """
    try:
        stripe.Webhook.construct_event(
            request_body,
            signature,
            STRIPE_WEBHOOK_SECRET,
        )
        return True
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        return False


def create_invoice_endpoint(change_order_id: str) -> Dict[str, Any]:
    """
    API endpoint handler for creating an invoice.

    Args:
        change_order_id: UUID of the change order

    Returns:
        Endpoint response
    """
    service = StripeInvoicingService()
    return service.create_invoice_from_change_order(change_order_id)


def payment_link_endpoint(change_order_id: str) -> str:
    """
    API endpoint handler for generating payment link.

    Args:
        change_order_id: UUID of the change order

    Returns:
        Payment link URL
    """
    service = StripeInvoicingService()
    return service.create_payment_link(change_order_id)


def webhook_endpoint(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    API endpoint handler for Stripe webhooks.

    Args:
        event: Stripe webhook event

    Returns:
        Webhook handling result
    """
    service = StripeInvoicingService()
    return service.handle_payment_webhook(event)


if __name__ == "__main__":
    # Example usage
    service = StripeInvoicingService()

    # This would be called when a change order is approved
    # result = service.create_invoice_from_change_order("change-order-uuid")
    # print(json.dumps(result, indent=2, default=str))
