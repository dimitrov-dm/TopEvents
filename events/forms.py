from django import forms
from django.contrib.auth import get_user_model

from .models import Event, TicketType

User = get_user_model()


class EventForm(forms.ModelForm):
    organizer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "location",
            "start_datetime",
            "end_datetime",
            "image",
            "organizer",
        ]
        widgets = {
            "start_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user = kwargs.get("user")

        self.fields["start_datetime"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]
        self.fields["end_datetime"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        if user and (user.is_staff or user.is_superuser):
            self.fields["organizer"].queryset = User.objects.filter(
                organizer_profile__is_verified=True,
                organizer_profile__can_create_events=True,
            ).order_by("username")
            self.fields["organizer"].required = True
        else:
            self.fields.pop("organizer")

    def clean(self):
        cleaned_data = super().clean()

        start = cleaned_data.get("start_datetime")
        end = cleaned_data.get("end_datetime")

        if start and end and end <= start:
            self.add_error(
                "end_datetime",
                "The event must end after it starts.",
            )

        return cleaned_data


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = [
            "name",
            "description",
            "price",
            "quantity",
        ]