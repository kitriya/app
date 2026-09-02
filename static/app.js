// ---- Like forms: submit via fetch so the page doesn't reload ----
document.addEventListener('submit', function (e) {
  const form = e.target;
  if (!form.classList.contains('like-form')) return;

  e.preventDefault();
  const btn = form.querySelector('button');
  const path = btn.querySelector('svg path');
  const wasLiked = btn.dataset.liked === 'true';

  fetch(form.action, { method: 'POST', body: new FormData(form) }).catch(function () {});

  btn.dataset.liked = wasLiked ? 'false' : 'true';
  if (path) {
    path.setAttribute('fill', wasLiked ? 'none' : '#C4536B');
    path.setAttribute('stroke', '#C4536B');
  }

  const container = form.closest('article, div');
  const countEl = container ? container.querySelector('.like-count') : null;
  if (countEl) {
    let n = parseInt(countEl.dataset.count || '0', 10);
    n = wasLiked ? Math.max(0, n - 1) : n + 1;
    countEl.dataset.count = n;
    countEl.textContent = n;
  }
});

// ---- Double-tap / double-click to like a photo, with a heart burst ----
function lufricaDoubleTap(mediaEl) {
  const form = mediaEl.parentElement.querySelector('.like-form');
  if (form) {
    const btn = form.querySelector('button');
    if (btn && btn.dataset.liked !== 'true') {
      form.requestSubmit();
    }
  }

  const burst = document.createElement('div');
  burst.className = 'lf-burst';
  burst.style.position = 'absolute';
  burst.style.top = '50%';
  burst.style.left = '50%';
  burst.style.transform = 'translate(-50%,-50%)';
  burst.style.pointerEvents = 'none';
  burst.innerHTML = '<svg viewBox="0 0 24 24" width="90" height="90" fill="#F4EFE6"><path d="M12 21s-7-4.35-9.5-8.5C.5 8.5 3 5 6.5 5c2 0 3.5 1.5 5.5 4 2-2.5 3.5-4 5.5-4C21 5 23.5 8.5 21.5 12.5 19 16.65 12 21 12 21z"/></svg>';
  mediaEl.style.position = 'relative';
  mediaEl.appendChild(burst);
  setTimeout(function () { burst.remove(); }, 700);
}

// ---- Count-up animation for profile stats ----
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-countup]').forEach(function (el) {
    const target = parseInt(el.dataset.countup, 10) || 0;
    const duration = 600;
    const start = performance.now();
    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      el.textContent = Math.floor(progress * target);
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = target;
    }
    requestAnimationFrame(step);
  });
});

// ---- Reels: tap video to toggle sound (matches the muted-icon overlay) ----
function lufricaToggleMute(video, event) {
  event.preventDefault();
  video.muted = !video.muted;

  const container = video.parentElement;
  const icon = container.querySelector('.mute-icon');
  if (!icon) return;

  if (video.muted) {
    icon.innerHTML = '<path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>';
  } else {
    icon.innerHTML = '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/>';
    // Only one reel should play with sound at a time — mute any others.
    document.querySelectorAll('video').forEach(function (v) {
      if (v !== video) v.muted = true;
    });
    document.querySelectorAll('.mute-icon').forEach(function (i) {
      if (i !== icon) i.innerHTML = '<path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>';
    });
  }
}
// ---- Create page: media type toggle (accept + multiple) ----
function lufricaSetAccept(radio) {
  const input = document.getElementById('media-input');
  const label = document.getElementById('dropzone-label');
  if (radio.value === 'reel') {
    input.setAttribute('accept', 'video/*');
    input.removeAttribute('multiple');
    label.textContent = 'Tap to choose a video from your device';
  } else if (radio.value === 'carousel') {
    input.setAttribute('accept', 'image/*');
    input.setAttribute('multiple', 'true');
    label.textContent = 'Tap to choose multiple photos';
  } else {
    input.setAttribute('accept', 'image/*');
    input.removeAttribute('multiple');
    label.textContent = 'Tap to choose a photo from your device';
  }
  document.getElementById('preview').innerHTML = '';
}

// ---- Create page: live preview of selected file(s) ----
function lufricaPreview(event) {
  const files = event.target.files;
  const preview = document.getElementById('preview');
  preview.innerHTML = '';
  if (!files || !files.length) return;

  Array.from(files).slice(0, 10).forEach(function (file) {
    const url = URL.createObjectURL(file);
    const isVideo = file.type.startsWith('video');
    const el = document.createElement(isVideo ? 'video' : 'img');
    el.src = url;
    el.id = 'preview-media';
    el.className = 'lf-filter-none';
    el.style.width = '100%';
    el.style.borderRadius = '8px';
    el.style.marginTop = '8px';
    el.style.maxHeight = '220px';
    el.style.objectFit = 'cover';
    if (isVideo) {
      el.muted = true;
      el.controls = true;
    }
    preview.appendChild(el);
  });
}

// ---- Create page: live filter preview ----
function lufricaApplyFilter(filterName) {
  document.querySelectorAll('#preview img, #preview video').forEach(function (el) {
    el.className = 'lf-filter-' + filterName;
  });
}
