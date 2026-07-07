from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create a user with the given username and password, or update the password if it exists.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--password', required=True)

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.save(update_fields=['password'])

        action = 'created' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'User {username} {action}.'))
