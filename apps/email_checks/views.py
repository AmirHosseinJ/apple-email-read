from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.email_checks.serializers import EmailCheckRunSerializer
from apps.email_checks.services import run_outlook_check
from apps.scraper.exceptions import LoginFailed, MfaRequired, ScraperTimeout, OutlookScraperError


class OutlookEmailCheckRunView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = EmailCheckRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            result = run_outlook_check(
                email=data['email'],
                password=data['password'],
                max_messages=data['max_messages'],
            )
        except LoginFailed as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except MfaRequired as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except ScraperTimeout as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except OutlookScraperError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                'status': 'success',
                'result': result,
            },
            status=status.HTTP_200_OK,
        )
