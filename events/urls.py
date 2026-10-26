from django.urls import path

from .views import EventListView, EventDetailView, EventCreateView, EventUpdateView, EventDeleteView, \
    TicketTypeCreateView, TicketTypeUpdateView, TicketTypeDeleteView

urlpatterns = [
    path("", EventListView.as_view(), name="event-list"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/create/", EventCreateView.as_view(), name="event-create"),
    path("events/<int:pk>/edit/", EventUpdateView.as_view(), name="event-edit"),
    path("events/<int:pk>/delete/", EventDeleteView.as_view(), name="event-delete"),
    path(
        "events/<int:event_pk>/tickets/create/",
        TicketTypeCreateView.as_view(),
        name="ticket-type-create",
    ),

    path(
        "tickets/<int:pk>/edit/",
        TicketTypeUpdateView.as_view(),
        name="ticket-type-edit",
    ),

    path(
        "tickets/<int:pk>/delete/",
        TicketTypeDeleteView.as_view(),
        name="ticket-type-delete",
    ),
]