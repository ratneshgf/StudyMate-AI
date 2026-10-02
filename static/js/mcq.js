(() => {
  const start = document.querySelector('#start-mcq');
  const intro = document.querySelector('#quiz-intro');
  const body = document.querySelector('#quiz-body');
  if (!start || !intro || !body) return;

  const questionList = body.querySelector('.quiz-questions');
  const progress = document.querySelector('#quiz-progress');
  const result = document.querySelector('#quiz-result');
  const score = document.querySelector('#quiz-score');
  const retry = document.querySelector('#retry-mcq');
  const newTest = document.querySelector('#new-mcq');
  const errorMessage = document.querySelector('#quiz-error');
  let questions = [...questionList.querySelectorAll('.quiz-question')];
  let version = 0;
  let answered = 0;
  let correct = 0;

  function scrollToQuiz() {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelector('#mcq')?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function resetScore() {
    answered = 0;
    correct = 0;
    progress.textContent = `0 of ${questions.length} answered`;
    result.hidden = true;
    errorMessage.hidden = true;
    errorMessage.textContent = '';
  }

  function makeQuestion(item, index, round) {
    const fieldset = document.createElement('fieldset');
    fieldset.className = 'quiz-question';
    fieldset.dataset.correctIndex = String(item.correct_index);
    fieldset.dataset.correctAnswer = item.correct_answer;
    fieldset.dataset.difficulty = item.difficulty || 'practice';
    fieldset.dataset.explanation = item.explanation || '';

    const legend = document.createElement('legend');
    const number = document.createElement('span');
    number.className = 'quiz-number';
    number.textContent = `Question ${index + 1} of 10`;
    const prompt = document.createElement('span');
    prompt.className = 'quiz-prompt';
    prompt.textContent = item.question;
    legend.append(number, prompt);
    fieldset.append(legend);

    const choices = document.createElement('div');
    choices.className = 'quiz-options';
    item.options.forEach((option, choiceIndex) => {
      const label = document.createElement('label');
      label.className = 'quiz-option';
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `mcq-${round}-${index}`;
      input.value = String(choiceIndex);
      const text = document.createElement('span');
      text.textContent = option;
      label.append(input, text);
      choices.append(label);
    });
    fieldset.append(choices);

    const feedback = document.createElement('p');
    feedback.className = 'quiz-feedback';
    feedback.setAttribute('aria-live', 'polite');
    feedback.hidden = true;
    fieldset.append(feedback);
    return fieldset;
  }

  function makeLevelGroup(level, items, round) {
    const group = document.createElement('section');
    group.className = `quiz-level-card level-${level}`;
    group.dataset.level = level;
    const heading = document.createElement('h3');
    heading.textContent = `${level[0].toUpperCase()}${level.slice(1)} - ${items.length} questions`;
    group.append(heading);
    items.forEach((item, index) => group.append(makeQuestion(item, item.number - 1, round)));
    return group;
  }

  start.addEventListener('click', () => {
    intro.hidden = true;
    body.hidden = false;
    questions[0]?.querySelector('input')?.focus();
  });

  body.addEventListener('change', event => {
    if (!(event.target instanceof HTMLInputElement) || event.target.type !== 'radio') return;
    const question = event.target.closest('.quiz-question');
    if (!question || question.classList.contains('is-answered')) return;

    const choice = Number(event.target.value);
    const answer = Number(question.dataset.correctIndex);
    const isCorrect = choice === answer;
    question.classList.add('is-answered');
    const options = [...question.querySelectorAll('.quiz-option')];
    options[answer]?.classList.add('is-correct');
    if (!isCorrect) options[choice]?.classList.add('is-wrong');
    question.querySelectorAll('input').forEach(input => { input.disabled = true; });

    const feedback = question.querySelector('.quiz-feedback');
    feedback.textContent = isCorrect
      ? `Correct! The answer is ${question.dataset.correctAnswer}.`
      : `Not quite. The correct answer is ${question.dataset.correctAnswer}.`;
    if (question.dataset.explanation) feedback.textContent += `\n${question.dataset.explanation}`;
    feedback.classList.toggle('is-correct', isCorrect);
    feedback.classList.toggle('is-wrong', !isCorrect);
    feedback.hidden = false;

    answered += 1;
    if (isCorrect) correct += 1;
    progress.textContent = `${answered} of ${questions.length} answered`;
    if (answered === questions.length) {
      score.textContent = `You scored ${correct} out of ${questions.length}`;
      result.hidden = false;
      score.focus();
    }
  });

  retry.addEventListener('click', () => {
    resetScore();
    questions.forEach(question => {
      question.classList.remove('is-answered');
      question.querySelectorAll('input').forEach(input => { input.checked = false; input.disabled = false; });
      question.querySelectorAll('.quiz-option').forEach(option => option.classList.remove('is-correct', 'is-wrong'));
      const feedback = question.querySelector('.quiz-feedback');
      feedback.textContent = '';
      feedback.hidden = true;
      feedback.classList.remove('is-correct', 'is-wrong');
    });
    scrollToQuiz();
    questions[0]?.querySelector('input')?.focus();
  });

  newTest?.addEventListener('click', async () => {
    const nextVersion = version + 1;
    newTest.disabled = true;
    newTest.textContent = 'Creating new test...';
    errorMessage.textContent = 'Creating a fresh set of questions. This can take a few minutes.';
    errorMessage.classList.add('is-loading');
    errorMessage.hidden = false;
    try {
      const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
      const response = await fetch(newTest.dataset.url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ version: nextVersion,
          previous_questions: questions.map(question => question.querySelector('.quiz-prompt').textContent) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not load a new test. Please try again.');
      if (!Array.isArray(data.questions) || data.questions.length !== 10 ||
          data.questions.some(question => !Array.isArray(question.options) || question.options.length !== 4)) {
        throw new Error('The new test was incomplete. Please try again.');
      }
      const levels = data.questions.some(item => item.difficulty === 'practice')
        ? ['practice'] : ['easy', 'medium', 'advanced'];
      const groups = levels.map(level => makeLevelGroup(
        level, data.questions.filter(item => item.difficulty === level), nextVersion));
      questionList.replaceChildren(...groups);
      questions = [...questionList.querySelectorAll('.quiz-question')];
      version = nextVersion;
      resetScore();
      scrollToQuiz();
      questions[0]?.querySelector('input')?.focus();
    } catch (error) {
      errorMessage.textContent = error.message;
      errorMessage.classList.remove('is-loading');
      errorMessage.hidden = false;
    } finally {
      newTest.disabled = false;
      newTest.textContent = 'New test';
    }
  });
})();
