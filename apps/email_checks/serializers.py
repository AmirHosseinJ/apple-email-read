from rest_framework import serializers


class EmailCheckRunSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    max_messages = serializers.IntegerField(
        min_value=1,
        max_value=50,
        default=10,
        required=False,
    )


class WebhookQuerySerializer(serializers.Serializer):
    webhook = serializers.URLField()
    header_key = serializers.CharField(max_length=255, allow_blank=True, required=False, default='')
    header_value = serializers.CharField(max_length=1024, allow_blank=True, required=False, default='')
