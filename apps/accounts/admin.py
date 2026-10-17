from django.contrib import admin

from .models import PatientProfile


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "sex", "age", "location")
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone")
