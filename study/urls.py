from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("app/", views.dashboard, name="dashboard"),
    path("history/", views.history, name="history"),
    path("study/<int:pk>/", views.result, name="result"),
    path("study/<int:pk>/quiz/", views.new_quiz, name="new_quiz"),
    path("study/<int:pk>/save/", views.save, name="save"),
    path("study/<int:pk>/regenerate/", views.regenerate, name="regenerate"),
    path("study/<int:pk>/delete/", views.delete, name="delete"),
    path("study/<int:pk>/download/<str:fmt>/", views.download, name="download"),
    path("api/study/history", views.api_history),
    path("api/study/<int:pk>", views.api_detail),
]
