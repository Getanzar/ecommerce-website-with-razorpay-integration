web: python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py createcachetable && gunicorn config.wsgi:application
