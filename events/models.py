from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator


class OrganizerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organizer_profile",
    )
    is_verified = models.BooleanField(default=False)
    can_create_events = models.BooleanField(default=False)

    def __str__(self):
        return f"Organizer: {self.user.username}"


class Event(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=255)

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    image = models.ImageField(upload_to="events/", blank=True, null=True)

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events"
    )

    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class TicketType(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="ticket_types",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    quantity = models.PositiveIntegerField()
    quantity_sold = models.PositiveIntegerField(default=0)

    def clean(self):
        super().clean()

        if (
            self.quantity is not None
            and self.quantity_sold is not None
            and self.quantity < self.quantity_sold
        ):
            raise ValidationError({
                "quantity": (
                    "Total quantity cannot be lower than "
                    "the number of tickets already sold."
                )
            })

    def __str__(self):
        return f"{self.event.title} - {self.name}"
    

class TicketPriceChange(models.Model):
    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_changes",
    )
    ticket_type_name = models.CharField(max_length=100)
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_price_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.ticket_type_name}: "
            f"{self.old_price} → {self.new_price}"
        )


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.user:
            return f"Order #{self.pk} - {self.user.username}"
        return f"Order #{self.pk} - {self.customer_email}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    price_at_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    def __str__(self):
        return (
            f"{self.quantity} x {self.ticket_type.name} "
            f"(Order #{self.order_id})"
        )