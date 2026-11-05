'use strict';
(() => {
  for (const image of document.querySelectorAll('[data-saved-avatar]')) {
    image.addEventListener('error', () => { image.hidden = true; });
    if (image.complete && !image.naturalWidth) image.hidden = true;
  }

  const form = document.querySelector('[data-avatar-editor]');
  if (!form) return;
  const fileInput = form.querySelector('[data-avatar-file]');
  const remove = form.querySelector('[data-avatar-remove]');
  const preview = form.querySelector('[data-avatar-preview]');
  const image = form.querySelector('[data-avatar-preview-image]');
  const status = form.querySelector('[data-avatar-status]');
  const reset = form.querySelector('[data-avatar-reset]');
  const savedUrl = preview.dataset.avatarCurrent;
  const initialStatus = status.textContent;
  let generation = 0;
  let reader = null;

  function cancelRead() {
    generation += 1;
    if (reader && reader.readyState === FileReader.LOADING) reader.abort();
    reader = null;
  }

  function showImage(url) {
    image.hidden = !url;
    if (url) image.src = url;
    else image.removeAttribute('src');
  }

  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('is-error', error);
  }

  function restoreSaved() {
    cancelRead();
    fileInput.value = '';
    if (remove) remove.checked = false;
    showImage(savedUrl);
    reset.hidden = true;
    message(initialStatus);
  }

  fileInput.addEventListener('change', () => {
    cancelRead();
    const file = fileInput.files[0];
    if (!file) { restoreSaved(); return; }
    if (remove) remove.checked = false;
    reset.hidden = false;
    if (file.size > 5 * 1024 * 1024) {
      fileInput.value = '';
      showImage(savedUrl);
      message('Ảnh vượt quá 5 MB. Vui lòng chọn ảnh nhỏ hơn.', true);
      return;
    }
    if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      fileInput.value = '';
      showImage(savedUrl);
      message('Vui lòng chọn ảnh JPG, PNG hoặc WebP.', true);
      return;
    }
    const current = generation;
    message('Đang tạo ảnh xem trước…');
    reader = new FileReader();
    reader.addEventListener('load', () => {
      if (current !== generation) return;
      showImage(reader.result);
      message('Đang xem trước ảnh mới. Bấm “Lưu ảnh” để cập nhật ở cả hai vị trí.');
    });
    reader.addEventListener('error', () => {
      if (current !== generation) return;
      fileInput.value = '';
      showImage(savedUrl);
      message('Không đọc được ảnh. Vui lòng chọn lại tệp khác.', true);
    });
    reader.readAsDataURL(file);
  });

  if (remove) {
    remove.addEventListener('change', () => {
      cancelRead();
      fileInput.value = '';
      showImage(remove.checked ? '' : savedUrl);
      reset.hidden = !remove.checked;
      message(remove.checked ? 'Sẽ dùng lại chữ cái mặc định sau khi bạn bấm “Lưu ảnh”.' : initialStatus);
    });
    if (remove.checked) {
      showImage('');
      reset.hidden = false;
    }
  }

  image.addEventListener('error', () => {
    image.hidden = true;
    if (fileInput.files.length) message('Không thể xem trước ảnh này. Vui lòng chọn ảnh JPG, PNG hoặc WebP hợp lệ.', true);
  });
  reset.addEventListener('click', () => {
    restoreSaved();
    fileInput.focus();
  });
})();
