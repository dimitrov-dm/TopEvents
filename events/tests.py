from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Event, Order, OrderItem, TicketType
from .services import (
    can_pay_order,
    create_order,
    expire_order,
    expire_pending_orders,
    mark_order_paid,
)


User = get_user_model()


class OrderServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testcustomer",
            email="customer@example.com",
            password="test-password-123",
        )

        self.event = Event.objects.create(
            title="Test Concert",
            description="A concert used for testing.",
            location="Sofia",
            start_datetime=timezone.now() + timedelta(days=30),
            end_datetime=timezone.now() + timedelta(days=30, hours=3),
            organizer=self.user,
            approval_status=Event.ApprovalStatus.APPROVED,
        )

        self.ticket_type = TicketType.objects.create(
            event=self.event,
            name="General Admission",
            description="Standard entry.",
            price=Decimal("25.00"),
            quantity=100,
        )

    def create_pending_order(self, quantity=2, minutes_remaining=10):
        order = Order.objects.create(
            user=self.user,
            customer_name=self.user.username,
            customer_email=self.user.email,
            status=Order.Status.PENDING,
            expires_at=timezone.now() + timedelta(
                minutes=minutes_remaining
            ),
        )

        OrderItem.objects.create(
            order=order,
            ticket_type=self.ticket_type,
            quantity=quantity,
            price_at_purchase=self.ticket_type.price,
        )

        return order


    def test_create_order_success(self):
        order = create_order(
            self.user,
            [(self.ticket_type.pk, 2)],
        )

        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertIsNotNone(order.expires_at)

        time_remaining = order.expires_at - timezone.now()
        self.assertGreater(time_remaining.total_seconds(), 0)
        self.assertLessEqual(
            time_remaining.total_seconds(),
            15 * 60,
        )

        item = order.items.get()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(
            item.price_at_purchase,
            Decimal("25.00"),
        )

        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 0)

    def test_create_order_with_multiple_ticket_selections(self):
        order = create_order(
            self.user,
            [
                (self.ticket_type.pk, 2),
                (self.ticket_type.pk, 3),
            ],
        )

        item = order.items.get()

        self.assertEqual(item.quantity, 5)
        self.assertEqual(order.items.count(), 1)

    def test_create_order_rejects_empty_selections(self):
        with self.assertRaises(ValidationError):
            create_order(self.user, [])

        self.assertEqual(Order.objects.count(), 0)

    def test_create_order_rejects_zero_or_negative_quantity(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    create_order(
                        self.user,
                        [(self.ticket_type.pk, quantity)],
                    )

        self.assertEqual(Order.objects.count(), 0)

    def test_create_order_rejects_insufficient_inventory(self):
        with self.assertRaises(ValidationError):
            create_order(
                self.user,
                [(self.ticket_type.pk, 101)],
            )

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 0)


    def test_expire_order_cancels_expired_pending_order(self):
        order = self.create_pending_order(minutes_remaining=-1)

        result = expire_order(order.pk)

        self.assertTrue(result)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_expire_order_does_not_cancel_active_reservation(self):
        order = self.create_pending_order(minutes_remaining=10)

        result = expire_order(order.pk)

        self.assertFalse(result)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_expire_pending_orders_cancels_only_expired_orders(self):
        expired_order = self.create_pending_order(
            minutes_remaining=-5
        )
        active_order = self.create_pending_order(
            minutes_remaining=10
        )

        expired_count = expire_pending_orders()

        self.assertEqual(expired_count, 1)

        expired_order.refresh_from_db()
        active_order.refresh_from_db()

        self.assertEqual(
            expired_order.status,
            Order.Status.CANCELLED,
        )
        self.assertEqual(
            active_order.status,
            Order.Status.PENDING,
        )

    def test_can_pay_order_checks_status_and_expiration(self):
        active_order = self.create_pending_order(minutes_remaining=10)

        self.assertTrue(can_pay_order(active_order))

        active_order.expires_at = timezone.now() - timedelta(seconds=1)
        active_order.save(update_fields=["expires_at"])

        self.assertFalse(can_pay_order(active_order))

        active_order.status = Order.Status.PAID
        active_order.save(update_fields=["status"])

        self.assertFalse(can_pay_order(active_order))


    def test_mark_order_paid_increments_quantity_sold(self):
        order = self.create_pending_order(quantity=3)

        result = mark_order_paid(order.pk)

        self.assertTrue(result)

        order.refresh_from_db()
        self.ticket_type.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(self.ticket_type.quantity_sold, 3)

    def test_mark_order_paid_cancels_expired_order(self):
        order = self.create_pending_order(
            quantity=2,
            minutes_remaining=-1,
        )

        result = mark_order_paid(order.pk)

        self.assertFalse(result)

        order.refresh_from_db()
        self.ticket_type.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.ticket_type.quantity_sold, 0)

    def test_mark_order_paid_rejects_already_paid_order(self):
        order = self.create_pending_order(quantity=2)
        order.status = Order.Status.PAID
        order.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            mark_order_paid(order.pk)

        self.ticket_type.refresh_from_db()
        self.assertEqual(self.ticket_type.quantity_sold, 0)

    def test_mark_order_paid_rejects_empty_order(self):
        order = Order.objects.create(
            user=self.user,
            customer_name=self.user.username,
            customer_email=self.user.email,
            status=Order.Status.PENDING,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(ValidationError):
            mark_order_paid(order.pk)

        order.refresh_from_db()
        self.ticket_type.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.ticket_type.quantity_sold, 0)

    def test_mark_order_paid_does_not_oversell_tickets(self):
        self.ticket_type.quantity_sold = 99
        self.ticket_type.save(update_fields=["quantity_sold"])

        order = self.create_pending_order(
            quantity=2,
            minutes_remaining=10,
        )

        with self.assertRaises(ValidationError):
            mark_order_paid(order.pk)

        self.ticket_type.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.ticket_type.quantity_sold, 99)
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_mark_order_paid_rolls_back_if_one_ticket_type_oversells(self):
        vip_ticket = TicketType.objects.create(
            event=self.event,
            name="VIP",
            description="VIP access.",
            price=Decimal("50.00"),
            quantity=20,
        )

        order = create_order(
            self.user,
            [
                (self.ticket_type.pk, 3),
                (vip_ticket.pk, 2),
            ],
        )

        vip_ticket.quantity_sold = 19
        vip_ticket.save(update_fields=["quantity_sold"])

        with self.assertRaises(ValidationError):
            mark_order_paid(order.pk)

        self.ticket_type.refresh_from_db()
        vip_ticket.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.ticket_type.quantity_sold, 0)
        self.assertEqual(vip_ticket.quantity_sold, 19)
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_mark_order_paid_updates_multiple_ticket_types(self):
        vip_ticket = TicketType.objects.create(
            event=self.event,
            name="VIP",
            description="VIP access.",
            price=Decimal("50.00"),
            quantity=20,
        )

        order = create_order(
            self.user,
            [
                (self.ticket_type.pk, 3),
                (vip_ticket.pk, 2),
            ],
        )

        result = mark_order_paid(order.pk)

        self.assertTrue(result)

        self.ticket_type.refresh_from_db()
        vip_ticket.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.ticket_type.quantity_sold, 3)
        self.assertEqual(vip_ticket.quantity_sold, 2)
        self.assertEqual(order.status, Order.Status.PAID)

    def test_mark_order_paid_preserves_other_active_reservations(self):
        vip_ticket = TicketType.objects.create(
            event=self.event,
            name="VIP",
            description="VIP access.",
            price=Decimal("50.00"),
            quantity=20,
        )

        order_a = create_order(
            self.user,
            [(vip_ticket.pk, 2)],
        )

        order_b = create_order(
            self.user,
            [(vip_ticket.pk, 3)],
        )

        vip_ticket.quantity_sold = 16
        vip_ticket.save(update_fields=["quantity_sold"])

        with self.assertRaises(ValidationError):
            mark_order_paid(order_a.pk)

        vip_ticket.refresh_from_db()
        order_a.refresh_from_db()
        order_b.refresh_from_db()

        self.assertEqual(vip_ticket.quantity_sold, 16)
        self.assertEqual(order_a.status, Order.Status.PENDING)
        self.assertEqual(order_b.status, Order.Status.PENDING)

    def test_active_reservation_reduces_available_inventory(self):
        self.create_pending_order(quantity=90)

        with self.assertRaises(ValidationError):
            create_order(
                self.user,
                [(self.ticket_type.pk, 11)],
            )

        self.assertEqual(Order.objects.count(), 1)

    def test_cancelling_reservation_releases_inventory(self):
        order = self.create_pending_order(
            quantity=90,
            minutes_remaining=-1,
        )

        expire_order(order.pk)

        new_order = create_order(
            self.user,
            [(self.ticket_type.pk, 100)],
        )

        self.assertEqual(new_order.status, Order.Status.PENDING)
        self.assertEqual(new_order.items.get().quantity, 100)

    def test_order_preserves_price_at_purchase(self):
        order = create_order(
            self.user,
            [(self.ticket_type.pk, 2)],
        )

        self.ticket_type.price = Decimal("35.00")
        self.ticket_type.save(update_fields=["price"])

        item = order.items.get()

        self.assertEqual(
            item.price_at_purchase,
            Decimal("25.00"),
        )
        self.assertEqual(
            item.ticket_type.price,
            Decimal("35.00"),
        )
