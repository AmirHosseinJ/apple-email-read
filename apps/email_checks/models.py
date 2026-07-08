from django.conf import settings
from django.db import models


class EmailCheckRequest(models.Model):
    email = models.CharField(max_length=254)
    password = models.TextField()
    status = models.CharField(max_length=50)
    otp = models.CharField(max_length=16, blank=True, null=True)
    total_try = models.IntegerField(default=0)
    task_id = models.CharField(max_length=255, blank=True)
    max_messages = models.SmallIntegerField()
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    start_at = models.DateTimeField(blank=True, null=True)
    finish_at = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        db_table = 'email_checks_emailcheckrequest'

class Webhook(models.Model):
    ip = models.GenericIPAddressField(unique=True)
    webhook = models.URLField()
    header_key = models.CharField(max_length=255, blank=True)
    header_value = models.CharField(max_length=1024, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webhook"
        indexes = [
            models.Index(fields=["ip"]),
        ]

    def __str__(self):
        return f"{self.ip} -> {self.webhook}"