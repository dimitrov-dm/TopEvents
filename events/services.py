from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Order, OrderItem, TicketType


RESERVATION_MINUTES = 15


@transaction.atomic
def create_order(user, ticket_selections):
    if not ticket_selections:
        raise ValidationError("Your order cannot be empty.")

    selections = {}

    for ticket_type_id, quantity in ticket_selections:
        if quantity <= 0:
            raise ValidationError(
                "Ticket quantity must be greater than zero."
            )

        selections[ticket_type_id] = (
            selections.get(ticket_type_id, 0) + quantity
        )

    now = timezone.now()
    expires_at = now + timedelta(minutes=RESERVATION_MINUTES)

    ticket_types = {}

    for ticket_type_id in sorted(selections):
        ticket_type = (
            TicketType.objects
            .select_for_update()
            .get(pk=ticket_type_id)
        )
        ticket_types[ticket_type_id] = ticket_type

    for ticket_type_id, quantity in selections.items():
        ticket_type = ticket_types[ticket_type_id]

        reserved = (
            OrderItem.objects
            .filter(
                ticket_type=ticket_type,
                order__status=Order.Status.PENDING,
                order__expires_at__gt=now,
            )
            .aggregate(total=Sum("quantity"))["total"]
            or 0
        )

        available = (
            ticket_type.quantity
            - ticket_type.quantity_sold
            - reserved
        )

        if quantity > available:
            if available <= 0:
                raise ValidationError(
                    f"No tickets are currently available "
                    f"for {ticket_type.name}."
                )

            raise ValidationError(
                f"Only {available} tickets are currently "
                f"available for {ticket_type.name}."
            )

    order = Order.objects.create(
        user=user,
        customer_name=user.get_full_name() or user.username,
        customer_email=user.email,
        status=Order.Status.PENDING,
        expires_at=expires_at,
    )

    for ticket_type_id, quantity in selections.items():
        ticket_type = ticket_types[ticket_type_id]

        OrderItem.objects.create(
            order=order,
            ticket_type=ticket_type,
            quantity=quantity,
            price_at_purchase=ticket_type.price,
        )

    return order


def can_pay_order(order):
    if order.status != Order.Status.PENDING:
        return False

    if order.expires_at is None:
        return False

    if order.expires_at <= timezone.now():
        return False

    return True


@transaction.atomic
def expire_order(order_id):
    now = timezone.now()

    order = (
        Order.objects
        .select_for_update()
        .get(pk=order_id)
    )

    if order.status != Order.Status.PENDING:
        return False

    if order.expires_at is None or order.expires_at > now:
        return False

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])

    return True


@transaction.atomic
def expire_pending_orders():
    now = timezone.now()

    expired_order_ids = list(
        Order.objects.filter(
            status=Order.Status.PENDING,
            expires_at__lte=now,
        ).values_list("id", flat=True)
    )

    expired_count = 0

    for order_id in expired_order_ids:
        if expire_order(order_id):
            expired_count += 1

    return expired_count


@transaction.atomic
def mark_order_paid(order_id):
    order = (
        Order.objects
        .select_for_update()
        .get(pk=order_id)
    )

    now = timezone.now()

    if order.status != Order.Status.PENDING:
        raise ValidationError(
            "Only pending orders can be marked as paid."
        )

    if order.expires_at is None or order.expires_at <= now:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])

        return False

    items = list(order.items.all().order_by("ticket_type_id"))

    if not items:
        raise ValidationError(
            "An empty order cannot be marked as paid."
        )

    ticket_types = {}

    for item in items:
        ticket_type_id = item.ticket_type_id

        if ticket_type_id not in ticket_types:
            ticket_types[ticket_type_id] = (
                TicketType.objects
                .select_for_update()
                .get(pk=ticket_type_id)
            )

    order_quantities = {}

    for item in items:
        ticket_type_id = item.ticket_type_id
        order_quantities[ticket_type_id] = (
                order_quantities.get(ticket_type_id, 0) + item.quantity
        )

    for ticket_type_id, order_quantity in order_quantities.items():
        ticket_type = ticket_types[ticket_type_id]

        other_reserved = (
                OrderItem.objects.filter(
                    ticket_type_id=ticket_type_id,
                    order__status=Order.Status.PENDING,
                    order__expires_at__gt=now,
                )
                .exclude(order_id=order.pk)
                .aggregate(total=Sum("quantity"))["total"]
                or 0
        )

        committed = (
                ticket_type.quantity_sold
                + order_quantity
                + other_reserved
        )

        if committed > ticket_type.quantity:
            raise ValidationError(
                f"Not enough tickets available for {ticket_type.name}."
            )

    for ticket_type_id, order_quantity in order_quantities.items():
        ticket_type = ticket_types[ticket_type_id]
        ticket_type.quantity_sold += order_quantity
        ticket_type.save(update_fields=["quantity_sold"])

    order.status = Order.Status.PAID
    order.save(update_fields=["status", "updated_at"])

    return True
