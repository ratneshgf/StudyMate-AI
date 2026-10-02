(() => {
  const form = document.querySelector('#gen-form');
  if (!form || !window.fetch || !window.ReadableStream) return;
  const live = document.querySelector('#generation-live');
  const stage = document.querySelector('#generation-stage');
  const elapsed = document.querySelector('#generation-time');
  const sections = document.querySelector('#generation-sections');
  const button = form.querySelector('button');
  let running = false;

  function text(tag, value, parent) {
    const node = document.createElement(tag);
    node.textContent = value;
    parent.append(node);
    return node;
  }

  function render(event) {
    if (event.stage === 'error') throw new Error(event.message);
    if (event.stage === 'redirect') {
      window.location.assign(event.url);
      return true;
    }
    const next = {
      starting: 'Preparing your study material',
      reading: 'Reading your uploaded page',
      notes: 'Notes ready. Preparing related topics...',
      related_topics: 'Related topics ready. Preparing exam questions...',
      exam_questions: 'Exam questions ready. Preparing viva questions...',
      viva_questions: 'Viva questions ready. Preparing MCQ questions...',
      mcq_questions: 'Questions ready. Saving your study material...',
    };
    stage.textContent = next[event.stage] || 'Preparing your study material';
    if (!event.data) return false;
    const card = document.createElement('section');
    card.className = 'generation-section';
    if (event.stage === 'notes') {
      text('h3', event.data.topic, card);
      text('p', event.data.short_notes.definition, card);
      const list = document.createElement('ul');
      event.data.short_notes.key_points.forEach(point => text('li', point, list));
      card.append(list);
    } else if (event.stage === 'related_topics') {
      text('h3', 'Related topics', card);
      event.data.forEach(item => {
        const detail = document.createElement('details');
        text('summary', item.title, detail);
        text('p', item.definition, detail);
        card.append(detail);
      });
    } else if (event.stage === 'mcq_questions') {
      text('h3', 'Your 10-question MCQ test is ready', card);
    } else {
      text('h3', event.stage === 'exam_questions' ? 'Exam questions' : 'Viva questions', card);
      for (const level of ['easy', 'medium', 'advanced']) {
        text('h4', level[0].toUpperCase() + level.slice(1), card);
        event.data.filter(item => item.difficulty === level).forEach(item => {
          const detail = document.createElement('details');
          text('summary', item.question, detail);
          text('p', item.answer, detail);
          card.append(detail);
        });
      }
    }
    sections.append(card);
    return false;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (running) return;
    running = true;
    button.disabled = true;
    live.hidden = false;
    sections.replaceChildren();
    stage.textContent = 'Preparing your study material';
    const started = Date.now();
    const update = () => {
      elapsed.textContent = 'Time elapsed: ' + Math.floor((Date.now() - started) / 1000)
        + 's. You can read completed sections below while the rest is prepared.';
    };
    update();
    const timer = setInterval(update, 1000);
    let reader;
    try {
      const response = await fetch(form.action || window.location.href, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: { Accept: 'application/x-ndjson' },
      });
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/x-ndjson')) {
        let message = 'Could not generate the topic. Please refresh and try again.';
        if (response.headers.get('Content-Type')?.includes('application/json')) {
          message = (await response.json()).error || message;
        }
        throw new Error(message);
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        let newline;
        while ((newline = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, newline);
          buffer = buffer.slice(newline + 1);
          if (line.trim() && render(JSON.parse(line))) return;
        }
        if (done) {
          if (buffer.trim() && render(JSON.parse(buffer))) return;
          throw new Error('The connection ended before all sections were saved. Please try again.');
        }
      }
    } catch (error) {
      stage.textContent = error.message;
    } finally {
      clearInterval(timer);
      if (reader) {
        try { await reader.cancel(); } catch (_) { /* Connection already closed. */ }
      }
      running = false;
      button.disabled = false;
    }
  });
})();
