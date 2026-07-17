from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models



class CustomUserManager(BaseUserManager):
    """Custom manager where email is the unique identifier instead of username."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """Production-ready Custom User model matching enterprise requirements."""
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'  # Makes email the primary login credential
    REQUIRED_FIELDS = []      # Removes default requirement for username

    objects = CustomUserManager()

    def __str__(self):
        return self.email