const menuButton = document.querySelector('.nav-toggle');
const menu = document.querySelector('#main-nav');
function closeMenu() { menuButton?.setAttribute('aria-expanded', 'false'); menu?.classList.remove('is-open'); }
menuButton?.addEventListener('click', () => {
  const open = menuButton.getAttribute('aria-expanded') !== 'true';
  menuButton.setAttribute('aria-expanded', String(open));
  menu.classList.toggle('is-open', open);
});
menu?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => { if (event.key === 'Escape' && menu?.classList.contains('is-open')) { closeMenu(); menuButton.focus(); } });
document.addEventListener('click', event => { if (!event.target.closest('.bar')) closeMenu(); });
document.querySelector('.password-toggle')?.addEventListener('click', event => {
  const field = document.querySelector('#password');
  const show = field.type === 'password';
  field.type = show ? 'text' : 'password';
  event.currentTarget.textContent = show ? 'Hide' : 'Show';
  event.currentTarget.setAttribute('aria-pressed', String(show));
});
const video = document.querySelector('.hero-video');
const videoButton = document.querySelector('.video-toggle');
if (video && videoButton) {
  const updateVideoButton = () => {
    videoButton.textContent = video.paused ? 'Play background' : 'Pause background';
    videoButton.setAttribute('aria-pressed', String(video.paused));
  };
  video.addEventListener('play', updateVideoButton);
  video.addEventListener('pause', updateVideoButton);
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (motion.matches) { video.autoplay = false; video.pause(); }
  motion.addEventListener('change', event => { if (event.matches) video.pause(); });
  videoButton.addEventListener('click', () => {
    if (video.paused) video.play().catch(updateVideoButton); else video.pause();
  });
  updateVideoButton();
}
