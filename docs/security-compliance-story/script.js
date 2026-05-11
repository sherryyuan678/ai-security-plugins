/* security-compliance-story-site — deck navigation */
(function () {
  'use strict';

  const slides = Array.from(document.querySelectorAll('.slide'));
  const total = slides.length;

  const tocList = document.getElementById('tocList');
  const toc = document.getElementById('toc');
  const tocBtn = document.getElementById('tocBtn');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  const progressFill = document.getElementById('progressFill');
  const slideCount = document.getElementById('slideCount');

  // Build TOC
  slides.forEach((s, i) => {
    const title = s.dataset.title || `Slide ${i + 1}`;
    const id = s.id;
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = `#${id}`;
    a.textContent = title;
    a.dataset.index = i;
    li.appendChild(a);
    tocList.appendChild(li);
  });

  const tocLinks = Array.from(tocList.querySelectorAll('a'));

  let currentIndex = 0;

  function setActive(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    currentIndex = i;
    slides.forEach((s, idx) => s.classList.toggle('is-active', idx === i));
    tocLinks.forEach((a, idx) => a.classList.toggle('active', idx === i));
    progressFill.style.width = `${((i + 1) / total) * 100}%`;
    slideCount.textContent = `${i + 1} / ${total}`;
  }

  function goTo(i, behavior = 'smooth') {
    i = Math.max(0, Math.min(slides.length - 1, i));
    slides[i].scrollIntoView({ behavior, block: 'start' });
    setActive(i);
  }

  // Click navigation in TOC
  tocLinks.forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const i = parseInt(a.dataset.index, 10);
      goTo(i);
      if (window.innerWidth < 900) closeToc();
    });
  });

  // Prev / next
  prevBtn.addEventListener('click', () => goTo(currentIndex - 1));
  nextBtn.addEventListener('click', () => goTo(currentIndex + 1));

  // Keyboard navigation
  document.addEventListener('keydown', (e) => {
    // Don't hijack form/text inputs or when modifier keys are held
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      e.preventDefault();
      goTo(currentIndex + 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault();
      goTo(currentIndex - 1);
    } else if (e.key === 'Home') {
      e.preventDefault(); goTo(0);
    } else if (e.key === 'End') {
      e.preventDefault(); goTo(slides.length - 1);
    } else if (e.key.toLowerCase() === 't') {
      e.preventDefault(); toggleToc();
    }
  });

  // TOC toggle
  function openToc() {
    toc.hidden = false;
    tocBtn.setAttribute('aria-expanded', 'true');
    document.body.classList.add('toc-open');
  }
  function closeToc() {
    toc.hidden = true;
    tocBtn.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('toc-open');
  }
  function toggleToc() {
    if (toc.hidden) openToc(); else closeToc();
  }
  tocBtn.addEventListener('click', toggleToc);

  // Click outside TOC closes it (on mobile widths)
  document.addEventListener('click', (e) => {
    if (toc.hidden) return;
    if (toc.contains(e.target)) return;
    if (e.target === tocBtn) return;
    if (window.innerWidth < 900) closeToc();
  });

  // Open TOC by default on desktop
  if (window.innerWidth >= 1100) openToc();

  // Track active slide on scroll using IntersectionObserver
  const io = new IntersectionObserver(
    (entries) => {
      // Pick the entry whose center is closest to viewport center
      let best = null;
      let bestRatio = 0;
      entries.forEach((entry) => {
        if (entry.intersectionRatio > bestRatio) {
          bestRatio = entry.intersectionRatio;
          best = entry.target;
        }
      });
      if (best) {
        const i = slides.indexOf(best);
        if (i >= 0) setActive(i);
      }
    },
    {
      threshold: [0.25, 0.5, 0.75],
      rootMargin: '-72px 0px -80px 0px'
    }
  );
  slides.forEach((s) => io.observe(s));

  // Initial state — pick the slide whose top is closest to current scroll
  function syncFromScroll() {
    const y = window.scrollY + window.innerHeight / 3;
    let best = 0;
    let bestDelta = Infinity;
    slides.forEach((s, i) => {
      const d = Math.abs(s.offsetTop - y);
      if (d < bestDelta) { bestDelta = d; best = i; }
    });
    setActive(best);
  }
  window.addEventListener('load', syncFromScroll);
  setActive(0);

  // Hash deep-link
  if (location.hash) {
    const target = document.querySelector(location.hash);
    if (target && target.classList.contains('slide')) {
      const i = slides.indexOf(target);
      if (i >= 0) {
        // Defer to allow layout
        requestAnimationFrame(() => goTo(i, 'auto'));
      }
    }
  }
})();
