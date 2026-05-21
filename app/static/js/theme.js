(function () {
  const key = 'agroguide-theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(key);
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    root.classList.add('dark');
  }
  function toggle() {
    root.classList.toggle('dark');
    localStorage.setItem(key, root.classList.contains('dark') ? 'dark' : 'light');
    if (window.lucide) lucide.createIcons();
  }
  document.querySelectorAll('#theme-toggle').forEach((el) => el.addEventListener('click', toggle));
})();
