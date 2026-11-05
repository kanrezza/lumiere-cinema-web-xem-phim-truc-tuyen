"""Normalize public profile images; never publish an original uploaded file."""
import io
import re
import warnings

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
MAX_AVATAR_EDGE = 8192
AVATAR_SIZE = 512


def normalized_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise ValidationError('Ảnh đại diện tối đa 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValidationError('Chọn ảnh JPG, PNG hoặc WebP.')
                width, height = image.size
                if width <= 0 or height <= 0 or max(width, height) > MAX_AVATAR_EDGE or width * height > MAX_AVATAR_PIXELS:
                    raise ValidationError('Ảnh quá lớn. Chọn ảnh tối đa 20 megapixel và mỗi cạnh không quá 8192 px.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValidationError('Vui lòng chọn ảnh tĩnh JPG, PNG hoặc WebP.')
                image.verify()
            upload.seek(0)
            with Image.open(upload) as image:
                image = ImageOps.exif_transpose(image)
                has_alpha = 'A' in image.getbands() or (image.mode == 'P' and 'transparency' in image.info)
                image = image.convert('RGBA' if has_alpha else 'RGB')
                image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
                # A fresh image drops EXIF, GPS, comments, profiles and other input metadata.
                clean = Image.new(image.mode, image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, format='WEBP', quality=88, method=4)
        return ContentFile(output.getvalue(), name='avatar.webp')
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError('File ảnh không hợp lệ hoặc bị hỏng. Chọn ảnh JPG, PNG hoặc WebP khác.') from error


def is_managed_avatar(name):
    return bool(name and re.fullmatch(r'avatars/[0-9a-f]{32}\.webp', name))
