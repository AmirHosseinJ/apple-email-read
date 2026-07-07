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
