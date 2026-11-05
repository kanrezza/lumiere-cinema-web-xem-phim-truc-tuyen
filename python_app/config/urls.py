from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from cinema import views as v
from cinema.forms import LoginForm
urlpatterns = [
    path('', v.landing, name='landing'), path('browse/', v.catalog, name='catalog'), path('movies/<slug:slug>/', v.movie_detail, name='movie'),
    path('accounts/register/', v.register, name='register'), path('accounts/login/', auth.LoginView.as_view(redirect_authenticated_user=True, authentication_form=LoginForm, extra_context={'title':'Chào mừng trở lại', 'subtitle':'Tiếp tục câu chuyện của bạn.', 'button':'Đăng nhập'}), name='login'), path('accounts/', include('django.contrib.auth.urls')),
    path('library/', v.library, name='library'), path('profile/', v.profile, name='profile'), path('profile/avatar/', v.profile_avatar, name='profile_avatar'),
    path('movies/<int:pk>/save/', v.watchlist_toggle, name='save'), path('movies/<int:pk>/comment/', v.comment, name='comment'), path('movies/<int:pk>/rate/', v.rate, name='rate'),
    path('watch/<int:pk>/', v.watch, name='watch'), path('watch/<int:pk>/progress/', v.progress, name='progress'), path('watch/<int:pk>/report/', v.report, name='report'),
    path('watch/<int:pk>/ticket/', v.stream_ticket, name='ticket'), path('stream/<int:pk>/<str:filename>/', v.stream, name='stream'),
    path('vip/', v.plans, name='plans'), path('checkout/<int:pk>/', v.checkout, name='checkout'), path('checkout/', v.checkout, name='checkout_selected'), path('payments/ipn/', v.ipn, name='ipn'), path('payments/return/', v.payment_return, name='payment_return'),
    path('watch/<int:pk>/room/', v.create_room, name='create_room'), path('rooms/<uuid:pk>/', v.room, name='room'), path('rooms/<uuid:pk>/join/', v.join_room, name='join_room'), path('rooms/<uuid:pk>/state/', v.room_state, name='room_state'),
    path('countries/', v.countries, name='countries'), path('genres/', v.categories, name='categories'),
    path('actors/', v.actors, name='actors'), path('actors/<int:pk>/', v.actor_detail, name='actor'),
    path('history/clear/', v.clear_history, name='clear_history'), path('comments/<int:pk>/delete/', v.delete_comment, name='delete_comment'),
    path('rooms/<uuid:pk>/leave/', v.leave_room, name='leave_room'), path('studio/', v.studio, name='studio'),
    path('admin/', admin.site.urls),
]
if settings.DEBUG: urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
