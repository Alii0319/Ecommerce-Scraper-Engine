from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class AuthenticationFlowTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.User = get_user_model()

	def test_login_returns_tokens_for_active_user(self):
		user = self.User.objects.create_user(
			email='login-test@example.com',
			password='StrongPass123!',
			first_name='Login',
			last_name='Tester',
		)

		response = self.client.post(
			'/api/auth/login/',
			{
				'email': 'login-test@example.com',
				'password': 'StrongPass123!',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertIn('access', payload)
		self.assertIn('refresh', payload)
		self.assertTrue(payload['access'])
		self.assertTrue(payload['refresh'])

	def test_register_creates_user_with_hashed_password(self):
		response = self.client.post(
			'/api/auth/register/',
			{
				'email': 'register-test@example.com',
				'password': 'StrongPass123!',
				'first_name': 'Register',
				'last_name': 'Tester',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertTrue(self.User.objects.filter(email='register-test@example.com').exists())
		user = self.User.objects.get(email='register-test@example.com')
		self.assertTrue(user.check_password('StrongPass123!'))
