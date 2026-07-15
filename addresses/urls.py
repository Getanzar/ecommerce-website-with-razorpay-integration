from django.urls import path
from . import views

urlpatterns = [

    path("", views.address_list, name="address_list"),

    path("add/", views.add_address, name="add_address"),

    path("edit/<int:pk>/", views.edit_address, name="edit_address"),

    path("delete/<int:pk>/", views.delete_address, name="delete_address"),

    path("default/<int:pk>/", views.default_address, name="default_address"),

]