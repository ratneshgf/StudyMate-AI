(function () {
  // File picker label
  var f = document.querySelector('.drop input'), t = document.getElementById('drop-text');
  if (f) f.addEventListener('change', function () {
    document.getElementById('drop').classList.toggle('has', !!f.files.length);
    t.textContent = f.files.length ? f.files[0].name : t.dataset.d;
  });
  if (t) t.dataset.d = t.textContent;

  // Prevent duplicate requests and show elapsed time, not simulated progress.
  var busyTimer;
  document.querySelectorAll('#gen-form, form[data-busy]').forEach(function (fm) {
    fm.addEventListener('submit', function (event) {
      if (fm.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }
      fm.dataset.submitting = 'true';
      var overlay = document.getElementById('busy');
      if (!overlay) return;
      overlay.hidden = false;
      var steps = overlay.querySelector('ol');
      if (steps) steps.hidden = true;
      var status = overlay.querySelector('.generation-status');
      if (!status) {
        status = document.createElement('p');
        status.className = 'generation-status';
        overlay.querySelector('.steps').append(status);
      }
      var started = Date.now();
      function update() {
        var seconds = Math.floor((Date.now() - started) / 1000);
        status.textContent = 'Preparing notes and questions. Time elapsed: ' + seconds + 's.';
      }
      update();
      clearInterval(busyTimer);
      busyTimer = setInterval(update, 1000);
    });
  });
  window.addEventListener('pageshow', function () {
    clearInterval(busyTimer);
    document.querySelectorAll('[data-submitting]').forEach(function (fm) {
      delete fm.dataset.submitting;
    });
    var overlay = document.getElementById('busy');
    if (overlay) overlay.hidden = true;
  });

  // Copy buttons
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var box = document.getElementById('c-' + b.dataset.copy), txt = '';
      box.querySelectorAll('h3, p, li, summary').forEach(function (n) {
        txt += (n.tagName === 'P' && n.parentNode.tagName === 'DETAILS' ? 'Ans: ' : '') + n.textContent.trim() + '\n';
      });
      navigator.clipboard.writeText(txt.trim()).then(function () {
        b.classList.add('ok'); setTimeout(function () { b.classList.remove('ok'); }, 1400);
      });
    });
  });
})();
