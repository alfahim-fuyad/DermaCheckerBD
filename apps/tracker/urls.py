from django.urls import path
from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("new/", views.create_view, name="create"),
    path("<str:lesion_id>/", views.detail_view, name="detail"),
    path("<str:lesion_id>/add-photo/", views.add_photo_view, name="add_photo"),
    path("<str:lesion_id>/delete/", views.delete_view, name="delete"),
    path("<str:lesion_id>/photo/<int:photo_id>/delete/", views.delete_photo_view, name="delete_photo"),
    path("<str:lesion_id>/summary.pdf", views.summary_pdf_view, name="summary_pdf"),
]
