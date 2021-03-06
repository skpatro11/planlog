from django.test import TestCase
from planlog.models.user import User


class UserTestCase(TestCase):
    def setUp(self):
        user1 = User(email='user1@gmail.com', username='user1', full_name='User One')
        user1.set_password('user1')
        user1.save()

    def test_user_authentication(self):
        user = User.objects.get(username='user1')
        self.assertEqual(user.check_password('user1'), True)