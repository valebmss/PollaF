from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('eliminatorias/', views.eliminatorias, name='eliminatorias'),
    path('ranking/', views.ranking, name='ranking'),
    path('mundial/', views.mundial, name='mundial'),
    path('llenar-prueba/', views.llenar_prueba, name='llenar_prueba'),
    path('registro/', views.registro, name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
