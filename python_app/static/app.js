'use strict';
window.csrfToken = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
window.postForm = async (url, data) => {
  const response = await fetch(url, {method:'POST', credentials:'same-origin', headers:{'X-CSRFToken': csrfToken(), 'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams(data)});
  if (!response.ok || response.redirected) throw new Error('Yêu cầu bị từ chối. Kiểm tra quyền truy cập hoặc đăng nhập lại.');
  return response.json();
};

const membershipForm = document.getElementById('membership-form');
if (membershipForm) {
  membershipForm.addEventListener('change', (event) => {
    if (event.target.name === 'plan') {
      document.getElementById('selected-price').textContent = event.target.dataset.price;
    }
  });
}
