(function () {
  const canvas = document.getElementById('admin-chart');
  if (!canvas || typeof labels === 'undefined' || !labels.length) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth || 600;
  const h = canvas.height = 160;
  const max = Math.max(...data, 1);
  const barW = w / (labels.length * 1.5);
  labels.forEach((label, i) => {
    const barH = (data[i] / max) * (h - 30);
    const x = i * barW * 1.5 + 20;
    ctx.fillStyle = '#16a34a';
    ctx.fillRect(x, h - barH - 10, barW, barH);
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter, sans-serif';
    ctx.fillText(String(data[i]), x, h - barH - 14);
  });
})();
