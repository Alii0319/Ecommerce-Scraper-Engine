import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims matching buildUserFromTokens
        token['email'] = user.email
        token['first_name'] = user.first_name or ''
        token['last_name'] = user.last_name or ''
        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'first_name', 'last_name')

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("A user with this email domain record already exists.")
        return value.lower()

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Za-z]', value):
            raise serializers.ValidationError("Password must include at least one letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must include at least one number.")
        if not re.search(r'[^A-Za-z0-9]', value):
            raise serializers.ValidationError("Password must include at least one special character.")
        return value

    def create(self, validated_data):
        # Destructure clean parameters to enforce password hashing via the Custom Manager
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user


class WebSocketTicketSerializer(serializers.Serializer):
    """Response schema for short-lived WebSocket authentication tickets."""

    ticket = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
