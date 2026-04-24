from django.urls import path
from .views import RouteView, index

urlpatterns = [
    path("",  index, name="home"),       # serves the UI
    path("api/route", RouteView.as_view(), name='route'),
]