from django.urls import path

from .views import JournalList, chat_view

urlpatterns = [
    path("coach/chat/", chat_view, name="coach-chat"),
    path("journal/", JournalList.as_view(), name="journal"),
]
