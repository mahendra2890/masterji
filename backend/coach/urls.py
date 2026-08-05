from django.urls import path

from . import views

urlpatterns = [
    path("state/", views.StateView.as_view(), name="coach_state"),
    path("goals/", views.GoalsView.as_view(), name="coach_goals"),
    path("goals/<int:pk>/advance/", views.AdvanceView.as_view(), name="coach_advance"),
    path("goals/<int:pk>/retire/", views.RetireView.as_view(), name="coach_retire"),
    path("goals/<int:pk>/complete/", views.CompleteView.as_view(), name="coach_complete"),
    path("checkins/declare/", views.DeclareView.as_view(), name="coach_declare"),
    path("checkins/prove/", views.ProveView.as_view(), name="coach_prove"),
    path("chat/", views.ChatView.as_view(), name="coach_chat"),
]
