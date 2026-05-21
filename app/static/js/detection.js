(function () {
  const dropZone = document.getElementById('drop-zone');
  const input = document.getElementById('image-input');
  const preview = document.getElementById('preview');
  const form = document.getElementById('detect-form');
  const cameraBtn = document.getElementById('camera-btn');
  const video = document.getElementById('camera-stream');
  const canvas = document.getElementById('camera-canvas');
  let stream = null;

  if (!dropZone || !input) return;

  dropZone.addEventListener('click', () => input.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      showPreview(e.dataTransfer.files[0]);
    }
  });

  input.addEventListener('change', () => {
    if (input.files[0]) showPreview(input.files[0]);
  });

  function showPreview(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      preview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
  }

  cameraBtn?.addEventListener('click', async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      video.srcObject = stream;
      video.classList.remove('hidden');
      const snap = document.createElement('button');
      snap.type = 'button';
      snap.className = 'btn-primary mt-2';
      snap.textContent = 'Capture photo';
      snap.onclick = () => {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);
        canvas.toBlob((blob) => {
          const file = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
          const dt = new DataTransfer();
          dt.items.add(file);
          input.files = dt.files;
          showPreview(file);
          stream.getTracks().forEach((t) => t.stop());
          video.classList.add('hidden');
          snap.remove();
        }, 'image/jpeg', 0.92);
      };
      form.appendChild(snap);
    } catch (err) {
      alert('Camera access denied or unavailable.');
    }
  });
})();
