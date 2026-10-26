from django.contrib import admin

from .models import Event, OrganizerProfile, TicketType, TicketPriceChange, Order, OrderItem


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_verified", "can_create_events")
    list_filter = ("is_verified", "can_create_events")
    search_fields = ("user__username", "user__email")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "location",
        "start_datetime",
        "end_datetime",
        "organizer",
        "approval_status",
    )
    list_filter = ("approval_status", "start_datetime", "location")
    search_fields = ("title", "location", "description")


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "event",
        "price",
        "quantity",
        "quantity_sold",
    )

    readonly_fields = ("quantity_sold",)

    def save_model(self, request, obj, form, change):
        old_price = None

        if change:
            old_obj = TicketType.objects.get(pk=obj.pk)
            old_price = old_obj.price

        super().save_model(request, obj, form, change)

        if change and old_price != obj.price:
            TicketPriceChange.objects.create(
                ticket_type=obj,
                ticket_type_name=obj.name,
                old_price=old_price,
                new_price=obj.price,
                changed_by=request.user,
            )


@admin.register(TicketPriceChange)
class TicketPriceChangeAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_type_name",
        "old_price",
        "new_price",
        "changed_by",
        "changed_at",
    )
    list_filter = ("changed_at",)
    search_fields = ("ticket_type_name", "changed_by__username")
    readonly_fields = (
        "ticket_type",
        "ticket_type_name",
        "old_price",
        "new_price",
        "changed_by",
        "changed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "customer_name",
        "customer_email",
        "status",
        "created_at",
    )

    list_filter = ("status", "created_at")

    search_fields = (
        "customer_name",
        "customer_email",
        "user__username",
    )

    readonly_fields = (
        "user",
        "customer_name",
        "customer_email",
        "status",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "ticket_type",
        "quantity",
        "price_at_purchase",
    )
    list_filter = ("ticket_type",)
    search_fields = (
        "order__customer_name",
        "order__customer_email",
        "ticket_type__name",
    )