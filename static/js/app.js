(function () {
  // File picker label
  var f = document.querySelector('.drop input'), t = document.getElementById('drop-text');
  if (f) f.addEventListener('change', function () {
    document.getElementById('drop').classList.toggle('has', !!f.files.length);
    t.textContent = f.files.length ? f.files[0].name : t.dataset.d;
  });
  if (t) t.dataset.d = t.textContent;

  // Progress overlay: steps light up while the server works
  function busy() {
    var o = document.getElementById('busy'); if (!o) return;
    o.hidden = false;
    var s = o.querySelectorAll('li'), i = 0;
    s[0].className = 'now';
    setInterval(function () {
      if (i < s.length - 1) { s[i].className = 'done'; s[++i].className = 'now'; }
    }, 3500);
  }
  document.querySelectorAll('#gen-form, form[data-busy]').forEach(function (fm) {
    fm.addEventListener('submit', busy);
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
