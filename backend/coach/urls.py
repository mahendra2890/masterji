from django.urls import path

from . import views

urlpatterns = [
    path("state/", views.StateView.as_view(), name="coach_state"),
    path("goals/", views.GoalsView.as_view(), name="coach_goals"),
    # PATCH only, and only the title — see GoalUpdateView.
    path("goals/<int:pk>/", views.GoalUpdateView.as_view(), name="coach_goal_update"),
    path("goals/<int:pk>/history/", views.GoalHistoryView.as_view(), name="coach_history"),
    path("goals/<int:pk>/advance/", views.AdvanceView.as_view(), name="coach_advance"),
    path("goals/<int:pk>/retire/", views.RetireView.as_view(), name="coach_retire"),
    path("goals/<int:pk>/complete/", views.CompleteView.as_view(), name="coach_complete"),
    path("checkins/declare/", views.DeclareView.as_view(), name="coach_declare"),
    path(
        "checkins/<int:pk>/judge/",
        views.JudgeDeclarationView.as_view(),
        name="coach_judge_declaration",
    ),
    path("checkins/prove/", views.ProveView.as_view(), name="coach_prove"),
    path("chat/", views.ChatView.as_view(), name="coach_chat"),
    # Public: no auth, no tenancy — the same list for every reader.
    path("changelog/", views.ChangelogView.as_view(), name="coach_changelog"),
]
