from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('api/auth/token/', TokenObtainPairView.as_view(), name='jwt-obtain'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='jwt-refresh'),
    path('api/auth/api-token/', obtain_auth_token, name='api-token-auth'),
    path('api/', include('apps.email_checks.urls')),
    path('admin/', admin.site.urls),
]
