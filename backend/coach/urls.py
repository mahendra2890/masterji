from django.urls import path

from . import views

urlpatterns = [
    path("state/", views.StateView.as_view(), name="coach_state"),
    path("goals/", views.GoalsView.as_view(), name="coach_goals"),
    # PATCH only, and only the title — see GoalUpdateView.
    path("goals/<int:pk>/", views.GoalUpdateView.as_view(), name="coach_goal_update"),
    path("goals/<int:pk>/history/", views.GoalHistoryView.as_view(), name="coach_history"),
    # The same record as history/, as a file the builder can keep.
    path("goals/<int:pk>/export/", views.GoalExportView.as_view(), name="coach_export"),
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
    # A proof screenshot, signed on the way past. Two literal routes rather
    # than one with a <str:kind> segment: `kind` selects a model and an
    # ownership path, so the set of legal values belongs in the router, where
    # an unknown one is a 404, and not in a dict lookup that would raise.
    path(
        "checkins/<int:pk>/image/",
        views.ProofImageView.as_view(),
        {"kind": "checkins"},
        name="coach_checkin_image",
    ),
    path(
        "attempts/<int:pk>/image/",
        views.ProofImageView.as_view(),
        {"kind": "attempts"},
        name="coach_attempt_image",
    ),
    path("chat/", views.ChatView.as_view(), name="coach_chat"),
    # The inverse of chat/: available only while there is no goal.
    path(
        "workshop/chat/",
        views.WorkshopChatView.as_view(),
        name="coach_workshop_chat",
    ),
    # Public: no auth, no tenancy — the same list for every reader.
    path("changelog/", views.ChangelogView.as_view(), name="coach_changelog"),
]
