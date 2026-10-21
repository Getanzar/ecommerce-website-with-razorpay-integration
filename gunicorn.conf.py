"""Allow the shared seller assistant's sequential text and image requests to finish.

Gunicorn automatically loads this file from the project working directory, even
when Render's saved start command is simply gunicorn config.wsgi:application.
"""
timeout = 150
worker_class = "gthread"
threads = 2
