from django.urls import path
from . import views

app_name = "doctors"

urlpatterns = [
    path("", views.finder_view, name="finder"),
    path("panel/", views.panel_view, name="panel"),
    path("panel/delete/<str:reference_id>/", views.delete_record_view, name="delete_record"),
    path("panel/serial-report/", views.serial_report_view, name="serial_report"),
    path("panel/review/<str:reference_id>/", views.review_update_view, name="review_update"),
    path("search/", views.search_view, name="search"),
    path("geocode/", views.geocode_view, name="geocode"),
]
