(function () {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  const typing = document.getElementById('typing-indicator');
  const sendBtn = document.getElementById('chat-send');
  const clearBtn = document.getElementById('clear-chat');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!form || !input || !messages) return;

  function scrollBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function badgeLabel(sourceType) {
    if (sourceType === 'rag') return 'RAG Answer';
    if (sourceType === 'internet') return 'Internet Result';
    if (sourceType === 'gemini') return 'Gemini';
    if (sourceType === 'fallback') return 'Fallback';
    return 'Local Knowledge';
  }

  function badgeClass(sourceType) {
    if (sourceType === 'rag') {
      return 'border-violet-400/50 text-violet-700 dark:text-violet-300';
    }
    if (sourceType === 'internet') {
      return 'border-sky-400/50 text-sky-700 dark:text-sky-300';
    }
    if (sourceType === 'fallback') {
      return 'border-amber-400/50 text-amber-700 dark:text-amber-300';
    }
    return 'border-emerald-400/50 text-emerald-700 dark:text-emerald-300';
  }

  function emptyState() {
    const empty = document.createElement('p');
    empty.className = 'text-center text-slate-500 text-sm py-8';
    empty.textContent = 'Ask about crops, irrigation, fertilizer, pests, or plant diseases.';
    messages.insertBefore(empty, typing);
  }

  function removeEmptyState() {
    const empty = messages.querySelector('p.text-center');
    if (empty) empty.remove();
  }

  function escapeHtml(value) {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatInlineMarkdown(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_]+)__/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  }

  function renderMarkdown(value) {
    const lines = value.replace(/\r\n?/g, '\n').split('\n');
    const html = [];
    let listType = null;

    function closeList() {
      if (listType) html.push(`</${listType}>`);
      listType = null;
    }

    lines.forEach((line) => {
      const unordered = line.match(/^\s*[-+*]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      const heading = line.match(/^\s*(#{1,3})\s+(.+)$/);
      const nextListType = unordered ? 'ul' : ordered ? 'ol' : null;

      if (nextListType) {
        if (listType !== nextListType) {
          closeList();
          listType = nextListType;
          html.push(`<${listType}>`);
        }
        html.push(`<li>${formatInlineMarkdown((unordered || ordered)[1])}</li>`);
        return;
      }

      closeList();
      if (heading) {
        const level = heading[1].length + 2;
        html.push(`<h${level}>${formatInlineMarkdown(heading[2])}</h${level}>`);
      } else if (line.trim()) {
        html.push(`<p>${formatInlineMarkdown(line)}</p>`);
      }
    });
    closeList();
    return html.join('');
  }

  function formatSavedMessages() {
    messages.querySelectorAll('[data-markdown="true"]').forEach((bubble) => {
      let sources = [];
      try {
        sources = JSON.parse(bubble.dataset.sources || '[]');
      } catch {
        sources = [];
      }
      bubble.innerHTML = renderMarkdown(stripCitationArtifacts(bubble.textContent.trim()));
      appendSources(bubble, sources);
    });
  }

  function appendSources(bubble, sources) {
    const usableSources = Array.isArray(sources)
      ? sources.filter(
          (source) => source && source.name && /^https?:\/\//i.test(source.url || '')
        )
      : [];
    if (!usableSources.length) return;

    const section = document.createElement('div');
    section.className = 'chat-sources';

    const heading = document.createElement('p');
    heading.className = 'chat-sources-title';
    heading.textContent = 'Sources';
    section.appendChild(heading);

    const buttons = document.createElement('div');
    buttons.className = 'chat-source-buttons';
    usableSources.forEach((source) => {
      const words = source.name.trim().split(/\s+/);
      const shortName = words.length > 3 ? `${words.slice(0, 3).join(' ')}…` : source.name;
      const link = document.createElement('a');
      link.className = 'chat-source-button';
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = shortName;
      link.setAttribute('aria-label', `Open source: ${source.name}`);
      link.title = source.name;
      buttons.appendChild(link);
    });
    section.appendChild(buttons);
    bubble.appendChild(section);
  }

  function updateAssistantMeta(view, sourceType, isError) {
    view.badge.className =
      'source-badge text-[11px] px-2 py-0.5 rounded-full border ' + badgeClass(sourceType);
    view.badge.textContent = badgeLabel(sourceType);
    if (isError) {
      view.bubble.className =
        'chat-message-content whitespace-pre-wrap px-4 py-3 rounded-2xl text-sm leading-relaxed ' +
        'glass-card border border-amber-500/40 text-amber-800 dark:text-amber-200';
    }
  }

  function createStreamingRenderer(bubble) {
    const queue = [];
    const waiters = [];
    let renderedText = '';
    let running = false;
    let inputComplete = false;
    const startBufferSize = 60;
    const minimumBufferSize = 12;

    function resolveWaiters() {
      if (running || queue.length) return;
      while (waiters.length) waiters.shift()();
    }

    async function pump() {
      if (running) return;
      if (!inputComplete && queue.length < startBufferSize) return;
      running = true;
      while (queue.length) {
        if (!inputComplete && queue.length <= minimumBufferSize) break;
        renderedText += queue.shift();
        bubble.innerHTML = renderMarkdown(stripCitationArtifacts(renderedText));
        scrollBottom();
        await new Promise((resolve) => setTimeout(resolve, 30));
      }
      running = false;
      if (inputComplete && queue.length) {
        pump();
        return;
      }
      resolveWaiters();
    }

    return {
      enqueue(text) {
        const tokens = (text || '').match(/\S+\s*|\s+/g) || [];
        queue.push(...tokens);
        pump();
      },
      text() {
        return renderedText + queue.join('');
      },
      complete() {
        inputComplete = true;
        pump();
        if (!running && !queue.length) return Promise.resolve();
        return new Promise((resolve) => waiters.push(resolve));
      },
    };
  }

  function stripCitationArtifacts(text) {
    return (text || '')
      .replace(/\s*\[(?:\s*\d+(?:\s*,\s*\d+)*\s*(?:,\s*supplemental search context\s*)?|\s*supplemental search context\s*)\]/gi, '')
      .replace(/\s*\[(?:\s*[\d,]+\s*|\s*(?:supplemental search context)?\s*)$/i, '');
  }

  function append(role, text, options = {}) {
    removeEmptyState();
    const sourceType = options.sourceType || 'local';
    const wrap = document.createElement('div');
    wrap.className = 'chat-row group flex gap-2 ' + (role === 'user' ? 'justify-end' : '');
    if (options.id) wrap.dataset.messageId = options.id;

    const column = document.createElement('div');
    column.className = 'max-w-[85%]';

    const meta = document.createElement('div');
    meta.className = 'flex items-center gap-2 mb-1 ' + (role === 'user' ? 'justify-end' : '');

    let badge = null;
    if (role !== 'user') {
      badge = document.createElement('span');
      badge.className = 'source-badge text-[11px] px-2 py-0.5 rounded-full border ' + badgeClass(sourceType);
      badge.textContent = badgeLabel(sourceType);
      meta.appendChild(badge);
    }

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'delete-message opacity-70 hover:opacity-100 text-slate-400 hover:text-red-500';
    del.title = 'Delete message';
    if (options.id) del.dataset.messageId = options.id;
    del.innerHTML = '<i data-lucide="trash-2" class="w-3.5 h-3.5"></i>';
    meta.appendChild(del);

    const bubble = document.createElement('div');
    bubble.className =
      'chat-message-content whitespace-pre-wrap px-4 py-3 rounded-2xl text-sm leading-relaxed ' +
      (role === 'user'
        ? 'bg-agro-600 text-white'
        : options.isError
          ? 'glass-card border border-amber-500/40 text-amber-800 dark:text-amber-200'
          : 'glass-card');
    if (role === 'user') {
      bubble.textContent = text;
    } else {
      bubble.dataset.markdown = 'true';
      bubble.innerHTML = renderMarkdown(stripCitationArtifacts(text));
    }

    column.appendChild(meta);
    column.appendChild(bubble);
    if (role !== 'user') appendSources(bubble, options.sources);
    wrap.appendChild(column);
    messages.insertBefore(wrap, typing);
    scrollBottom();
    if (clearBtn) clearBtn.disabled = false;
    if (window.lucide) lucide.createIcons();
    return { wrap, column, bubble, badge, deleteButton: del };
  }

  function setLoading(on) {
    typing.classList.toggle('hidden', !on);
    input.disabled = on;
    sendBtn.disabled = on;
    if (on) scrollBottom();
  }

  async function post(url) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    });
    if (!res.ok) throw new Error('Request failed');
    return res.json();
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const userView = append('user', text);
    input.value = '';
    setLoading(true);
    let assistantView = null;
    let renderer = null;
    try {
      const res = await fetch('/chatbot/message/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok || !res.body) throw new Error('Streaming request failed');

      assistantView = append('assistant', '', { sourceType: 'rag' });
      assistantView.bubble.classList.add('is-streaming');
      renderer = createStreamingRenderer(assistantView.bubble);
      typing.classList.add('hidden');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let doneEvent = null;

      function handleEvent(block) {
        const data = block
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n');
        if (!data) return;
        const event = JSON.parse(data);
        if (event.type === 'chunk') {
          renderer.enqueue(event.text || '');
        } else if (event.type === 'done') {
          doneEvent = event;
        } else if (event.type === 'error') {
          throw new Error(event.message || 'Streaming failed');
        }
      }

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() || '';
        events.forEach(handleEvent);
        if (done) break;
      }
      if (buffer.trim()) handleEvent(buffer);
      if (!doneEvent) throw new Error('Stream ended before completion');
      await renderer.complete();
      assistantView.bubble.classList.remove('is-streaming');

      userView.wrap.dataset.messageId = doneEvent.user_message_id;
      userView.deleteButton.dataset.messageId = doneEvent.user_message_id;
      assistantView.wrap.dataset.messageId = doneEvent.assistant_message_id;
      assistantView.deleteButton.dataset.messageId = doneEvent.assistant_message_id;
      updateAssistantMeta(assistantView, doneEvent.source_type, doneEvent.error);
      appendSources(assistantView.bubble, doneEvent.sources);
      setLoading(false);
    } catch {
      setLoading(false);
      const streamedText = renderer ? renderer.text() : '';
      if (renderer) await renderer.complete();
      const errorText = streamedText
        ? `${streamedText}\n\nThe response was interrupted. Please try again.`
        : 'Connection error. Please check your network and try again.';
      if (assistantView) {
        assistantView.bubble.classList.remove('is-streaming');
        assistantView.bubble.innerHTML = renderMarkdown(stripCitationArtifacts(errorText));
        updateAssistantMeta(assistantView, 'fallback', true);
      } else {
        append('assistant', errorText, { sourceType: 'fallback', isError: true });
      }
    }
  });

  messages.addEventListener('click', async (e) => {
    const btn = e.target.closest('.delete-message');
    if (!btn || !btn.dataset.messageId) return;
    try {
      await post(`/chatbot/delete/${btn.dataset.messageId}`);
      const row = btn.closest('.chat-row');
      if (row) row.remove();
      if (!messages.querySelector('.chat-row')) {
        emptyState();
        if (clearBtn) clearBtn.disabled = true;
      }
    } catch {
      alert('Could not delete this message. Please try again.');
    }
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      if (!confirm('Clear your entire chat history? This cannot be undone.')) return;
      try {
        await post('/chatbot/clear');
        messages.querySelectorAll('.chat-row').forEach((row) => row.remove());
        emptyState();
        clearBtn.disabled = true;
      } catch {
        alert('Could not clear chat history. Please try again.');
      }
    });
  }

  formatSavedMessages();
  scrollBottom();
})();
