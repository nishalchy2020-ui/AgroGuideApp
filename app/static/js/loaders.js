document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', (e) => {
    const btn = form.querySelector('[data-loading]');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    const label = btn.innerHTML;
    btn.innerHTML = '<span class="loader loader-dark inline-block"></span> Processing...';
    btn.dataset.originalLabel = label;
  });
});
