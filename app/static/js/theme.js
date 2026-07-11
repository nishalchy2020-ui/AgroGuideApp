(function () {
  const key = 'agroguide-theme';
  const root = document.documentElement;
  function toggle() {
    root.classList.toggle('dark');
    localStorage.setItem(key, root.classList.contains('dark') ? 'dark' : 'light');
    if (window.lucide) lucide.createIcons();
  }
  document.querySelectorAll('#theme-toggle').forEach((el) => el.addEventListener('click', toggle));
})();
