'use strict';
(() => {
  const dialog = document.getElementById('movie-quickview');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const triggers = [...document.querySelectorAll('.quickview-trigger')];
  const title = dialog.querySelector('#quickview-title');
  const image = dialog.querySelector('#quickview-image');
  const meta = dialog.querySelector('#quickview-meta');
  const description = dialog.querySelector('#quickview-description');
  const status = dialog.querySelector('#quickview-status');
  const statusMessage = dialog.querySelector('#quickview-status-message');
  const details = dialog.querySelector('#quickview-details');
  const play = dialog.querySelector('#quickview-play');
  const playLabel = dialog.querySelector('#quickview-play-label');
  const vip = dialog.querySelector('#quickview-vip');
  const close = dialog.querySelector('.quickview-close');
  let returnFocus = null;
  let addedScrollLock = false;
  let pointerStartedOutside = false;

  function isOutside(event) {
    const rect = dialog.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
  }

  function open(trigger) {
    const movie = trigger.dataset;
    title.textContent = movie.movieTitle;
    description.textContent = movie.movieDescription;
    status.textContent = movie.movieStatus;
    status.classList.toggle('is-preparing', movie.movieReady !== '1');
    statusMessage.textContent = movie.movieStatusMessage;
    statusMessage.hidden = !movie.movieStatusMessage;
    meta.textContent = [movie.movieYear, movie.movieKind, movie.movieDuration ? `${movie.movieDuration} phút` : ''].filter(Boolean).join(' · ');
    image.src = movie.movieImage;
    details.href = movie.movieDetail;
    vip.hidden = movie.movieVip !== '1';
    const hasPlayback = movie.movieReady === '1' && Boolean(movie.moviePlay);
    play.hidden = !hasPlayback;
    if (hasPlayback) play.href = movie.moviePlay;
    else play.removeAttribute('href');
    playLabel.textContent = movie.moviePlayLabel;
    returnFocus = trigger;
    addedScrollLock = !document.body.classList.contains('quickview-open');
    document.body.classList.add('quickview-open');
    dialog.showModal();
  }

  for (const trigger of triggers) {
    trigger.hidden = false;
    trigger.addEventListener('click', () => open(trigger));
  }
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('pointerdown', event => {pointerStartedOutside = event.target === dialog && isOutside(event);});
  dialog.addEventListener('click', event => {
    if (pointerStartedOutside && event.target === dialog && isOutside(event)) dialog.close();
    pointerStartedOutside = false;
  });
  dialog.addEventListener('close', () => {
    if (addedScrollLock) document.body.classList.remove('quickview-open');
    addedScrollLock = false;
    if (returnFocus?.isConnected) returnFocus.focus({preventScroll:true});
    returnFocus = null;
  });
})();
