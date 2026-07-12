(function () {
  const dropZone = document.getElementById('drop-zone');
  const input = document.getElementById('image-input');
  const preview = document.getElementById('preview');
  const form = document.getElementById('detect-form');
  const cameraBtn = document.getElementById('camera-btn');
  const video = document.getElementById('camera-stream');
  const canvas = document.getElementById('camera-canvas');
  const analyzeBtn = document.getElementById('analyze-btn');
  const status = document.getElementById('upload-status');
  const statusText = document.getElementById('upload-status-text');
  let stream = null;
  let selectedFile = null;
  let submitting = false;

  if (!dropZone || !input || !form) return;

  dropZone.addEventListener('click', () => input.click());
  dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragover');
    if (event.dataTransfer.files.length) {
      selectedFile = event.dataTransfer.files[0];
      showPreview(selectedFile);
    }
  });

  input.addEventListener('change', () => {
    if (input.files[0]) {
      selectedFile = input.files[0];
      showPreview(selectedFile);
    }
  });

  function showPreview(file) {
    const reader = new FileReader();
    reader.onload = (event) => {
      preview.src = event.target.result;
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
          if (!blob) return;
          selectedFile = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
          showPreview(selectedFile);
          stream.getTracks().forEach((track) => track.stop());
          video.classList.add('hidden');
          snap.remove();
        }, 'image/jpeg', 0.85);
      };
      form.appendChild(snap);
    } catch (error) {
      alert('Camera access denied or unavailable. You can still choose a photo from your phone.');
    }
  });

  function setStatus(message, isError = false) {
    statusText.textContent = message;
    status.classList.remove('hidden');
    status.classList.toggle('bg-red-600', isError);
    status.classList.toggle('text-white', isError);
  }

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      const url = URL.createObjectURL(file);
      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('This photo format could not be read. Try a JPG or PNG image.'));
      };
      image.src = url;
    });
  }

  async function compressImage(file) {
    const image = await loadImage(file);
    const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
    const output = document.createElement('canvas');
    output.width = Math.max(1, Math.round(image.naturalWidth * scale));
    output.height = Math.max(1, Math.round(image.naturalHeight * scale));
    output.getContext('2d').drawImage(image, 0, 0, output.width, output.height);

    const blob = await new Promise((resolve) => output.toBlob(resolve, 'image/jpeg', 0.78));
    if (!blob) throw new Error('The photo could not be compressed. Please try another image.');
    return new File([blob], 'leaf-photo.jpg', { type: 'image/jpeg', lastModified: Date.now() });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitting) return;

    const file = selectedFile || input.files[0];
    if (!file) {
      alert('Please choose or capture an image first.');
      return;
    }

    submitting = true;
    analyzeBtn.disabled = true;
    try {
      setStatus('Compressing image…');
      const compressed = await compressImage(file);
      const body = new FormData(form);
      body.set('image', compressed, compressed.name);

      setStatus('Uploading image…');
      const response = await fetch(form.action, {
        method: 'POST',
        body,
        credentials: 'same-origin',
      });
      const html = await response.text();
      if (!response.ok) throw new Error(`Upload failed (${response.status}). Please try again.`);

      setStatus('Loading result…');
      history.replaceState(null, '', response.url);
      document.open();
      document.write(html);
      document.close();
    } catch (error) {
      setStatus(error.message || 'The image could not be uploaded. Please try again.', true);
      analyzeBtn.disabled = false;
      submitting = false;
    }
  });
})();
