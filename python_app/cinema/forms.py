from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User
from .avatars import normalized_avatar

class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Email đã được sử dụng.')
        return email

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'bio')

class AvatarForm(forms.Form):
    avatar = forms.FileField(label='Ảnh đại diện', required=False, widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}))
    remove_avatar = forms.BooleanField(label='Xóa ảnh đại diện', required=False)

    def __init__(self, *args, upload_error=None, **kwargs):
        self.upload_error = upload_error
        super().__init__(*args, **kwargs)

    def clean_avatar(self):
        upload = self.cleaned_data.get('avatar')
        return normalized_avatar(upload) if upload and not self.upload_error else None

    def clean(self):
        cleaned = super().clean()
        if self.upload_error:
            raise forms.ValidationError(self.upload_error)
        if cleaned.get('avatar') and cleaned.get('remove_avatar'):
            raise forms.ValidationError('Chọn ảnh mới hoặc xóa ảnh hiện tại, không chọn cả hai cùng lúc.')
        if not cleaned.get('avatar') and not cleaned.get('remove_avatar') and 'avatar' not in self.errors:
            raise forms.ValidationError('Chọn ảnh mới hoặc đánh dấu xóa ảnh hiện tại.')
        return cleaned

class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Tên đăng nhập hoặc email', widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}))
