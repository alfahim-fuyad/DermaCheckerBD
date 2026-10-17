from django.urls import path
from . import views

app_name = "predictor"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("result/<str:reference_id>/", views.result_view, name="result"),
    path("result/<str:reference_id>/pdf/", views.pdf_report_view, name="pdf_report"),
    path("result/<str:reference_id>/delete/", views.delete_record_view, name="delete"),
    path("history/", views.history_view, name="history"),
    path("history/clear/", views.clear_history_view, name="clear_history"),
]
