from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return  # skip in Django reloader subprocess
        from .data_loader import get_fuel_data, geocode_from_csv
        get_fuel_data()