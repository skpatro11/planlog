import jwt
from urllib.parse import urlencode
from smtplib import SMTPException
from django.contrib.auth import authenticate
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from planlog.models.user import User
from .serializers import LoginSerializer, RegisterSerializer, LoggedInUserSerializer, ProfileSerializer


def get_user_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class AuthenticationStatusView(APIView):
    def get(self, request):
        if bool(request.user and request.user.is_authenticated):
            return Response(data={'detail': 'User is logged in'}, status=status.HTTP_200_OK)
        else:
            return Response(data={'detail': 'User is not logged in'}, status=status.HTTP_401_UNAUTHORIZED)


class RegisterView(APIView):
    def get(self, request):
        send_confirmation = request.query_params.get('send_confirmation', None)
        confirmation_token = request.query_params.get('confirmation_token', None)

        if send_confirmation:
            encoded_token = jwt.encode({
                'email': send_confirmation,
                'exp': timezone.now() + timezone.timedelta(hours=2)
            }, key=settings.SECRET_KEY, algorithm="HS256")

            # Sending email
            confirmation_url = settings.FRONTEND_BASE_URL + settings.FRONTEND_CONFIRMATION_URL + '?' + urlencode({'confirmation_token': encoded_token})
            try:
                subject = 'Registration confirmation email'
                html_message = render_to_string('emails/auth/confirmation_email.html', {'confirmation_url': confirmation_url})
                plain_message = strip_tags(html_message)
                from_email = settings.DEFAULT_NO_REPLY_EMAIL
                to = send_confirmation

                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=from_email,
                    recipient_list=[to],
                    html_message=html_message,
                    fail_silently=False
                )
            except SMTPException:
                print('Log the error')

            return Response(data={'detail': 'Email has been sent'}, status=status.HTTP_200_OK)

        elif confirmation_token:
            try:
                decoded_data = jwt.decode(confirmation_token, key=settings.SECRET_KEY, algorithms=['HS256'])
                decoded_data.pop('exp')
                return Response(data={'detail': 'The confirmation link is valid', 'data': decoded_data}, status=status.HTTP_200_OK)
            except jwt.ExpiredSignatureError:
                return Response(data={'detail': 'The confirmation link has been expired!'}, status=status.HTTP_401_UNAUTHORIZED)
            except jwt.InvalidTokenError:
                return Response(data={'detail': 'Invalid token provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data={'detail': 'Please provide additional information'}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        confirmation_token = request.query_params.get('confirmation_token', None)

        if not confirmation_token:
            return Response(data={'detail': 'Please provide confirmation token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded_data = jwt.decode(confirmation_token, key=settings.SECRET_KEY, algorithms=['HS256'])
            serializer = RegisterSerializer(data=request.data)

            # Check for response body
            if not serializer.is_valid():
                return Response(
                    data={
                        'detail': 'Invalid user input',
                        'errors': serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Checking for existing User with the given email address
            try:
                User.objects.get(email=serializer.data.get('email'))
                return Response(data={'detail': 'User exists with this email address'}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                pass

            new_user_details = serializer.data
            password = new_user_details.pop('password')

            user = User(**new_user_details)
            user.set_password(password)
            user.is_email_verified = True
            user.save()

            return Response(data={'detail': 'Account created successfully'}, status=status.HTTP_200_OK)

        except jwt.ExpiredSignatureError:
            return Response(data={'detail': 'The confirmation link has been expired!'}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response(data={'detail': 'Invalid token provided'}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        # Check for response body
        if not serializer.is_valid():
            return Response(
                data={
                    'detail': 'Invalid user input',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validating username/email-address and password
        user: User = authenticate(**serializer.data)
        if not user:
            return Response(data={'detail': 'Invalid email address or password'}, status=status.HTTP_401_UNAUTHORIZED)

        # Saving user track information
        user.last_login_at = timezone.now()
        user.last_login_ip = get_user_ip(request)
        user.save()

        logged_in_serializer = LoggedInUserSerializer(user)
        return Response(data=logged_in_serializer.data, status=status.HTTP_200_OK)


class AvailabilityView(APIView):
    def get(self, request):
        username = request.query_params.get('username', None)
        email = request.query_params.get('email', None)

        if username:
            kwargs = {'username': username}
        elif email:
            kwargs = {'email': email}
        else:
            return Response(data={'detail': 'Please provide the availability criteria'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            User.objects.get(**kwargs)
            return Response(data={'detail': False}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response(data={'detail': True}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile_serializer = ProfileSerializer(request.user)

        return Response(data=profile_serializer.data, status=status.HTTP_200_OK)
