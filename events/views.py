from django.views.generic import CreateView, ListView, DetailView, UpdateView, DeleteView
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy

from .forms import EventForm, TicketTypeForm
from .models import Event, OrganizerProfile, TicketType, TicketPriceChange


class EventListView(ListView):
    model = Event
    template_name = "events/event_list.html"
    context_object_name = "events"
    ordering = ["start_datetime"]

    def get_queryset(self):
        return Event.objects.filter(
            approval_status=Event.ApprovalStatus.APPROVED
        ).order_by("start_datetime")

class EventDetailView(DetailView):
    model = Event
    template_name = "events/event_detail.html"
    context_object_name = "event"

    def get_queryset(self):
        return Event.objects.filter(
            approval_status=Event.ApprovalStatus.APPROVED
        )


class EventCreateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    CreateView,
):
    model = Event
    form_class = EventForm
    template_name = "events/event_form.html"
    success_url = reverse_lazy("event-list")
    raise_exception = True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def test_func(self):
        user = self.request.user

        if user.is_staff or user.is_superuser:
            return True

        try:
            profile = user.organizer_profile
        except OrganizerProfile.DoesNotExist:
            return False

        return profile.is_verified and profile.can_create_events

    def form_valid(self, form):
        user = self.request.user

        if user.is_staff or user.is_superuser:
            form.instance.approval_status = Event.ApprovalStatus.APPROVED
        else:
            form.instance.organizer = user
            form.instance.approval_status = Event.ApprovalStatus.PENDING

        return super().form_valid(form)


class EventUpdateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    UpdateView,
):
    model = Event
    form_class = EventForm
    template_name = "events/event_form.html"
    success_url = reverse_lazy("event-list")

    def test_func(self):
        event = self.get_object()
        user = self.request.user

        return (
            user.is_staff
            or user.is_superuser
            or event.organizer_id == user.id
        )

    def form_valid(self, form):
        if (
            not self.request.user.is_staff
            and not self.request.user.is_superuser
            and form.instance.approval_status == Event.ApprovalStatus.APPROVED
        ):
            form.instance.approval_status = Event.ApprovalStatus.PENDING

        return super().form_valid(form)


class EventDeleteView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    DeleteView,
):
    model = Event
    template_name = "events/event_confirm_delete.html"
    success_url = reverse_lazy("event-list")

    def test_func(self):
        event = self.get_object()
        user = self.request.user

        return (
            user.is_staff
            or user.is_superuser
            or event.organizer_id == user.id
        )


class TicketTypeCreateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    CreateView,
):
    model = TicketType
    form_class = TicketTypeForm
    template_name = "events/ticket_type_form.html"

    def test_func(self):
        event = self.get_event()
        user = self.request.user

        return (
            user.is_staff
            or user.is_superuser
            or event.organizer_id == user.id
        )

    def get_event(self):
        return Event.objects.get(pk=self.kwargs["event_pk"])

    def form_valid(self, form):
        form.instance.event = self.get_event()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "event-detail",
            kwargs={"pk": self.get_event().pk},
        )


class TicketTypeUpdateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    UpdateView,
):
    model = TicketType
    form_class = TicketTypeForm
    template_name = "events/ticket_type_form.html"

    def test_func(self):
        ticket_type = self.get_object()
        user = self.request.user

        return (
            user.is_staff
            or user.is_superuser
            or ticket_type.event.organizer_id == user.id
        )

    def get_success_url(self):
        return reverse_lazy(
            "event-detail",
            kwargs={"pk": self.object.event.pk},
        )

    def form_valid(self, form):
        with transaction.atomic():
            old_price = self.get_object().price

            response = super().form_valid(form)

            new_price = self.object.price

            if old_price != new_price:
                TicketPriceChange.objects.create(
                    ticket_type=self.object,
                    ticket_type_name=self.object.name,
                    old_price=old_price,
                    new_price=new_price,
                    changed_by=self.request.user,
                )

        return response

class TicketTypeDeleteView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    DeleteView,
):
    model = TicketType
    template_name = "events/ticket_type_confirm_delete.html"

    def test_func(self):
        ticket_type = self.get_object()
        user = self.request.user

        return (
            user.is_staff
            or user.is_superuser
            or ticket_type.event.organizer_id == user.id
        )

    def get_success_url(self):
        return reverse_lazy(
            "event-detail",
            kwargs={"pk": self.object.event.pk},
        )