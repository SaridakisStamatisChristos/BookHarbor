(function () {
  'use strict';
  const notice = document.querySelector('#notice');
  function flash(message) {
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = false;
  }
  async function requestJSON(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }
  async function downloadBook(token, holder, button) {
    button.disabled = true;
    holder.textContent = 'Queuing download…';
    try {
      const data = await requestJSON('/api/download', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({token})
      });
      holder.textContent = data.reused ? 'Already ' + data.status + ' (#' + data.job_id + '). See My Library.' : 'Queued #' + data.job_id + ' — check My Library for progress.';
      flash(data.reused ? 'That edition is already in your library or queue.' : 'Book added to download queue. See My Library for status.');
    } catch (err) {
      holder.textContent = err.message;
      button.disabled = false;
    }
  }
  document.querySelectorAll('.download-btn').forEach(button => {
    button.addEventListener('click', () => {
      const holder = button.closest('.bookcard').querySelector('.cardstatus');
      downloadBook(button.dataset.token, holder, button);
    });
  });
  document.querySelectorAll('.inspect-btn').forEach(button => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      const card = button.closest('.bookcard');
      const holder = card.querySelector('.cardstatus');
      holder.textContent = 'Checking open download files…';
      try {
        const data = await requestJSON('/api/formats?token=' + encodeURIComponent(button.dataset.token));
        if (!data.options.length) {
          holder.textContent = data.message;
          button.textContent = 'No open files';
          return;
        }
        data.options.forEach(offer => {
          const link = document.createElement('button');
          link.className = 'small primary download-btn';
          link.textContent = '↓ ' + offer.fmt;
          link.addEventListener('click', () => downloadBook(offer.token, holder, link));
          button.parentElement.insertBefore(link, button);
        });
        button.remove();
        holder.textContent = 'Public files found. Pick a format.';
      } catch(err) {
        holder.textContent = err.message;
        button.disabled = false;
      }
    });
  });
  const batchButton = document.querySelector('#batch-download');
  if (batchButton) batchButton.addEventListener('click', async () => {
    const selected = Array.from(document.querySelectorAll('.batch-choice:checked'));
    if (selected.length < 1 || selected.length > 10) {
      flash('Please select between 1 and 10 books.'); return;
    }
    batchButton.disabled = true;
    batchButton.textContent = 'Checking available files…';
    try {
      const result = await requestJSON('/api/batch', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          tokens: selected.map(box => box.value),
          preference: document.querySelector('#batch-pref').value
        })
      });
      const summary = result.queued.length + ' queued; ' + result.skipped.length + ' skipped. Visit My Library for progress.';
      flash(summary);
      batchButton.textContent = 'Batch queued';
    } catch (err) {
      flash(err.message);
      batchButton.textContent = '↓ Download selected';
    } finally { batchButton.disabled = false; }
  });
  document.querySelectorAll('.retry-btn').forEach(button => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      const feedback = button.closest('.file-actions').querySelector('.jobfeedback');
      feedback.textContent = 'Checking original file…';
      try {
        const result = await requestJSON('/api/retry/' + button.dataset.job, {method: 'POST', headers: {'X-BookHarbor-Action': 'retry'}});
        feedback.textContent = result.reused ? 'Already ' + result.status : 'Retry queued (#' + result.job_id + ')';
        flash(feedback.textContent);
      } catch (err) { feedback.textContent = err.message; }
      finally { button.disabled = false; }
    });
  });
  document.querySelectorAll('.verify-btn').forEach(button => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      const feedback = button.closest('.file-actions').querySelector('.jobfeedback');
      feedback.textContent = 'Checking SHA-256…';
      try {
        const result = await requestJSON('/api/verify/' + button.dataset.job);
        feedback.textContent = result.status === 'verified' ? '✓ File integrity verified' :
          result.status === 'untracked' ? 'Checksum unavailable (v0.1 file)' :
          result.status === 'missing' ? 'File missing from library' : '⚠ Integrity mismatch';
      } catch (err) { feedback.textContent = err.message; }
      finally { button.disabled = false; }
    });
  });
  if (document.querySelector('.status-running, .status-queued')) {
    setTimeout(() => location.reload(), 7000);
  }
})();
