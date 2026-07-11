# Apple Email Read

## Run with Docker

Copy `.env.example` to `.env` and replace `DJANGO_SECRET_KEY` before using the app outside local development. The `.env` file is required and is loaded by both the web and Celery containers. Then start the API, Celery worker, PostgreSQL, and Redis:

```sh
docker compose up --build
```

Nginx exposes the API at `http://localhost` locally and `http://45.195.200.99` on the server. Gunicorn, PostgreSQL, and Redis are available only inside the Compose network. Database migrations run automatically when the web container starts. To run Django management commands:

```sh
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
```

Stop the stack with `docker compose down`. Add `--volumes` only when you also want to delete the PostgreSQL and Redis data.
