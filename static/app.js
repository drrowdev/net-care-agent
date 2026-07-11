/* Extracted from static/index.html (Phase 4 UI split). */
  let selectedTaskId = null;
  let pollingInterval = null;
  let currentReportText = '';

  // ── UI label localization ───────────────────────────────────────────────
  // Returns input as-is by default (English). To add a locale, replace the
  // body of translateCategory/translateStatus/translateStage/translateType
  // with a lookup table keyed off the language configured in
  // patient.language on the profile.
  function translateCategory(cat) {
    return cat;
  }
  function translateStatus(s) {
    return s;
  }
  function translateStage(s) {
    return s;
  }
  function translateType(t) {
    return t;
  }

  // ── Formatting helpers ──────────────────────────────────────────────────
  function safeClassToken(value, fallback = '') {
    const token = String(value == null ? '' : value);
    return /^[a-z0-9_-]+$/i.test(token) ? token : fallback;
  }

  function safeExternalUrl(value) {
    try {
      const url = new URL(String(value || ''), window.location.origin);
      return /^(https?):$/.test(url.protocol) ? url.href : '';
    } catch (_) {
      return '';
    }
  }

  async function readJsonResponse(response) {
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error(`Invalid JSON response (${response.status})`);
    }
    if (!response.ok) {
      const message = data && typeof data.error === 'string'
        ? data.error
        : `Request failed (${response.status})`;
      throw new Error(message);
    }
    return data;
  }

  async function readJobSubmission(response) {
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error(`Invalid JSON response (${response.status})`);
    }
    if (response.ok || (response.status === 409 && data && data.job_id)) return data;
    throw new Error(data && typeof data.error === 'string'
      ? data.error
      : `Request failed (${response.status})`);
  }

  async function waitForJob(jobId, timeoutMs = 900000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job = await readJsonResponse(response);
      if (job.status === 'done') return job;
      if (job.status === 'error' || job.status === 'interrupted') {
        throw new Error(job.retry_guidance || job.error || 'The job did not complete.');
      }
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
    throw new Error('The job is still running. Check the task log for progress.');
  }

  function relativeTime(iso) {
    if (!iso) return '';
    // Ensure UTC interpretation by appending Z if missing
    const ts = iso.endsWith('Z') ? iso : iso + 'Z';
    const diff = Date.now() - new Date(ts).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60)  return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s/60)}m ago`;
    if (s < 86400) return `${Math.floor(s/3600)}h ago`;
    const d = new Date(ts);
    return `${String(d.getDate()).padStart(2,'0')}-${String(d.getMonth()+1).padStart(2,'0')}-${d.getFullYear()}`;
  }

  function duration(t) {
    const started = t.started_at || t.started;
    const finished = t.finished_at || t.finished;
    if (!started || !finished) return '';
    const d = Math.round((new Date(finished) - new Date(started)) / 1000);
    return d < 60 ? `${d}s` : `${Math.floor(d/60)}m ${d%60}s`;
  }

  function docTypeLabel(t) {
    const map = {
      lab_result: 'Lab result',
      imaging_report: 'Imaging',
      doctor_note: 'Doctor note',
      pathology_report: 'Pathology',
      appointment_summary: 'Appointment',
      research_paper: 'Literature',
      digest: 'Digest',
      other: 'Document',
    };
    return map[t.doc_type] || t.doc_type || '—';
  }

  let allBiomarkers = [];

  function filterBiomarkers() {
    const query = (document.getElementById('bm-search')?.value || '').toLowerCase();
    const filtered = query
      ? allBiomarkers.filter(b =>
          (b.marker||'').toLowerCase().includes(query) ||
          (b.originalMarker||'').toLowerCase().includes(query))
      : allBiomarkers;
    renderBiomarkers(filtered);
  }

  function renderBiomarkers(bms) {
    document.getElementById('bm-list').innerHTML = bms.length
      ? bms.map(b => `
        <div class="bm-row">
          <span class="bm-name">${escHtml(b.marker)}</span>
          <span class="bm-val">${b.value != null ? escHtml(b.value + ' ' + (b.unit||'')) : '—'}</span>
          <span class="bm-flag ${safeClassToken(b.flag, 'normal')}">${escHtml(b.flag || '—')}</span>
          <span class="bm-date">${escHtml(b.date || '')} · ref: ${escHtml(b.reference_range || '—')}</span>
        </div>`).join('')
      : '<div class="empty-state">No biomarkers recorded</div>';
  }

  // ── Status sidebar ──────────────────────────────────────────────────────
  async function loadStatus() {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      renderSidebar(d);
    } catch(e) { console.error('Status error:', e); }
  }

  function renderSidebar(d) {
    const p = d.patient;
    document.getElementById('patient-dx').textContent = p.diagnosis || 'No diagnosis recorded';

    const sstrClass = p.sstr_status === 'positive' ? 'positive' : p.sstr_status === 'negative' ? 'negative' : 'unknown';
    document.getElementById('patient-meta').innerHTML = `
      <div class="meta-row">
        <span class="meta-label">Age / Sex</span>
        <span class="meta-val">${escHtml(p.age || '—')} / ${escHtml(p.sex || '—')}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Ki-67</span>
        <span class="meta-val ${p.ki67_percent == null ? 'unknown' : ''}">${p.ki67_percent != null ? escHtml(p.ki67_percent + '%') : 'unknown'}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">SSTR</span>
        <span class="meta-val ${sstrClass}">${escHtml(p.sstr_status || 'unknown')}${p.sstr_score != null ? ' ('+escHtml(p.sstr_score)+')' : ''}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Trials</span>
        <span class="meta-val clickable" onclick="openModal('trials')">${escHtml((d.stats && d.stats.trials_tracked != null) ? d.stats.trials_tracked : 0)}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Papers</span>
        <span class="meta-val clickable" onclick="openModal('papers')">${escHtml((d.stats && d.stats.literature_watched != null) ? d.stats.literature_watched : 0)}</span>
      </div>
    `;

    // Treatments — categorized
    const txs = d.treatments_classified || [];
    const active    = txs.filter(t => t.category === 'active');
    const planned   = txs.filter(t => t.category === 'planned');
    const completed = txs.filter(t => t.category === 'completed');

    // Sort by date within each category
    const sortByDate = (arr, desc = false) => [...arr].sort((a, b) => {
      if (!a.date && !b.date) return 0;
      if (!a.date) return 1;
      if (!b.date) return -1;
      return desc ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date);
    });

    const sortedActive    = sortByDate(active, false);
    const sortedPlanned   = sortByDate(planned, false);
    const sortedCompleted = sortByDate(completed, true);

    // Fallback to raw list if not yet classified
    const rawTxs = (p.current_treatments || []);

    const txRow = (t) => {
      const idx = txs.indexOf(t);
      const dotColor = t.category === 'active' ? 'var(--accent)'
                     : t.category === 'planned' ? 'var(--amber)' : 'var(--text2)';
      const textStyle = t.category === 'completed' ? ' style="color:var(--text2)"' : '';
      const completeBtn = t.category !== 'completed'
        ? `<button class="tx-action-btn complete" title="Mark as completed" onclick="markTreatment(${idx},'completed')">✓</button>` : '';
      return `
        <div class="tx-item">
          <div class="tx-dot" style="background:${dotColor}"></div>
          <div class="tx-item-text">
            <span${textStyle}>${escHtml(t.label || t.text)}</span>
            ${t.date ? `<span class="tx-date">${escHtml(fmtDate(t.date))}</span>` : ''}
          </div>
          <div class="tx-actions">
            ${completeBtn}
            <button class="tx-action-btn remove" title="Remove" onclick="removeTreatment(${idx})">✕</button>
          </div>
        </div>`;
    };

    if (txs.length === 0 && rawTxs.length === 0) {
      document.getElementById('tx-list').innerHTML =
        '<div class="empty-state">No treatments recorded</div>';
    } else if (txs.length === 0) {
      document.getElementById('tx-list').innerHTML =
        rawTxs.map(t => `<div class="tx-item"><div class="tx-dot"></div>${escHtml(t)}</div>`).join('');
    } else {
      let txHtml = '';

      if (sortedActive.length) {
        txHtml += `<div class="tx-category-head">Active</div>`;
        txHtml += sortedActive.map(t => txRow(t)).join('');
      }

      if (sortedPlanned.length) {
        txHtml += `<div class="tx-category-head">Planned</div>`;
        txHtml += sortedPlanned.map(t => txRow(t)).join('');
      }

      if (sortedCompleted.length) {
        const compId = 'tx-completed-list';
        const isOpen = document.getElementById(compId) ?
          !document.getElementById(compId).classList.contains('hidden') : false;
        txHtml += `
          <div class="tx-category-head tx-category-toggle" onclick="toggleCompleted()">
            Completed
            <span id="tx-completed-caret" style="float:right;font-size:10px">${isOpen ? '▲' : '▼'}</span>
          </div>
          <div id="${compId}" class="${isOpen ? '' : 'hidden'}">
            ${sortedCompleted.map(t => txRow(t)).join('')}
          </div>`;
      }

      document.getElementById('tx-list').innerHTML = txHtml;
    }

    // Biomarkers — normalize names and filter out non-serum markers
    const rawBms = d.recent_biomarkers || [];

    // Name normalization — strip single-letter lab-name prefixes
    // (S-, B-, U-, P-, fS- etc., common in Nordic/European lab systems)
    // and normalize to clean display names
    const bmNormalize = (name) => {
      const stripped = name.replace(/^[fFsSpPbBuU]-/i, '').trim();
      const n = stripped.toLowerCase();
      const orig = name.toLowerCase();

      // Exclude Ki-67/MIB-1 — shown in patient pane
      if (n.includes('ki-67') || n.includes('ki67') || n.includes('mib-1') ||
          n.includes('mib1') || n.includes('proliferation') ||
          orig.includes('ki-67') || orig.includes('mib-1')) return null;
      // Exclude non-serum metrics
      if (n.includes('radiation dose') || n.includes(' gy') || orig.includes(' gy')) return null;

      if (n.includes('chromogranin') || n === 'cga') return 'CgA (Chromogranin A)';
      if (n === 'nse' || n.includes('neuron-specific enolase')) return 'NSE';
      if (n.includes('5-hiaa') || n.includes('5hiaa') || n === '5hiaa') return '5-HIAA';
      if (n.includes('hemoglobin') || n === 'hb' || n === 'hgb') return 'Hemoglobin';
      if (n.includes('thrombocyte') || n.includes('platelet') || n === 'trom' || n === 'plt') return 'Thrombocytes';
      if (n.includes('leukocyte') || n === 'leuk' || n === 'wbc') return 'Leukocytes';
      if (n.includes('neutrophil') || n === 'neut') return 'Neutrophils';
      if (n.includes('creatinine') || n === 'krea' || n === 'crea') return 'Creatinine';
      if (n === 'alt' || n.includes('alanine aminotransferase')) return 'ALT';
      if (n === 'ast' || n.includes('aspartate aminotransferase')) return 'AST';
      if (n.includes('bilirubin') || n === 'bil') return 'Bilirubin';
      if (n.includes('alkaline phosphatase') || n === 'afos' || n === 'alp') return 'ALP';
      if (n.includes('albumin') || n === 'alb') return 'Albumin';
      if (n.includes('calcium') || n === 'ca') return 'Calcium';
      if (n.includes('sodium') || n === 'na') return 'Sodium';
      if (n.includes('potassium') || n === 'k') return 'Potassium';
      if (n.includes('glucose') || n === 'gluk' || n === 'gluc') return 'Glucose';
      if (n.includes('hba1c') || n === 'a1c') return 'HbA1c';
      if (n.includes('tsh')) return 'TSH';
      if (n.includes('serotonin') || n === '5-ht') return 'Serotonin';
      // Return stripped version (without S-/B- prefix) if no match
      return stripped || name;
    };

    // Deduplicate by normalized name + date, filter nulls
    const seen = new Set();
    allBiomarkers = rawBms
      .map(b => {
        const normalized = bmNormalize(b.marker || '');
        if (!normalized) return null;
        return { ...b, marker: normalized, originalMarker: b.marker };
      })
      .filter(b => {
        if (!b) return false;
        const key = `${b.marker}|${b.date}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });

    filterBiomarkers();

    // Alerts
    const alerts = d.alerts || [];
    document.getElementById('alerts-list').innerHTML = alerts.length
      ? alerts.map((a, i) => `
        <div class="alert-item ${safeClassToken(a.priority, 'normal')}">
          <div class="alert-msg">${escHtml(a.message)}</div>
          ${a.action_required ? `<div class="alert-action">→ ${escHtml(a.action_required)}</div>` : ''}
          <div class="alert-meta">
            <span class="alert-priority ${safeClassToken(a.priority, 'normal')}">${escHtml(a.priority || '—')}</span>
            <button class="resolve-btn" onclick="resolveAlert(${i})">Resolve</button>
          </div>
        </div>`).join('')
      : '<div class="empty-state">No active alerts</div>';

    // Mirror to mobile patient panel
    if (isMobile()) mirrorSidebarToMobile();
  }

  async function resolveAlert(idx) {
    await fetch(`/api/alerts/resolve/${idx}`, { method: 'POST' });
    loadStatus();
  }

  // ── Executive Summary ───────────────────────────────────────────────────
  let summaryOpen = true;

  function toggleSummary() {
    summaryOpen = !summaryOpen;
    document.getElementById('summary-body').classList.toggle('hidden', !summaryOpen);
    document.getElementById('summary-caret').classList.toggle('open', summaryOpen);
  }

  function toggleCompleted() {
    const list = document.getElementById('tx-completed-list');
    const caret = document.getElementById('tx-completed-caret');
    if (!list) return;
    list.classList.toggle('hidden');
    if (caret) caret.textContent = list.classList.contains('hidden') ? '▼' : '▲';
  }

  async function markTreatment(idx, category) {
    const r = await fetch('/api/treatments/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_category', idx, category }),
    });
    if (r.ok) await loadStatus();
  }

  async function removeTreatment(idx) {
    const r = await fetch('/api/treatments/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'remove', idx }),
    });
    if (r.ok) await loadStatus();
  }

  async function generateSummary() {
    const btn = document.getElementById('btn-gen-summary');
    if (btn) { btn.disabled = true; btn.textContent = '⊙ Generating…'; }
    try {
      const r = await fetch('/api/summary/generate', { method: 'POST' });
      const submitted = await readJobSubmission(r);
      const completed = await waitForJob(submitted.job_id);
      const d = completed.result || {};
      const summary = d.summary || d;
      renderSummary(summary);
      // Reload full status to refresh treatments sidebar
      await loadStatus();
    } catch(e) {
      console.error('Summary generation failed:', e);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '⊙ Generate summary'; }
    }
  }

  async function dismissAction(idx) {
    // Show inline feedback dialog
    const el = document.getElementById('action-' + idx);
    if (!el) return;

    // Build quick feedback options
    const feedbackHtml = `
      <div id="dismiss-dialog-${idx}" style="margin-top:8px;padding:10px;background:var(--bg2);border-radius:6px;border:0.5px solid var(--border)">
        <div style="font-size:11px;color:var(--text2);margin-bottom:8px;font-weight:500">Why removing? (optional — feeds back into agent)</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
          ${['Doctor advised against','Not applicable now','Already being done','Renal constraints','Done at last appointment'].map(opt =>
            `<button onclick="quickDismiss(${idx},'${opt}','constraint')" style="font-size:11px;padding:3px 8px;border:0.5px solid var(--border2);border-radius:4px;background:var(--bg1);color:var(--text1);cursor:pointer">${opt}</button>`
          ).join('')}
        </div>
        <div style="display:flex;gap:6px">
          <input id="dismiss-text-${idx}" placeholder="Or type a reason…" style="flex:1;font-size:12px;padding:5px 8px;border:0.5px solid var(--border);border-radius:4px;background:var(--bg1);color:var(--text0);outline:none" onkeydown="if(event.key==='Enter')quickDismiss(${idx},document.getElementById('dismiss-text-${idx}').value,'context')">
          <button onclick="quickDismiss(${idx},document.getElementById('dismiss-text-${idx}').value,'context')" style="font-size:11px;padding:5px 10px;border:0.5px solid var(--border2);border-radius:4px;background:var(--bg1);color:var(--text1);cursor:pointer">Remove</button>
          <button onclick="quickDismiss(${idx},'','')" style="font-size:11px;padding:5px 10px;border:0.5px solid var(--border);border-radius:4px;background:var(--bg1);color:var(--text2);cursor:pointer">Remove without note</button>
        </div>
      </div>`;

    // Insert dialog after action item
    const existing = document.getElementById('dismiss-dialog-' + idx);
    if (existing) { existing.remove(); return; }
    el.insertAdjacentHTML('afterend', feedbackHtml);
  }

  async function quickDismiss(idx, feedback, category) {
    const el = document.getElementById('action-' + idx);
    const dlg = document.getElementById('dismiss-dialog-' + idx);
    if (el) el.style.opacity = '0.3';
    if (dlg) dlg.remove();
    try {
      await fetch(`/api/summary/dismiss-action/${idx}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback: feedback.trim(), category }),
      });
      await loadSummary();
      if (feedback.trim()) await loadJudgments();
    } catch(e) { if (el) el.style.opacity = '1'; }
  }

  async function reportMissedSummary() {
    const note = prompt('What was missed or incorrect? This records review feedback only; it will not change clinical facts.');
    if (!note || !note.trim()) return;
    const r = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target: 'summary',
        item_id: 'current',
        assessment: 'missed',
        note: note.trim(),
      }),
    });
    if (r.ok) await loadSummary();
  }

  // ── Clinical Judgments ───────────────────────────────────────────────────
  async function loadJudgments() {
    try {
      const r = await fetch('/api/judgments');
      const js = await r.json();
      renderJudgments(js);
    } catch(e) {}
  }

  function renderJudgments(judgments) {
    const catColor = { constraint:'var(--red)', preference:'var(--accent)', outcome:'var(--blue)', context:'var(--text2)' };
    const catLabel = { constraint:'Constraint', preference:'Preference', outcome:'Outcome', context:'Context' };
    const html = judgments.length ? judgments.map(j => {
      const effective = j.effective_status || j.status || 'active';
      const lifecycle = effective !== 'active'
        ? `<span style="font-size:9px;color:var(--amber);font-weight:600">NEEDS REVIEW${j.review_reason ? ` · ${escHtml(j.review_reason)}` : ''}</span>`
        : '<span style="font-size:9px;color:var(--green)">ACTIVE</span>';
      return `
      <div class="judgment-row" data-judgment-id="${escHtml(j.id)}" style="display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:0.5px solid var(--border)">
        <span style="font-size:10px;font-weight:600;padding:2px 6px;border-radius:3px;background:var(--bg2);color:${catColor[j.category]||'var(--text2)'};flex-shrink:0;margin-top:1px">${escHtml(catLabel[j.category]||j.category||'Context')}</span>
        <div style="flex:1">
          <div class="judgment-text" style="font-size:12px;color:var(--text0);line-height:1.5">${escHtml(j.text)}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:2px">${escHtml(j.date||'')} · ${lifecycle}${j.scope ? ` · ${escHtml(j.scope)}` : ''}</div>
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0">
          <button data-category="${safeClassToken(j.category, 'context')}" data-status="${safeClassToken(j.status, 'active')}" onclick="startEditJudgment(this)" title="Edit" style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:11px;padding:0 2px;opacity:0.4;line-height:1" onmouseenter="this.style.opacity='1';this.style.color='var(--blue)'" onmouseleave="this.style.opacity='0.4';this.style.color='var(--text2)'">✎</button>
          <button onclick="deleteJudgment(this.closest('.judgment-row').dataset.judgmentId)" title="Delete" style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:12px;padding:0 2px;opacity:0.4;line-height:1" onmouseenter="this.style.opacity='1';this.style.color='var(--red)'" onmouseleave="this.style.opacity='0.4';this.style.color='var(--text2)'">✕</button>
        </div>
      </div>`;}).join('')
    : '<div style="font-size:12px;color:var(--text2);padding:12px 0;text-align:center">No clinical notes yet.<br>Add notes after appointments or dismiss actions with feedback.</div>';

    const desktop = document.getElementById('judgments-list');
    if (desktop) desktop.innerHTML = html;
    const mobile = document.getElementById('mob-judgments-list');
    if (mobile) mobile.innerHTML = html;
  }

  function startEditJudgment(button) {
    const row = button.closest('.judgment-row');
    const textEl = row?.querySelector('.judgment-text');
    if (!row || !textEl) return;
    const currentCat = button.dataset.category || 'context';
    const currentStatus = button.dataset.status || 'active';

    // Already editing?
    if (row.querySelector('.judgment-edit-area')) return;

    const currentText = textEl.textContent;
    textEl.style.display = 'none';

    const catOptions = ['constraint','preference','outcome','context']
      .map(c => `<option value="${c}"${c===currentCat?' selected':''}>${c.charAt(0).toUpperCase()+c.slice(1)}</option>`)
      .join('');

    const editHtml = `<div class="judgment-edit-area" style="display:flex;flex-direction:column;gap:6px;margin-top:2px">
      <textarea class="judgment-edit-text" style="font-size:12px;padding:6px 8px;border:0.5px solid var(--border2);border-radius:5px;background:var(--bg1);color:var(--text0);outline:none;font-family:var(--sans);line-height:1.5;resize:vertical;min-height:60px;width:100%">${escHtml(currentText)}</textarea>
      <div style="display:flex;gap:6px;align-items:center">
        <select class="judgment-edit-category" style="font-size:11px;padding:4px 6px;border:0.5px solid var(--border);border-radius:4px;background:var(--bg1);color:var(--text1);cursor:pointer">${catOptions}</select>
        <select class="judgment-edit-status" style="font-size:11px;padding:4px 6px;border:0.5px solid var(--border);border-radius:4px;background:var(--bg1);color:var(--text1);cursor:pointer">
          ${['active','needs_review','superseded'].map(s => `<option value="${s}"${s===currentStatus?' selected':''}>${s.replace('_',' ')}</option>`).join('')}
        </select>
        <button onclick="saveEditJudgment(this)" style="font-size:11px;padding:4px 10px;border:0.5px solid var(--accent);border-radius:4px;background:var(--accent-dim);color:var(--accent);cursor:pointer;font-weight:500">Save</button>
        <button onclick="cancelEditJudgment(this)" style="font-size:11px;padding:4px 10px;border:0.5px solid var(--border);border-radius:4px;background:none;color:var(--text2);cursor:pointer">Cancel</button>
      </div>
    </div>`;

    textEl.insertAdjacentHTML('afterend', editHtml);
    const ta = row.querySelector('.judgment-edit-text');
    if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
  }

  function cancelEditJudgment(button) {
    const row = button.closest('.judgment-row');
    const textEl = row?.querySelector('.judgment-text');
    const editArea = row?.querySelector('.judgment-edit-area');
    if (textEl) textEl.style.display = '';
    if (editArea) editArea.remove();
  }

  async function saveEditJudgment(button) {
    const row = button.closest('.judgment-row');
    const jid = row?.dataset.judgmentId;
    const ta = row?.querySelector('.judgment-edit-text');
    const catEl = row?.querySelector('.judgment-edit-category');
    const statusEl = row?.querySelector('.judgment-edit-status');
    const text = (ta?.value || '').trim();
    if (!jid || !text) return;
    try {
      await fetch(`/api/judgments/${encodeURIComponent(jid)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, category: catEl?.value || 'context', status: statusEl?.value || 'active' }),
      });
      await loadJudgments();
    } catch(e) { console.error('Edit judgment error:', e); }
  }

  async function addMobJudgment() {
    const input = document.getElementById('mob-judgment-input');
    const cat   = document.getElementById('mob-judgment-cat');
    const text  = (input?.value || '').trim();
    if (!text) return;
    input.value = '';
    await fetch('/api/judgments/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, category: cat?.value || 'context' }),
    });
    await loadJudgments();
  }

  async function addJudgment() {
    const input = document.getElementById('judgment-input');
    const cat   = document.getElementById('judgment-cat');
    const text  = (input?.value || '').trim();
    if (!text) return;
    input.value = '';
    await fetch('/api/judgments/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, category: cat?.value || 'context' }),
    });
    await loadJudgments();
  }

  async function deleteJudgment(jid) {
    await fetch(`/api/judgments/${encodeURIComponent(jid)}`, { method: 'DELETE' });
    await loadJudgments();
  }

  // ── Symptoms ─────────────────────────────────────────────────────────────
  async function loadSymptoms() {
    try {
      const r = await fetch('/api/symptoms');
      const list = await r.json();
      renderSymptoms(list);
    } catch (e) { console.error('Symptoms error:', e); }
  }

  function renderSymptoms(symptoms) {
    const wrap = document.getElementById('symptoms-list');
    if (!wrap) return;
    if (!symptoms.length) {
      wrap.innerHTML = '<div class="sym-empty">No symptoms logged.</div>';
      return;
    }
    wrap.innerHTML = symptoms.slice(0, 30).map(s => {
      const sev = s.severity ? `<span class="sym-sev sev-${safeClassToken(s.severity, 'unknown')}">${escHtml(s.severity)}</span>` : '';
      const src = s.source === 'ai' ? '<span class="sym-ai" title="auto-captured by intake">AI</span>' : '';
      const note = s.note ? `<div class="sym-note">${escHtml(s.note)}</div>` : '';
      const related = s.related_treatment ? `<span class="sym-related">↳ ${escHtml(s.related_treatment)}</span>` : '';
      return `
        <div class="sym-row" data-id="${escHtml(s.id)}">
          <div class="sym-head">
            <span class="sym-date">${escHtml(s.date || '')}</span>
            ${sev}
            <span class="sym-name">${escHtml(s.symptom || '')}</span>
            ${src}
            <button class="sym-del" onclick="deleteSymptom(this.closest('.sym-row').dataset.id)" title="Delete">✕</button>
          </div>
          ${note}
          ${related}
        </div>`;
    }).join('');
  }

  async function addSymptom() {
    const name = document.getElementById('sym-name').value.trim();
    if (!name) return;
    const sev = document.getElementById('sym-sev').value;
    const note = document.getElementById('sym-note').value.trim();
    try {
      const r = await fetch('/api/symptoms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symptom: name,
          severity: sev ? parseInt(sev, 10) : null,
          note: note || null,
        }),
      });
      if (!r.ok) {
        const err = await r.json();
        alert(err.error || 'Failed to log symptom');
        return;
      }
      document.getElementById('sym-name').value = '';
      document.getElementById('sym-sev').value = '';
      document.getElementById('sym-note').value = '';
      await loadSymptoms();
    } catch (e) { console.error('Add symptom error:', e); }
  }

  async function deleteSymptom(sid) {
    if (!confirm('Delete this symptom entry?')) return;
    await fetch(`/api/symptoms/${encodeURIComponent(sid)}`, { method: 'DELETE' });
    await loadSymptoms();
  }

  // ── "Since last login" delta indicator ───────────────────────────────────
  async function loadChanges() {
    try {
      const r = await fetch('/api/changes');
      const d = await r.json();
      renderChangesBadge(d);
    } catch (e) { console.error('Changes error:', e); }
  }

  function renderChangesBadge(d) {
    const btn = document.getElementById('btn-changes');
    const count = document.getElementById('changes-count');
    if (!btn || !count) return;
    const total = (d && d.new && d.new.total_new) || 0;
    if (total > 0) {
      count.textContent = total;
      btn.style.display = '';
      btn.title = _changesBreakdown(d.new);
    } else {
      btn.style.display = 'none';
    }
  }

  function _changesBreakdown(n) {
    const parts = [];
    if (n.biomarkers) parts.push(`${n.biomarkers} biomarker${n.biomarkers === 1 ? '' : 's'}`);
    if (n.imaging) parts.push(`${n.imaging} imaging`);
    if (n.documents) parts.push(`${n.documents} document${n.documents === 1 ? '' : 's'}`);
    if (n.trials) parts.push(`${n.trials} trial${n.trials === 1 ? '' : 's'}`);
    if (n.papers) parts.push(`${n.papers} paper${n.papers === 1 ? '' : 's'}`);
    if (n.alerts) parts.push(`${n.alerts} alert${n.alerts === 1 ? '' : 's'}`);
    if (n.symptoms) parts.push(`${n.symptoms} symptom${n.symptoms === 1 ? '' : 's'}`);
    if (n.judgments) parts.push(`${n.judgments} judgment${n.judgments === 1 ? '' : 's'}`);
    if (n.executive_summary) parts.push('exec summary refreshed');
    return parts.length ? `New since last ack: ${parts.join(', ')}` : 'Mark all updates as seen';
  }

  async function acknowledgeChanges() {
    try {
      await fetch('/api/changes/acknowledge', { method: 'POST' });
      await loadChanges();
    } catch (e) { console.error('Acknowledge error:', e); }
  }

  async function loadSummary() {
    try {
      const r = await fetch('/api/summary');
      const d = await r.json();
      renderSummary(d);
    } catch(e) { console.error('Summary error:', e); }
  }

  function summaryIsStale(d) {
    if (typeof d.stale === 'boolean') return d.stale;
    if (d.profile_revision != null && d.summary_revision != null) {
      return String(d.profile_revision) !== String(d.summary_revision);
    }
    const summaryDate = d.generated_at || '';
    const latestDoc = (d.recent_documents || [])[0];
    const latestDocDate = latestDoc ? (latestDoc.added_at || latestDoc.date || '') : '';
    return Boolean(summaryDate && latestDocDate && latestDocDate > summaryDate);
  }

  function renderSummary(d) {
    const body = document.getElementById('summary-body');
    const empty = document.getElementById('summary-empty');
    const inline = document.getElementById('summary-status-inline');
    const updated = document.getElementById('summary-updated');

    if (!d || d.status === 'not_generated') {
      empty.style.display = 'block';
      inline.innerHTML = '';
      updated.textContent = '';
      return;
    }

    empty.style.display = 'none';

    // Status pill in header
    const statusLabels = {
      stable: 'STABLE', responding: 'RESPONDING',
      progressing: 'PROGRESSING', insufficient_data: 'DATA PENDING'
    };
    inline.innerHTML = `<span class="s-pill status-${safeClassToken(d.overall_status, 'insufficient_data')}">${escHtml(statusLabels[d.overall_status] || d.overall_status || 'DATA PENDING')}</span>`;

    // Updated timestamp
    // Revision fields are authoritative; dates support profiles created before revisions.
    const isStale = summaryIsStale(d);
    updated.innerHTML = d.generated_at
      ? `Updated ${escHtml(d.generated_at_timestamp || d.generated_at)} · rev ${escHtml(d.summary_revision ?? '—')}/${escHtml(d.profile_revision ?? '—')}${isStale ? ' <span style="color:var(--amber);font-size:10px">· new data available</span>' : ''}`
      : '';

    let html = '';

    // Pills row
    html += `<div class="summary-pills">`;
    if (d.status_confidence) {
      html += `<span class="s-pill" title="${escHtml(d.status_rationale || '')}">CONFIDENCE: ${escHtml(d.status_confidence.toUpperCase())}</span>`;
    }
    const prrtLabels = {
      eligible: 'PRRT: ELIGIBLE', likely_eligible: 'PRRT: LIKELY ELIGIBLE',
      pending_dotatate: 'PRRT: NEEDS DOTATATE', not_eligible: 'PRRT: NOT ELIGIBLE', unknown: 'PRRT: UNKNOWN'
    };
    html += `<span class="s-pill prrt-${safeClassToken(d.prrt_status, 'unknown')}" title="${escHtml(d.prrt_rationale||'')}">${escHtml(prrtLabels[d.prrt_status] || 'PRRT: UNKNOWN')}</span>`;
    if (d.cga_trend) {
      const cgaLabels = { rising: '↑ CgA RISING', stable: '→ CgA STABLE', falling: '↓ CgA FALLING', insufficient_data: 'CgA: NO DATA' };
      html += `<span class="s-pill cga-${safeClassToken(d.cga_trend, 'insufficient_data')}" title="${escHtml(d.cga_trend_detail||'')}">${escHtml(cgaLabels[d.cga_trend] || 'CgA: NO DATA')}</span>`;
      if (d.cga_trend_detail) {
        html += `<span style="font-family:var(--mono);font-size:10px;color:var(--text2)">${escHtml(d.cga_trend_detail)}</span>`;
      }
    }
    html += `</div>`;
    if (d.status_rationale) {
      html += `<div style="font-size:11px;color:var(--text2);margin:2px 0 10px">${escHtml(d.status_rationale)}</div>`;
    }

    // Key concern
    if (d.key_concern) {
      html += `<div class="summary-concern">
        <div class="summary-concern-label">Key concern</div>
        ${escHtml(d.key_concern)}
      </div>`;
    }

    // Narrative
    if (d.summary) {
      html += `<div class="summary-narrative">${escHtml(d.summary)}</div>`;
    }

    if ((d.evidence_links || []).length) {
      html += `<div class="summary-section"><div class="summary-section-label">Evidence</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${d.evidence_links.map(link => {
          const url = link.evidence_url || link.source_url;
          return `<a href="${escHtml(url)}" target="_blank" rel="noopener" class="btn-digest" style="text-decoration:none;font-size:10px">${escHtml(link.label)} · ${escHtml(link.evidence_status)}</a>`;
        }).join('')}</div></div>`;
    }

    html += `<div style="margin:12px 0 2px"><button class="btn-digest" style="border-color:var(--amber);color:var(--amber)" onclick="reportMissedSummary()">⚑ Report something missed or incorrect</button>${d.feedback_pending ? ` <span style="font-size:10px;color:var(--amber)">${escHtml(d.feedback_pending)} review item(s) recorded</span>` : ''}</div>`;

    // Next actions
    if (d.next_actions && d.next_actions.length) {
      html += `<div class="summary-section">
        <div class="summary-section-label">Recommended actions</div>`;
      d.next_actions.forEach((a, idx) => {
        const provBadge = a.provisional
          ? `<span style="font-family:var(--mono);font-size:9px;color:var(--text2);border:0.5px solid var(--border);padding:1px 4px;border-radius:2px;margin-left:4px">TBD</span>`
          : '';
        html += `<div class="action-item" id="action-${idx}">
          <span class="action-priority ${safeClassToken(a.priority, 'medium')}">${escHtml(a.priority || 'medium')}</span>
          <div class="action-text">
            <div class="action-main">${escHtml(a.action)}${provBadge}</div>
            ${a.rationale ? `<div class="action-sub">${escHtml(a.rationale)}</div>` : ''}
          </div>
          <div class="action-timeframe">${escHtml(a.timeframe||'')}</div>
          <button onclick="dismissAction(${idx})" title="Dismiss" style="background:none;border:none;color:var(--text2);font-size:13px;cursor:pointer;padding:0 0 0 8px;flex-shrink:0;line-height:1;opacity:0.25;transition:opacity .15s,color .15s" onmouseenter="this.style.opacity='1';this.style.color='var(--red)'" onmouseleave="this.style.opacity='0.25';this.style.color='var(--text2)'" class="action-dismiss-btn">✕</button>
        </div>`;
      });
      html += `</div>`;
    }


    // Timeline — interactive graph with hover tooltips
    if (d.timeline && d.timeline.length) {
      const tid = 'tl_' + Math.random().toString(36).slice(2,8);
      const items = d.timeline;
      html += `<div class="summary-section">
        <div class="summary-section-label">Timeline</div>
        <div id="${tid}" style="padding:4px 0 8px;position:relative"></div>
      </div>`;

      setTimeout(() => {
        const el = document.getElementById(tid);
        if (!el) return;

        const W = Math.max(el.offsetWidth || 680, 400);
        const ROW_H = 54;
        const HEADER_H = 32;   // month labels row
        const AXIS_Y = HEADER_H + 8;  // axis sits below header
        const H = AXIS_Y + ROW_H * items.length + 20;
        const PAD_L = 16, PAD_R = 16;
        const trackW = W - PAD_L - PAD_R;

        const typeColor = {
          scan:'#0f6e56', appointment:'#185fa5', treatment:'#854f0b',
          test:'#5a5650', milestone:'#1a6e40', trial:'#6b48c8', deadline:'#a32d2d'
        };
        const typeBg = {
          scan:'#e0f5ef', appointment:'#deeaf7', treatment:'#fdf3e3',
          test:'#f0ede8', milestone:'#e8f5ee', trial:'#ede8f8', deadline:'#fcebeb'
        };

        const parseDate = s => {
          if (!s) return null;
          const m = s.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
          if (m) return new Date(+m[1], +m[2]-1, m[3]?+m[3]:1);
          return null;
        };

        const dates = items.map(t => parseDate(t.date)).filter(Boolean);
        const today = new Date();
        const allDates = [...dates, today];
        let minD = new Date(Math.min(...allDates));
        let maxD = new Date(Math.max(...allDates));
        minD = new Date(minD.getFullYear(), minD.getMonth() - 1, 1);
        maxD = new Date(maxD.getFullYear(), maxD.getMonth() + 2, 1);
        const range = maxD - minD || 1;
        const toX = d => PAD_L + (d - minD) / range * trackW;
        const todayX = toX(today);

        // ── Pre-compute event x positions and which event-date labels will show ──
        // (Needed up front so month labels can avoid colliding with them.)
        const eventXs = items.map(t => {
          const d3 = parseDate(t.date);
          return d3 ? toX(d3) : PAD_L + trackW * 0.5;
        });
        // Suppress event date label if another event is within 45px
        const dateLabelVisible = eventXs.map((cx, i) =>
          eventXs.every((ox, j) => j === i || Math.abs(ox - cx) > 45)
        );
        // Reserved x-zones in the header row that month labels must avoid:
        // the today marker and every visible event-date label.
        const reservedXs = [todayX, ...eventXs.filter((_, i) => dateLabelVisible[i])];
        const nearReserved = (x, gap = 30) =>
          reservedXs.some(rx => Math.abs(rx - x) < gap);

        // ── Month labels in header row — skip if too close to neighbour or reserved zone ──
        let grid = '';
        let lastMonthLabelX = -999;
        let d2 = new Date(minD.getFullYear(), minD.getMonth(), 1);
        while (d2 <= maxD) {
          const x = toX(d2);
          if (x >= PAD_L && x <= W - PAD_R) {
            const lbl = d2.toLocaleDateString('en', {month:'short', year:'2-digit'});
            const approxW = lbl.length * 6;
            if (x - lastMonthLabelX > approxW + 8 && !nearReserved(x, approxW / 2 + 18)) {
              grid += `<text x="${x.toFixed(1)}" y="${(HEADER_H - 4).toFixed(1)}" font-size="10" fill="#9a9288" text-anchor="middle" font-family="sans-serif">${lbl}</text>`;
              lastMonthLabelX = x;
            }
            // Grid line runs full height
            grid += `<line x1="${x.toFixed(1)}" y1="${AXIS_Y}" x2="${x.toFixed(1)}" y2="${H}" stroke="#e8e4dc" stroke-width="0.5"/>`;
          }
          d2 = new Date(d2.getFullYear(), d2.getMonth() + 1, 1);
        }

        // Axis line
        grid += `<line x1="${PAD_L}" y1="${AXIS_Y}" x2="${W-PAD_R}" y2="${AXIS_Y}" stroke="#cdc8c0" stroke-width="1"/>`;

        // Today line + label (in header row, clear of event dates)
        grid += `<line x1="${todayX.toFixed(1)}" y1="${AXIS_Y}" x2="${todayX.toFixed(1)}" y2="${H}" stroke="#a32d2d" stroke-width="1.5" stroke-dasharray="3,2" opacity="0.6"/>
        <text x="${todayX.toFixed(1)}" y="${(HEADER_H - 4).toFixed(1)}" font-size="9" fill="#a32d2d" text-anchor="middle" font-family="sans-serif" font-weight="700">today</text>`;

        // ── Event nodes ──
        let nodes = '';
        items.forEach((t, i) => {
          const d3 = parseDate(t.date);
          const cx = eventXs[i];
          const cy = AXIS_Y + 14 + i * ROW_H;
          const color = typeColor[t.type] || '#5a5650';
          const bg = typeBg[t.type] || '#f0ede8';
          const isPast = d3 && d3 < today;
          const isCurrent = d3 && Math.abs(d3 - today) < 1000*60*60*24*25;
          const prov = t.provisional;
          const r = isCurrent ? 8 : 6;

          // Vertical connector from axis to dot
          nodes += `<line x1="${cx.toFixed(1)}" y1="${AXIS_Y}" x2="${cx.toFixed(1)}" y2="${(cy-r).toFixed(1)}" stroke="${color}" stroke-width="1" opacity="${isPast?'0.25':'0.5'}" stroke-dasharray="${prov?'3,2':''}"/>`;

          // Date label — show below axis on a tick, suppressed if crowded
          const dateStr = d3 ? fmtDate(t.date) : '?';
          if (dateLabelVisible[i]) {
            nodes += `<line x1="${cx.toFixed(1)}" y1="${AXIS_Y}" x2="${cx.toFixed(1)}" y2="${(AXIS_Y+4).toFixed(1)}" stroke="#cdc8c0" stroke-width="1"/>`;
            nodes += `<text x="${cx.toFixed(1)}" y="${(AXIS_Y-3).toFixed(1)}" font-size="9" fill="${isPast?'#b0a898':color}" text-anchor="middle" font-family="sans-serif" font-weight="600">${escHtml(dateStr)}</text>`;
          }

          // Main dot
          const safeEvent = escHtml(t.event || '');
          const safeDate  = escHtml(dateStr);
          const tid2 = tid + '_' + i;

          nodes += `<g class="tl-node" id="${tid2}"
            data-event="${safeEvent}" data-date="${safeDate}"
            data-type="${escHtml(t.type||'')}"
            data-prov="${prov?'true':'false'}"
            data-color="${color}" data-bg="${bg}"
            style="cursor:pointer">`;

          nodes += `<circle cx="${cx.toFixed(1)}" cy="${cy}" r="14" fill="transparent"/>`;
          nodes += `<circle cx="${cx.toFixed(1)}" cy="${cy}" r="${r}" fill="${bg}" stroke="${color}" stroke-width="${isCurrent?2.5:1.5}" opacity="${isPast?'0.55':'1'}"/>`;
          if (isPast) nodes += `<circle cx="${cx.toFixed(1)}" cy="${cy}" r="2.5" fill="${color}" opacity="0.55"/>`;
          if (isCurrent) nodes += `<circle cx="${cx.toFixed(1)}" cy="${cy}" r="${r+4}" fill="none" stroke="${color}" stroke-width="1" opacity="0.3"/>`;

          // Short label — offset right so it doesn't sit under the dot
          const short = t.event && t.event.length > 20 ? t.event.slice(0,19)+'…' : (t.event||'');
          const provMark = prov ? ' ~' : '';
          // Alternate label side left/right based on proximity to neighbours
          const nextX = eventXs[i+1];
          const labelAnchor = (nextX && Math.abs(nextX - cx) < 80) ? 'start' : 'middle';
          const labelX = labelAnchor === 'start' ? cx + r + 6 : cx;
          nodes += `<text x="${labelX.toFixed(1)}" y="${(cy + r + 13).toFixed(1)}" font-size="10" fill="${isPast?'#9a9288':'#1e1c18'}" text-anchor="${labelAnchor}" font-family="sans-serif" font-weight="${isCurrent?'600':'400'}">${escHtml(short)}${provMark}</text>`;

          nodes += `</g>`;
        });

        // Tooltip element (positioned via JS)
        const tooltipId = tid + '_tt';
        el.innerHTML = `
          <svg id="${tid}_svg" width="${W}" height="${H}" style="display:block;overflow:visible">
            ${grid}
            ${nodes}
          </svg>`;

        // Append tooltip to body so it never causes container scrollbars
        let tt = document.getElementById(tooltipId);
        if (!tt) {
          tt = document.createElement('div');
          tt.id = tooltipId;
          tt.style.cssText = 'display:none;position:fixed;background:#fff;border:0.5px solid #cdc8c0;border-radius:8px;padding:10px 14px;box-shadow:0 4px 16px rgba(0,0,0,0.12);max-width:260px;pointer-events:none;z-index:9999;font-family:sans-serif';
          document.body.appendChild(tt);
        }

        // Attach hover events
        const svgEl = document.getElementById(tid + '_svg');
        items.forEach((t, i) => {
          const nodeEl = document.getElementById(tid + '_' + i);
          if (!nodeEl) return;
          const color = nodeEl.dataset.color;
          const bg = nodeEl.dataset.bg;

          nodeEl.addEventListener('mouseenter', (e) => {
            const circles = nodeEl.querySelectorAll('circle');
            circles.forEach(c => { if (parseFloat(c.getAttribute('r')) <= 8) c.setAttribute('r', (parseFloat(c.getAttribute('r'))+2).toString()); });

            const typeLabel = translateType(nodeEl.dataset.type);
            const provText  = nodeEl.dataset.prov === 'true' ? '<div style="font-size:11px;color:#854f0b;margin-top:4px;font-style:italic">⚠ Provisional — not yet confirmed</div>' : '';

            tt.innerHTML = `
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                <span style="background:${bg};color:${color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px;border:0.5px solid ${color}">${escHtml(typeLabel)}</span>
                <span style="font-size:12px;font-weight:600;color:#1e1c18">${escHtml(nodeEl.dataset.date)}</span>
              </div>
              <div style="font-size:13px;color:#1e1c18;line-height:1.5;font-weight:500">${escHtml(nodeEl.dataset.event)}</div>
              ${provText}`;
            tt.style.display = 'block';

            // Position tooltip using viewport coords (fixed positioning)
            const nodeRect = nodeEl.getBoundingClientRect();
            let left = nodeRect.right + 8;
            let top  = nodeRect.top - 10;
            // Keep within viewport
            if (left + 270 > window.innerWidth) left = nodeRect.left - 278;
            if (top + 120 > window.innerHeight) top = window.innerHeight - 130;
            if (top < 8) top = 8;
            tt.style.left = left + 'px';
            tt.style.top  = top + 'px';
          });

          nodeEl.addEventListener('mouseleave', () => {
            const circles = nodeEl.querySelectorAll('circle');
            circles.forEach(c => { if (parseFloat(c.getAttribute('r')) <= 10) c.setAttribute('r', (parseFloat(c.getAttribute('r'))-2).toString()); });
            tt.style.display = 'none';
          });
        });

      }, 60);
    }

    // Best trial
    if (d.best_trial && d.best_trial.nct_id) {
      html += `<div class="summary-section">
        <div class="summary-section-label">Best matched trial</div>
        <div class="trial-chip">
          <a class="trial-chip-id" href="https://clinicaltrials.gov/study/${encodeURIComponent(d.best_trial.nct_id)}" target="_blank" rel="noopener noreferrer">${escHtml(d.best_trial.nct_id)}</a>
          <span class="trial-chip-why">${escHtml(d.best_trial.why_relevant||d.best_trial.title||'')}</span>
        </div>
      </div>`;
    }

    body.innerHTML = html;
  }

  // ── Tutkimukset / Artikkelit Modal ───────────────────────────────────────────────
  async function removeItem(type, id, button) {
    const endpoint = type === 'trials' ? `/api/trials/${encodeURIComponent(id)}` : `/api/papers/${encodeURIComponent(id)}`;
    const r = await fetch(endpoint, { method: 'DELETE' });
    if (r.ok) {
      const el = button?.closest('.modal-item');
      if (el) el.remove();
      // Refresh sidebar counts
      await loadStatus();
    }
  }

  async function openModal(type) {
    document.getElementById('modal-overlay').classList.add('open');
    document.getElementById('modal-title').textContent =
      type === 'trials' ? 'Clinical Trials' : 'Research Papers';
    document.getElementById('modal-body').innerHTML =
      '<div class="modal-empty">Loading…</div>';

    try {
      const r = await fetch(`/api/${type}`);
      const items = await r.json();
      renderModal(type, items);
    } catch(e) {
      document.getElementById('modal-body').innerHTML =
        '<div class="modal-empty">Failed to load.</div>';
    }
  }

  function closeModal(e) {
    if (!e || e.target === document.getElementById('modal-overlay') || !e.target) {
      document.getElementById('modal-overlay').classList.remove('open');
    }
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });

  function renderModal(type, items) {
    const body = document.getElementById('modal-body');
    if (!items.length) {
      body.innerHTML = `<div class="modal-empty">No ${type} found yet.<br>Run a digest to search for relevant ${type}.</div>`;
      return;
    }

    if (type === 'trials') {
      body.innerHTML = items.map(t => {
        const url = safeExternalUrl(t.url);
        return `
        <div class="modal-item">
          <div class="modal-item-title">${escHtml(t.title || 'Untitled')}</div>
          <div class="modal-item-meta">
            <span class="modal-item-id">${escHtml(t.nct_id || '')}</span>
            <span class="modal-tag ${(t.status||'').toLowerCase() === 'recruiting' ? 'recruiting' : ''}">${escHtml(t.status || '—')}</span>
            ${t.phase ? `<span class="modal-tag">${escHtml(t.phase)}</span>` : ''}
            ${(t.countries||[]).length ? `<span class="modal-item-sub">${escHtml(t.countries.join(', '))}</span>` : ''}
            ${url ? `<a class="modal-item-link" href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">View ↗</a>` : ''}
            <button class="modal-close" data-item-id="${escHtml(t.nct_id)}" style="margin-left:auto" title="Remove" onclick="removeItem('trials',this.dataset.itemId,this)">✕</button>
          </div>
          ${t.brief_summary ? `<div class="modal-item-sub" style="margin-top:5px;color:var(--text2)">${escHtml(t.brief_summary.slice(0,200))}${t.brief_summary.length>200?'…':''}</div>` : ''}
          <div style="font-family:var(--mono);font-size:10px;color:var(--text2);margin-top:4px">Added ${escHtml(fmtDate(t.date_added||''))}</div>
        </div>`;
      }).join('');
    } else {
      body.innerHTML = items.map(p => {
        const url = safeExternalUrl(p.url);
        return `
        <div class="modal-item">
          <div class="modal-item-title">${escHtml(p.title || 'Untitled')}</div>
          <div class="modal-item-meta">
            <span class="modal-item-id">PMID ${escHtml(p.pmid || '')}</span>
            <span class="modal-item-sub">${escHtml(p.journal || '')}${p.date ? ' · ' + escHtml(p.date) : ''}</span>
            ${url ? `<a class="modal-item-link" href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">PubMed ↗</a>` : ''}
            <button class="modal-close" data-item-id="${escHtml(p.pmid)}" style="margin-left:auto" title="Remove" onclick="removeItem('papers',this.dataset.itemId,this)">✕</button>
          </div>
          ${p.authors ? `<div class="modal-item-sub" style="margin-top:3px">${escHtml(p.authors)}</div>` : ''}
          <div style="font-family:var(--mono);font-size:10px;color:var(--text2);margin-top:4px">Query: ${escHtml(p.query||'')} · Added ${escHtml(fmtDate(p.date_added||''))}</div>
        </div>`;
      }).join('');
    }
  }

  // ── Task log ────────────────────────────────────────────────────────────
  async function loadTasks() {
    try {
      const r = await fetch('/api/jobs');
      const tasks = await r.json();
      renderTasks(tasks);
      updateHeaderStatus(tasks);
    } catch(e) {}
  }

  function renderTasks(tasks) {
    document.getElementById('log-count').textContent = `${tasks.length} task${tasks.length !== 1 ? 's' : ''}`;

    if (!tasks.length) {
      document.getElementById('task-list').innerHTML =
        '<div class="empty-state">No tasks yet.<br>Feed a document to begin.</div>';
      return;
    }

    document.getElementById('task-list').innerHTML = tasks.map(t => `
      <div class="task-item status-${safeClassToken(t.status, 'unknown')} ${selectedTaskId === t.id ? 'selected' : ''}"
           data-task-id="${escHtml(t.id)}" onclick="selectTask(this.dataset.taskId)">
        <div class="task-header">
          <span class="task-type ${t.type === 'digest' ? 'digest' : (t.type === 'deep-sweep' ? 'deep-sweep' : '')}">${escHtml(t.type || 'task')}</span>
          ${t.doc_type ? `<span class="task-doctype">${escHtml(docTypeLabel(t))}</span>` : ''}
          <span class="task-time">${escHtml(relativeTime(t.created_at))}</span>
        </div>
        <div class="task-preview">${escHtml((t.summary || t.input_preview || '').slice(0, 100))}</div>
        <div class="task-status-row">
          <span class="status-badge ${safeClassToken(t.status, 'unknown')}">${escHtml(translateStatus(t.status))}</span>
          ${t.status === 'done' && duration(t) ? `<span class="task-duration">${escHtml(duration(t))}</span>` : ''}
          ${t.status === 'error' ? `<span class="task-duration" style="color:var(--red)">${escHtml((t.error||'').slice(0,60))}</span>` : ''}
          ${t.status === 'interrupted' ? `<span class="task-duration" style="color:var(--amber)">${escHtml((t.retry_guidance||t.error||'Interrupted').slice(0,60))}</span>` : ''}
        </div>
      </div>`).join('');

    // Mirror to mobile
    if (isMobile()) {
      const mobList = document.getElementById('mob-task-list');
      if (mobList) mobList.innerHTML = document.getElementById('task-list').innerHTML;
      const mobCount = document.getElementById('mob-log-count');
      if (mobCount) mobCount.textContent = `${tasks.length} task${tasks.length !== 1 ? 's' : ''}`;
    }
  }

  function updateHeaderStatus(tasks) {
    const running = tasks.filter(t => t.status === 'running');
    const bar = document.getElementById('running-bar');
    const dot = document.getElementById('pulse-dot');
    const lbl = document.getElementById('header-status');
    if (running.length) {
      bar.classList.add('visible');
      dot.style.background = 'var(--amber)';
      lbl.textContent = `${running.length} käynnissä…`;
    } else {
      bar.classList.remove('visible');
      dot.style.background = 'var(--accent)';
      lbl.textContent = 'Idle';
    }
  }

  function closePanel() {
    document.getElementById('report-panel').classList.add('collapsed');
    selectedTaskId = null;
    // Re-render task list to clear selection highlight
    fetch('/api/jobs').then(r => r.json()).then(tasks => renderTasks(tasks));
  }

  async function selectTask(id) {
    selectedTaskId = id;
    // Open panel
    document.getElementById('report-panel').classList.remove('collapsed');
    // Re-render task list to update selection
    const r = await fetch('/api/jobs');
    const tasks = await r.json();
    renderTasks(tasks);

    let task = tasks.find(t => t.id === id);
    if (!task) return;
    if (task.status === 'done' || task.status === 'error' || task.status === 'interrupted') {
      try {
        task = await readJsonResponse(await fetch(`/api/jobs/${encodeURIComponent(id)}`));
      } catch (_) {}
    }

    const panel = document.getElementById('panel-body');
    const copyBtn = document.getElementById('copy-btn');

    if (task.status === 'running' || task.status === 'queued') {
      panel.innerHTML = `
        <div class="report-empty">
          <div class="report-empty-icon" style="animation:pulse 1s infinite">⊙</div>
          <div class="report-empty-text">
            ${task.status === 'queued' ? 'Queued — starting soon…' : 'Analysing…'}
            <br><br>
            <span style="color:var(--text2);font-size:10px">Stage: ${escHtml(task.stage || 'processing')}</span>
            <br>
            <span style="color:var(--text2);font-size:10px">This usually takes 30–90 seconds.</span>
          </div>
        </div>`;
      copyBtn.classList.remove('visible');
      currentReportText = '';
      return;
    }

    if (task.status === 'error') {
      panel.innerHTML = `<div class="report-text" style="color:var(--red)">Error:\n\n${escHtml(task.error || 'Unknown error')}</div>`;
      copyBtn.classList.remove('visible');
      currentReportText = '';
      return;
    }

    if (task.status === 'interrupted') {
      panel.innerHTML = `<div class="report-text" style="color:var(--amber)">Interrupted:\n\n${escHtml(task.retry_guidance || task.error || 'Re-submit this request to retry.')}</div>`;
      copyBtn.classList.remove('visible');
      currentReportText = '';
      return;
    }

    // Show key findings chips if present
    let html = '';
    if (task.key_findings && task.key_findings.length) {
      html += `<div class="findings-chips">${task.key_findings.map(f =>
        `<span class="finding-chip">${escHtml(f)}</span>`).join('')}</div>`;
    }

    // Job details hydrate report artifacts on demand.
    if (task.report) {
      currentReportText = task.report;
      html += `<div class="report-text">${formatReport(task.report)}</div>`;
      copyBtn.classList.add('visible');
    } else if (task.result) {
      currentReportText = JSON.stringify(task.result, null, 2);
      html += `<div class="report-text">${formatReport(currentReportText)}</div>`;
      copyBtn.classList.add('visible');
    } else {
      html += `<div class="report-text" style="color:var(--text2)">No report generated.</div>`;
    }

    panel.innerHTML = html;

    // Mirror to mobile analysis overlay
    if (isMobile()) {
      const mobBody = document.getElementById('mob-panel-body');
      if (mobBody) mobBody.innerHTML = html;
      document.getElementById('mob-analysis').classList.add('open');
    }
  }

  function formatReport(text) {
    // Light formatting: highlight headers and key phrases
    return escHtml(text)
      .replace(/^(#{1,3}\s.+)$/gm, '<strong>$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(NCT\d{8})/g, '<span style="color:var(--teal)">$1</span>')
      .replace(/(PMID:\s*\d+)/gi, '<span style="color:var(--teal)">$1</span>')
      .replace(/(URGENT|CRITICAL|IMPORTANT)/gi, '<span style="color:var(--red)">$1</span>')
      .replace(/(PRRT|Lutathera|Lu-177|Ac-225)/g, '<span style="color:var(--amber)">$1</span>');
  }

  function escHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function fmtDate(s) {
    if (!s) return '';
    const str = String(s);
    // Handle date ranges like "2026-05 to 2026-08"
    if (str.includes(' to ')) {
      return str.split(' to ').map(p => fmtDate(p.trim())).join(' – ');
    }
    // YYYY-MM-DD → DD-MM-YYYY
    const m = str.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
    // YYYY-MM → MM-YYYY
    const m2 = str.match(/^(\d{4})-(\d{2})$/);
    if (m2) return `${m2[2]}-${m2[1]}`;
    return str;
  }

  function copyReport() {
    if (!currentReportText) return;
    navigator.clipboard.writeText(currentReportText).then(() => {
      const btn = document.getElementById('copy-btn');
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = orig, 1500);
    });
  }

  // ── Feed ────────────────────────────────────────────────────────────────
  function toggleFeedPopover(force) {
    const pop = document.getElementById('feed-popover');
    const back = document.getElementById('feed-backdrop');
    const willShow = (typeof force === 'boolean') ? force : !pop.classList.contains('visible');
    pop.classList.toggle('visible', willShow);
    back.classList.toggle('visible', willShow);
    if (willShow) {
      setTimeout(() => {
        const ta = document.getElementById('feed-textarea');
        if (ta && document.getElementById('tab-text').classList.contains('visible')) ta.focus();
      }, 50);
    }
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const pop = document.getElementById('feed-popover');
      if (pop && pop.classList.contains('visible')) toggleFeedPopover(false);
    }
  });

  function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach((b, i) =>
      b.classList.toggle('active', (i === 0 && tab === 'text') || (i === 1 && tab === 'file')));
    document.getElementById('tab-text').classList.toggle('visible', tab === 'text');
    document.getElementById('tab-file').classList.toggle('visible', tab === 'file');
  }

  function updateCharCount() {
    const n = document.getElementById('feed-textarea').value.length;
    document.getElementById('char-count').textContent = `${n.toLocaleString()} chars`;
  }

  async function feedText() {
    const text = document.getElementById('feed-textarea').value.trim();
    if (!text) return;
    if (!await submitFeed(text)) return;
    document.getElementById('feed-textarea').value = '';
    updateCharCount();
    toggleFeedPopover(false);
  }

  async function submitFeed(text) {
    document.getElementById('btn-feed').disabled = true;
    try {
      const r = await fetch('/api/feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const d = await readJsonResponse(r);
      await activateSubmittedTask(d);
      return true;
    } catch (e) {
      alert(e.message);
      return false;
    } finally {
      document.getElementById('btn-feed').disabled = false;
    }
  }

  async function activateSubmittedTask(data) {
    const id = data.job_id || data.task_id;
    if (!id) throw new Error('Response did not include a job ID');
    selectedTaskId = id;
    await loadTasks();
    await selectTask(id);
  }

  async function handleDrop(e) {
    e.preventDefault();
    document.getElementById('tab-file').classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file && await processFile(file)) toggleFeedPopover(false);
  }

  async function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file && await processFile(file)) toggleFeedPopover(false);
    e.target.value = '';
  }

  async function processFile(file) {
    const btn = document.getElementById('btn-feed');
    btn.disabled = true;
    try {
      const form = new FormData();
      form.append('file', file, file.name);
      const r = await fetch('/api/feed-file', {
        method: 'POST',
        body: form,
      });
      const d = await readJsonResponse(r);
      await activateSubmittedTask(d);
      return true;
    } catch (e) {
      alert(e.message);
      return false;
    } finally {
      btn.disabled = false;
    }
  }

  async function runDigest() {
    const btn = document.getElementById('btn-digest');
    btn.disabled = true;
    try {
      const r = await fetch('/api/digest', { method: 'POST' });
      const d = await readJobSubmission(r);
      await activateSubmittedTask(d);
    } finally {
      btn.disabled = false;
    }
  }

  async function runDeepSweep() {
    const btn = document.getElementById('btn-deep-sweep');
    if (!confirm('Run an ensemble deep-sweep? This runs two premium models (Fable 5 + Opus 4.8) plus a synthesis pass — it takes a few minutes and costs roughly $1–2 per run. Findings are for oncologist review and are NOT saved to the tracked lists.')) {
      return;
    }
    btn.disabled = true;
    try {
      const r = await fetch('/api/deep-sweep', { method: 'POST' });
      const d = await readJobSubmission(r);
      await activateSubmittedTask(d);
    } finally {
      btn.disabled = false;
    }
  }

  // ── Polling loop ────────────────────────────────────────────────────────
  function startPolling() {
    pollingInterval = setInterval(async () => {
      await loadTasks();
      await loadStatus();
      await loadChanges();
      // If selected task just completed, auto-load its report and refresh summary
      if (selectedTaskId) {
        const r = await fetch(`/api/jobs/${selectedTaskId}`);
        const t = await r.json();
        if (t.status === 'done' || t.status === 'error' || t.status === 'interrupted') {
          const panel = document.getElementById('panel-body');
          if (panel.querySelector('.report-empty')) {
            selectTask(selectedTaskId);
          }
        }
      }
    }, 3000);
  }

  // ── Questions ────────────────────────────────────────────────────────────
  let questionsOpen = false;

  function toggleQuestions() {
    questionsOpen = !questionsOpen;
    document.getElementById('q-body').classList.toggle('hidden', !questionsOpen);
    const caret = document.getElementById('q-caret');
    if (caret) caret.textContent = questionsOpen ? '▼' : '▶';
    if (questionsOpen) loadQuestions();
  }

  async function loadQuestions() {
    try {
      const r = await fetch('/api/questions');
      const qs = await r.json();
      renderQuestions(qs);
    } catch(e) { console.error('Questions load error:', e); }
  }

  function renderQuestions(qs) {
    const urgent = qs.filter(q => !q.asked && q.priority === 'urgent');
    const high   = qs.filter(q => !q.asked && q.priority === 'high');
    const medium = qs.filter(q => !q.asked && (q.priority === 'medium' || !q.priority));
    const asked  = qs.filter(q => q.asked);

    const badge = document.getElementById('q-count-badge');
    if (badge) {
      badge.textContent = qs.length;
      badge.className = `q-count-badge${qs.length ? ' has-questions' : ''}`;
    }

    const qRow = (q) => `
      <div class="q-item${q.asked?' asked':''}" data-question-id="${escHtml(q.id)}">
        <div class="q-priority-dot ${safeClassToken(q.priority, 'medium')}"></div>
        <div class="q-checkbox${q.asked?' checked':''}" onclick="toggleQuestion(this.closest('.q-item').dataset.questionId)">${q.asked?'✓':''}</div>
        <div class="q-text-wrap">
          <div class="q-text${q.asked?' asked':''}">${escHtml(q.text)}</div>
          <div class="q-meta">
            <span class="q-cat ${safeClassToken(q.category, 'Other')}">${escHtml(translateCategory(q.category||'Other'))}</span>
            ${q.rationale ? `<span class="q-rationale">${escHtml(q.rationale)}</span>` : ''}
          </div>
        </div>
        <button class="q-delete" onclick="deleteQuestion(this.closest('.q-item').dataset.questionId)" title="Poista">✕</button>
      </div>`;

    const grpHdr = (label, color) =>
      `<div style="font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:${color};padding:8px 16px 2px;border-bottom:1px solid var(--border)">${label}</div>`;

    let html = '';
    if (urgent.length) { html += grpHdr('Kiireelliset', 'var(--red)');   html += urgent.map(qRow).join(''); }
    if (high.length)   { html += grpHdr('Tärkeät', 'var(--amber)');      html += high.map(qRow).join(''); }
    if (medium.length) { html += grpHdr('Muut', 'var(--text2)');         html += medium.map(qRow).join(''); }
    if (asked.length)  { html += grpHdr('Kysytty', 'var(--text2)');      html += asked.map(qRow).join(''); }
    if (!html) html = '<div class="q-empty">Ei kysymyksiä vielä. Klikkaa ↻ Luo tai lisää oma.</div>';

    const desktop = document.getElementById('q-list');
    if (desktop) desktop.innerHTML = html;
    const mobile = document.getElementById('mob-q-list');
    if (mobile) mobile.innerHTML = html;
  }

  async function generateQuestions(isMob = false) {
    const btnId    = isMob ? 'mob-q-gen-btn' : 'q-gen-btn';
    const apptType = 'oncology follow-up';
    const btn = document.getElementById(btnId);
    if (btn) { btn.disabled = true; btn.textContent = '…'; }

    // Open questions panel on desktop if closed
    if (!isMob && !questionsOpen) toggleQuestions();

    try {
      const r = await fetch('/api/questions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ appointment_type: apptType }),
      });
      const submitted = await readJobSubmission(r);
      const completed = await waitForJob(submitted.job_id);
      renderQuestions((completed.result || {}).questions || []);
    } catch(e) { console.error('Generate questions error:', e); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = isMob ? '↻' : '↻ Luo'; }
    }
  }

  async function addQuestion(isMob = false) {
    const inputId = isMob ? 'mob-q-add-input' : 'q-add-input';
    const input = document.getElementById(inputId);
    const text = (input?.value || '').trim();
    if (!text) return;
    input.value = '';
    try {
      await fetch('/api/questions/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      await loadQuestions();
    } catch(e) { console.error('Add question error:', e); }
  }

  async function toggleQuestion(qid) {
    try {
      await fetch(`/api/questions/${encodeURIComponent(qid)}/toggle`, { method: 'POST' });
      await loadQuestions();
    } catch(e) { console.error('Toggle question error:', e); }
  }

  async function deleteQuestion(qid) {
    try {
      await fetch(`/api/questions/${encodeURIComponent(qid)}`, { method: 'DELETE' });
      await loadQuestions();
    } catch(e) { console.error('Delete question error:', e); }
  }

  // ── Mobile helpers ───────────────────────────────────────────────────────
  const isMobile = () => window.innerWidth <= 768;

  function mirrorSidebarToMobile() {
    const pairs = [
      ['patient-dx',    'mob-patient-dx',    'textContent'],
      ['patient-meta',  'mob-patient-meta',  'innerHTML'],
      ['tx-list',       'mob-tx-list',       'innerHTML'],
      ['bm-list',       'mob-bm-list',       'innerHTML'],
      ['alerts-list',   'mob-alerts-list',   'innerHTML'],
    ];
    for (const [src, dst, prop] of pairs) {
      const s = document.getElementById(src);
      const d = document.getElementById(dst);
      if (s && d) d[prop] = s[prop];
    }
  }

  function switchMobPanel(name) {
    document.querySelectorAll('.mob-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.mob-nav-btn').forEach(b => b.classList.remove('active'));
    const panel = document.getElementById(`mob-${name}`);
    const btn = document.getElementById(`mobnav-${name}`);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');
    if (name === 'summary') populateMobSummary();
    if (name === 'questions') { loadQuestions(); loadJudgments(); }
  }

  function closeMobAnalysis() {
    document.getElementById('mob-analysis').classList.remove('open');
  }

  function syncTextarea(el) {
    const desktop = document.getElementById('feed-textarea');
    if (desktop) desktop.value = el.value;
    const count = document.getElementById('mob-char-count');
    if (count) count.textContent = `${el.value.length.toLocaleString()} chars`;
  }

  function feedMobText() {
    const ta = document.getElementById('mob-feed-textarea');
    if (ta && ta.value.trim()) {
      document.getElementById('feed-textarea').value = ta.value;
      feedText();
      ta.value = '';
      const count = document.getElementById('mob-char-count');
      if (count) count.textContent = '0 chars';
    }
  }

  function populateMobSummary() {
    fetch('/api/summary').then(r => r.json()).then(d => {
      const el = document.getElementById('mob-summary');
      if (!el) return;
      if (!d || d.status === 'not_generated') {
        el.innerHTML = `<div class="summary-empty"><div style="margin-bottom:10px">Ei tiivistelmää vielä.</div><button class="btn-digest" onclick="generateSummary()">⊙ Luo</button></div>`;
        return;
      }
      const statusLabels = {stable:'STABLE',responding:'RESPONDING',progressing:'PROGRESSING',insufficient_data:'DATA PENDING'};
      let html = `<div style="padding:12px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg1);z-index:5">`;
      html += `<span class="s-pill status-${safeClassToken(d.overall_status, 'insufficient_data')}">${escHtml(statusLabels[d.overall_status]||d.overall_status||'DATA PENDING')}</span>`;
      const staleLabel = summaryIsStale(d) ? ' · new data available' : '';
      html += `<span style="font-family:var(--mono);font-size:10px;color:var(--text2);flex:1">${d.generated_at?'Updated '+escHtml(fmtDate(d.generated_at))+staleLabel:''}</span>`;
      html += `<button class="btn-digest" style="font-size:10px;padding:3px 8px" onclick="generateSummary()">↻</button></div>`;
      if (d.key_concern) html += `<div class="summary-concern" style="margin:10px 16px 0"><div class="summary-concern-label">Key concern</div>${escHtml(d.key_concern)}</div>`;
      if (d.summary) html += `<div class="summary-narrative" style="margin:10px 16px">${escHtml(d.summary)}</div>`;
      if (d.next_actions && d.next_actions.length) {
        html += `<div class="summary-section" style="margin:0 16px"><div class="summary-section-label">Recommended actions</div>`;
        for (const a of d.next_actions) {
          const prov = a.provisional ? `<span style="font-family:var(--mono);font-size:9px;color:var(--text2);border:1px solid var(--border);padding:1px 4px;border-radius:2px;margin-left:4px">TBD</span>` : '';
          html += `<div class="action-item"><span class="action-priority ${safeClassToken(a.priority, 'medium')}">${escHtml(a.priority || 'medium')}</span><div class="action-text"><div class="action-main">${escHtml(a.action)}${prov}</div>${a.rationale?`<div class="action-sub">${escHtml(a.rationale)}</div>`:''}</div><div class="action-timeframe">${escHtml(a.timeframe||'')}</div></div>`;
        }
        html += '</div>';
      }
      if (d.timeline && d.timeline.length) {
        html += `<div class="summary-section" style="margin:12px 16px 0"><div class="summary-section-label">Timeline</div>`;
        for (const t of d.timeline) {
          const prov = t.provisional ? `<span style="font-family:var(--mono);font-size:9px;color:var(--text2);border:1px solid var(--border);padding:1px 4px;border-radius:2px;margin-left:4px">TBD</span>` : '';
          html += `<div class="timeline-item"><span class="timeline-date">${escHtml(fmtDate(t.date||''))}</span><span class="timeline-event">${escHtml(t.event||'')}${prov}</span><span class="timeline-type ${safeClassToken(t.type, 'test')}">${escHtml(translateType(t.type||''))}</span></div>`;
        }
        html += '</div>';
      }
      html += '<div style="height:16px"></div>';
      el.innerHTML = html;
    }).catch(() => {});
  }

  // ── Chat ─────────────────────────────────────────────────────────────────
  let chatHistory = [];
  let chatOpen = false;

  function toggleChat() {
    chatOpen = !chatOpen;
    const panel = document.getElementById('chat-panel');
    panel.style.display = chatOpen ? 'flex' : 'none';
    if (chatOpen) setTimeout(() => document.getElementById('chat-input')?.focus(), 50);
  }

  function clearChat() {
    chatHistory = [];
    const msgs = document.getElementById('chat-messages');
    msgs.innerHTML = `<div style="font-size:12px;color:var(--text2);text-align:center;padding:20px 0">
      Ask anything about the patient's data, research findings, or treatment options.
      <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">
        <button class="chat-suggestion" onclick="sendSuggestion(this)">What are the most urgent actions right now?</button>
        <button class="chat-suggestion" onclick="sendSuggestion(this)">Summarise the biomarker trends over time</button>
        <button class="chat-suggestion" onclick="sendSuggestion(this)">Why is PRRT still being considered given the renal concerns?</button>
        <button class="chat-suggestion" onclick="sendSuggestion(this)">What do the tracked trials have in common?</button>
      </div>
    </div>`;
  }

  function sendSuggestion(btn) {
    const text = btn.textContent;
    document.getElementById('chat-input').value = text;
    sendChat();
  }

  // ── Lightweight, self-contained Markdown renderer for chat replies ────────
  // Assistant messages arrive as Markdown (headings, tables, lists, bold…).
  // We render a safe subset to HTML. Input is HTML-escaped FIRST, then a fixed
  // set of tags is introduced, so model output can never inject live markup.
  function mdSanitizeUrl(url) {
    const u = (url || '').trim();
    if (/^(https?:\/\/|mailto:|tel:|#|\/)/i.test(u)) return u.replace(/"/g, '%22');
    if (/^[a-z0-9._~\-]+(\/|\?|#|$)/i.test(u)) return u.replace(/"/g, '%22');
    return '';
  }

  function mdInline(s) {
    // s is already HTML-escaped. Protect inline code spans from other passes.
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (m, t, url) => {
      const safe = mdSanitizeUrl(url);
      return safe ? `<a href="${safe}" target="_blank" rel="noopener noreferrer">${t}</a>` : t;
    });
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[\s(])__(?!\s)(.+?)__(?=[\s).,;:!?]|$)/g, '$1<strong>$2</strong>');
    s = s.replace(/(^|[^*\w])\*(?!\s)([^*]+?)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[\s(])_(?!\s)([^_]+?)_(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>');
    s = s.replace(/~~(.+?)~~/g, '<del>$1</del>');
    s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
    return s;
  }

  function renderMarkdown(text) {
    if (!text) return '';
    const lines = escHtml(text).replace(/\r\n?/g, '\n').split('\n');
    const isSep = (l) =>
      l != null && l.includes('-') &&
      /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/.test(l);
    const splitRow = (l) => {
      let t = l.trim();
      if (t.startsWith('|')) t = t.slice(1);
      if (t.endsWith('|')) t = t.slice(0, -1);
      return t.split('|').map((c) => c.trim());
    };
    const blockStart = (l, next) =>
      /^\s*$/.test(l) || /^\s*#{1,6}\s+/.test(l) || /^\s*```+/.test(l) ||
      /^\s*[-*+]\s+/.test(l) || /^\s*\d+\.\s+/.test(l) || /^\s*&gt;\s?/.test(l) ||
      /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l) || (/\|/.test(l) && isSep(next));

    let html = '';
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^\s*$/.test(line)) { i++; continue; }

      if (/^\s*```+/.test(line)) {
        i++;
        const buf = [];
        while (i < lines.length && !/^\s*```+\s*$/.test(lines[i])) buf.push(lines[i++]);
        i++;
        html += `<pre><code>${buf.join('\n')}</code></pre>`;
        continue;
      }

      if (/\|/.test(line) && isSep(lines[i + 1])) {
        const header = splitRow(line);
        i += 2;
        const rows = [];
        while (i < lines.length && /\|/.test(lines[i]) && !/^\s*$/.test(lines[i])) rows.push(splitRow(lines[i++]));
        let t = '<table><thead><tr>' + header.map((h) => `<th>${mdInline(h)}</th>`).join('') + '</tr></thead>';
        if (rows.length) {
          t += '<tbody>' + rows.map((r) => {
            let cells = '';
            for (let c = 0; c < header.length; c++) cells += `<td>${mdInline(r[c] || '')}</td>`;
            return `<tr>${cells}</tr>`;
          }).join('') + '</tbody>';
        }
        html += t + '</table>';
        continue;
      }

      const h = line.match(/^\s*(#{1,6})\s+(.*)$/);
      if (h) { const n = h[1].length; html += `<h${n}>${mdInline(h[2].trim())}</h${n}>`; i++; continue; }

      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { html += '<hr>'; i++; continue; }

      if (/^\s*&gt;\s?/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*&gt;\s?/, ''));
        html += `<blockquote>${mdInline(buf.join('<br>'))}</blockquote>`;
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) buf.push(lines[i++].replace(/^\s*[-*+]\s+/, ''));
        html += '<ul>' + buf.map((it) => `<li>${mdInline(it)}</li>`).join('') + '</ul>';
        continue;
      }

      if (/^\s*\d+\.\s+/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) buf.push(lines[i++].replace(/^\s*\d+\.\s+/, ''));
        html += '<ol>' + buf.map((it) => `<li>${mdInline(it)}</li>`).join('') + '</ol>';
        continue;
      }

      const buf = [];
      while (i < lines.length && !blockStart(lines[i], lines[i + 1])) buf.push(lines[i++]);
      html += `<p>${mdInline(buf.join('<br>'))}</p>`;
    }
    return html || '<p></p>';
  }

  function appendMsg(role, text) {
    const msgs = document.getElementById('chat-messages');
    // Remove suggestion block on first message
    const sugg = msgs.querySelector('.chat-suggestion');
    if (sugg) sugg.closest('div').remove();

    const now = new Date().toLocaleTimeString('en', {hour:'2-digit', minute:'2-digit'});
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    const body = role === 'assistant' ? renderMarkdown(text) : escHtml(text).replace(/\n/g,'<br>');
    div.innerHTML = `
      <div class="chat-bubble ${role}">${body}</div>
      <div class="chat-time">${now}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  function updateLastMsg(div, text) {
    const bubble = div.querySelector('.chat-bubble');
    // updateLastMsg is only ever called for assistant replies/errors.
    if (bubble) bubble.innerHTML = renderMarkdown(text);
    const msgs = document.getElementById('chat-messages');
    msgs.scrollTop = msgs.scrollHeight;
  }

  async function sendChat() {
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('chat-send-btn');
    const text = (input?.value || '').trim();
    if (!text || btn.disabled) return;

    input.value = '';
    appendMsg('user', text);
    chatHistory.push({ role: 'user', content: text });

    btn.disabled = true;
    btn.textContent = '…';
    const thinkingDiv = appendMsg('assistant', 'Thinking…');
    thinkingDiv.querySelector('.chat-bubble').classList.add('thinking');

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: chatHistory.slice(0, -1) }),
      });
      const data = await r.json();
      if (data.error) throw new Error(data.error);
      const completed = await waitForJob(data.job_id);
      const reply = (completed.result || {}).reply;
      if (!reply) throw new Error('No response was produced.');

      thinkingDiv.querySelector('.chat-bubble').classList.remove('thinking');
      updateLastMsg(thinkingDiv, reply);
      chatHistory.push({ role: 'assistant', content: reply });
    } catch(e) {
      thinkingDiv.querySelector('.chat-bubble').classList.remove('thinking');
      updateLastMsg(thinkingDiv, `Error: ${e.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Send';
      input.focus();
    }
  }

  // ── Init ────────────────────────────────────────────────────────────────
  loadStatus();
  loadTasks();
  loadSummary();
  loadQuestions();
  loadJudgments();
  loadSymptoms();
  loadChanges();
  startPolling();
  if (isMobile()) switchMobPanel('summary');
