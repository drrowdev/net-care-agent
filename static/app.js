/* Extracted from static/index.html (Phase 4 UI split). */
  let selectedTaskId = null;
  let pollingInterval = null;
  let currentReportText = '';
  let activeView = 'today';
  let latestResearchUpdate = null;
  let lastDialogTrigger = null;
  let hadActiveJobs = false;
  let pendingSummary = null;
  let activeDialogSurface = null;
  let currentReceipt = null;
  let patientEvidence = null;
  let imagingHistoryExpanded = false;
  let sourceHistoryExpanded = false;
  let receiptMutationPending = false;
  let taskSelectionEpoch = 0;
  let latestProfileRevision = null;
  let phiEpoch = 0;
  let statusLoadEpoch = 0;
  let summaryLoadEpoch = 0;
  let taskLoadEpoch = 0;
  let workflowRevision = null;
  let clinicalConvergenceRevision = null;
  let clinicalConvergenceRunning = false;
  let visitsById = new Map();
  let appointmentOptions = [];
  let appointmentQuestionSources = [];
  let questionLoadEpoch = 0;
  let visitLoadEpoch = 0;
  let generatedQuestionsUnavailable = false;
  let followUpsById = new Map();
  let followUpFilter = 'active';
  let followUpLoadEpoch = 0;
  let followUpProjectionStale = false;
  let selectedFollowUpId = null;
  let followUpSelectionEpoch = 0;
  let followUpDialogOpen = false;
  let followUpDialogMode = null;
  let followUpOutcomeStatus = null;
  let pendingFollowUpIntent = null;
  let activeFollowUpIntent = null;
  let pendingFollowUpCompletion = null;
  let followUpMutationPending = false;
  let followUpMutationOwner = null;
  let summaryActionMutationOwner = null;
  let followUpDrafts = new Map();
  let selectedVisitId = null;
  let visitSelectionEpoch = 0;
  let appointmentDialogOpen = false;
  let activeAppointmentTab = 'questions';
  let pendingWorkflowIntent = null;
  let activeWorkflowIntent = null;
  let workflowMutationPending = false;
  let appointmentDrafts = new Map();
  let decisionSuccessorConflicts = new Set();
  const failedLoads = new Map();

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

  function revisionIsOlder(candidate, current) {
    if (candidate == null || current == null) return false;
    const candidateNumber = Number(candidate);
    const currentNumber = Number(current);
    return Number.isFinite(candidateNumber)
      && Number.isFinite(currentNumber)
      && candidateNumber < currentNumber;
  }

  function followUpControlsLocked() {
    return followUpMutationPending
      || pendingFollowUpCompletion !== null
      || summaryActionMutationOwner !== null
      || (
        typeof workflowMutationPending !== 'undefined'
        && workflowMutationPending
      );
  }

  function newMutationId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return `mutation-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function normalizedRevision(value) {
    if (value == null) return null;
    const revision = typeof value === 'number' ? value : Number(value);
    return Number.isSafeInteger(revision) && revision >= 0 ? revision : NaN;
  }

  function capturePatientRequest(options = {}) {
    const request = { requestPhiEpoch: phiEpoch };
    if (options.taskSelection) {
      request.requestTaskEpoch = taskSelectionEpoch;
      request.requestTaskId = selectedTaskId;
    }
    if (options.visitSelection) {
      request.requestVisitEpoch = visitSelectionEpoch;
      request.requestVisitId = selectedVisitId;
    }
    if (options.followUpSelection) {
      request.requestActionEpoch = followUpSelectionEpoch;
      request.requestActionId = selectedFollowUpId;
    }
    return request;
  }

  function patientRequestIsCurrent(request) {
    if (!request || request.requestPhiEpoch !== phiEpoch) return false;
    if (
      request.requestTaskEpoch != null
      && (
        request.requestTaskEpoch !== taskSelectionEpoch
        || request.requestTaskId !== selectedTaskId
      )
    ) return false;
    if (
      request.requestVisitEpoch != null
      && (
        request.requestVisitEpoch !== visitSelectionEpoch
        || (
          ('requestVisitId' in request || 'visitId' in request)
          && (request.requestVisitId ?? request.visitId ?? null) !== selectedVisitId
        )
      )
    ) return false;
    if (
      request.requestActionEpoch != null
      && (
        request.requestActionEpoch !== followUpSelectionEpoch
        || (
          ('requestActionId' in request || 'actionId' in request)
          && (request.requestActionId ?? request.actionId ?? null) !== selectedFollowUpId
        )
      )
    ) return false;
    return true;
  }

  function requestClinicalConvergence(profileRevision) {
    const revision = normalizedRevision(profileRevision);
    if (!Number.isSafeInteger(revision)) return;
    if (
      clinicalConvergenceRevision == null
      || revision > clinicalConvergenceRevision
    ) {
      clinicalConvergenceRevision = revision;
    }
    if (clinicalConvergenceRunning) return;
    clinicalConvergenceRunning = true;
    Promise.resolve().then(async () => {
      while (clinicalConvergenceRevision != null) {
        const targetRevision = clinicalConvergenceRevision;
        clinicalConvergenceRevision = null;
        await refreshClinicalWorkflowState(targetRevision);
      }
    }).catch(error => {
      reportLoadError('clinical-convergence', error);
    }).finally(() => {
      clinicalConvergenceRunning = false;
      if (clinicalConvergenceRevision != null) {
        requestClinicalConvergence(clinicalConvergenceRevision);
      }
    });
  }

  function advancePatientAuthority(profileRevision) {
    const revision = normalizedRevision(profileRevision);
    const current = normalizedRevision(latestProfileRevision);
    if (
      !Number.isSafeInteger(revision)
      || (Number.isSafeInteger(current) && revision <= current)
    ) return false;
    phiEpoch += 1;
    taskSelectionEpoch += 1;
    syncChatRevision(revision, true, false);
    requestClinicalConvergence(revision);
    return true;
  }

  function authorizePatientResponse(request, data, options = {}) {
    if (!patientRequestIsCurrent(request)) {
      return { accepted: false, profileAdvanced: false };
    }
    const hasProfileRevision = data != null
      && !Array.isArray(data)
      && Object.prototype.hasOwnProperty.call(data, 'profile_revision');
    const responseProfileRevision = hasProfileRevision
      ? normalizedRevision(data.profile_revision)
      : null;
    if (hasProfileRevision && !Number.isSafeInteger(responseProfileRevision)) {
      return { accepted: false, profileAdvanced: false };
    }
    const currentProfileRevision = normalizedRevision(latestProfileRevision);
    if (
      Number.isSafeInteger(responseProfileRevision)
      && Number.isSafeInteger(currentProfileRevision)
      && responseProfileRevision < currentProfileRevision
    ) {
      return { accepted: false, profileAdvanced: false };
    }

    const hasWorkflowRevision = data != null
      && !Array.isArray(data)
      && Object.prototype.hasOwnProperty.call(data, 'workflow_revision');
    const responseWorkflowRevision = hasWorkflowRevision
      ? normalizedRevision(data.workflow_revision)
      : null;
    if (hasWorkflowRevision && !Number.isSafeInteger(responseWorkflowRevision)) {
      return { accepted: false, profileAdvanced: false };
    }
    const currentWorkflowRevision = normalizedRevision(workflowRevision);
    const strictWorkflowProjection = options.workflow === 'projection';
    const staleWorkflowProjection = strictWorkflowProjection
      && Number.isSafeInteger(currentWorkflowRevision)
      && (
        !Number.isSafeInteger(responseWorkflowRevision)
        || responseWorkflowRevision < currentWorkflowRevision
      );

    const profileAdvanced = Number.isSafeInteger(responseProfileRevision)
      && (
        !Number.isSafeInteger(currentProfileRevision)
        || responseProfileRevision > currentProfileRevision
      );
    if (profileAdvanced) {
      advancePatientAuthority(responseProfileRevision);
    }
    if (staleWorkflowProjection) {
      if (profileAdvanced) requestClinicalConvergence(responseProfileRevision);
      return { accepted: false, profileAdvanced };
    }
    const workflowAdvanced = Number.isSafeInteger(responseWorkflowRevision)
      && (
        !Number.isSafeInteger(currentWorkflowRevision)
        || responseWorkflowRevision > currentWorkflowRevision
      );
    if (workflowAdvanced) {
      workflowRevision = responseWorkflowRevision;
      if (!profileAdvanced && Number.isSafeInteger(currentProfileRevision)) {
        requestClinicalConvergence(currentProfileRevision);
      }
    }
    return {
      accepted: true,
      profileAdvanced,
      workflowAdvanced,
      requestPhiEpoch: phiEpoch,
      profileRevision: responseProfileRevision,
      workflowRevision: responseWorkflowRevision,
    };
  }

  function setAppointmentMessage(message, tone = '') {
    const status = document.getElementById('appointment-status-message');
    if (!status) return;
    status.textContent = message || '';
    status.className = `appointment-status-message${tone ? ` ${safeClassToken(tone)}` : ''}`;
  }

  function clearWorkflowRetry() {
    if (pendingWorkflowIntent?.body) pendingWorkflowIntent.body = {};
    pendingWorkflowIntent = null;
    for (const id of ['appointment-retry', 'visit-create-retry']) {
      const retry = document.getElementById(id);
      if (retry) retry.hidden = true;
    }
  }

  function invalidateWorkflowRetryOnDraftChange() {
    if (!pendingWorkflowIntent) return;
    const createIntent = !pendingWorkflowIntent.visitId;
    clearWorkflowRetry();
    if (createIntent) {
      setFormError('visit-create-error', 'Draft changed. Submit it as a new visit request.');
    }
    setAppointmentMessage(
      'The draft changed. Submit it as a new request after reviewing the latest visit.',
      'conflict',
    );
  }

  function setAppointmentMutationBusy(busy) {
    document.querySelectorAll(
      '#appointment-dialog .button, #visit-create-panel .button'
    ).forEach(control => {
      if (busy) {
        control.dataset.workflowWasDisabled = String(control.disabled);
        control.disabled = true;
      } else if ('workflowWasDisabled' in control.dataset) {
        control.disabled = control.dataset.workflowWasDisabled === 'true';
        delete control.dataset.workflowWasDisabled;
      }
    });
  }

  function createWorkflowIntent(url, body, visitId = selectedVisitId) {
    return {
      method: 'POST',
      url,
      body: { ...body, mutation_id: newMutationId() },
      visitId: visitId || null,
      requestPhiEpoch: phiEpoch,
      requestVisitEpoch: visitSelectionEpoch,
      requestVisitId: selectedVisitId,
    };
  }

  function workflowIntentCanRender(intent) {
    if (intent.requestPhiEpoch !== phiEpoch) return false;
    if (intent.requestVisitEpoch !== visitSelectionEpoch) return false;
    return !intent.visitId || intent.visitId === selectedVisitId;
  }

  async function refreshClinicalWorkflowState(profileRevision, expectedWorkflowRevision = null) {
    redactGeneratedQuestionChoices();
    redactGeneratedSummaryActions();
    const refreshPhiEpoch = phiEpoch;
    taskSelectionEpoch += 1;
    const status = await loadStatus();
    if (refreshPhiEpoch !== phiEpoch || status?.profile_revision == null) return false;
    const statusRevision = status.profile_revision;
    syncChatRevision(statusRevision, true, false);
    const refreshResults = await Promise.allSettled([
      loadSummary(),
      loadQuestions(),
      loadTasks(),
      loadVisits(),
      loadFollowUps(),
    ]);
    if (refreshPhiEpoch !== phiEpoch) return false;
    const loadsSucceeded = refreshResults.every(
      result => result.status === 'fulfilled' && result.value !== null
    );
    const revisionValues = [
      statusRevision,
      refreshResults[0].value?.profile_revision,
      refreshResults[1].value?.profileRevision,
      refreshResults[3].value?.profileRevision,
      refreshResults[4].value?.profileRevision,
    ];
    const workflowValues = [
      refreshResults[3].value?.workflowRevision,
      refreshResults[4].value?.workflowRevision,
    ];
    const verified = loadsSucceeded
      && statusRevision != null
      && !revisionIsOlder(statusRevision, profileRevision)
      && revisionValues.every(value => (
        value != null && String(value) === String(statusRevision)
      ))
      && workflowValues.every(value => value != null)
      && !revisionIsOlder(workflowValues[0], expectedWorkflowRevision)
      && workflowValues.every(value => (
        String(value) === String(workflowValues[0])
      ))
      && String(latestProfileRevision) === String(statusRevision);
    return { verified };
  }

  async function consumeWorkflowResponse(data, intent) {
    if (!workflowIntentCanRender(intent)) return false;
    const authority = authorizePatientResponse(intent, data, { workflow: 'targeted' });
    if (!authority.accepted) return false;
    const responseVisitEpoch = visitSelectionEpoch;
    const responseVisitId = selectedVisitId;
    if (appointmentDialogOpen) captureAppointmentDraft();
    if (data.visit?.id) {
      visitsById.set(data.visit.id, data.visit);
      revalidateDecisionSuccessorState(data.visit);
    }
    if (data.item?.question_snapshots && data.item.id) visitsById.set(data.item.id, data.item);
    if (data.item?.visit_id && data.item.id) {
      followUpsById.set(data.item.id, data.item);
    }

    const renderedResponseVisit = Boolean(data.visit?.id);
    if (renderedResponseVisit) {
      renderVisitPreparation();
      renderAppointmentWorkspace();
    }
    if (authority.profileAdvanced) {
      const refreshed = await refreshClinicalWorkflowState(
        data.profile_revision,
        data.workflow_revision,
      );
      return refreshed?.verified === true
        && responseVisitEpoch === visitSelectionEpoch
        && responseVisitId === selectedVisitId;
    }

    if (!renderedResponseVisit) {
      renderVisitPreparation();
      renderAppointmentWorkspace();
    }
    reportLoadSuccess('appointment-workflow');
    return true;
  }

  async function handleWorkflowConflict(error, intent) {
    if (!workflowIntentCanRender(intent)) return false;
    if (appointmentDialogOpen) captureAppointmentDraft();
    clearWorkflowRetry();
    if (intent.body.supersedes_id) {
      decisionSuccessorConflicts.add(intent.body.supersedes_id);
      clearDecisionSuccessorState(intent.visitId);
      if (appointmentDialogOpen && workflowIntentCanRender(intent)) renderVisitDecisions();
    }
    const generatedSource = intent.body.source_kind === 'generated';
    const message = generatedSource
      ? 'The assessment changed. Reloaded questions must be reviewed before adding one.'
      : (error.message || 'This visit changed. Review the latest version before trying again.');
    if (generatedSource) redactGeneratedQuestionChoices();
    setAppointmentMessage(message, 'conflict');
    reportLoadError('appointment-workflow', error);
    await Promise.allSettled([loadVisits(), loadFollowUps(), loadQuestions()]);
    return true;
  }

  async function performWorkflowIntent(intent, explicitRetry = false) {
    if (followUpControlsLocked() || workflowMutationPending) return null;
    workflowMutationPending = true;
    let consumedSuccessfully = false;
    activeWorkflowIntent = intent;
    setAppointmentMutationBusy(true);
    setFollowUpMutationBusy(true);
    if (!explicitRetry) clearWorkflowRetry();
    setAppointmentMessage(explicitRetry ? 'Retrying the unchanged request…' : 'Saving…', 'saving');
    try {
      const response = await fetch(intent.url, {
        method: intent.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(intent.body),
      });
      const data = await readJsonResponse(response);
      const consumed = await consumeWorkflowResponse(data, intent);
      if (!consumed) return null;
      consumedSuccessfully = true;
      clearWorkflowRetry();
      if (workflowIntentCanRender(intent)) setAppointmentMessage('Saved.', 'success');
      return data;
    } catch (error) {
      if (intent.requestPhiEpoch !== phiEpoch) {
        if (error?.status === 401 || error?.status === 403) {
          reportLoadError('appointment-workflow', error);
        }
        return null;
      }
      if (shouldEvictClientPhi(error)) {
        evictClientPhi(error);
        reportLoadError('appointment-workflow', error);
        return null;
      }
      if (!workflowIntentCanRender(intent)) return null;
      if (error?.status === 409) {
        await handleWorkflowConflict(error, intent);
        return null;
      }
      if (
        error instanceof TypeError
        || error?.name === 'AbortError'
        || navigator.onLine === false
      ) {
        pendingWorkflowIntent = intent;
        if (String(intent.url || '').includes('/follow-ups')) {
          markFollowUpProjectionStale(
            'Follow-through is offline. The last loaded actions are read-only; caregiver-entered drafts remain available in this tab.',
          );
        }
        const retry = document.getElementById(
          intent.visitId ? 'appointment-retry' : 'visit-create-retry'
        );
        if (retry) retry.hidden = false;
        if (!intent.visitId) {
          setFormError('visit-create-error', 'Connection lost. Your draft is still available.');
        }
        setAppointmentMessage('Connection lost. Your draft is still available.', 'offline');
        reportLoadError('appointment-workflow', error);
        return null;
      }
      setAppointmentMessage(error?.message || 'The request could not be saved.', 'error');
      reportLoadError('appointment-workflow', error);
      return null;
    } finally {
      const ownsCleanup = consumedSuccessfully || workflowIntentCanRender(intent);
      workflowMutationPending = false;
      if (activeWorkflowIntent === intent) activeWorkflowIntent = null;
      if (ownsCleanup) {
        setFollowUpMutationBusy(false);
        setAppointmentMutationBusy(false);
        updateAppointmentFormValidity();
      }
    }
  }

  async function submitWorkflowMutation(url, body, visitId = selectedVisitId, method = 'POST') {
    if (followUpControlsLocked() || workflowMutationPending) return null;
    const intent = createWorkflowIntent(url, body, visitId);
    intent.method = method;
    return performWorkflowIntent(intent);
  }

  async function retryWorkflowIntent() {
    const intent = pendingWorkflowIntent;
    if (!intent) return;
    if (!workflowIntentCanRender(intent)) {
      clearWorkflowRetry();
      setAppointmentMessage('The visit changed. Review it before submitting a new request.', 'conflict');
      return;
    }
    const result = await performWorkflowIntent(intent, true);
    finalizeRetriedWorkflowIntent(intent, result);
  }

  async function readJsonResponse(response, canEvictClientPhi = () => true) {
    if (response.status === 401 || response.status === 403) {
      const authError = new Error('Authorization failed.');
      authError.status = response.status;
      if (canEvictClientPhi()) evictClientPhi(authError);
    }
    let data;
    try {
      data = await response.json();
    } catch (_) {
      const error = new Error(`The server returned an invalid response (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    if (!response.ok) {
      const message = data && typeof data.error === 'string'
        ? data.error
        : `Request failed (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.retryAfter = response.headers.get('Retry-After');
      error.data = data;
      if (response.status === 401 || response.status === 403) {
        if (canEvictClientPhi()) evictClientPhi(error);
      }
      throw error;
    }
    return data;
  }

  async function readJobSubmission(response) {
    if (response.status === 401 || response.status === 403) {
      const authError = new Error('Authorization failed.');
      authError.status = response.status;
      evictClientPhi(authError);
    }
    let data;
    try {
      data = await response.json();
    } catch (_) {
      const error = new Error(`The server returned an invalid response (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    if (response.ok || (response.status === 409 && data && data.job_id)) return data;
    const error = new Error(data && typeof data.error === 'string'
      ? data.error
      : `Request failed (${response.status})`);
    error.status = response.status;
    error.retryAfter = response.headers.get('Retry-After');
    error.data = data;
    if (response.status === 401 || response.status === 403) {
      evictClientPhi(error);
    }
    throw error;
  }

  async function requireOk(response) {
    if (!response.ok) await readJsonResponse(response);
    return response;
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

  function reportLoadSuccess(scope) {
    failedLoads.delete(scope);
    renderAppState();
  }

  function reportLoadError(scope, error) {
    failedLoads.set(scope, error);
    renderAppState();
  }

  function shouldEvictClientPhi(error) {
    return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
  }

  function restoreDialogFocus() {
    const target = lastDialogTrigger;
    lastDialogTrigger = null;
    if (target?.isConnected && !target.hidden && target.offsetParent !== null) {
      target.focus();
      return;
    }
    document.getElementById(`nav-${activeView}`)?.focus();
  }

  function dialogFocusable(surface) {
    if (!surface) return [];
    return [...surface.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )].filter(item => !item.hidden && item.offsetParent !== null);
  }

  function setBackgroundInert(activeTopLevel) {
    [...document.body.children].forEach(child => {
      const keep = child === activeTopLevel || child.id === 'feed-backdrop' || child.classList.contains('skip-link');
      if (keep) {
        child.inert = false;
        if (child.dataset.dialogAriaHidden === 'true') {
          child.removeAttribute('aria-hidden');
          delete child.dataset.dialogAriaHidden;
        }
      } else {
        child.inert = true;
        if (!child.hasAttribute('aria-hidden')) {
          child.setAttribute('aria-hidden', 'true');
          child.dataset.dialogAriaHidden = 'true';
        }
      }
    });
  }

  function activateDialog(surface, trigger = document.activeElement) {
    if (!surface) return;
    lastDialogTrigger = trigger;
    activeDialogSurface = surface;
    const topLevel = surface.closest('body > *') || surface;
    setBackgroundInert(topLevel);
    document.body.classList.add('dialog-open');
    const focusable = dialogFocusable(surface);
    (focusable[0] || surface).focus();
  }

  function deactivateDialog(surface, restoreFocus = true) {
    if (surface && activeDialogSurface !== surface) return;
    activeDialogSurface = null;
    [...document.body.children].forEach(child => {
      child.inert = false;
      if (child.dataset.dialogAriaHidden === 'true') {
        child.removeAttribute('aria-hidden');
        delete child.dataset.dialogAriaHidden;
      }
    });
    document.body.classList.remove('dialog-open');
    if (restoreFocus) restoreDialogFocus();
    else lastDialogTrigger = null;
  }

  function trapDialogFocus(event) {
    if (event.key !== 'Tab' || !activeDialogSurface) return false;
    const focusable = dialogFocusable(activeDialogSurface);
    if (!focusable.length) {
      event.preventDefault();
      activeDialogSurface.focus();
      return true;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return true;
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
      return true;
    }
    return false;
  }

  function loadFailureMarkup(label, retryCall) {
    return `<div class="load-failure" role="alert"><strong>${escHtml(label)} unavailable</strong><span>Nothing was removed. Retry when the connection is available.</span><button class="button secondary" onclick="${retryCall}">Retry</button></div>`;
  }

  function setFormError(id, message) {
    const error = document.getElementById(id);
    if (error) error.textContent = message || '';
  }

  function updateFormValidity() {
    const question = (document.getElementById('q-add-input')?.value || '').trim();
    const judgment = (document.getElementById('judgment-input')?.value || '').trim();
    const symptom = (document.getElementById('sym-name')?.value || '').trim();
    const chat = (document.getElementById('chat-input')?.value || '').trim();
    const questionButton = document.getElementById('q-add-btn');
    const judgmentButton = document.getElementById('judgment-add-btn');
    const symptomButton = document.getElementById('sym-add-btn');
    const chatButton = document.getElementById('chat-send-btn');
    if (questionButton) questionButton.disabled = !question;
    if (judgmentButton) judgmentButton.disabled = !judgment;
    if (symptomButton) symptomButton.disabled = !symptom;
    if (chatButton && !chatButton.dataset.busy) chatButton.disabled = !chat;
    if (question) setFormError('q-form-error', '');
    if (judgment) setFormError('judgment-form-error', '');
    if (symptom) setFormError('sym-form-error', '');
    if (chat) setFormError('chat-form-error', '');
    updateAppointmentFormValidity();
  }

  function renderAppState() {
    const banner = document.getElementById('app-state-banner');
    if (!banner) return;
    if (!failedLoads.size && navigator.onLine !== false) {
      banner.hidden = true;
      banner.classList.remove('offline');
      return;
    }

    const errors = [...failedLoads.values()];
    const error = errors.find(item => item?.status === 403)
      || errors.find(item => item?.status === 401)
      || errors[0];
    const offline = navigator.onLine === false || error instanceof TypeError;
    let title = 'Patient data could not be loaded';
    let message = error?.message || 'Check your connection and try again.';

    if (error?.status === 401) {
      title = 'Sign-in required';
      message = 'Your session has expired or is not authenticated. Sign in again, then retry.';
    } else if (error?.status === 403) {
      title = 'Access to this patient record is denied';
      message = 'You are signed in, but this account is not on the patient record allowlist.';
    } else if (offline) {
      title = 'Connection lost';
      message = 'The page cannot reach NET/Care. Patient data has not been removed; reconnect and retry.';
    }

    document.getElementById('app-state-title').textContent = title;
    document.getElementById('app-state-message').textContent = message;
    banner.classList.toggle('offline', offline);
    banner.hidden = false;
  }

  async function retryInitialLoad() {
    failedLoads.clear();
    renderAppState();
    await Promise.allSettled([
      loadStatus(),
      loadTasks(),
      loadSummary(),
      loadQuestions(),
      loadJudgments(),
      loadSymptoms(),
      loadPatientEvidence(),
      loadVisits(),
      loadFollowUps(),
    ]);
  }

  function switchView(name, trigger) {
    const next = document.getElementById(`view-${name}`);
    if (!next) return;
    activeView = name;
    document.querySelectorAll('.app-view').forEach(view => {
      const selected = view === next;
      view.hidden = !selected;
      view.classList.toggle('active', selected);
    });
    document.querySelectorAll('.view-nav-button').forEach(button => {
      const selected = button.id === `nav-${name}`;
      button.classList.toggle('active', selected);
      if (selected) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    if (name === 'questions') {
      loadQuestions();
      loadJudgments();
      loadVisits();
      loadFollowUps();
    } else if (name === 'patient') {
      loadStatus();
      loadSymptoms();
      loadPatientEvidence();
    } else if (name === 'activity') {
      loadTasks();
    } else if (name === 'today') {
      loadStatus();
      loadSummary();
      loadFollowUps();
    }
    if (window.location.hash !== `#${name}`) {
      history.replaceState(null, '', `#${name}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (!trigger) document.getElementById(`nav-${name}`)?.focus();
  }

  window.addEventListener('online', retryInitialLoad);
  window.addEventListener('offline', renderAppState);

  function refreshAfterVisibilityRestore() {
    if (document.hidden) return;
    const refreshes = [loadTasks(), loadStatus()];
    if (activeView === 'today') refreshes.push(loadSummary(), loadFollowUps());
    if (activeView === 'questions' || appointmentDialogOpen) {
      refreshes.push(loadVisits(), loadFollowUps(), loadQuestions());
    }
    Promise.allSettled(refreshes);
  }

  document.addEventListener('visibilitychange', refreshAfterVisibilityRestore);

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
    const request = capturePatientRequest();
    const requestLoadEpoch = ++statusLoadEpoch;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request) && requestLoadEpoch === statusLoadEpoch
    );
    try {
      const r = await fetch('/api/status');
      if (!requestIsCurrent()) return null;
      const d = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, d);
      if (!authority.accepted) return null;
      renderSidebar(d);
      reportLoadSuccess('status');
      return d;
    } catch(e) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(e)) {
        reportLoadError('status', e);
        if (requestIsCurrent()) evictClientPhi(e);
        return null;
      }
      renderStatusFailure();
      reportLoadError('status', e);
      return null;
    }
  }

  function renderStatusFailure() {
    const patient = document.getElementById('patient-dx');
    const patientMeta = document.getElementById('patient-meta');
    const treatments = document.getElementById('tx-list');
    const biomarkers = document.getElementById('bm-list');
    const alerts = document.getElementById('alerts-list');
    const search = document.getElementById('bm-search');
    redactGeneratedQuestionChoices();
    latestResearchUpdate = null;
    allBiomarkers = [];
    renderLatestResearchUpdate(null);
    clearFreshnessProjection();
    if (patient) patient.textContent = 'Patient profile unavailable';
    if (patientMeta) patientMeta.innerHTML = '';
    if (treatments) treatments.innerHTML = loadFailureMarkup('Treatments', 'loadStatus()');
    if (biomarkers) biomarkers.innerHTML = loadFailureMarkup('Biomarkers', 'loadStatus()');
    if (alerts) alerts.innerHTML = loadFailureMarkup('Alerts', 'loadStatus()');
    if (search) {
      search.value = '';
      search.disabled = true;
    }
  }

  function evictClientPhi(error = null) {
    phiEpoch += 1;
    statusLoadEpoch += 1;
    taskSelectionEpoch += 1;
    selectedTaskId = null;
    currentReportText = '';
    currentReceipt = null;
    pendingSummary = null;
    summaryLoadEpoch += 1;
    taskLoadEpoch += 1;
    latestProfileRevision = null;
    latestResearchUpdate = null;
    patientEvidence = null;
    allBiomarkers = [];
    workflowRevision = null;
    clinicalConvergenceRevision = null;
    visitsById = new Map();
    appointmentOptions = [];
    appointmentQuestionSources = [];
    questionLoadEpoch += 1;
    visitLoadEpoch += 1;
    generatedQuestionsUnavailable = false;
    followUpsById = new Map();
    followUpLoadEpoch += 1;
    followUpProjectionStale = false;
    selectedFollowUpId = null;
    followUpSelectionEpoch += 1;
    followUpDialogOpen = false;
    followUpDialogMode = null;
    followUpOutcomeStatus = null;
    if (pendingFollowUpIntent?.body) pendingFollowUpIntent.body = {};
    if (activeFollowUpIntent?.body) activeFollowUpIntent.body = {};
    pendingFollowUpIntent = null;
    activeFollowUpIntent = null;
    pendingFollowUpCompletion = null;
    followUpMutationPending = false;
    followUpMutationOwner = null;
    summaryActionMutationOwner = null;
    followUpDrafts = new Map();
    selectedVisitId = null;
    visitSelectionEpoch += 1;
    appointmentDialogOpen = false;
    activeAppointmentTab = 'questions';
    if (pendingWorkflowIntent?.body) pendingWorkflowIntent.body = {};
    if (activeWorkflowIntent?.body) activeWorkflowIntent.body = {};
    pendingWorkflowIntent = null;
    activeWorkflowIntent = null;
    workflowMutationPending = false;
    appointmentDrafts = new Map();
    decisionSuccessorConflicts = new Set();
    chatHistory = [];
    chatHistoryRevision = null;
    document.querySelectorAll('.action-feedback').forEach(editor => editor.remove());
    renderLatestResearchUpdate(null);
    clearFreshnessProjection();

    const clear = (id, html = '') => {
      const element = document.getElementById(id);
      if (element) element.innerHTML = html;
    };
    const patient = document.getElementById('patient-dx');
    if (patient) patient.textContent = 'Patient data unavailable';
    clear('patient-meta');
    clear('tx-list');
    clear('bm-list');
    clear('alerts-list');
    clear('imaging-history');
    clear('source-history');
    clear('q-list');
    clear('visit-list');
    clear('visit-source-questions');
    clear('visit-question-list');
    clear('visit-decision-list');
    clear('visit-followup-list');
    clear('follow-up-list');
    clear('follow-up-status');
    clear('follow-up-edit-copy');
    clear('follow-up-outcome-copy');
    clear('follow-up-outcome-guidance');
    clear('follow-up-dialog-status');
    clear('judgments-list');
    clear('symptoms-list');
    clear('summary-status-inline');
    clear('summary-updated');
    clear('summary-body', '<div class="summary-empty">Patient assessment unavailable.</div>');
    clear('task-list');
    clear('panel-body', '<div class="report-empty">Activity detail unavailable.</div>');

    const appointmentOverlay = document.getElementById('appointment-overlay');
    const appointmentDialog = document.getElementById('appointment-dialog');
    const followUpOverlay = document.getElementById('follow-up-overlay');
    const followUpDialog = document.getElementById('follow-up-dialog');
    if (
      followUpDialog
      && typeof followUpDialog.contains === 'function'
      && followUpDialog.contains(document.activeElement)
    ) {
      document.activeElement?.blur();
    }
    followUpOverlay?.classList.remove('open');
    followUpOverlay?.setAttribute('aria-hidden', 'true');
    if (followUpOverlay) followUpOverlay.inert = true;
    if (followUpDialog) followUpDialog.inert = true;
    if (
      appointmentDialog
      && typeof appointmentDialog.contains === 'function'
      && appointmentDialog.contains(document.activeElement)
    ) {
      document.activeElement?.blur();
    }
    appointmentOverlay?.classList.remove('open');
    appointmentOverlay?.setAttribute('aria-hidden', 'true');
    if (appointmentOverlay) appointmentOverlay.inert = true;
    if (appointmentDialog) appointmentDialog.inert = true;
    const appointmentTitle = document.getElementById('appointment-dialog-title');
    if (appointmentTitle) appointmentTitle.textContent = 'Appointment unavailable';
    const appointmentMeta = document.getElementById('appointment-dialog-meta');
    if (appointmentMeta) appointmentMeta.textContent = '';
    const appointmentStatus = document.getElementById('appointment-status-message');
    if (appointmentStatus) {
      appointmentStatus.textContent = '';
      appointmentStatus.className = 'appointment-status-message';
    }
    const visitStatus = document.getElementById('visit-status-badge');
    if (visitStatus) {
      visitStatus.textContent = '';
      visitStatus.className = 'visit-status-badge';
    }
    const visitSelector = document.getElementById('appointment-visit-select');
    if (visitSelector) {
      visitSelector.innerHTML = '';
      visitSelector.value = '';
    }
    const sourceSelector = document.getElementById('visit-source-appointment');
    if (sourceSelector) {
      sourceSelector.innerHTML =
        '<option value="">Create without imported appointment</option>';
      sourceSelector.value = '';
    }
    const decisionSelector = document.getElementById('visit-followup-decision');
    if (decisionSelector) {
      decisionSelector.innerHTML = '<option value="">No linked decision</option>';
      decisionSelector.value = '';
    }
    const visitCreatePanel = document.getElementById('visit-create-panel');
    if (visitCreatePanel) visitCreatePanel.hidden = true;
    document.getElementById('visit-create-toggle')?.setAttribute('aria-expanded', 'false');
    for (const name of ['questions', 'decisions', 'followups']) {
      const active = name === 'questions';
      const tab = document.getElementById(`appointment-tab-${name}`);
      const panel = document.getElementById(`appointment-panel-${name}`);
      tab?.classList.toggle('active', active);
      tab?.setAttribute('aria-selected', String(active));
      if (tab) tab.tabIndex = active ? 0 : -1;
      panel?.classList.toggle('active', active);
      if (panel) panel.hidden = !active;
    }
    for (const id of [
      'appointment-retry', 'visit-create-retry', 'visit-decision-cancel-supersede',
      'follow-up-retry', 'follow-up-dialog-retry'
    ]) {
      const element = document.getElementById(id);
      if (element) element.hidden = true;
    }
    const decisionLabel = document.getElementById('visit-decision-label');
    if (decisionLabel) {
      decisionLabel.textContent = 'Caregiver-entered decision attributed to the clinician';
    }
    for (const id of [
      'visit-create-error', 'visit-details-error', 'visit-question-error',
      'visit-decision-error', 'visit-followup-error', 'follow-up-create-error',
      'follow-up-edit-error', 'follow-up-outcome-error'
    ]) {
      const status = document.getElementById(id);
      if (status) status.textContent = '';
    }

    const search = document.getElementById('bm-search');
    if (search) {
      search.value = '';
      search.disabled = true;
    }
    const report = document.getElementById('report-panel');
    report?.classList.add('collapsed');
    report?.setAttribute('aria-hidden', 'true');
    clearReportCopyState();
    const modal = document.getElementById('modal-overlay');
    modal?.classList.remove('open');
    modal?.setAttribute('aria-hidden', 'true');
    clear('modal-body');
    const chat = document.getElementById('chat-panel');
    if (chat) {
      chat.style.display = 'none';
      chat.setAttribute('aria-hidden', 'true');
    }
    chatOpen = false;
    clear(
      'chat-messages',
      `<div class="chat-revision-notice" role="alert">${
        error?.status === 401 || error?.status === 403
          ? 'Patient chat was cleared because authorization is unavailable.'
          : 'Patient chat was cleared because current data could not be loaded.'
      }</div>`,
    );
    const chatInput = document.getElementById('chat-input');
    if (chatInput) chatInput.value = '';
    for (const id of [
      'judgment-input', 'q-add-input', 'sym-name', 'sym-note',
      'visit-create-title', 'visit-create-date', 'visit-create-time',
      'visit-create-clinician', 'visit-create-location',
      'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
      'visit-edit-clinician', 'visit-edit-location',
      'visit-manual-question', 'visit-decision-text', 'visit-decision-supersedes',
      'visit-followup-text', 'visit-followup-owner', 'visit-followup-due',
      'follow-up-create-text', 'follow-up-create-owner', 'follow-up-create-due',
      'follow-up-edit-owner', 'follow-up-edit-due', 'follow-up-outcome-text',
      'dismiss-text-0', 'dismiss-text-1', 'dismiss-text-2',
      'dismiss-text-3', 'dismiss-text-4'
    ]) {
      const input = document.getElementById(id);
      if (input) input.value = '';
    }
    const severity = document.getElementById('sym-sev');
    if (severity) severity.value = '';
    for (const id of ['visit-manual-category', 'visit-manual-priority']) {
      const select = document.getElementById(id);
      if (select) select.value = '';
    }
    const outcomeKind = document.getElementById('follow-up-outcome-kind');
    if (outcomeKind) outcomeKind.value = 'administrative';
    const followUpDialogStatus = document.getElementById('follow-up-dialog-status');
    if (followUpDialogStatus) {
      followUpDialogStatus.textContent = '';
      followUpDialogStatus.className = 'follow-up-dialog-status';
    }
    const followUpTitle = document.getElementById('follow-up-dialog-title');
    if (followUpTitle) followUpTitle.textContent = 'Follow-up unavailable';
    for (const id of [
      'follow-up-edit-copy', 'follow-up-outcome-copy', 'follow-up-outcome-guidance'
    ]) {
      const node = document.getElementById(id);
      if (node) node.textContent = '';
    }
    for (const id of [
      'follow-up-create-form', 'follow-up-edit-form', 'follow-up-outcome-form'
    ]) {
      const form = document.getElementById(id);
      if (form) form.hidden = true;
    }
    for (const name of ['active', 'completed', 'cancelled', 'all']) {
      const count = document.getElementById(`follow-up-count-${name}`);
      if (count) count.textContent = '0';
    }
    const followUpRetry = document.getElementById('follow-up-retry');
    if (followUpRetry) followUpRetry.hidden = true;
    document.querySelectorAll(
      '.judgment-edit-text, .receipt-editor input, .receipt-editor textarea, .receipt-editor select'
    ).forEach(control => {
      if ('value' in control) control.value = '';
      control.closest('.judgment-edit-area, .receipt-editor')?.remove();
    });
    const feed = document.getElementById('feed-popover');
    const backdrop = document.getElementById('feed-backdrop');
    feed?.classList.remove('visible');
    feed?.setAttribute('aria-hidden', 'true');
    backdrop?.classList.remove('visible');
    const feedText = document.getElementById('feed-textarea');
    if (feedText) feedText.value = '';
    updateCharCount();
    lastDialogTrigger = null;
    activeDialogSurface = null;
    document.body.classList.remove('dialog-open');
    [...document.body.children].forEach(child => { child.inert = false; });
    [...document.body.children].forEach(child => {
      if (child.dataset.dialogAriaHidden === 'true') {
        child.removeAttribute('aria-hidden');
        delete child.dataset.dialogAriaHidden;
      }
    });
    if (appointmentOverlay) appointmentOverlay.inert = true;
    if (appointmentDialog) appointmentDialog.inert = true;
    if (followUpOverlay) followUpOverlay.inert = true;
    if (followUpDialog) followUpDialog.inert = true;
    setFollowUpMutationBusy(false);
    setAppointmentMutationBusy(false);
    updateAppointmentFormValidity();
  }

  function renderLatestResearchUpdate(update) {
    const card = document.getElementById('research-update-card');
    if (!card) return;
    if (!update) {
      document.getElementById('research-update-title').textContent = '';
      document.getElementById('research-update-detail').textContent = '';
      document.getElementById('research-update-trials').hidden = true;
      document.getElementById('research-update-papers').hidden = true;
      card.hidden = true;
      return;
    }

    const trialCount = Number(update.trial_count) || 0;
    const paperCount = Number(update.paper_count) || 0;
    const total = trialCount + paperCount;
    const source = update.trigger === 'digest' ? 'Latest digest' : 'Latest document analysis';
    const when = update.completed_at ? ` · completed ${relativeTime(update.completed_at)}` : '';
    document.getElementById('research-update-title').textContent = total
      ? 'Latest research additions'
      : 'No new trials or papers';
    document.getElementById('research-update-detail').textContent = total
      ? `${trialCount} trial${trialCount === 1 ? '' : 's'} and ${paperCount} paper${paperCount === 1 ? '' : 's'} were not previously tracked. ${source}${when}.`
      : `${source}${when} found no research that was not already tracked.`;

    const trialsButton = document.getElementById('research-update-trials');
    const papersButton = document.getElementById('research-update-papers');
    trialsButton.hidden = trialCount === 0;
    papersButton.hidden = paperCount === 0;
    trialsButton.textContent = `${trialCount} new trial${trialCount === 1 ? '' : 's'}`;
    papersButton.textContent = `${paperCount} new paper${paperCount === 1 ? '' : 's'}`;
    card.classList.toggle('empty', total === 0);
    card.hidden = false;
  }

  function renderSidebar(d) {
    const search = document.getElementById('bm-search');
    if (search) search.disabled = false;
    const p = d.patient || {};
    latestResearchUpdate = d.latest_research_update || null;
    renderLatestResearchUpdate(latestResearchUpdate);
    document.getElementById('patient-dx').textContent = p.diagnosis || 'No diagnosis recorded';

    const sstrClass = p.sstr_status === 'positive' ? 'positive' : p.sstr_status === 'negative' ? 'negative' : 'unknown';
    const newTrials = Number(latestResearchUpdate?.trial_count) || 0;
    const newPapers = Number(latestResearchUpdate?.paper_count) || 0;
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
        <button class="meta-val clickable" onclick="openModal('trials')">${escHtml((d.stats && d.stats.trials_tracked != null) ? d.stats.trials_tracked : 0)}${newTrials ? ` <span class="meta-new-count">${escHtml(newTrials)} new</span>` : ''}</button>
      </div>
      <div class="meta-row">
        <span class="meta-label">Papers</span>
        <button class="meta-val clickable" onclick="openModal('papers')">${escHtml((d.stats && d.stats.literature_watched != null) ? d.stats.literature_watched : 0)}${newPapers ? ` <span class="meta-new-count">${escHtml(newPapers)} new</span>` : ''}</button>
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
    const rawTxs = (d.treatments_fallback?.length
      ? d.treatments_fallback
      : (p.current_treatments || []));

    const txRow = (t) => {
      const dotColor = t.category === 'active' ? 'var(--accent)'
                     : t.category === 'planned' ? 'var(--amber)' : 'var(--text2)';
      const textStyle = t.category === 'completed' ? ' style="color:var(--text2)"' : '';
      const completeBtn = t.category !== 'completed'
        ? `<button class="tx-action-btn complete" data-treatment-id="${escHtml(t.id)}" data-edit-token="${escHtml(t.edit_token)}" aria-label="Mark ${escHtml(t.label || t.text)} as completed" title="Mark as completed" onclick="editTreatment(this,'complete')">✓</button>` : '';
      return `
        <div class="tx-item">
          <div class="tx-dot" style="background:${dotColor}"></div>
          <div class="tx-item-text">
            <span${textStyle}>${escHtml(t.label || t.text)}</span>
            ${t.date ? `<span class="tx-date">${escHtml(fmtDate(t.date))}</span>` : ''}
          </div>
          <div class="tx-actions">
            ${completeBtn}
            <button class="tx-action-btn remove" data-treatment-id="${escHtml(t.id)}" data-edit-token="${escHtml(t.edit_token)}" aria-label="Remove ${escHtml(t.label || t.text)}" title="Remove" onclick="editTreatment(this,'remove')">✕</button>
          </div>
        </div>`;
    };

    if (txs.length === 0 && rawTxs.length === 0) {
      document.getElementById('tx-list').innerHTML =
        '<div class="empty-state">No treatments recorded</div>';
    } else if (txs.length === 0) {
      document.getElementById('tx-list').innerHTML =
        `${d.treatments_classification_current === false ? '<div class="classification-stale-notice">Classification outdated — showing raw treatment entries.</div>' : ''}
        ${rawTxs.map(t => `<div class="tx-item"><div class="tx-dot"></div>${escHtml(t)}</div>`).join('')}`;
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
      ? alerts.map(a => `
        <div class="alert-item ${safeClassToken(a.priority, 'normal')}" data-alert-id="${escHtml(a.id)}" data-resolve-token="${escHtml(a.resolve_token)}">
          <div class="alert-msg">${escHtml(a.message)}</div>
          ${a.action_required ? `<div class="alert-action">→ ${escHtml(a.action_required)}</div>` : ''}
          <div class="alert-meta">
            <span class="alert-priority ${safeClassToken(a.priority, 'normal')}">${escHtml(a.priority || '—')}</span>
            <button class="resolve-btn" onclick="resolveAlert(this.closest('.alert-item'))">Mark resolved</button>
          </div>
        </div>`).join('')
      : '<div class="empty-state">No active alerts</div>';
  }

  async function resolveAlert(row) {
    const alertId = row?.dataset.alertId;
    const expectedToken = row?.dataset.resolveToken;
    if (!alertId || !expectedToken || latestProfileRevision == null) return;
    const request = capturePatientRequest();
    try {
      const result = await readJsonResponse(await fetch(`/api/alerts/${encodeURIComponent(alertId)}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_token: expectedToken,
          expected_profile_revision: latestProfileRevision,
        }),
      }));
      if (!authorizePatientResponse(request, result).accepted) return;
      await loadStatus();
    } catch (error) {
      if (!patientRequestIsCurrent(request)) return;
      reportLoadError('action', error);
    }
  }

  // ── Executive Summary ───────────────────────────────────────────────────
  let summaryOpen = true;

  async function loadPatientEvidence() {
    const request = capturePatientRequest();
    try {
      const evidence = await readJsonResponse(await fetch('/api/patient/evidence'));
      if (!authorizePatientResponse(request, evidence).accepted) return null;
      patientEvidence = evidence;
      renderPatientEvidence();
      reportLoadSuccess('patient-evidence');
      return patientEvidence;
    } catch (error) {
      if (!patientRequestIsCurrent(request)) return null;
      if (shouldEvictClientPhi(error)) evictClientPhi(error);
      if (!patientRequestIsCurrent(request)) return null;
      patientEvidence = null;
      document.getElementById('imaging-history').innerHTML = loadFailureMarkup('Imaging history', 'loadPatientEvidence()');
      document.getElementById('source-history').innerHTML = loadFailureMarkup('Source history', 'loadPatientEvidence()');
      reportLoadError('patient-evidence', error);
      return null;
    }
  }

  function evidenceBadge(status) {
    const normalized = ['verified', 'missing', 'invalid'].includes(status) ? status : 'missing';
    const label = normalized === 'verified' ? 'Exact source' : normalized === 'invalid' ? 'Invalid source quote' : 'No exact source';
    return `<span class="evidence-badge ${normalized}">${label}</span>`;
  }

  function renderPatientEvidence() {
    if (!patientEvidence) return;
    const imaging = patientEvidence.imaging || [];
    const visibleImaging = imagingHistoryExpanded ? imaging : imaging.slice(0, 3);
    document.getElementById('imaging-history').innerHTML = visibleImaging.length
      ? `${visibleImaging.map(item => `
          <article class="evidence-history-row">
            <div class="evidence-history-main">
              <strong>${escHtml(item.modality || 'Imaging')}</strong>
              <time>${escHtml(fmtDate(item.date || ''))}</time>
              <p>${escHtml(item.impression || item.findings || 'No impression recorded')}</p>
            </div>
            <div class="evidence-history-actions">
              ${evidenceBadge(item.evidence_status)}
              ${item.evidence_url ? `<a class="evidence-link" href="${escHtml(item.evidence_url)}" target="_blank" rel="noopener">Open exact span</a>` : ''}
              ${item.source_url ? `<a class="evidence-link" href="${escHtml(item.source_url)}" target="_blank" rel="noopener">Source details</a>` : ''}
            </div>
          </article>`).join('')}
          ${imaging.length > 3 ? `<button class="history-toggle" onclick="toggleImagingHistory()">${imagingHistoryExpanded ? 'Show recent imaging only' : `Show all ${imaging.length} imaging records`}</button>` : ''}`
      : '<div class="empty-state">No imaging records yet.</div>';

    const documents = patientEvidence.documents || [];
    const sources = patientEvidence.sources || [];
    const sourcesById = new Map(sources.map(source => [source.id, source]));
    const documentSourceIds = new Set(documents.map(document => document.source_document_id).filter(Boolean));
    const history = [
      ...documents.map(document => ({
        ...sourcesById.get(document.source_document_id),
        ...document,
        history_kind: 'document',
      })),
      ...sources
        .filter(source => !documentSourceIds.has(source.id))
        .map(source => ({ ...source, history_kind: 'source' })),
    ].sort((a, b) => String(b.added_at || b.ingested_at || b.date || '').localeCompare(String(a.added_at || a.ingested_at || a.date || '')));
    const visibleSources = sourceHistoryExpanded ? history : history.slice(0, 5);
    document.getElementById('source-history').innerHTML = visibleSources.length
      ? `${visibleSources.map(source => {
          const sourceUrl = source.artifacts?.text?.url || source.artifacts?.source?.url || source.source_url;
          const status = source.import_status || (source.excluded_from_clinical_context ? 'excluded' : 'legacy');
          return `<article class="source-history-row">
            <div class="source-history-main">
              <strong>${escHtml(source.filename || source.type || source.document_type || 'Legacy document record')}</strong>
              <span>${escHtml(source.summary || source.document_summary || 'Clinical source document')}</span>
              <time>Added ${escHtml(relativeTime(source.added_at || source.ingested_at || source.date))}</time>
            </div>
            <div class="evidence-history-actions">
              <span class="import-status ${safeClassToken(status, 'legacy')}">${escHtml(status.replace(/_/g, ' '))}</span>
              ${sourceUrl ? `<a class="evidence-link" href="${escHtml(sourceUrl)}" target="_blank" rel="noopener">Open source</a>` : ''}
              ${source.receipt_job_id ? `<button class="evidence-link button-link" data-job-id="${escHtml(source.receipt_job_id)}" onclick="openReceiptJob(this.dataset.jobId)">View import receipt</button>` : ''}
            </div>
          </article>`;
        }).join('')}
        ${history.length > 5 ? `<button class="history-toggle" onclick="toggleSourceHistory()">${sourceHistoryExpanded ? 'Show recent sources only' : `Show all ${history.length} sources`}</button>` : ''}`
      : '<div class="empty-state">No source documents have been fed yet.</div>';
  }

  function toggleImagingHistory() {
    imagingHistoryExpanded = !imagingHistoryExpanded;
    renderPatientEvidence();
  }

  function toggleSourceHistory() {
    sourceHistoryExpanded = !sourceHistoryExpanded;
    renderPatientEvidence();
  }

  async function openReceiptJob(jobId) {
    switchView('activity', document.getElementById('nav-activity'));
    await selectTask(jobId);
  }

  function toggleSummary() {
    summaryOpen = !summaryOpen;
    document.getElementById('summary-body').classList.toggle('hidden', !summaryOpen);
    document.getElementById('summary-caret').classList.toggle('open', summaryOpen);
    const toggle = document.getElementById('summary-toggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(summaryOpen));
      toggle.title = summaryOpen ? 'Collapse assessment' : 'Expand assessment';
    }
  }

  function toggleCompleted() {
    const list = document.getElementById('tx-completed-list');
    const caret = document.getElementById('tx-completed-caret');
    if (!list) return;
    list.classList.toggle('hidden');
    if (caret) caret.textContent = list.classList.contains('hidden') ? '▼' : '▲';
  }

  async function editTreatment(button, action) {
    const treatmentId = button?.dataset.treatmentId;
    const expectedToken = button?.dataset.editToken;
    if (!treatmentId || !expectedToken || latestProfileRevision == null) return;
    const request = capturePatientRequest();
    try {
      const result = await readJsonResponse(await fetch(`/api/treatments/${encodeURIComponent(treatmentId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          expected_token: expectedToken,
          expected_profile_revision: latestProfileRevision,
        }),
      }));
      if (!authorizePatientResponse(request, result).accepted) return;
      await loadStatus();
    } catch (error) {
      if (!patientRequestIsCurrent(request)) return;
      reportLoadError('action', error);
    }
  }

  async function generateSummary() {
    const request = capturePatientRequest();
    const btn = document.getElementById('btn-gen-summary');
    if (btn) { btn.disabled = true; btn.textContent = '⊙ Generating…'; }
    try {
      const r = await fetch('/api/summary/generate', { method: 'POST' });
      const submitted = await readJobSubmission(r);
      if (!authorizePatientResponse(request, submitted).accepted) return;
      const completed = await waitForJob(submitted.job_id);
      if (!authorizePatientResponse(request, completed).accepted) return;
      await Promise.all([loadSummary(), loadStatus()]);
    } catch(e) {
      if (!patientRequestIsCurrent(request)) return;
      reportLoadError('summary', e);
    } finally {
      if (patientRequestIsCurrent(request) && btn) {
        btn.disabled = false;
        btn.textContent = '↻ Refresh assessment';
      }
    }
  }

  async function dismissAction(idx) {
    if (followUpControlsLocked()) return;
    // Show inline feedback dialog
    const el = document.getElementById('action-' + idx);
    if (!el) return;

    // Build quick feedback options
    const feedbackHtml = `
      <div id="dismiss-dialog-${idx}" class="action-feedback" style="margin-top:8px;padding:10px;background:var(--bg2);border-radius:6px;border:0.5px solid var(--border)">
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
    if (existing) {
      existing.remove();
      renderPendingSummary();
      return;
    }
    el.insertAdjacentHTML('afterend', feedbackHtml);
  }

  async function quickDismiss(idx, feedback, category) {
    if (followUpControlsLocked()) return;
    const mutationOwner = {};
    summaryActionMutationOwner = mutationOwner;
    const requestPhiEpoch = phiEpoch;
    let requestSummaryEpoch = summaryLoadEpoch;
    const mutationIsCurrent = () => (
      summaryActionMutationOwner === mutationOwner
      && requestPhiEpoch === phiEpoch
      && requestSummaryEpoch === summaryLoadEpoch
    );
    setFollowUpMutationBusy(true);
    const el = document.getElementById('action-' + idx);
    const dlg = document.getElementById('dismiss-dialog-' + idx);
    const payload = {
      feedback: feedback.trim(),
      category,
      expected_action: el?.dataset.actionText || '',
      summary_revision: el?.dataset.summaryRevision || null,
    };
    if (el) el.style.opacity = '0.3';
    if (dlg) dlg.remove();
    try {
      const response = await fetch(`/api/summary/dismiss-action/${idx}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!mutationIsCurrent()) return;
      await requireOk(response);
      if (!mutationIsCurrent()) return;
      const summary = await loadSummary();
      requestSummaryEpoch += 1;
      if (!mutationIsCurrent() || summary === null) return;
      if (feedback.trim()) {
        await loadJudgments();
        if (!mutationIsCurrent()) return;
      }
    } catch(e) {
      if (!mutationIsCurrent()) return;
      if (el) el.style.opacity = '1';
      reportLoadError('action', e);
    } finally {
      if (mutationIsCurrent()) {
        summaryActionMutationOwner = null;
        setFollowUpMutationBusy(false);
        refreshGeneratedActionControls();
        updateFollowUpFormValidity();
      } else if (summaryActionMutationOwner === mutationOwner) {
        summaryActionMutationOwner = null;
      }
    }
  }

  async function reportMissedSummary() {
    if (followUpControlsLocked()) return;
    const mutationOwner = {};
    summaryActionMutationOwner = mutationOwner;
    const requestPhiEpoch = phiEpoch;
    let requestSummaryEpoch = summaryLoadEpoch;
    const mutationIsCurrent = () => (
      summaryActionMutationOwner === mutationOwner
      && requestPhiEpoch === phiEpoch
      && requestSummaryEpoch === summaryLoadEpoch
    );
    setFollowUpMutationBusy(true);
    try {
      const note = prompt('What was missed or incorrect? This records review feedback only; it will not change clinical facts.');
      if (!note || !note.trim()) return;
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target: 'summary',
          item_id: 'current',
          assessment: 'missed',
          note: note.trim(),
        }),
      });
      if (!mutationIsCurrent()) return;
      await requireOk(response);
      if (!mutationIsCurrent()) return;
      const summary = await loadSummary();
      requestSummaryEpoch += 1;
      if (!mutationIsCurrent() || summary === null) return;
    } catch (error) {
      if (!mutationIsCurrent()) return;
      reportLoadError('action', error);
    } finally {
      if (mutationIsCurrent()) {
        summaryActionMutationOwner = null;
        setFollowUpMutationBusy(false);
        refreshGeneratedActionControls();
        updateFollowUpFormValidity();
      } else if (summaryActionMutationOwner === mutationOwner) {
        summaryActionMutationOwner = null;
      }
    }
  }

  // ── Clinical Judgments ───────────────────────────────────────────────────
  async function loadJudgments() {
    const request = capturePatientRequest();
    try {
      const r = await fetch('/api/judgments');
      const js = await readJsonResponse(r);
      if (!authorizePatientResponse(request, js).accepted) return [];
      renderJudgments(js);
      reportLoadSuccess('judgments');
      return js;
    } catch(e) {
      if (!patientRequestIsCurrent(request)) return [];
      if (shouldEvictClientPhi(e)) {
        evictClientPhi(e);
        return [];
      }
      document.getElementById('judgments-list').innerHTML = loadFailureMarkup('Clinical notes', 'loadJudgments()');
      reportLoadError('judgments', e);
      return [];
    }
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
          <button class="judgment-action" data-category="${safeClassToken(j.category, 'context')}" data-status="${safeClassToken(j.status, 'active')}" onclick="startEditJudgment(this)" title="Edit clinical note" aria-label="Edit clinical note">✎</button>
          <button class="judgment-action danger" onclick="deleteJudgment(this.closest('.judgment-row').dataset.judgmentId)" title="Delete clinical note" aria-label="Delete clinical note">✕</button>
        </div>
      </div>`;}).join('')
    : '<div style="font-size:12px;color:var(--text2);padding:12px 0;text-align:center">No clinical notes yet.<br>Add notes after appointments or dismiss actions with feedback.</div>';

    const list = document.getElementById('judgments-list');
    if (list) list.innerHTML = html;
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
      await requireOk(await fetch(`/api/judgments/${encodeURIComponent(jid)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, category: catEl?.value || 'context', status: statusEl?.value || 'active' }),
      }));
      await loadJudgments();
    } catch(e) {
      reportLoadError('action', e);
    }
  }

  async function addJudgment() {
    const requestPhiEpoch = phiEpoch;
    const input = document.getElementById('judgment-input');
    const cat   = document.getElementById('judgment-cat');
    const text  = (input?.value || '').trim();
    if (!text) {
      setFormError('judgment-form-error', 'Enter the clinician’s guidance before adding the note.');
      updateFormValidity();
      return;
    }
    input.value = '';
    try {
      await requireOk(await fetch('/api/judgments/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, category: cat?.value || 'context' }),
      }));
      await loadJudgments();
      setFormError('judgment-form-error', '');
    } catch (error) {
      if (requestPhiEpoch !== phiEpoch) return;
      input.value = text;
      setFormError('judgment-form-error', error.message || 'The note could not be added.');
      reportLoadError('action', error);
    }
    updateFormValidity();
  }

  async function deleteJudgment(jid) {
    try {
      await requireOk(await fetch(`/api/judgments/${encodeURIComponent(jid)}`, { method: 'DELETE' }));
      await loadJudgments();
    } catch (error) {
      reportLoadError('action', error);
    }
  }

  // ── Symptoms ─────────────────────────────────────────────────────────────
  async function loadSymptoms() {
    const request = capturePatientRequest();
    try {
      const r = await fetch('/api/symptoms');
      const list = await readJsonResponse(r);
      if (!authorizePatientResponse(request, list).accepted) return [];
      renderSymptoms(list);
      reportLoadSuccess('symptoms');
      return list;
    } catch (e) {
      if (!patientRequestIsCurrent(request)) return [];
      if (shouldEvictClientPhi(e)) {
        evictClientPhi(e);
        return [];
      }
      document.getElementById('symptoms-list').innerHTML = loadFailureMarkup('Symptoms', 'loadSymptoms()');
      reportLoadError('symptoms', e);
      return [];
    }
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
            <button class="sym-del" onclick="deleteSymptom(this.closest('.sym-row').dataset.id)" title="Delete symptom" aria-label="Delete symptom">✕</button>
          </div>
          ${note}
          ${related}
        </div>`;
    }).join('');
  }

  async function addSymptom() {
    const requestPhiEpoch = phiEpoch;
    const name = document.getElementById('sym-name').value.trim();
    if (!name) {
      setFormError('sym-form-error', 'Enter a symptom before logging it.');
      updateFormValidity();
      return;
    }
    const sev = document.getElementById('sym-sev').value;
    const note = document.getElementById('sym-note').value.trim();
    try {
      await readJsonResponse(await fetch('/api/symptoms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symptom: name,
          severity: sev ? parseInt(sev, 10) : null,
          note: note || null,
        }),
      }));
      document.getElementById('sym-name').value = '';
      document.getElementById('sym-sev').value = '';
      document.getElementById('sym-note').value = '';
      await loadSymptoms();
      setFormError('sym-form-error', '');
    } catch (e) {
      if (requestPhiEpoch !== phiEpoch) return;
      setFormError('sym-form-error', e.message || 'The symptom could not be logged.');
      reportLoadError('action', e);
    }
    updateFormValidity();
  }

  async function deleteSymptom(sid) {
    if (!confirm('Delete this symptom entry?')) return;
    try {
      await requireOk(await fetch(`/api/symptoms/${encodeURIComponent(sid)}`, { method: 'DELETE' }));
      await loadSymptoms();
    } catch (error) {
      reportLoadError('action', error);
    }
  }

  async function loadSummary() {
    const request = capturePatientRequest();
    const requestSummaryEpoch = ++summaryLoadEpoch;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request) && requestSummaryEpoch === summaryLoadEpoch
    );
    try {
      const r = await fetch('/api/summary');
      if (!requestIsCurrent()) return null;
      const d = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, d);
      if (!authority.accepted) return null;
      if (
        latestProfileRevision != null
        && d.profile_revision != null
        && normalizedRevision(d.profile_revision) < normalizedRevision(latestProfileRevision)
      ) {
        redactGeneratedSummaryActions();
        pendingSummary = null;
        renderSummary({
          status: 'stale',
          content_hidden: true,
          profile_revision: latestProfileRevision,
          summary_revision: d.summary_revision,
        });
        reportLoadSuccess('summary');
        return d;
      }
      const editor = document.querySelector('.action-feedback');
      const responseStale = d.status === 'stale' || d.content_hidden || summaryIsStale(d);
      const editorRevision = editor?.previousElementSibling?.dataset.summaryRevision;
      const sameRevision = String(editorRevision ?? '') === String(d.summary_revision ?? '');
      if (editor && responseStale) {
        editor.querySelectorAll('button, input').forEach(control => { control.disabled = true; });
        editor.remove();
        pendingSummary = null;
        renderSummary(d);
      } else if (editor && sameRevision) {
        pendingSummary = d;
      } else if (editor) {
        editor.querySelectorAll('button, input').forEach(control => { control.disabled = true; });
        editor.remove();
        pendingSummary = null;
        renderSummary(d);
      } else {
        pendingSummary = null;
        renderSummary(d);
      }
      reportLoadSuccess('summary');
      return d;
    } catch(e) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(e)) {
        reportLoadError('summary', e);
        if (requestIsCurrent()) evictClientPhi(e);
        return null;
      }
      if (!patientRequestIsCurrent(request)) return null;
      document.getElementById('summary-body').innerHTML = loadFailureMarkup('Assessment', 'loadSummary()');
      renderFreshness(null, e);
      reportLoadError('summary', e);
      return null;
    }
  }

  function renderPendingSummary() {
    if (!pendingSummary || document.querySelector('.action-feedback')) return;
    const summary = pendingSummary;
    pendingSummary = null;
    renderSummary(summary);
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

  function renderFreshness(d, error = null) {
    const banner = document.getElementById('freshness-banner');
    if (!banner) return;
    const title = document.getElementById('freshness-title');
    const message = document.getElementById('freshness-message');
    banner.hidden = false;
    banner.className = 'freshness-banner';

    if (error) {
      banner.classList.add('error');
      title.textContent = 'Assessment freshness is unavailable';
      message.textContent = 'The assessment could not be compared with the latest patient data.';
      return;
    }

    if (!d || d.status === 'not_generated') {
      banner.classList.add('stale');
      title.textContent = 'No current assessment';
      message.textContent = 'Generate an assessment after checking that the patient record is complete.';
      return;
    }
    if (d.status === 'stale' || d.content_hidden) {
      banner.classList.add('stale');
      title.textContent = 'Assessment refresh required';
      message.textContent = 'Generated clinical conclusions are hidden because the patient record changed.';
      return;
    }

    const stale = summaryIsStale(d);
    const latestDoc = (d.recent_documents || [])[0];
    const latestDetail = latestDoc
      ? ` Latest source: ${latestDoc.summary || latestDoc.type || 'clinical document'}${latestDoc.date ? ` (${fmtDate(latestDoc.date)})` : ''}.`
      : '';
    if (stale) {
      banner.classList.add('stale');
      title.textContent = 'New patient data needs assessment';
      message.textContent = `This summary predates the current patient record.${latestDetail}`;
    } else {
      banner.classList.add('current');
      title.textContent = 'Assessment is current';
      message.textContent = d.generated_at
        ? `Updated ${fmtDate(d.generated_at_timestamp || d.generated_at)} and aligned with the current record.`
        : 'The summary is aligned with the current patient record.';
    }
  }

  function clearFreshnessProjection() {
    const banner = document.getElementById('freshness-banner');
    const title = document.getElementById('freshness-title');
    const message = document.getElementById('freshness-message');
    if (title) title.textContent = '';
    if (message) message.textContent = '';
    if (banner) {
      banner.className = 'freshness-banner';
      banner.hidden = true;
    }
  }

  function summaryActionIsCurrent(action, summary) {
    return action?.stale === false
      && typeof action.id === 'string'
      && Boolean(action.id.trim())
      && typeof action.source_token === 'string'
      && Boolean(action.source_token.trim())
      && typeof action.generation_id === 'string'
      && Boolean(action.generation_id.trim())
      && action.source_profile_revision != null
      && summary?.profile_revision != null
      && String(action.source_profile_revision) === String(summary.profile_revision)
      && String(action.generation_id) === String(summary.generation_id || '')
      && String(summary.summary_revision ?? '') === String(summary.profile_revision ?? '');
  }

  function generatedActionAccepted(sourceId) {
    return [...followUpsById.values()].some(
      item => item?.origin_snapshot?.kind === 'executive_summary_action'
        && item.origin_snapshot.source_id === sourceId
    );
  }

  function refreshGeneratedActionControls() {
    document.querySelectorAll('[data-generated-action-source-id]').forEach(row => {
      const button = row.querySelector('.action-accept-btn');
      if (!button) return;
      const accepted = generatedActionAccepted(row.dataset.generatedActionSourceId);
      if (followUpControlsLocked()) {
        if (!('followUpWasDisabled' in button.dataset)) {
          button.dataset.followUpWasDisabled = String(followUpProjectionStale || accepted);
        }
        button.disabled = true;
      } else {
        button.disabled = followUpProjectionStale || accepted;
      }
      button.textContent = accepted ? 'Accepted' : 'Add to follow-through';
      row.classList?.toggle('stale-projection', followUpProjectionStale);
    });
  }

  function redactGeneratedSummaryActions() {
    document.querySelectorAll('[data-generated-action-source-id]').forEach(row => {
      row.removeAttribute('data-generated-action-source-id');
      row.removeAttribute('data-generated-action-source-token');
      row.className = 'action-item unavailable';
      row.innerHTML = '<div class="summary-action-unavailable"><strong>Generated action unavailable</strong><span>Reload the current assessment before using this action.</span></div>';
    });
  }

  async function acceptGeneratedFollowUp(row) {
    if (followUpProjectionStale) {
      setFollowUpStatus('Reload the current action list before accepting an assessment action.', 'offline');
      return;
    }
    if (followUpControlsLocked()) return;
    const sourceId = row?.dataset.generatedActionSourceId;
    const sourceToken = row?.dataset.generatedActionSourceToken;
    if (!sourceId || !sourceToken) return;
    await submitFollowUpMutation(
      '/api/follow-ups',
      {
        origin_kind: 'executive_summary_action',
        source_id: sourceId,
        expected_source_token: sourceToken,
      },
      { sourceKind: 'generated' },
    );
  }

  function renderClaimEvidence(items) {
    const evidence = Array.isArray(items) && items.length
      ? items
      : [{ evidence_status: 'missing', label: 'No exact source span linked' }];
    return `<div class="claim-evidence">${evidence.map(item => {
      const status = ['verified', 'missing', 'invalid'].includes(item.evidence_status)
        ? item.evidence_status
        : 'missing';
      if (status === 'verified' && item.evidence_url) {
        return `<a class="claim-evidence-link verified" href="${escHtml(item.evidence_url)}" target="_blank" rel="noopener">Evidence: ${escHtml(item.label)}</a>`;
      }
      return `<span class="claim-evidence-link ${status}">${status === 'invalid' ? 'Invalid evidence link' : 'Evidence not linked'}</span>`;
    }).join('')}</div>`;
  }

  function renderSummary(d) {
    const body = document.getElementById('summary-body');
    const inline = document.getElementById('summary-status-inline');
    const updated = document.getElementById('summary-updated');
    renderFreshness(d);

    if (!d || d.status === 'not_generated') {
      inline.innerHTML = '';
      updated.textContent = '';
      body.innerHTML = `<div class="summary-empty">
        <div style="margin-bottom:10px">No assessment has been generated yet.</div>
        <button class="button secondary" onclick="generateSummary()">Generate assessment</button>
      </div>`;
      return;
    }
    if (d.status === 'stale' || d.content_hidden) {
      inline.innerHTML = '<span class="s-pill status-insufficient_data">ASSESSMENT NEEDS REFRESH</span>';
      updated.textContent = `Record rev ${d.profile_revision ?? '—'} · prior assessment rev ${d.summary_revision ?? '—'}`;
      body.innerHTML = `<div class="summary-empty stale-summary-hidden">
        <strong>Prior generated assessment is hidden</strong>
        <div>The patient record changed after it was generated. Refresh the assessment before using its actions, PRRT screening, or trial suggestion.</div>
        <button class="button secondary" onclick="generateSummary()">Refresh assessment</button>
      </div>`;
      return;
    }

    // Status pill in header
    const statusLabels = {
      stable: 'STABLE', responding: 'RESPONDING',
      progressing: 'PROGRESSING', insufficient_data: 'DATA PENDING'
    };
    inline.innerHTML = `<span class="s-pill status-${safeClassToken(d.overall_status, 'insufficient_data')}">${escHtml(statusLabels[d.overall_status] || d.overall_status || 'DATA PENDING')}</span>`;

    // Updated timestamp
    // Revision fields are authoritative; dates support profiles created before revisions.
    const isStale = summaryIsStale(d);
    updated.textContent = d.generated_at
      ? `Updated ${d.generated_at_timestamp || fmtDate(d.generated_at)} · record rev ${d.profile_revision ?? '—'} · assessment rev ${d.summary_revision ?? '—'}${isStale ? ' · new data available' : ''}`
      : '';

    let html = '';

    // Pills row
    html += `<div class="summary-pills">`;
    if (d.status_confidence) {
      html += `<span class="s-pill" title="${escHtml(d.status_rationale || '')}">CONFIDENCE: ${escHtml(d.status_confidence.toUpperCase())}</span>`;
    }
    const prrtLabels = {
      eligible: 'PRRT: POTENTIAL FIT', likely_eligible: 'PRRT: MAY FIT',
      pending_dotatate: 'PRRT: NEEDS RECEPTOR-IMAGING REVIEW',
      not_eligible: 'PRRT: NOT SUPPORTED BY CURRENT RECORD', unknown: 'PRRT: NOT ASSESSED'
    };
    html += `<span class="s-pill prrt-${safeClassToken(d.prrt_status, 'unknown')}" title="${escHtml(d.prrt_rationale||'')}">${escHtml(prrtLabels[d.prrt_status] || 'PRRT: NOT ASSESSED')}</span>`;
    if (d.cga_trend) {
      const cgaLabels = { rising: '↑ CgA RISING', stable: '→ CgA STABLE', falling: '↓ CgA FALLING', insufficient_data: 'CgA: NO DATA' };
      html += `<span class="s-pill cga-${safeClassToken(d.cga_trend, 'insufficient_data')}" title="${escHtml(d.cga_trend_detail||'')}">${escHtml(cgaLabels[d.cga_trend] || 'CgA: NO DATA')}</span>`;
    }
    html += `</div>`;
    if (d.cga_trend_detail) {
      html += `<div class="summary-rationale"><strong>CgA trend:</strong> ${escHtml(d.cga_trend_detail)}${renderClaimEvidence(d.claim_evidence?.claims?.cga_trend_detail)}</div>`;
    }
    if (d.status_rationale) {
      html += `<div class="summary-rationale">${escHtml(d.status_rationale)}${renderClaimEvidence(d.claim_evidence?.claims?.status_rationale)}</div>`;
    }
    if (d.prrt_rationale) {
      html += `<div class="summary-rationale"><strong>PRRT screening context:</strong> ${escHtml(d.prrt_rationale)}${renderClaimEvidence(d.claim_evidence?.claims?.prrt_rationale)}</div>`;
    }

    // Key concern
    if (d.key_concern) {
      html += `<div class="summary-concern">
        <div class="summary-concern-label">Key concern</div>
        ${escHtml(d.key_concern)}
        ${renderClaimEvidence(d.claim_evidence?.claims?.key_concern)}
      </div>`;
    }

    // Narrative
    if (d.summary) {
      html += `<div class="summary-narrative">${escHtml(d.summary)}${renderClaimEvidence(d.claim_evidence?.claims?.summary)}</div>`;
    }

    html += `<div style="margin:18px 22px 2px"><button class="btn-digest summary-feedback-button" style="border-color:var(--amber);color:var(--amber)" onclick="reportMissedSummary()">⚑ Report something missed or incorrect</button>${d.feedback_pending ? ` <span style="font-size:10px;color:var(--amber)">${escHtml(d.feedback_pending)} review item(s) recorded</span>` : ''}</div>`;

    // Next actions
    if (d.next_actions && d.next_actions.length) {
      html += `<div class="summary-section">
        <div class="summary-section-label">What to do next</div>
        <div class="action-list">`;
      d.next_actions.forEach((a, idx) => {
        if (!summaryActionIsCurrent(a, d)) {
          html += `<div class="action-item unavailable">
            <div class="summary-action-unavailable"><strong>Generated action unavailable</strong><span>Reload the current assessment before using this action.</span></div>
          </div>`;
          return;
        }
        const provBadge = a.provisional
          ? `<span style="font-family:var(--mono);font-size:9px;color:var(--text2);border:0.5px solid var(--border);padding:1px 4px;border-radius:2px;margin-left:4px">TBD</span>`
          : '';
        const accepted = generatedActionAccepted(a.id);
        html += `<div class="action-item" id="action-${idx}" data-action-text="${escHtml(a.action || '')}" data-summary-revision="${escHtml(d.summary_revision ?? '')}" data-generated-action-source-id="${escHtml(a.id)}" data-generated-action-source-token="${escHtml(a.source_token)}">
          <span class="action-priority ${safeClassToken(a.priority, 'medium')}">${escHtml(a.priority || 'medium')}</span>
          <div class="action-text">
            <div class="action-main">${escHtml(a.action)}${provBadge}</div>
            ${a.rationale ? `<div class="action-sub">${escHtml(a.rationale)}</div>` : ''}
            ${renderClaimEvidence(d.claim_evidence?.actions?.[idx])}
          </div>
          <div class="action-timeframe">${escHtml(a.due_date ? `Due ${fmtDate(a.due_date)}` : (a.timeframe || 'Review with care team'))}</div>
          <div class="action-controls">
            <button class="button secondary action-accept-btn" onclick="acceptGeneratedFollowUp(this.closest('.action-item'))" ${accepted ? 'disabled' : ''}>${accepted ? 'Accepted' : 'Add to follow-through'}</button>
            <button onclick="dismissAction(${idx})" aria-label="Review or dismiss this action" title="Review or dismiss" class="icon-button action-dismiss-btn">⋯</button>
          </div>
        </div>`;
      });
      html += `</div></div>`;
    }


    // A linear timeline remains readable with a keyboard, a screen reader, and on phones.
    if (d.timeline && d.timeline.length) {
      const today = new Date().toISOString().slice(0, 10);
      html += `<div class="summary-section">
        <div class="summary-section-label">Timeline</div>
        <ol class="timeline-list">${d.timeline.map(item => {
          const date = item.date || '';
          const past = date && date < today ? ' past' : '';
          return `<li class="timeline-entry${past}">
            <time datetime="${escHtml(date)}">${escHtml(fmtDate(date) || 'Date pending')}</time>
            <span class="timeline-event-copy">${escHtml(item.event || '')}</span>
            <span class="timeline-type ${safeClassToken(item.type, 'test')}">${escHtml(translateType(item.type || 'Event'))}</span>
            ${item.provisional ? '<span class="timeline-provisional">Provisional — confirm with the care team</span>' : ''}
          </li>`;
        }).join('')}</ol>
      </div>`;
    }

    // Trial for clinician discussion (never presented as an eligibility finding).
    if (d.best_trial && d.best_trial.nct_id) {
      html += `<div class="summary-section">
        <div class="summary-section-label">Trial to discuss</div>
        <div class="trial-chip">
          <a class="trial-chip-id" href="https://clinicaltrials.gov/study/${encodeURIComponent(d.best_trial.nct_id)}" target="_blank" rel="noopener noreferrer">${escHtml(d.best_trial.nct_id)}</a>
          <span class="trial-chip-why">${escHtml(d.best_trial.why_relevant||d.best_trial.title||'')}</span>
        </div>
      </div>`;
    }

    body.innerHTML = html;
    refreshGeneratedActionControls();
    if (followUpControlsLocked()) setFollowUpMutationBusy(true);
  }

  // ── Tutkimukset / Artikkelit Modal ───────────────────────────────────────────────
  async function removeItem(type, id, button) {
    const endpoint = type === 'trials' ? `/api/trials/${encodeURIComponent(id)}` : `/api/papers/${encodeURIComponent(id)}`;
    try {
      await requireOk(await fetch(endpoint, { method: 'DELETE' }));
      const el = button?.closest('.modal-item');
      if (el) el.remove();
      // Refresh sidebar counts
      await loadStatus();
    } catch (error) {
      reportLoadError('action', error);
    }
  }

  async function openModal(type) {
    const requestPhiEpoch = phiEpoch;
    const trigger = document.activeElement;
    const overlay = document.getElementById('modal-overlay');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.getElementById('modal-title').textContent =
      type === 'trials' ? 'Clinical trials' : 'Research papers';
    document.getElementById('modal-body').innerHTML =
      '<div class="modal-empty">Loading…</div>';
    activateDialog(overlay.querySelector('.modal'), trigger);

    try {
      const r = await fetch(`/api/${type}`);
      const items = await readJsonResponse(r);
      if (requestPhiEpoch !== phiEpoch) return;
      renderModal(type, items);
    } catch(e) {
      if (requestPhiEpoch !== phiEpoch) return;
      document.getElementById('modal-body').innerHTML =
        `<div class="modal-empty">Could not load these items. ${escHtml(e.message)}</div>`;
    }
  }

  function closeModal(e) {
    if (!e || e.target === document.getElementById('modal-overlay') || !e.target) {
      document.getElementById('modal-overlay').classList.remove('open');
      document.getElementById('modal-overlay').setAttribute('aria-hidden', 'true');
      deactivateDialog(document.querySelector('#modal-overlay .modal'));
    }
  }

  function renderModal(type, items) {
    const body = document.getElementById('modal-body');
    if (!items.length) {
      body.innerHTML = `<div class="modal-empty">No ${type} found yet.<br>Run a digest to search for relevant ${type}.</div>`;
      return;
    }

    const idField = type === 'trials' ? 'nct_id' : 'pmid';
    const updateField = type === 'trials' ? 'trial_ids' : 'paper_ids';
    const newIds = new Set(
      Array.isArray(latestResearchUpdate?.[updateField])
        ? latestResearchUpdate[updateField].map(String)
        : []
    );
    const orderedItems = [...items].sort(
      (a, b) => Number(newIds.has(String(b[idField] || ''))) - Number(newIds.has(String(a[idField] || '')))
    );
    const newCount = orderedItems.filter(item => newIds.has(String(item[idField] || ''))).length;
    document.getElementById('modal-title').textContent =
      `${type === 'trials' ? 'Clinical trials' : 'Research papers'}${newCount ? ` · ${newCount} new` : ''}`;

    if (type === 'trials') {
      body.innerHTML = orderedItems.map(t => {
        const url = safeExternalUrl(t.url);
        const isNew = newIds.has(String(t.nct_id || ''));
        return `
        <div class="modal-item${isNew ? ' new-research' : ''}">
          <div class="modal-item-heading">
            <div class="modal-item-title">${escHtml(t.title || 'Untitled')}</div>
            ${isNew ? '<span class="new-research-badge">New</span>' : ''}
          </div>
          <div class="modal-item-meta">
            <span class="modal-item-id">${escHtml(t.nct_id || '')}</span>
            <span class="modal-tag ${(t.status||'').toLowerCase() === 'recruiting' ? 'recruiting' : ''}">${escHtml(t.status || '—')}</span>
            ${t.phase ? `<span class="modal-tag">${escHtml(t.phase)}</span>` : ''}
            ${(t.countries||[]).length ? `<span class="modal-item-sub">${escHtml(t.countries.join(', '))}</span>` : ''}
            ${url ? `<a class="modal-item-link" href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">View ↗</a>` : ''}
            <button class="modal-close" data-item-id="${escHtml(t.nct_id)}" style="margin-left:auto" title="Remove tracked trial" aria-label="Remove tracked trial" onclick="removeItem('trials',this.dataset.itemId,this)">✕</button>
          </div>
          ${t.brief_summary ? `<div class="modal-item-sub" style="margin-top:5px;color:var(--text2)">${escHtml(t.brief_summary.slice(0,200))}${t.brief_summary.length>200?'…':''}</div>` : ''}
          <div style="font-family:var(--mono);font-size:10px;color:var(--text2);margin-top:4px">Added ${escHtml(fmtDate(t.date_added||''))}</div>
        </div>`;
      }).join('');
    } else {
      body.innerHTML = orderedItems.map(p => {
        const url = safeExternalUrl(p.url);
        const isNew = newIds.has(String(p.pmid || ''));
        return `
        <div class="modal-item${isNew ? ' new-research' : ''}">
          <div class="modal-item-heading">
            <div class="modal-item-title">${escHtml(p.title || 'Untitled')}</div>
            ${isNew ? '<span class="new-research-badge">New</span>' : ''}
          </div>
          <div class="modal-item-meta">
            <span class="modal-item-id">PMID ${escHtml(p.pmid || '')}</span>
            <span class="modal-item-sub">${escHtml(p.journal || '')}${p.date ? ' · ' + escHtml(p.date) : ''}</span>
            ${url ? `<a class="modal-item-link" href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">PubMed ↗</a>` : ''}
            <button class="modal-close" data-item-id="${escHtml(p.pmid)}" style="margin-left:auto" title="Remove tracked paper" aria-label="Remove tracked paper" onclick="removeItem('papers',this.dataset.itemId,this)">✕</button>
          </div>
          ${p.authors ? `<div class="modal-item-sub" style="margin-top:3px">${escHtml(p.authors)}</div>` : ''}
          <div style="font-family:var(--mono);font-size:10px;color:var(--text2);margin-top:4px">Query: ${escHtml(p.query||'')} · Added ${escHtml(fmtDate(p.date_added||''))}</div>
        </div>`;
      }).join('');
    }
  }

  // ── Task log ────────────────────────────────────────────────────────────
  async function loadTasks() {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++taskLoadEpoch;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request) && requestLoadEpoch === taskLoadEpoch
    );
    try {
      const r = await fetch('/api/jobs');
      if (!requestIsCurrent()) return null;
      const tasks = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      if (!authorizePatientResponse(request, tasks).accepted) return [];
      if (tasks.some(t => t.status === 'running' || t.status === 'queued')) {
        hadActiveJobs = true;
      }
      renderTasks(tasks);
      revalidateOpenTask(tasks);
      updateHeaderStatus(tasks);
      reportLoadSuccess('tasks');
      return tasks;
    } catch(e) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(e)) {
        reportLoadError('tasks', e);
        if (requestIsCurrent()) evictClientPhi(e);
        return null;
      }
      document.getElementById('task-list').innerHTML = loadFailureMarkup('Processing activity', 'loadTasks()');
      document.getElementById('log-count').textContent = 'Unavailable';
      updateHeaderStatus(null, e);
      reportLoadError('tasks', e);
      return null;
    }
  }

  function renderTasks(tasks) {
    document.getElementById('log-count').textContent = `${tasks.length} task${tasks.length !== 1 ? 's' : ''}`;

    if (!tasks.length) {
      document.getElementById('task-list').innerHTML =
        '<div class="empty-state">No tasks yet.<br>Feed a document to begin.</div>';
      return;
    }

    document.getElementById('task-list').innerHTML = tasks.map(t => `
      <button class="task-item status-${safeClassToken(t.status, 'unknown')} ${selectedTaskId === t.id ? 'selected' : ''}"
           data-task-id="${escHtml(t.id)}" onclick="selectTask(this.dataset.taskId)">
        <div class="task-header">
          <span class="task-type ${t.type === 'digest' ? 'digest' : (t.type === 'deep-sweep' ? 'deep-sweep' : '')}">${escHtml(t.type || 'task')}</span>
          ${t.doc_type ? `<span class="task-doctype">${escHtml(docTypeLabel(t))}</span>` : ''}
          <span class="task-time">${escHtml(relativeTime(t.created_at))}</span>
        </div>
        <div class="task-preview">${t.derived_content_stale ? escHtml(staleTaskCopy(t).preview) : escHtml((t.summary || t.input_preview || '').slice(0, 100))}</div>
        <div class="task-status-row">
          <span class="status-badge ${safeClassToken(t.status, 'unknown')}">${escHtml(translateStatus(t.status))}</span>
          ${t.status === 'done' && duration(t) ? `<span class="task-duration">${escHtml(duration(t))}</span>` : ''}
          ${t.status === 'error' ? `<span class="task-duration" style="color:var(--red)">${escHtml((t.error||'').slice(0,60))}</span>` : ''}
          ${t.status === 'interrupted' ? `<span class="task-duration" style="color:var(--amber)">${escHtml((t.retry_guidance||t.error||'Interrupted').slice(0,60))}</span>` : ''}
        </div>
      </button>`).join('');
  }

  function staleTaskCopy(task) {
    const type = task.type === 'deep-sweep'
      ? 'Deep-sweep report'
      : task.type === 'digest'
        ? 'Digest report'
        : task.type === 'feed'
          ? 'Document analysis'
          : 'Generated result';
    if (task.derived_content_stale_reason === 'source_document_corrected_or_undone') {
      return {
        title: 'Document analysis is outdated',
        detail: 'The source document was corrected or undone.',
        preview: 'Document corrected — prior analysis hidden',
      };
    }
    if (task.derived_content_stale_reason === 'freshness_cannot_be_verified') {
      return {
        title: `${type} freshness cannot be verified`,
        detail: 'This retained legacy task has no source profile revision.',
        preview: `${type} freshness cannot be verified`,
      };
    }
    if (task.derived_content_stale_reason === 'generated_content_invalidated') {
      return {
        title: `${type} is outdated`,
        detail: 'Generated content was invalidated by a review-state change.',
        preview: `${type} outdated — review state changed`,
      };
    }
    if (task.derived_content_stale_reason === 'question_generation_superseded') {
      return {
        title: 'Generated questions are superseded',
        detail: 'A newer appointment-question generation replaced this result.',
        preview: 'Generated questions superseded by a newer run',
      };
    }
    return {
      title: `${type} is outdated`,
      detail: 'The patient record changed after this task was generated.',
      preview: `${type} outdated — patient record changed`,
    };
  }

  function clearReportCopyState() {
    currentReportText = '';
    const copy = document.getElementById('copy-btn');
    if (copy) {
      copy.classList.remove('visible');
      copy.disabled = true;
    }
  }

  function revalidateOpenTask(tasks) {
    const panel = document.getElementById('report-panel');
    if (!selectedTaskId || panel?.classList.contains('collapsed')) return;
    const task = tasks.find(item => item.id === selectedTaskId);
    if (!task?.derived_content_stale) return;
    const copy = staleTaskCopy(task);
    const receiptHtml = currentReceipt?.job_id === selectedTaskId
      ? renderReceipt(currentReceipt)
      : '';
    document.getElementById('panel-body').innerHTML = `${receiptHtml}
      <div class="load-failure stale-artifact" role="alert">
        <strong>${escHtml(copy.title)}</strong><span>${escHtml(copy.detail)} The original artifact remains retained for audit.</span>
      </div>`;
    clearReportCopyState();
  }

  function updateHeaderStatus(tasks, error = null) {
    const running = Array.isArray(tasks)
      ? tasks.filter(t => t.status === 'running' || t.status === 'queued')
      : [];
    const bar = document.getElementById('running-bar');
    const dot = document.getElementById('pulse-dot');
    const lbl = document.getElementById('header-status');
    const navCount = document.getElementById('nav-running-count');
    if (error) {
      bar.classList.remove('visible');
      dot.style.background = 'var(--red)';
      lbl.textContent = 'Unavailable';
      if (navCount) navCount.hidden = true;
    } else if (running.length) {
      bar.classList.add('visible');
      dot.style.background = 'var(--amber)';
      lbl.textContent = `Processing ${running.length}`;
      if (navCount) {
        navCount.textContent = running.length;
        navCount.hidden = false;
      }
    } else {
      bar.classList.remove('visible');
      dot.style.background = 'var(--accent)';
      lbl.textContent = 'Idle';
      if (navCount) navCount.hidden = true;
    }
  }

  function closePanel() {
    const request = capturePatientRequest();
    const report = document.getElementById('report-panel');
    report.classList.add('collapsed');
    report.setAttribute('aria-hidden', 'true');
    selectedTaskId = null;
    taskSelectionEpoch += 1;
    currentReceipt = null;
    // Re-render task list to clear selection highlight
    fetch('/api/jobs')
      .then(readJsonResponse)
      .then(tasks => {
        if (authorizePatientResponse(request, tasks).accepted) renderTasks(tasks);
      })
      .catch(error => {
        if (patientRequestIsCurrent(request)) reportLoadError('tasks', error);
      });
    deactivateDialog(report);
  }

  function receiptValueSummary(value, category) {
    if (value == null) return 'Not recorded';
    if (typeof value !== 'object') return String(value);
    if (category === 'biomarkers') return `${value.marker || 'Biomarker'}: ${value.value ?? '—'} ${value.unit || ''}`.trim();
    if (category === 'imaging') return `${value.modality || 'Imaging'}: ${value.impression || value.findings || 'Finding recorded'}`;
    if (category === 'symptoms') return `${value.symptom || 'Symptom'}${value.severity ? ` (severity ${value.severity})` : ''}`;
    if (category === 'appointments') return `${value.date || ''} ${value.description || value.type || 'Appointment'}`.trim();
    if (category === 'documents') return value.summary || value.type || 'Document summary';
    if (category === 'alerts') return value.message || 'Safety alert';
    return JSON.stringify(value);
  }

  function renderReceipt(receipt) {
    currentReceipt = receipt;
    const status = safeClassToken(receipt.status, 'active');
    const changes = receipt.changes || [];
    return `<section class="receipt-card" aria-labelledby="receipt-heading">
      <div class="receipt-header">
        <div>
          <p class="eyebrow">Document reconciliation</p>
          <h3 id="receipt-heading">${escHtml(receipt.filename || receipt.document_type || 'Pasted clinical text')}</h3>
          <p>${escHtml(receipt.document_summary || 'Structured import receipt')} · ${escHtml(relativeTime(receipt.ingested_at))}</p>
        </div>
        <span class="import-status ${status}">${escHtml((receipt.status || 'active').replace(/_/g, ' '))}</span>
      </div>
      <div class="receipt-summary">
        <span>${receipt.counts?.added || 0} added</span>
        <span>${(receipt.counts?.updated || 0) + (receipt.counts?.conflict || 0)} changed</span>
        <span>${receipt.counts?.unchanged || 0} unchanged</span>
        <a href="${escHtml(receipt.source_url)}" target="_blank" rel="noopener">Source details</a>
      </div>
      <div class="receipt-error" id="receipt-error" role="alert" aria-live="polite"></div>
      <div class="receipt-changes">${changes.map(change => {
        const operation = safeClassToken(change.operation, 'unchanged');
        const state = safeClassToken(change.state, 'active');
        const editable = change.editable_fields?.length && ['active', 'corrected'].includes(change.state) && !change.conflicted;
        const removable = change.removable !== false && change.target?.kind !== 'none' && ['active', 'corrected'].includes(change.state) && !change.conflicted;
        const history = change.history?.length
          ? `<span class="receipt-history">${change.history.length} audit event${change.history.length === 1 ? '' : 's'}</span>`
          : '';
        const corrected = change.state === 'corrected';
        const firstValue = corrected ? change.after : change.before;
        const secondValue = corrected ? change.effective_value : change.after;
        const firstLabel = corrected ? 'Original extraction' : 'Before';
        const secondLabel = corrected ? 'Caregiver correction' : 'From this document';
        return `<article class="receipt-change ${operation} ${state}" data-change-id="${escHtml(change.id)}">
          <div class="receipt-change-heading">
            <strong>${escHtml(change.label)}</strong>
            <span class="change-badge ${operation}">${escHtml(change.operation)}</span>
            ${change.state !== 'active' ? `<span class="change-badge state">${escHtml(change.state)}</span>` : ''}
          </div>
          ${corrected || change.operation === 'updated' || change.operation === 'conflict'
            ? `<div class="value-diff"><span><small>${firstLabel}</small>${escHtml(receiptValueSummary(firstValue, change.category))}</span><span class="diff-arrow" aria-hidden="true">→</span><span><small>${secondLabel}</small>${escHtml(receiptValueSummary(secondValue, change.category))}</span></div>`
            : `<div class="receipt-value">${escHtml(receiptValueSummary(change.effective_value, change.category))}</div>`}
          <div class="receipt-provenance">
            ${evidenceBadge(change.evidence_status)}
            ${change.evidence_url ? `<a href="${escHtml(change.evidence_url)}" target="_blank" rel="noopener">Open exact span</a>` : ''}
            ${change.original_evidence_url ? `<a href="${escHtml(change.original_evidence_url)}" target="_blank" rel="noopener">Original extraction span (before correction)</a>` : ''}
            ${history}
          </div>
          ${change.conflicted ? `<div class="receipt-conflict">${escHtml(change.conflict_reason || 'This patient value changed later. Reload before editing.')}</div>` : ''}
          <div class="receipt-edit-slot"></div>
          ${(editable || removable) ? `<div class="receipt-actions">
            ${editable ? `<button class="button secondary" data-change-id="${escHtml(change.id)}" onclick="startReceiptCorrection(this.dataset.changeId)">Correct value</button>` : ''}
            ${removable ? `<button class="button danger-secondary" data-change-id="${escHtml(change.id)}" onclick="removeReceiptChange(this.dataset.changeId)">Remove imported value</button>` : ''}
          </div>` : ''}
        </article>`;
      }).join('')}</div>
      ${receipt.status !== 'undone' ? `<div class="receipt-undo">
        <div><strong>Undo this document’s structured changes</strong><p>The original source remains in history. Research findings are not deleted.</p></div>
        <button class="button danger-secondary" onclick="undoReceipt()" ${receipt.can_undo ? '' : 'disabled'}>Undo document changes</button>
      </div>` : ''}
    </section>`;
  }

  function receiptFieldInput(field, value) {
    const id = `receipt-field-${field}`;
    if (field === 'key_findings') {
      return `<label><span>Key findings (one per line)</span><textarea id="${id}" data-field="${field}" data-kind="array">${escHtml((value || []).join('\n'))}</textarea></label>`;
    }
    if (field === 'new_lesions' || typeof value === 'boolean') {
      return `<label><span>${escHtml(field.replace(/_/g, ' '))}</span><select id="${id}" data-field="${field}" data-kind="boolean"><option value=""${value == null ? ' selected' : ''}>Not set</option><option value="true"${value === true ? ' selected' : ''}>Yes</option><option value="false"${value === false ? ' selected' : ''}>No</option></select></label>`;
    }
    const kind = field === 'severity' || typeof value === 'number' ? 'number' : 'string';
    return `<label><span>${escHtml(field.replace(/_/g, ' '))}</span><input id="${id}" data-field="${field}" data-kind="${kind}" value="${escHtml(value ?? '')}"></label>`;
  }

  function startReceiptCorrection(changeId) {
    const change = currentReceipt?.changes?.find(item => item.id === changeId);
    const row = document.querySelector(`.receipt-change[data-change-id="${CSS.escape(changeId)}"]`);
    const slot = row?.querySelector('.receipt-edit-slot');
    if (!change || !slot || change.conflicted) return;
    const current = change.effective_value;
    const fields = change.editable_fields || [];
    const inputs = change.target?.kind === 'collection'
      ? fields.map(field => receiptFieldInput(field, current?.[field])).join('')
      : receiptFieldInput('value', current);
    slot.innerHTML = `<div class="receipt-editor">
      ${inputs}
      <div class="receipt-editor-actions">
        <button class="button primary receipt-save" data-change-id="${escHtml(changeId)}" onclick="saveReceiptCorrection(this.dataset.changeId)" disabled>Save correction</button>
        <button class="button secondary" onclick="this.closest('.receipt-editor').remove()">Cancel</button>
      </div>
    </div>`;
    const controls = [...slot.querySelectorAll('[data-field]')];
    const save = slot.querySelector('.receipt-save');
    const initial = JSON.stringify(controls.map(input => parsedReceiptInput(input)));
    controls.forEach(input => input.addEventListener('input', () => {
      save.disabled = JSON.stringify(controls.map(control => parsedReceiptInput(control))) === initial;
    }));
    controls[0]?.focus();
  }

  function parsedReceiptInput(input) {
    if (input.dataset.kind === 'array') return input.value.split('\n').map(item => item.trim()).filter(Boolean);
    if (input.dataset.kind === 'boolean') return input.value === '' ? null : input.value === 'true';
    if (input.dataset.kind === 'number') {
      if (!input.value.trim()) return null;
      const value = Number(input.value);
      return Number.isFinite(value) ? value : input.value;
    }
    return input.value.trim() || null;
  }

  async function saveReceiptCorrection(changeId) {
    const change = currentReceipt?.changes?.find(item => item.id === changeId);
    const row = document.querySelector(`.receipt-change[data-change-id="${CSS.escape(changeId)}"]`);
    const inputs = [...(row?.querySelectorAll('.receipt-editor [data-field]') || [])];
    if (!change || !inputs.length) return;
    let replacement;
    if (change.target?.kind === 'collection') {
      replacement = Object.fromEntries(inputs.map(input => [input.dataset.field, parsedReceiptInput(input)]));
    } else {
      replacement = parsedReceiptInput(inputs[0]);
    }
    await submitReceiptMutation(
      `/api/jobs/${encodeURIComponent(currentReceipt.job_id)}/receipt/changes/${encodeURIComponent(changeId)}/correct`,
      {
        receipt_revision: currentReceipt.receipt_revision,
        target_token: change.target_token,
        replacement,
      },
    );
  }

  async function removeReceiptChange(changeId) {
    const change = currentReceipt?.changes?.find(item => item.id === changeId);
    if (!change || !confirm(`Remove the imported value “${change.label}”? The original source remains available.`)) return;
    await submitReceiptMutation(
      `/api/jobs/${encodeURIComponent(currentReceipt.job_id)}/receipt/changes/${encodeURIComponent(changeId)}/remove`,
      {
        receipt_revision: currentReceipt.receipt_revision,
        target_token: change.target_token,
      },
    );
  }

  async function undoReceipt() {
    if (!currentReceipt?.can_undo || !confirm('Undo this document’s structured changes? The original source and audit history will remain.')) return;
    await submitReceiptMutation(
      `/api/jobs/${encodeURIComponent(currentReceipt.job_id)}/receipt/undo`,
      {
        receipt_revision: currentReceipt.receipt_revision,
        undo_token: currentReceipt.undo_token,
      },
    );
  }

  async function submitReceiptMutation(url, body) {
    if (receiptMutationPending || !currentReceipt) return;
    const originJobId = currentReceipt.job_id;
    const originReceiptRevision = currentReceipt.receipt_revision;
    const originSelectionEpoch = taskSelectionEpoch;
    const request = capturePatientRequest({ taskSelection: true });
    receiptMutationPending = true;
    document.querySelectorAll('.receipt-card button').forEach(button => {
      button.dataset.pendingWasDisabled = String(button.disabled);
      button.disabled = true;
    });
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (response.status === 401 || response.status === 403) {
        const authError = new Error('Authorization failed.');
        authError.status = response.status;
        evictClientPhi(authError);
        throw authError;
      }
      let data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error(`The server returned an invalid response (${response.status}).`);
      }
      if (!authorizePatientResponse(request, data).accepted) return;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          const authError = new Error(data.error || 'Authorization failed.');
          authError.status = response.status;
          authError.data = data;
          evictClientPhi(authError);
          throw authError;
        }
        if (response.status === 409 && data.receipt && taskSelectionEpoch === originSelectionEpoch && selectedTaskId === originJobId && currentReceipt?.job_id === originJobId && currentReceipt?.receipt_revision === originReceiptRevision) {
          document.getElementById('panel-body').querySelector('.receipt-card')?.remove();
          document.getElementById('panel-body').insertAdjacentHTML('afterbegin', renderReceipt(data.receipt));
        }
        throw new Error(data.error || `Request failed (${response.status})`);
      }
      const refreshSelectedJob = taskSelectionEpoch === originSelectionEpoch && selectedTaskId === originJobId && currentReceipt?.job_id === originJobId && currentReceipt?.receipt_revision === originReceiptRevision;
      if (refreshSelectedJob) {
        const existing = document.getElementById('panel-body').querySelector('.receipt-card');
        if (existing) existing.outerHTML = renderReceipt(data.receipt);
        await selectTask(originJobId, originSelectionEpoch, data.receipt);
      }
      await Promise.allSettled([loadStatus(), loadSummary(), loadPatientEvidence()]);
      if (patientRequestIsCurrent(request)) reportLoadSuccess('action');
    } catch (error) {
      if (!patientRequestIsCurrent(request)) return;
      if (taskSelectionEpoch === originSelectionEpoch && selectedTaskId === originJobId && currentReceipt?.job_id === originJobId) {
        const target = document.getElementById('receipt-error');
        if (target) target.textContent = error.message || 'The receipt could not be updated.';
      }
      reportLoadError('action', error);
    } finally {
      receiptMutationPending = false;
      if (
        patientRequestIsCurrent(request)
        && taskSelectionEpoch === originSelectionEpoch
        && selectedTaskId === originJobId
      ) {
        document.querySelectorAll('.receipt-card button[data-pending-was-disabled]').forEach(button => {
          button.disabled = button.dataset.pendingWasDisabled === 'true';
          delete button.dataset.pendingWasDisabled;
        });
      }
    }
  }

  function receiptRefreshFailureMarkup(receipt, jobId, message) {
    return `${renderReceipt(receipt)}
      <div class="receipt-refresh-warning" role="status">
        <strong>Correction saved successfully.</strong>
        <span>${escHtml(message || 'Activity detail could not be refreshed.')}</span>
        <button class="button secondary" data-job-id="${escHtml(jobId)}" onclick="selectTask(this.dataset.jobId)">Retry detail refresh</button>
      </div>`;
  }

  async function selectTask(id, expectedEpoch = null, fallbackReceipt = null) {
    const selectionEpoch = expectedEpoch == null ? ++taskSelectionEpoch : expectedEpoch;
    if (selectionEpoch !== taskSelectionEpoch) return;
    selectedTaskId = id;
    const request = capturePatientRequest({ taskSelection: true });
    currentReceipt = fallbackReceipt;
    currentReportText = '';
    const loadingPanel = document.getElementById('panel-body');
    if (loadingPanel) {
      loadingPanel.innerHTML = fallbackReceipt
        ? `${renderReceipt(fallbackReceipt)}<div class="loading-state">Saved. Refreshing activity detail…</div>`
        : '<div class="loading-state">Loading activity detail…</div>';
    }
    document.getElementById('copy-btn')?.classList.remove('visible');
    // Open panel
    lastDialogTrigger = document.activeElement;
    const report = document.getElementById('report-panel');
    report.classList.remove('collapsed');
    report.setAttribute('aria-hidden', 'false');
    activateDialog(report, lastDialogTrigger);
    // Re-render task list to update selection
    let tasks;
    try {
      const r = await fetch('/api/jobs');
      tasks = await readJsonResponse(r);
      if (!authorizePatientResponse(request, tasks).accepted) return false;
    } catch (error) {
      if (!patientRequestIsCurrent(request)) return false;
      if (shouldEvictClientPhi(error) && !fallbackReceipt) {
        evictClientPhi(error);
      }
      if (!patientRequestIsCurrent(request)) return false;
      document.getElementById('panel-body').innerHTML = fallbackReceipt
        ? receiptRefreshFailureMarkup(fallbackReceipt, id, error.message)
        : loadFailureMarkup('Activity detail', 'loadTasks()');
      reportLoadError('tasks', error);
      return false;
    }
    renderTasks(tasks);

    let task = tasks.find(t => t.id === id);
    if (!task) {
      const missingError = new Error('The selected activity no longer exists.');
      evictClientPhi(missingError);
      reportLoadError('tasks', missingError);
      return false;
    }
    if (task.status === 'done' || task.status === 'error' || task.status === 'interrupted') {
      try {
        const detailResponse = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
        task = await readJsonResponse(detailResponse);
        if (!authorizePatientResponse(request, task).accepted) return false;
      } catch (error) {
        if (!patientRequestIsCurrent(request)) return false;
        if (fallbackReceipt) {
          document.getElementById('panel-body').innerHTML = receiptRefreshFailureMarkup(
            fallbackReceipt, id, error.message
          );
          reportLoadError('tasks', error);
          return false;
        }
        if (shouldEvictClientPhi(error)) evictClientPhi(error);
        reportLoadError('tasks', error);
        return false;
      }
    }

    const panel = document.getElementById('panel-body');
    const copyBtn = document.getElementById('copy-btn');

    let receiptHtml = '';
    currentReceipt = fallbackReceipt;
    if (fallbackReceipt) receiptHtml = renderReceipt(fallbackReceipt);
    if (task.receipt_url) {
      try {
        const receiptResponse = await fetch(task.receipt_url);
        const receipt = await readJsonResponse(receiptResponse);
        if (!authorizePatientResponse(request, receipt).accepted) return false;
        receiptHtml = renderReceipt(receipt);
      } catch (error) {
        if (!patientRequestIsCurrent(request)) return false;
        if (error?.status === 401 || error?.status === 403) {
          evictClientPhi(error);
          reportLoadError('tasks', error);
          return false;
        }
        receiptHtml = fallbackReceipt
          ? renderReceipt(fallbackReceipt)
          : `<div class="receipt-error visible">The import receipt could not be loaded. ${escHtml(error.message)}</div>`;
      }
    }
    if (!patientRequestIsCurrent(request)) return false;

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
      return true;
    }

    if (task.status === 'error') {
      panel.innerHTML = `${receiptHtml}<div class="report-text" style="color:var(--red)">Error:\n\n${escHtml(task.error || 'Unknown error')}</div>`;
      copyBtn.classList.remove('visible');
      currentReportText = '';
      return true;
    }

    if (task.status === 'interrupted') {
      panel.innerHTML = `${receiptHtml}<div class="report-text" style="color:var(--amber)">Interrupted:\n\n${escHtml(task.retry_guidance || task.error || 'Re-submit this request to retry.')}</div>`;
      copyBtn.classList.remove('visible');
      currentReportText = '';
      return true;
    }

    // Show key findings chips if present
    let html = receiptHtml;
    if (!task.derived_content_stale && task.key_findings && task.key_findings.length) {
      html += `<div class="findings-chips">${task.key_findings.map(f =>
        `<span class="finding-chip">${escHtml(f)}</span>`).join('')}</div>`;
    }

    // Job details hydrate report artifacts on demand.
    if (task.report_stale) {
      const staleCopy = staleTaskCopy({
        ...task,
        derived_content_stale_reason: task.report_stale_reason,
      });
      html += `<div class="load-failure stale-artifact" role="alert">
        <strong>${escHtml(staleCopy.title)}</strong>
        <span>${escHtml(staleCopy.detail)} The original report remains retained for audit but is hidden here.</span>
      </div>`;
      clearReportCopyState();
    } else if (task.report) {
      currentReportText = task.report;
      html += `<div class="report-text">${formatReport(task.report)}</div>`;
      copyBtn.classList.add('visible');
      copyBtn.disabled = false;
    } else if (task.result) {
      if (task.result.stale) {
        const staleCopy = staleTaskCopy(task);
        html += `<div class="load-failure stale-artifact" role="alert">
          <strong>${escHtml(staleCopy.title)}</strong>
          <span>${escHtml(staleCopy.detail)} Regenerate it before use.</span>
        </div>`;
        clearReportCopyState();
      } else {
        currentReportText = JSON.stringify(task.result, null, 2);
        html += `<div class="report-text">${formatReport(currentReportText)}</div>`;
        copyBtn.classList.add('visible');
        copyBtn.disabled = false;
      }
    } else {
      html += `<div class="report-text" style="color:var(--text2)">No report generated.</div>`;
    }

    panel.innerHTML = html;
    return true;
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
    const trigger = document.activeElement;
    pop.classList.toggle('visible', willShow);
    back.classList.toggle('visible', willShow);
    pop.setAttribute('aria-hidden', String(!willShow));
    if (willShow) {
      const error = document.getElementById('feed-form-error');
      error.hidden = true;
      error.textContent = '';
      activateDialog(pop, trigger);
      setTimeout(() => {
        const ta = document.getElementById('feed-textarea');
        if (ta && document.getElementById('tab-text').classList.contains('visible')) ta.focus();
      }, 50);
    } else {
      deactivateDialog(pop);
    }
  }
  document.addEventListener('keydown', (e) => {
    if (trapDialogFocus(e)) return;
    if (e.key !== 'Escape') return;
    if (followUpDialogOpen) {
      closeFollowUpDialog();
      return;
    }
    if (appointmentDialogOpen) {
      closeAppointmentWorkspace();
      return;
    }
    const pop = document.getElementById('feed-popover');
    if (pop?.classList.contains('visible')) {
      toggleFeedPopover(false);
      return;
    }
    if (document.getElementById('modal-overlay')?.classList.contains('open')) {
      closeModal();
      return;
    }
    if (!document.getElementById('report-panel')?.classList.contains('collapsed')) {
      closePanel();
      return;
    }
    if (chatOpen) toggleChat();
  });

  function switchTab(tab) {
    const textButton = document.getElementById('feed-tab-text');
    const fileButton = document.getElementById('feed-tab-file');
    textButton.classList.toggle('active', tab === 'text');
    textButton.setAttribute('aria-selected', String(tab === 'text'));
    textButton.tabIndex = tab === 'text' ? 0 : -1;
    fileButton.classList.toggle('active', tab === 'file');
    fileButton.setAttribute('aria-selected', String(tab === 'file'));
    fileButton.tabIndex = tab === 'file' ? 0 : -1;
    document.getElementById('tab-text').classList.toggle('visible', tab === 'text');
    document.getElementById('tab-text').setAttribute('aria-hidden', String(tab !== 'text'));
    document.getElementById('tab-file').classList.toggle('visible', tab === 'file');
    document.getElementById('tab-file').setAttribute('aria-hidden', String(tab !== 'file'));
  }

  function handleFeedTabKeydown(event) {
    const tabs = [document.getElementById('feed-tab-text'), document.getElementById('feed-tab-file')];
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    switchTab(next === 0 ? 'text' : 'file');
    tabs[next].focus();
  }

  function updateCharCount() {
    const value = document.getElementById('feed-textarea').value;
    const n = value.length;
    document.getElementById('char-count').textContent = `${n.toLocaleString()} characters`;
    document.getElementById('btn-feed').disabled = value.trim().length === 0;
    if (value.trim()) {
      const error = document.getElementById('feed-form-error');
      error.hidden = true;
      error.textContent = '';
    }
  }

  async function feedText() {
    const text = document.getElementById('feed-textarea').value.trim();
    if (!text) {
      showFeedError('Paste clinical text before processing the document.');
      return;
    }
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
      reportLoadSuccess('action');
      return true;
    } catch (e) {
      showFeedError(e.message);
      return false;
    } finally {
      document.getElementById('btn-feed').disabled = false;
    }
  }

  async function activateSubmittedTask(data) {
    const id = data.job_id || data.task_id;
    if (!id) throw new Error('Response did not include a job ID');
    const activationEpoch = ++taskSelectionEpoch;
    hadActiveJobs = true;
    selectedTaskId = id;
    await loadTasks();
    if (activationEpoch !== taskSelectionEpoch || selectedTaskId !== id) return;
    await selectTask(id, activationEpoch);
    if (activationEpoch !== taskSelectionEpoch || selectedTaskId !== id) return;
    switchView('activity');
    if (activationEpoch !== taskSelectionEpoch || selectedTaskId !== id) return;
    startPolling();
  }

  function showFeedError(message) {
    const error = document.getElementById('feed-form-error');
    error.textContent = message || 'The document could not be submitted.';
    error.hidden = false;
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
    const allowed = ['text/plain', 'text/markdown', 'application/pdf'];
    const extensionAllowed = /\.(txt|text|md|pdf)$/i.test(file?.name || '');
    if (!file || file.size === 0) {
      showFeedError('Choose a non-empty text, Markdown, or PDF file.');
      return false;
    }
    if (file.size > 20 * 1024 * 1024) {
      showFeedError('The file exceeds the 20 MB upload limit.');
      return false;
    }
    if (!extensionAllowed && !allowed.includes(file.type)) {
      showFeedError('Choose a .txt, .md, or .pdf file.');
      return false;
    }
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
      reportLoadSuccess('action');
      return true;
    } catch (e) {
      showFeedError(e.message);
      return false;
    } finally {
      updateCharCount();
    }
  }

  async function runDigest() {
    const btn = document.getElementById('btn-digest');
    btn.disabled = true;
    try {
      const r = await fetch('/api/digest', { method: 'POST' });
      const d = await readJobSubmission(r);
      await activateSubmittedTask(d);
      reportLoadSuccess('action');
    } catch (e) {
      reportLoadError('action', e);
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
      reportLoadSuccess('action');
    } catch (e) {
      reportLoadError('action', e);
    } finally {
      btn.disabled = false;
    }
  }

  // ── Polling loop ────────────────────────────────────────────────────────
  function startPolling() {
    if (pollingInterval) clearTimeout(pollingInterval);
    const poll = async () => {
      const tasks = await loadTasks();
      const hasActiveJobs = tasks.some(t => t.status === 'running' || t.status === 'queued');

      if (hasActiveJobs || (activeView === 'today' && !document.hidden)) {
        await loadStatus();
      }
      if (hadActiveJobs && !hasActiveJobs) {
        const refreshes = [loadSummary()];
        if (activeView !== 'today') refreshes.push(loadStatus());
        await Promise.allSettled(refreshes);
      }

      // If selected task just completed, auto-load its report and refresh summary.
      if (selectedTaskId) {
        try {
          const t = tasks.find(task => task.id === selectedTaskId);
          if (t && (t.status === 'done' || t.status === 'error' || t.status === 'interrupted')) {
            const panel = document.getElementById('panel-body');
            if (panel.querySelector('.report-empty')) {
              await selectTask(selectedTaskId);
            }
          }
        } catch (error) {
          reportLoadError('tasks', error);
        }
      }

      hadActiveJobs = hasActiveJobs;
      const delay = document.hidden ? 60000 : (hasActiveJobs ? 3000 : 30000);
      pollingInterval = setTimeout(poll, delay);
    };
    pollingInterval = setTimeout(poll, 3000);
  }

  // ── Appointment working mode ────────────────────────────────────────────
  function currentVisit() {
    return selectedVisitId ? visitsById.get(selectedVisitId) || null : null;
  }

  function visitStatusLabel(status) {
    return {
      planned: 'Planned',
      in_progress: 'In progress',
      completed: 'Completed',
      cancelled: 'Cancelled',
    }[status] || 'Planned';
  }

  function sortedVisitQuestions(visit) {
    return [...(visit?.question_snapshots || [])].sort((a, b) => {
      if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
      const order = Number(a.order || 0) - Number(b.order || 0);
      return order || String(a.created_at || '').localeCompare(String(b.created_at || ''));
    });
  }

  function linkableAppointment(id) {
    return appointmentOptions.find(item => item.id === id) || null;
  }

  async function loadVisits() {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++visitLoadEpoch;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request) && requestLoadEpoch === visitLoadEpoch
    );
    try {
      const response = await fetch('/api/visits');
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, data, { workflow: 'projection' });
      if (!authority.accepted) return null;
      if (appointmentDialogOpen) captureAppointmentDraft();
      visitsById = new Map((data.items || []).map(item => [item.id, item]));
      decisionSuccessorConflicts = new Set();
      appointmentOptions = Array.isArray(data.appointments) ? data.appointments : [];
      if (selectedVisitId && !visitsById.has(selectedVisitId)) {
        selectedVisitId = null;
        visitSelectionEpoch += 1;
        closeAppointmentWorkspace();
      }
      renderAppointmentOptions();
      renderVisitPreparation();
      if (appointmentDialogOpen) renderAppointmentWorkspace();
      reportLoadSuccess('visits');
      const items = data.items || [];
      items.profileRevision = data.profile_revision;
      items.workflowRevision = data.workflow_revision;
      return items;
    } catch (error) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('visits', error);
        if (requestIsCurrent()) evictClientPhi(error);
        return null;
      } else {
        const list = document.getElementById('visit-list');
        if (list) list.innerHTML = loadFailureMarkup('Appointments', 'loadVisits()');
      }
      reportLoadError('visits', error);
      return null;
    }
  }

  function followUpItems() {
    return [...followUpsById.values()];
  }

  function followUpStatusLabel(status) {
    return {
      open: 'Open',
      in_progress: 'In progress',
      completed: 'Completed',
      cancelled: 'Cancelled',
    }[status] || 'Unavailable';
  }

  function localDateIso(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function dueDatePresentation(item) {
    if (!item?.due_date) return { label: 'No due date', tone: '' };
    if (!['open', 'in_progress'].includes(item.status)) {
      return { label: `Due ${fmtDate(item.due_date)}`, tone: '' };
    }
    const today = localDateIso();
    if (item.due_date < today) {
      return { label: `Overdue · ${fmtDate(item.due_date)}`, tone: 'overdue' };
    }
    const due = new Date(`${item.due_date}T12:00:00`);
    const now = new Date(`${today}T12:00:00`);
    const days = Math.round((due - now) / 86400000);
    if (days >= 0 && days <= 7) {
      return {
        label: days === 0 ? 'Due today' : `Due soon · ${fmtDate(item.due_date)}`,
        tone: 'soon',
      };
    }
    return { label: `Due ${fmtDate(item.due_date)}`, tone: '' };
  }

  function followUpOriginLabel(item) {
    const origin = item?.origin_snapshot || {};
    if (origin.kind === 'executive_summary_action') {
      return `Generated action snapshot · record revision ${origin.source_profile_revision ?? 'unavailable'} · generation ${origin.generation_id || 'unavailable'}`;
    }
    if (origin.kind === 'visit_decision') return 'Caregiver follow-up from a visit decision';
    if (origin.kind === 'alert') return 'Caregiver follow-up from an alert';
    return 'Manual caregiver follow-up';
  }

  function followUpOutcomePresentation(outcome) {
    if (!outcome) return null;
    if (outcome.kind === 'clinician_attributed') {
      return {
        label: 'Caregiver-entered · attributed to clinician · unverified',
        className: 'clinician-attributed',
      };
    }
    if (outcome.kind === 'caregiver_reported') {
      return {
        label: 'Caregiver-entered · caregiver reported · unverified',
        className: 'caregiver-reported',
      };
    }
    return {
      label: 'Caregiver-entered administrative outcome · not clinical evidence',
      className: 'administrative',
    };
  }

  function formatActionTimestamp(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return fmtDate(value);
    return parsed.toLocaleString([], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function setFollowUpStatus(message, tone = '') {
    const status = document.getElementById('follow-up-status');
    if (!status) return;
    status.textContent = message || '';
    status.className = `follow-up-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
  }

  function setFollowUpDialogStatus(message, tone = '') {
    const status = document.getElementById('follow-up-dialog-status');
    if (!status) return;
    status.textContent = message || '';
    status.className = `follow-up-dialog-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
  }

  function renderFollowUps() {
    const list = document.getElementById('follow-up-list');
    if (!list) return;
    const items = followUpItems();
    const staleNotice = followUpProjectionStale
      ? `<div class="follow-up-stale-note" role="status">
          <div><strong>Offline snapshot · read-only</strong><span>Reload the current action list before making changes.</span></div>
          <button class="button secondary follow-up-refresh-button" onclick="loadFollowUps()">Reload actions</button>
        </div>`
      : '';
    const createButton = document.getElementById('follow-up-create-button');
    if (createButton) createButton.disabled = followUpProjectionStale || followUpMutationPending;
    const counts = {
      active: items.filter(item => ['open', 'in_progress'].includes(item.status)).length,
      completed: items.filter(item => item.status === 'completed').length,
      cancelled: items.filter(item => item.status === 'cancelled').length,
      all: items.length,
    };
    Object.entries(counts).forEach(([name, count]) => {
      const badge = document.getElementById(`follow-up-count-${name}`);
      if (badge) badge.textContent = String(count);
    });
    const filtered = items.filter(item => (
      followUpFilter === 'all'
      || (followUpFilter === 'active' && ['open', 'in_progress'].includes(item.status))
      || item.status === followUpFilter
    )).sort((a, b) => {
      if (followUpFilter === 'active') {
        const dueA = a.due_date || '9999-12-31';
        const dueB = b.due_date || '9999-12-31';
        return dueA.localeCompare(dueB)
          || String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
      }
      return String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
    });
    list.setAttribute('aria-labelledby', `follow-up-filter-${followUpFilter}`);
    if (!filtered.length) {
      const empty = {
        active: 'No active follow-through tasks.',
        completed: 'No completed follow-through tasks.',
        cancelled: 'No cancelled follow-through tasks.',
        all: 'No follow-through tasks yet.',
      }[followUpFilter];
      list.innerHTML = `${staleNotice}<div class="empty-state">${escHtml(empty)}</div>`;
      refreshGeneratedActionControls();
      if (followUpControlsLocked()) setFollowUpMutationBusy(true);
      return;
    }
    list.innerHTML = filtered.map(item => {
      const due = dueDatePresentation(item);
      const outcome = followUpOutcomePresentation(item.outcome);
      const links = [
        item.visit_id && 'Linked visit',
        item.decision_id && 'Linked decision',
        item.alert_id && 'Linked alert',
      ].filter(Boolean);
      const lifecycle = [];
      if (item.status === 'open') {
        lifecycle.push(`<button class="button primary" ${followUpProjectionStale ? 'disabled' : ''} onclick="changeFollowUpStatus(this.closest('.follow-up-item'),'in_progress')">Start</button>`);
      } else if (item.status === 'in_progress') {
        lifecycle.push(`<button class="button secondary" ${followUpProjectionStale ? 'disabled' : ''} onclick="changeFollowUpStatus(this.closest('.follow-up-item'),'open')">Move to open</button>`);
      }
      if (['open', 'in_progress'].includes(item.status)) {
        lifecycle.push(`<button class="button secondary" ${followUpProjectionStale ? 'disabled' : ''} onclick="openFollowUpOutcomeDialog(this,this.closest('.follow-up-item').dataset.followUpId,'completed')">Complete</button>`);
        lifecycle.push(`<button class="button secondary danger" ${followUpProjectionStale ? 'disabled' : ''} onclick="openFollowUpOutcomeDialog(this,this.closest('.follow-up-item').dataset.followUpId,'cancelled')">Cancel</button>`);
      }
      const terminalAt = item.status === 'completed' ? item.completed_at : item.cancelled_at;
      return `<article class="follow-up-item" data-follow-up-id="${escHtml(item.id)}" data-follow-up-token="${escHtml(item.token)}">
        <div class="follow-up-item-heading">
          <span class="visit-status-badge ${safeClassToken(item.status, 'open')}">${escHtml(followUpStatusLabel(item.status))}</span>
          <span class="follow-up-due ${safeClassToken(due.tone)}">${escHtml(due.label)}</span>
        </div>
        <p class="follow-up-copy">${escHtml(item.text)}</p>
        <p class="follow-up-provenance">${escHtml(followUpOriginLabel(item))}</p>
        <div class="follow-up-metadata">
          <span>${escHtml(item.owner ? `Owner: ${item.owner}` : 'Owner not set')}</span>
          <span>Created ${escHtml(formatActionTimestamp(item.created_at))}</span>
          <span>Updated ${escHtml(formatActionTimestamp(item.updated_at))}</span>
          ${terminalAt ? `<span>${item.status === 'completed' ? 'Completed' : 'Cancelled'} ${escHtml(formatActionTimestamp(terminalAt))}</span>` : ''}
        </div>
        ${links.length ? `<div class="follow-up-links">${links.map(link => `<span>${escHtml(link)}</span>`).join('')}</div>` : ''}
        ${item.outcome ? `<div class="follow-up-outcome ${safeClassToken(outcome.className)}"><strong>Outcome</strong><p>${escHtml(item.outcome.text)}</p><span>${escHtml(outcome.label)}</span>${item.outcome.recorded_at ? `<time>${escHtml(formatActionTimestamp(item.outcome.recorded_at))}</time>` : ''}</div>` : ''}
        <div class="follow-up-actions">
          <button class="button secondary" ${followUpProjectionStale ? 'disabled' : ''} onclick="openFollowUpEditDialog(this,this.closest('.follow-up-item').dataset.followUpId)">Edit owner or due date</button>
          ${lifecycle.join('')}
        </div>
      </article>`;
    }).join('');
    list.innerHTML = staleNotice + list.innerHTML;
    refreshGeneratedActionControls();
    if (followUpControlsLocked()) setFollowUpMutationBusy(true);
  }

  function setFollowUpFilter(name) {
    if (!['active', 'completed', 'cancelled', 'all'].includes(name)) return;
    if (followUpControlsLocked()) return;
    followUpFilter = name;
    for (const filterName of ['active', 'completed', 'cancelled', 'all']) {
      const selected = filterName === name;
      const button = document.getElementById(`follow-up-filter-${filterName}`);
      button?.classList.toggle('active', selected);
      button?.setAttribute('aria-selected', String(selected));
      if (button) button.tabIndex = selected ? 0 : -1;
    }
    renderFollowUps();
  }

  function handleFollowUpFilterKeydown(event) {
    const names = ['active', 'completed', 'cancelled', 'all'];
    const tabs = names.map(name => document.getElementById(`follow-up-filter-${name}`));
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    setFollowUpFilter(names[next]);
    tabs[next]?.focus();
  }

  function clearFollowUpRetry() {
    if (pendingFollowUpIntent?.body) pendingFollowUpIntent.body = {};
    pendingFollowUpIntent = null;
    for (const id of ['follow-up-retry', 'follow-up-dialog-retry']) {
      const retry = document.getElementById(id);
      if (retry) retry.hidden = true;
    }
  }

  function followUpDraftKey(mode = followUpDialogMode, actionId = selectedFollowUpId, status = followUpOutcomeStatus) {
    if (mode === 'create') return 'create';
    if (mode === 'outcome') return `outcome:${actionId || 'unavailable'}:${status || 'unavailable'}`;
    return `edit:${actionId || 'unavailable'}`;
  }

  function captureFollowUpDraft() {
    if (!followUpDialogOpen || !followUpDialogMode) return;
    const key = followUpDraftKey();
    if (followUpDialogMode === 'create') {
      followUpDrafts.set(key, {
        text: document.getElementById('follow-up-create-text')?.value || '',
        owner: document.getElementById('follow-up-create-owner')?.value || '',
        dueDate: document.getElementById('follow-up-create-due')?.value || '',
      });
    } else if (followUpDialogMode === 'edit') {
      followUpDrafts.set(key, {
        owner: document.getElementById('follow-up-edit-owner')?.value || '',
        dueDate: document.getElementById('follow-up-edit-due')?.value || '',
      });
    } else if (followUpDialogMode === 'outcome') {
      followUpDrafts.set(key, {
        kind: document.getElementById('follow-up-outcome-kind')?.value || 'administrative',
        text: document.getElementById('follow-up-outcome-text')?.value || '',
      });
    }
  }

  function restoreFollowUpDraft() {
    const action = selectedFollowUpId ? followUpsById.get(selectedFollowUpId) : null;
    const draft = followUpDrafts.get(followUpDraftKey());
    if (followUpDialogMode === 'create') {
      document.getElementById('follow-up-create-text').value = draft?.text || '';
      document.getElementById('follow-up-create-owner').value = draft?.owner || '';
      document.getElementById('follow-up-create-due').value = draft?.dueDate || '';
    } else if (followUpDialogMode === 'edit') {
      document.getElementById('follow-up-edit-owner').value =
        draft?.owner ?? action?.owner ?? '';
      document.getElementById('follow-up-edit-due').value =
        draft?.dueDate ?? action?.due_date ?? '';
    } else if (followUpDialogMode === 'outcome') {
      document.getElementById('follow-up-outcome-kind').value = draft?.kind || 'administrative';
      document.getElementById('follow-up-outcome-text').value = draft?.text || '';
      updateFollowUpOutcomeGuidance();
    }
    updateFollowUpFormValidity();
  }

  function invalidateFollowUpRetryOnDraftChange() {
    if (pendingFollowUpIntent) {
      clearFollowUpRetry();
      setFollowUpDialogStatus(
        'The draft changed. Review the latest action and submit it as a new request.',
        'conflict',
      );
    }
    captureFollowUpDraft();
    updateFollowUpFormValidity();
  }

  function setFollowUpMutationBusy(busy) {
    document.querySelectorAll(
      '#follow-up-dialog button, #follow-up-dialog input, #follow-up-dialog textarea, '
      + '#follow-up-dialog select, #follow-up-list .button, #follow-up-create-button, '
      + '#follow-up-retry button, .follow-up-filter, .action-accept-btn, '
      + '.action-dismiss-btn, .action-feedback button, .action-feedback input, '
      + '.summary-feedback-button, .visit-open-button, #visit-create-toggle, '
      + '#appointment-dialog button, #appointment-dialog input, '
      + '#appointment-dialog textarea, #appointment-dialog select, '
      + '#visit-create-panel button, #visit-create-panel input, '
      + '#visit-create-panel textarea, #visit-create-panel select'
    ).forEach(control => {
      if (busy) {
        if (!('followUpWasDisabled' in control.dataset)) {
          control.dataset.followUpWasDisabled = String(control.disabled);
        }
        control.disabled = true;
      } else if ('followUpWasDisabled' in control.dataset) {
        control.disabled = control.dataset.followUpWasDisabled === 'true';
        delete control.dataset.followUpWasDisabled;
      }
    });
    if (busy && pendingFollowUpCompletion && !followUpMutationPending) {
      exposePendingFollowUpCompletionRetry();
    }
  }

  function exposePendingFollowUpCompletionRetry() {
    const retryContainer = document.getElementById(
      followUpDialogOpen ? 'follow-up-dialog-retry' : 'follow-up-retry'
    );
    if (!retryContainer) return;
    retryContainer.hidden = false;
    const retryButton = retryContainer.querySelector('button');
    if (retryButton) {
      retryButton.disabled = false;
      retryButton.textContent = 'Retry authoritative reload';
    }
  }

  function updateFollowUpOutcomeGuidance() {
    const kind = document.getElementById('follow-up-outcome-kind')?.value;
    const guidance = document.getElementById('follow-up-outcome-guidance');
    if (!guidance) return;
    guidance.textContent = {
      clinician_attributed: 'Caregiver-entered · attributed to clinician · unverified',
      caregiver_reported: 'Caregiver-entered · caregiver reported · unverified',
      administrative: 'Caregiver-entered administrative outcome · not clinical evidence',
    }[kind] || '';
  }

  function updateFollowUpFormValidity() {
    const createText = (document.getElementById('follow-up-create-text')?.value || '').trim();
    const outcomeText = (document.getElementById('follow-up-outcome-text')?.value || '').trim();
    const createButton = document.getElementById('follow-up-create-submit');
    const editButton = document.getElementById('follow-up-edit-submit');
    const outcomeButton = document.getElementById('follow-up-outcome-submit');
    const headerButton = document.getElementById('follow-up-create-button');
    const retryButton = document.getElementById('follow-up-retry-button');
    const dialogRetryButton = document.getElementById('follow-up-dialog-retry-button');
    const controlsLocked = followUpControlsLocked();
    if (createButton && !controlsLocked) {
      createButton.disabled = followUpProjectionStale || !createText;
    }
    if (editButton && !controlsLocked) editButton.disabled = followUpProjectionStale;
    if (outcomeButton && !controlsLocked) {
      outcomeButton.disabled = followUpProjectionStale || !outcomeText;
    }
    if (headerButton && !controlsLocked) headerButton.disabled = followUpProjectionStale;
    if (retryButton) {
      retryButton.disabled = pendingFollowUpCompletion ? false : controlsLocked;
    }
    if (dialogRetryButton) {
      dialogRetryButton.disabled = pendingFollowUpCompletion ? false : controlsLocked;
    }
    if (createText) setFormError('follow-up-create-error', '');
    if (outcomeText) setFormError('follow-up-outcome-error', '');
  }

  function renderFollowUpDialog() {
    if (!followUpDialogOpen) return;
    const action = selectedFollowUpId ? followUpsById.get(selectedFollowUpId) : null;
    const title = document.getElementById('follow-up-dialog-title');
    const create = document.getElementById('follow-up-create-form');
    const edit = document.getElementById('follow-up-edit-form');
    const outcome = document.getElementById('follow-up-outcome-form');
    create.hidden = followUpDialogMode !== 'create';
    edit.hidden = followUpDialogMode !== 'edit';
    outcome.hidden = followUpDialogMode !== 'outcome';
    if (followUpDialogMode === 'create') {
      title.textContent = 'Add caregiver follow-up';
    } else if (!action) {
      title.textContent = 'Follow-up unavailable';
      setFollowUpDialogStatus('This action is no longer available. Reload before continuing.', 'conflict');
      edit.hidden = true;
      outcome.hidden = true;
      return;
    } else if (followUpDialogMode === 'edit') {
      title.textContent = 'Edit owner or due date';
      document.getElementById('follow-up-edit-copy').textContent = action.text;
    } else {
      title.textContent = followUpOutcomeStatus === 'completed'
        ? 'Complete follow-up'
        : 'Cancel follow-up';
      document.getElementById('follow-up-outcome-copy').textContent = action.text;
      document.getElementById('follow-up-outcome-submit').textContent =
        followUpOutcomeStatus === 'completed' ? 'Complete follow-up' : 'Cancel follow-up';
    }
    restoreFollowUpDraft();
  }

  function openFollowUpDialog(mode, trigger, actionId = null, status = null) {
    if (followUpProjectionStale) {
      setFollowUpStatus('Reload the current action list before making changes.', 'offline');
      return;
    }
    if (!['create', 'edit', 'outcome'].includes(mode)) return;
    if (followUpControlsLocked()) return;
    if (actionId && !followUpsById.has(actionId)) {
      setFollowUpStatus('This action is no longer available. Reload before continuing.', 'conflict');
      loadFollowUps();
      return;
    }
    if (followUpDialogOpen) captureFollowUpDraft();
    selectedFollowUpId = actionId;
    followUpSelectionEpoch += 1;
    followUpDialogMode = mode;
    followUpOutcomeStatus = status;
    followUpDialogOpen = true;
    clearFollowUpRetry();
    setFollowUpDialogStatus('');
    for (const id of ['follow-up-create-error', 'follow-up-edit-error', 'follow-up-outcome-error']) {
      setFormError(id, '');
    }
    const overlay = document.getElementById('follow-up-overlay');
    const dialog = document.getElementById('follow-up-dialog');
    overlay.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    dialog.inert = false;
    renderFollowUpDialog();
    activateDialog(dialog, trigger);
  }

  function openFollowUpCreateDialog(trigger) {
    openFollowUpDialog('create', trigger);
  }

  function openFollowUpEditDialog(trigger, actionId) {
    openFollowUpDialog('edit', trigger, actionId);
  }

  function openFollowUpOutcomeDialog(trigger, actionId, status) {
    if (followUpProjectionStale) {
      setFollowUpStatus('Reload the current action list before recording an outcome.', 'offline');
      return;
    }
    if (followUpControlsLocked()) return;
    if (!['completed', 'cancelled'].includes(status)) return;
    const action = followUpsById.get(actionId);
    if (!action || !['open', 'in_progress'].includes(action.status)) {
      setFollowUpStatus('This action changed. Reload before recording an outcome.', 'conflict');
      loadFollowUps();
      return;
    }
    openFollowUpDialog('outcome', trigger, actionId, status);
  }

  function closeFollowUpDialog(
    preserveDraft = true,
    force = false,
    restoreFocus = true,
  ) {
    if (!followUpDialogOpen) return;
    if (followUpControlsLocked() && !force) {
      setFollowUpDialogStatus('Saving is still in progress. Wait for the result before closing.', 'saving');
      return;
    }
    if (preserveDraft) captureFollowUpDraft();
    followUpDialogOpen = false;
    selectedFollowUpId = null;
    followUpSelectionEpoch += 1;
    followUpDialogMode = null;
    followUpOutcomeStatus = null;
    clearFollowUpRetry();
    const overlay = document.getElementById('follow-up-overlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    const dialog = document.getElementById('follow-up-dialog');
    if (dialog) dialog.inert = true;
    deactivateDialog(dialog, restoreFocus);
  }

  function closeFollowUpFromBackdrop(event) {
    if (event?.target === document.getElementById('follow-up-overlay')) {
      closeFollowUpDialog();
    }
  }

  function clearFollowUpCachedProjection(message, tone = 'error') {
    const followUpDialog = document.getElementById('follow-up-dialog');
    const wasFollowUpDialogActive = followUpDialogOpen || activeDialogSurface === followUpDialog;
    if (pendingFollowUpIntent?.body) pendingFollowUpIntent.body = {};
    if (activeFollowUpIntent?.body) activeFollowUpIntent.body = {};
    if (
      pendingWorkflowIntent
      && String(pendingWorkflowIntent.url || '').includes('/follow-ups')
    ) {
      if (pendingWorkflowIntent.body) pendingWorkflowIntent.body = {};
      pendingWorkflowIntent = null;
    }
    if (
      activeWorkflowIntent
      && String(activeWorkflowIntent.url || '').includes('/follow-ups')
    ) {
      if (activeWorkflowIntent.body) activeWorkflowIntent.body = {};
      activeWorkflowIntent = null;
    }
    followUpsById = new Map();
    followUpLoadEpoch += 1;
    followUpProjectionStale = false;
    selectedFollowUpId = null;
    followUpSelectionEpoch += 1;
    followUpDialogOpen = false;
    followUpDialogMode = null;
    followUpOutcomeStatus = null;
    pendingFollowUpIntent = null;
    activeFollowUpIntent = null;
    followUpMutationPending = false;
    followUpDrafts = new Map();
    visitSelectionEpoch += 1;
    renderFollowUps();
    renderVisitFollowUps();
    setFollowUpStatus(message, tone);
    for (const id of [
      'follow-up-edit-copy', 'follow-up-outcome-copy', 'follow-up-outcome-guidance',
      'follow-up-dialog-status', 'follow-up-create-error', 'follow-up-edit-error',
      'follow-up-outcome-error'
    ]) {
      const node = document.getElementById(id);
      if (node) node.textContent = '';
    }
    for (const id of [
      'follow-up-create-text', 'follow-up-create-owner', 'follow-up-create-due',
      'follow-up-edit-owner', 'follow-up-edit-due', 'follow-up-outcome-text'
    ]) {
      const control = document.getElementById(id);
      if (control) control.value = '';
    }
    const outcomeKind = document.getElementById('follow-up-outcome-kind');
    if (outcomeKind) outcomeKind.value = 'administrative';
    const title = document.getElementById('follow-up-dialog-title');
    if (title) title.textContent = 'Follow-up unavailable';
    for (const id of [
      'follow-up-create-form', 'follow-up-edit-form', 'follow-up-outcome-form',
      'follow-up-retry', 'follow-up-dialog-retry'
    ]) {
      const node = document.getElementById(id);
      if (node) node.hidden = true;
    }
    const overlay = document.getElementById('follow-up-overlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (followUpDialog) followUpDialog.inert = true;
    if (wasFollowUpDialogActive) {
      document.activeElement?.blur();
      activeDialogSurface = null;
      lastDialogTrigger = null;
      document.body.classList.remove('dialog-open');
      [...document.body.children].forEach(child => { child.inert = false; });
      [...document.body.children].forEach(child => {
        if (child.dataset.dialogAriaHidden === 'true') {
          child.removeAttribute('aria-hidden');
          delete child.dataset.dialogAriaHidden;
        }
      });
      if (overlay) overlay.inert = true;
      if (followUpDialog) followUpDialog.inert = true;
    }
    refreshGeneratedActionControls();
    updateFollowUpFormValidity();
    updateAppointmentFormValidity();
  }

  function markFollowUpProjectionStale(message) {
    if (followUpDialogOpen) captureFollowUpDraft();
    followUpProjectionStale = true;
    renderFollowUps();
    renderVisitFollowUps();
    setFollowUpStatus(message, 'offline');
    setFollowUpDialogStatus(
      'The action list is offline and read-only. Your draft remains available in this tab.',
      'offline',
    );
    refreshGeneratedActionControls();
    updateFollowUpFormValidity();
    updateAppointmentFormValidity();
  }

  function isTransientFollowUpTransportError(error) {
    return error instanceof TypeError
      || error?.name === 'AbortError'
      || navigator.onLine === false;
  }

  async function loadFollowUps() {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++followUpLoadEpoch;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request) && requestLoadEpoch === followUpLoadEpoch
    );
    try {
      const response = await fetch('/api/follow-ups');
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, data, { workflow: 'projection' });
      if (!authority.accepted) return null;
      if (followUpDialogOpen) captureFollowUpDraft();
      followUpProjectionStale = false;
      followUpsById = new Map(
        (Array.isArray(data.items) ? data.items : [])
          .filter(item => item && typeof item.id === 'string')
          .map(item => [item.id, item])
      );
      renderFollowUps();
      renderVisitFollowUps();
      if (followUpDialogOpen) renderFollowUpDialog();
      setFollowUpStatus('');
      updateFollowUpFormValidity();
      updateAppointmentFormValidity();
      reportLoadSuccess('follow-ups');
      const items = followUpItems();
      items.profileRevision = data.profile_revision;
      items.workflowRevision = data.workflow_revision;
      return items;
    } catch (error) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('follow-ups', error);
        if (requestIsCurrent()) evictClientPhi(error);
        return null;
      } else {
        if (isTransientFollowUpTransportError(error)) {
          markFollowUpProjectionStale(
            'Follow-through is offline. The last loaded actions are read-only; caregiver-entered drafts remain available in this tab.',
          );
          reportLoadError('follow-ups', error);
          return followUpItems();
        } else {
          clearFollowUpCachedProjection(
            'Follow-through could not be loaded. Retry to get the current action list.',
            'error',
          );
          const list = document.getElementById('follow-up-list');
          if (list) list.innerHTML = loadFailureMarkup('Follow-through', 'loadFollowUps()');
          const visitList = document.getElementById('visit-followup-list');
          if (visitList && appointmentDialogOpen) {
            visitList.innerHTML = loadFailureMarkup('Visit follow-ups', 'loadFollowUps()');
          }
        }
      }
      reportLoadError('follow-ups', error);
      return null;
    }
  }

  function beginFollowUpMutation(allowPendingCompletion = false) {
    if (
      followUpMutationPending
      || summaryActionMutationOwner !== null
      || (pendingFollowUpCompletion !== null && !allowPendingCompletion)
    ) return null;
    const owner = {};
    followUpMutationOwner = owner;
    followUpMutationPending = true;
    return owner;
  }

  function createFollowUpIntent(url, body, options = {}) {
    return {
      method: options.method || 'POST',
      url,
      body: { ...body, mutation_id: newMutationId() },
      actionId: options.actionId || null,
      draftKey: options.draftKey || null,
      sourceKind: options.sourceKind || null,
      mutationOwner: options.mutationOwner || null,
      requestPhiEpoch: phiEpoch,
      requestActionEpoch: followUpSelectionEpoch,
      requestActionId: selectedFollowUpId,
    };
  }

  function followUpIntentCanRender(intent, expectedPhiEpoch = intent.requestPhiEpoch) {
    return expectedPhiEpoch === phiEpoch
      && intent.requestActionEpoch === followUpSelectionEpoch
      && intent.actionId === selectedFollowUpId;
  }

  function followUpIntentOwnsMutation(
    intent,
    expectedPhiEpoch = (
      intent.completionPhiEpoch
      ?? intent.pendingPhiEpoch
      ?? intent.requestPhiEpoch
    ),
  ) {
    return followUpMutationPending
      && followUpMutationOwner === intent.mutationOwner
      && followUpIntentCanRender(intent, expectedPhiEpoch);
  }

  async function handleFollowUpConflict(error, intent) {
    if (!followUpIntentCanRender(intent)) return false;
    if (followUpDialogOpen) captureFollowUpDraft();
    clearFollowUpRetry();
    if (intent.sourceKind === 'generated') redactGeneratedSummaryActions();
    const message = intent.sourceKind === 'generated'
      ? 'The generated action is unavailable. Reloaded assessment actions must be reviewed before accepting one.'
      : (error.message || 'This action changed. Review the latest version before trying again.');
    setFollowUpStatus(message, 'conflict');
    setFollowUpDialogStatus(message, 'conflict');
    reportLoadError('follow-up-mutation', error);
    await Promise.allSettled([
      loadFollowUps(),
      intent.sourceKind === 'generated' ? loadSummary() : Promise.resolve(),
    ]);
    return true;
  }

  async function consumeFollowUpResponse(data, intent, forceClinicalRefresh = false) {
    if (!followUpIntentOwnsMutation(intent)) return false;
    let authority;
    if (intent.responseAuthorized) {
      authority = {
        accepted: true,
        profileAdvanced: intent.responseProfileAdvanced === true,
      };
    } else {
      authority = authorizePatientResponse(intent, data, { workflow: 'targeted' });
      if (!authority.accepted) return false;
      intent.responseAuthorized = true;
      intent.responseProfileAdvanced = authority.profileAdvanced === true;
    }
    let requiresClinicalRefresh = forceClinicalRefresh || authority.profileAdvanced;
    let expectedPhiEpoch = phiEpoch;
    intent.pendingPhiEpoch = expectedPhiEpoch;
    let refreshed;
    if (requiresClinicalRefresh) {
      refreshed = await refreshClinicalWorkflowState(
        data.profile_revision,
        data.workflow_revision,
      );
    } else {
      refreshed = await loadFollowUps();
      if (
        Array.isArray(refreshed)
        && followUpIntentOwnsMutation(intent, expectedPhiEpoch)
        && (
          (
            data.profile_revision != null
            && String(refreshed.profileRevision) !== String(data.profile_revision)
          )
          || (
            data.workflow_revision != null
            && String(refreshed.workflowRevision) !== String(data.workflow_revision)
          )
        )
      ) {
        requiresClinicalRefresh = true;
        expectedPhiEpoch = phiEpoch;
        intent.pendingPhiEpoch = expectedPhiEpoch;
        refreshed = await refreshClinicalWorkflowState(
          refreshed.profileRevision ?? data.profile_revision,
          refreshed.workflowRevision ?? data.workflow_revision,
        );
      }
    }
    if (
      (
        requiresClinicalRefresh
          ? refreshed?.verified !== true
          : !Array.isArray(refreshed)
      )
      || !followUpIntentOwnsMutation(intent, expectedPhiEpoch)
    ) {
      if (followUpIntentOwnsMutation(intent, expectedPhiEpoch)) {
        pendingFollowUpCompletion = {
          data,
          intent,
          requiresClinicalRefresh,
        };
        const message =
          'The current follow-through state could not be verified. Retry the authoritative reload.';
        setFollowUpStatus(message, 'offline');
        setFollowUpDialogStatus(message, 'offline');
      }
      return false;
    }
    intent.completionPhiEpoch = expectedPhiEpoch;
    return true;
  }

  function restoreFollowUpMutationFocus(intent) {
    const row = intent.actionId
      ? [...document.querySelectorAll('.follow-up-item')]
        .find(item => item.dataset.followUpId === intent.actionId)
      : null;
    const target = row?.querySelector('.button')
      || document.getElementById('follow-up-create-button')
      || document.getElementById('follow-through-heading');
    if (target && typeof target.focus === 'function') target.focus();
  }

  function releaseFollowUpMutation(intent, restoreFocus = false, viewAlreadyValidated = false) {
    const stillOwned = followUpMutationPending
      && followUpMutationOwner === intent.mutationOwner;
    const viewIsCurrent = viewAlreadyValidated || followUpIntentOwnsMutation(intent);
    if (!stillOwned) return false;
    followUpMutationPending = false;
    setFollowUpMutationBusy(false);
    refreshGeneratedActionControls();
    updateFollowUpFormValidity();
    if (restoreFocus && viewIsCurrent) restoreFollowUpMutationFocus(intent);
    followUpMutationOwner = null;
    if (pendingFollowUpCompletion) {
      setFollowUpMutationBusy(true);
    }
    return true;
  }

  function finalizeFollowUpSuccess(data, intent) {
    if (!followUpIntentOwnsMutation(intent)) return false;
    if (intent.draftKey) followUpDrafts.delete(intent.draftKey);
    pendingFollowUpCompletion = null;
    clearFollowUpRetry();
    const closedDialog = followUpDialogOpen;
    if (closedDialog) closeFollowUpDialog(false, true, false);
    if (intent.method === 'POST' && data.item?.status === 'open') {
      followUpFilter = 'active';
      for (const filterName of ['active', 'completed', 'cancelled', 'all']) {
        const selected = filterName === followUpFilter;
        const button = document.getElementById(`follow-up-filter-${filterName}`);
        button?.classList.toggle('active', selected);
        button?.setAttribute('aria-selected', String(selected));
        if (button) button.tabIndex = selected ? 0 : -1;
      }
      renderFollowUps();
    }
    setFollowUpStatus('Saved.', 'success');
    reportLoadSuccess('follow-up-mutation');
    releaseFollowUpMutation(intent, true, true);
    return true;
  }

  async function performFollowUpIntent(intent, explicitRetry = false) {
    if (!followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
    activeFollowUpIntent = intent;
    setFollowUpMutationBusy(true);
    if (!explicitRetry) clearFollowUpRetry();
    setFollowUpStatus(explicitRetry ? 'Retrying the unchanged request…' : 'Saving…', 'saving');
    setFollowUpDialogStatus(explicitRetry ? 'Retrying the unchanged request…' : 'Saving…', 'saving');
    try {
      const response = await fetch(intent.url, {
        method: intent.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(intent.body),
      });
      if (!followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const data = await readJsonResponse(
        response,
        () => followUpIntentOwnsMutation(intent, intent.requestPhiEpoch),
      );
      if (!followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const consumed = await consumeFollowUpResponse(data, intent);
      if (!consumed || !followUpIntentOwnsMutation(intent)) return null;
      if (!finalizeFollowUpSuccess(data, intent)) return null;
      return data;
    } catch (error) {
      if (!followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('follow-up-mutation', error);
        if (followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) {
          evictClientPhi(error);
        }
        return null;
      }
      if (error?.status === 409) {
        await handleFollowUpConflict(error, intent);
        return null;
      }
      if (isTransientFollowUpTransportError(error)) {
        pendingFollowUpIntent = intent;
        markFollowUpProjectionStale(
          'Connection lost. Caregiver-entered drafts remain available in this tab.',
        );
        const retry = document.getElementById(
          followUpDialogOpen ? 'follow-up-dialog-retry' : 'follow-up-retry'
        );
        if (retry) retry.hidden = false;
        setFollowUpDialogStatus(
          'Connection lost. Your draft is still available for an explicit unchanged retry.',
          'offline',
        );
        reportLoadError('follow-up-mutation', error);
        return null;
      }
      const message = error?.message || 'The follow-up request could not be saved.';
      setFollowUpStatus(message, 'error');
      setFollowUpDialogStatus(message, 'error');
      const errorId = followUpDialogMode === 'create'
        ? 'follow-up-create-error'
        : (followUpDialogMode === 'outcome' ? 'follow-up-outcome-error' : 'follow-up-edit-error');
      setFormError(errorId, message);
      reportLoadError('follow-up-mutation', error);
      return null;
    } finally {
      if (activeFollowUpIntent === intent) activeFollowUpIntent = null;
      releaseFollowUpMutation(intent);
    }
  }

  async function submitFollowUpMutation(url, body, options = {}) {
    if (followUpProjectionStale) {
      setFollowUpStatus('Reload the current action list before making changes.', 'offline');
      return null;
    }
    const mutationOwner = beginFollowUpMutation();
    if (!mutationOwner) return null;
    selectedFollowUpId = options.actionId || null;
    followUpSelectionEpoch += 1;
    const intent = createFollowUpIntent(url, body, { ...options, mutationOwner });
    return performFollowUpIntent(intent);
  }

  async function retryFollowUpIntent() {
    if (pendingFollowUpCompletion) {
      const completion = pendingFollowUpCompletion;
      const mutationOwner = beginFollowUpMutation(true);
      if (!mutationOwner) return;
      completion.intent.mutationOwner = mutationOwner;
      completion.intent.pendingPhiEpoch = phiEpoch;
      delete completion.intent.completionPhiEpoch;
      setFollowUpMutationBusy(true);
      setFollowUpStatus('Retrying the authoritative reload…', 'saving');
      setFollowUpDialogStatus('Retrying the authoritative reload…', 'saving');
      try {
        const consumed = await consumeFollowUpResponse(
          completion.data,
          completion.intent,
          completion.requiresClinicalRefresh,
        );
        if (!consumed || !followUpIntentOwnsMutation(completion.intent)) return;
        finalizeFollowUpSuccess(completion.data, completion.intent);
      } finally {
        releaseFollowUpMutation(completion.intent);
      }
      return;
    }
    const intent = pendingFollowUpIntent;
    if (!intent) return;
    if (!followUpIntentCanRender(intent)) {
      clearFollowUpRetry();
      setFollowUpStatus(
        'The action changed. Review the latest version before submitting a new request.',
        'conflict',
      );
      return;
    }
    const mutationOwner = beginFollowUpMutation();
    if (!mutationOwner) return;
    intent.mutationOwner = mutationOwner;
    await performFollowUpIntent(intent, true);
  }

  async function createManualFollowUp() {
    if (followUpControlsLocked()) return;
    const text = (document.getElementById('follow-up-create-text')?.value || '').trim();
    if (!text) {
      setFormError('follow-up-create-error', 'Enter a caregiver follow-up.');
      updateFollowUpFormValidity();
      return;
    }
    if (/^(start|stop|hold|pause|resume|switch|increase|decrease|administer|take|skip|discontinue|withhold)\b/i.test(text)) {
      setFormError(
        'follow-up-create-error',
        'Use contact, ask, discuss, or confirm wording with the treating team.',
      );
      return;
    }
    const draftKey = followUpDraftKey('create', null, null);
    await submitFollowUpMutation(
      '/api/follow-ups',
      {
        origin_kind: 'manual',
        text,
        owner: (document.getElementById('follow-up-create-owner')?.value || '').trim() || null,
        due_date: document.getElementById('follow-up-create-due')?.value || null,
      },
      { draftKey },
    );
  }

  async function saveFollowUpDetails() {
    if (followUpControlsLocked()) return;
    const action = selectedFollowUpId ? followUpsById.get(selectedFollowUpId) : null;
    if (!action) return;
    const owner = (document.getElementById('follow-up-edit-owner')?.value || '').trim() || null;
    const dueDate = document.getElementById('follow-up-edit-due')?.value || null;
    if (owner === (action.owner || null) && dueDate === (action.due_date || null)) {
      setFormError('follow-up-edit-error', 'Change the owner or due date before saving.');
      return;
    }
    const draftKey = followUpDraftKey('edit', action.id, null);
    await submitFollowUpMutation(
      `/api/follow-ups/${encodeURIComponent(action.id)}`,
      { expected_token: action.token, owner, due_date: dueDate },
      { method: 'PATCH', actionId: action.id, draftKey },
    );
  }

  async function submitFollowUpOutcome() {
    if (followUpControlsLocked()) return;
    const action = selectedFollowUpId ? followUpsById.get(selectedFollowUpId) : null;
    const kind = document.getElementById('follow-up-outcome-kind')?.value;
    const text = (document.getElementById('follow-up-outcome-text')?.value || '').trim();
    if (!action || !['completed', 'cancelled'].includes(followUpOutcomeStatus)) return;
    if (!['administrative', 'caregiver_reported', 'clinician_attributed'].includes(kind)) {
      setFormError('follow-up-outcome-error', 'Choose the outcome source.');
      return;
    }
    if (!text) {
      setFormError('follow-up-outcome-error', 'Record what happened.');
      updateFollowUpFormValidity();
      return;
    }
    const targetStatus = followUpOutcomeStatus;
    const draftKey = followUpDraftKey('outcome', action.id, targetStatus);
    await submitFollowUpMutation(
      `/api/follow-ups/${encodeURIComponent(action.id)}`,
      {
        expected_token: action.token,
        status: targetStatus,
        outcome: { kind, text },
      },
      { method: 'PATCH', actionId: action.id, draftKey },
    );
  }

  async function changeFollowUpStatus(row, status) {
    if (followUpProjectionStale) {
      setFollowUpStatus('Reload the current action list before changing status.', 'offline');
      return;
    }
    if (followUpControlsLocked()) return;
    const actionId = row?.dataset.followUpId;
    const token = row?.dataset.followUpToken;
    const action = actionId ? followUpsById.get(actionId) : null;
    if (!action || !token) return;
    const allowed = (action.status === 'open' && status === 'in_progress')
      || (action.status === 'in_progress' && status === 'open');
    if (!allowed) {
      setFollowUpStatus('This lifecycle change is not available.', 'conflict');
      return;
    }
    await submitFollowUpMutation(
      `/api/follow-ups/${encodeURIComponent(action.id)}`,
      { expected_token: token, status },
      { method: 'PATCH', actionId: action.id },
    );
  }

  function renderAppointmentOptions() {
    const select = document.getElementById('visit-source-appointment');
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="">Create without imported appointment</option>'
      + appointmentOptions.map(item => {
        const label = [
          item.date ? fmtDate(item.date) : 'Date pending',
          item.description || item.type || item.with || 'Imported appointment',
        ].filter(Boolean).join(' · ');
        return `<option value="${escHtml(item.id)}">${escHtml(label)}</option>`;
      }).join('');
    if (appointmentOptions.some(item => item.id === current)) select.value = current;
  }

  function renderVisitPreparation() {
    const list = document.getElementById('visit-list');
    if (!list) return;
    const visits = [...visitsById.values()].sort((a, b) => {
      const terminalA = ['completed', 'cancelled'].includes(a.status) ? 1 : 0;
      const terminalB = ['completed', 'cancelled'].includes(b.status) ? 1 : 0;
      return terminalA - terminalB
        || String(a.date || '9999-12-31').localeCompare(String(b.date || '9999-12-31'))
        || String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
    });
    if (!visits.length) {
      list.innerHTML = '<div class="empty-state">No visit workspace yet. Create one for the next appointment.</div>';
      return;
    }
    list.innerHTML = visits.map(visit => {
      const source = linkableAppointment(visit.source_appointment_id);
      const details = [
        visit.date ? fmtDate(visit.date) : 'Date pending',
        visit.time,
        visit.clinician,
        visit.location,
      ].filter(Boolean).map(escHtml).join(' · ');
      return `<article class="visit-row" data-visit-id="${escHtml(visit.id)}" data-visit-token="${escHtml(visit.token)}">
        <div class="visit-row-main">
          <div class="visit-row-title">${escHtml(visit.title)}</div>
          <div class="visit-row-meta">${details || 'Visit details not set'}</div>
          ${source ? `<div class="visit-source-label">Linked imported appointment · ${escHtml(source.description || source.type || source.date || '')}</div>` : ''}
        </div>
        <span class="visit-status-badge ${safeClassToken(visit.status, 'planned')}">${escHtml(visitStatusLabel(visit.status))}</span>
        <button class="button secondary visit-open-button" onclick="openAppointmentWorkspace(this, this.closest('.visit-row').dataset.visitId)">Open appointment</button>
      </article>`;
    }).join('');
  }

  function toggleVisitCreateForm(force) {
    const panel = document.getElementById('visit-create-panel');
    const button = document.getElementById('visit-create-toggle');
    const show = typeof force === 'boolean' ? force : panel.hidden;
    panel.hidden = !show;
    button.setAttribute('aria-expanded', String(show));
    if (show) document.getElementById('visit-create-title')?.focus();
    else setFormError('visit-create-error', '');
  }

  function prefillVisitFromAppointment() {
    const sourceId = document.getElementById('visit-source-appointment')?.value;
    const source = linkableAppointment(sourceId);
    if (!source) return;
    document.getElementById('visit-create-title').value =
      source.description || source.type || 'Clinical appointment';
    document.getElementById('visit-create-date').value = source.date || '';
    document.getElementById('visit-create-time').value = source.time || '';
    document.getElementById('visit-create-clinician').value = source.with || '';
    document.getElementById('visit-create-location').value = source.location || '';
    updateAppointmentFormValidity();
  }

  function updateAppointmentFormValidity() {
    const createTitle = (document.getElementById('visit-create-title')?.value || '').trim();
    const manualQuestion = (document.getElementById('visit-manual-question')?.value || '').trim();
    const decision = (document.getElementById('visit-decision-text')?.value || '').trim();
    const followUp = (document.getElementById('visit-followup-text')?.value || '').trim();
    const createButton = document.getElementById('visit-create-submit');
    const questionButton = document.getElementById('visit-manual-question-submit');
    const decisionButton = document.getElementById('visit-decision-submit');
    const followUpButton = document.getElementById('visit-followup-submit');
    if (createButton) createButton.disabled = !createTitle;
    if (questionButton) questionButton.disabled = !manualQuestion;
    if (decisionButton) decisionButton.disabled = !decision;
    if (followUpButton) followUpButton.disabled = followUpProjectionStale || !followUp;
    if (createTitle) setFormError('visit-create-error', '');
    if (manualQuestion) setFormError('visit-question-error', '');
    if (decision) setFormError('visit-decision-error', '');
    if (followUp) setFormError('visit-followup-error', '');
  }

  function visitCreateBody() {
    return {
      title: (document.getElementById('visit-create-title')?.value || '').trim(),
      date: document.getElementById('visit-create-date')?.value || null,
      time: (document.getElementById('visit-create-time')?.value || '').trim() || null,
      clinician: (document.getElementById('visit-create-clinician')?.value || '').trim() || null,
      location: (document.getElementById('visit-create-location')?.value || '').trim() || null,
      source_appointment_id: document.getElementById('visit-source-appointment')?.value || null,
    };
  }

  function completeVisitCreation(result) {
    if (!result?.item?.id) return;
    for (const id of [
      'visit-create-title', 'visit-create-date', 'visit-create-time',
      'visit-create-clinician', 'visit-create-location', 'visit-source-appointment'
    ]) {
      const input = document.getElementById(id);
      if (input) input.value = '';
    }
    toggleVisitCreateForm(false);
    updateAppointmentFormValidity();
    openAppointmentWorkspace(document.getElementById('visit-create-toggle'), result.item.id);
  }

  function finalizeRetriedWorkflowIntent(intent, result) {
    if (!result) return;
    if (result.item?.question_snapshots && !intent.visitId) {
      completeVisitCreation(result);
      return;
    }
    const visitId = intent.visitId;
    if (intent.url.endsWith('/questions') && intent.body.source_kind === 'manual') {
      document.getElementById('visit-manual-question').value = '';
      const draft = appointmentDrafts.get(visitId);
      if (draft) draft.manualQuestion = '';
      setFormError('visit-question-error', '');
    } else if (intent.url.endsWith('/decisions')) {
      document.getElementById('visit-decision-text').value = '';
      cancelDecisionSuccessor();
      const draft = appointmentDrafts.get(visitId);
      if (draft) {
        draft.decisionText = '';
        draft.supersedesId = '';
      }
      setFormError('visit-decision-error', '');
    } else if (intent.url.endsWith('/follow-ups')) {
      for (const id of [
        'visit-followup-text', 'visit-followup-owner',
        'visit-followup-due', 'visit-followup-decision'
      ]) {
        const input = document.getElementById(id);
        if (input) input.value = '';
      }
      const draft = appointmentDrafts.get(visitId);
      if (draft) {
        draft.followUpText = '';
        draft.followUpOwner = '';
        draft.followUpDue = '';
        draft.followUpDecision = '';
      }
      setFormError('visit-followup-error', '');
    } else if (
      intent.method === 'PATCH'
      && intent.url === `/api/visits/${encodeURIComponent(visitId)}`
    ) {
      appointmentDrafts.delete(visitId);
      renderAppointmentWorkspace();
    }
    updateAppointmentFormValidity();
  }

  async function createVisit() {
    const body = visitCreateBody();
    if (!body.title) {
      setFormError('visit-create-error', 'Enter a visit title.');
      updateAppointmentFormValidity();
      return;
    }
    const result = await submitWorkflowMutation('/api/visits', body, null);
    completeVisitCreation(result);
  }

  function captureAppointmentDraft() {
    if (!selectedVisitId) return;
    const prior = appointmentDrafts.get(selectedVisitId) || {};
    const answers = { ...(prior.answers || {}) };
    document.querySelectorAll('#visit-question-list .visit-question').forEach(row => {
      const status = row.querySelector('.visit-answer-status');
      const text = row.querySelector('.visit-answer-text');
      if (row.dataset.visitQuestionId && status && text) {
        answers[row.dataset.visitQuestionId] = {
          status: status.value,
          text: text.value,
        };
      }
    });
    appointmentDrafts.set(selectedVisitId, {
      editTitle: document.getElementById('visit-edit-title')?.value || '',
      editDate: document.getElementById('visit-edit-date')?.value || '',
      editTime: document.getElementById('visit-edit-time')?.value || '',
      editClinician: document.getElementById('visit-edit-clinician')?.value || '',
      editLocation: document.getElementById('visit-edit-location')?.value || '',
      manualQuestion: document.getElementById('visit-manual-question')?.value || '',
      manualCategory: document.getElementById('visit-manual-category')?.value || 'Other',
      manualPriority: document.getElementById('visit-manual-priority')?.value || 'medium',
      decisionText: document.getElementById('visit-decision-text')?.value || '',
      supersedesId: document.getElementById('visit-decision-supersedes')?.value || '',
      followUpText: document.getElementById('visit-followup-text')?.value || '',
      followUpDecision: document.getElementById('visit-followup-decision')?.value || '',
      followUpOwner: document.getElementById('visit-followup-owner')?.value || '',
      followUpDue: document.getElementById('visit-followup-due')?.value || '',
      answers,
    });
  }

  function activeDecisionSuccessorId(visit, supersedesId) {
    const target = (visit.decisions || []).find(
      decision => decision.id === supersedesId && decision.status === 'active'
    );
    return target?.id || '';
  }

  function clearDecisionSuccessorState(visitId) {
    const draft = appointmentDrafts.get(visitId);
    if (draft) draft.supersedesId = '';
    if (!appointmentDialogOpen || selectedVisitId !== visitId) return;
    const input = document.getElementById('visit-decision-supersedes');
    if (input) input.value = '';
    const cancel = document.getElementById('visit-decision-cancel-supersede');
    if (cancel) cancel.hidden = true;
    const label = document.getElementById('visit-decision-label');
    if (label) label.textContent = 'Caregiver-entered decision attributed to the clinician';
  }

  function revalidateDecisionSuccessorState(visit) {
    const draft = appointmentDrafts.get(visit.id);
    const invalidDraft = draft?.supersedesId
      && !activeDecisionSuccessorId(visit, draft.supersedesId);
    if (invalidDraft) clearDecisionSuccessorState(visit.id);
    if (
      !appointmentDialogOpen
      || selectedVisitId !== visit.id
      || invalidDraft
    ) return;
    const input = document.getElementById('visit-decision-supersedes');
    if (!input?.value || activeDecisionSuccessorId(visit, input.value)) return;
    clearDecisionSuccessorState(visit.id);
  }

  function restoreAppointmentDraft(visit) {
    const draft = appointmentDrafts.get(visit.id);
    const values = draft || {
      editTitle: visit.title || '',
      editDate: visit.date || '',
      editTime: visit.time || '',
      editClinician: visit.clinician || '',
      editLocation: visit.location || '',
    };
    const supersedesId = activeDecisionSuccessorId(visit, values.supersedesId);
    if (draft && draft.supersedesId && !supersedesId) draft.supersedesId = '';
    const fields = {
      'visit-edit-title': values.editTitle ?? visit.title ?? '',
      'visit-edit-date': values.editDate ?? visit.date ?? '',
      'visit-edit-time': values.editTime ?? visit.time ?? '',
      'visit-edit-clinician': values.editClinician ?? visit.clinician ?? '',
      'visit-edit-location': values.editLocation ?? visit.location ?? '',
      'visit-manual-question': values.manualQuestion || '',
      'visit-manual-category': values.manualCategory || 'Other',
      'visit-manual-priority': values.manualPriority || 'medium',
      'visit-decision-text': values.decisionText || '',
      'visit-decision-supersedes': supersedesId,
      'visit-followup-text': values.followUpText || '',
      'visit-followup-owner': values.followUpOwner || '',
      'visit-followup-due': values.followUpDue || '',
    };
    Object.entries(fields).forEach(([id, value]) => {
      const input = document.getElementById(id);
      if (input) input.value = value;
    });
    const decisionSelect = document.getElementById('visit-followup-decision');
    if (decisionSelect && values.followUpDecision) decisionSelect.value = values.followUpDecision;
    const superseding = Boolean(supersedesId);
    document.getElementById('visit-decision-cancel-supersede').hidden = !superseding;
    document.getElementById('visit-decision-label').textContent = superseding
      ? 'Correct with a successor decision'
      : 'Caregiver-entered decision attributed to the clinician';
    Object.entries(values.answers || {}).forEach(([questionId, answer]) => {
      const row = [...document.querySelectorAll('#visit-question-list .visit-question')]
        .find(item => item.dataset.visitQuestionId === questionId);
      const status = row?.querySelector('.visit-answer-status');
      const text = row?.querySelector('.visit-answer-text');
      if (!status || !text) return;
      status.value = answer.status === 'unknown' ? 'unknown' : 'answered';
      text.value = answer.text || '';
      toggleVisitAnswerText(status);
    });
    updateAppointmentFormValidity();
  }

  function openAppointmentWorkspace(trigger, visitId) {
    if (followUpControlsLocked()) return;
    const visit = visitsById.get(visitId);
    if (!visit) {
      setAppointmentMessage('The visit is no longer available.', 'conflict');
      loadVisits();
      return;
    }
    if (selectedVisitId && selectedVisitId !== visitId) captureAppointmentDraft();
    selectedVisitId = visitId;
    visitSelectionEpoch += 1;
    appointmentDialogOpen = true;
    clearWorkflowRetry();
    const overlay = document.getElementById('appointment-overlay');
    overlay.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    const dialog = document.getElementById('appointment-dialog');
    dialog.inert = false;
    renderAppointmentWorkspace();
    activateDialog(dialog, trigger);
  }

  function closeAppointmentWorkspace() {
    if (!appointmentDialogOpen) return;
    captureAppointmentDraft();
    appointmentDialogOpen = false;
    visitSelectionEpoch += 1;
    clearWorkflowRetry();
    const overlay = document.getElementById('appointment-overlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    deactivateDialog(document.getElementById('appointment-dialog'));
  }

  function closeAppointmentFromBackdrop(event) {
    if (event?.target === document.getElementById('appointment-overlay')) {
      closeAppointmentWorkspace();
    }
  }

  function selectVisitInWorkspace(visitId) {
    if (!visitsById.has(visitId) || visitId === selectedVisitId) return;
    captureAppointmentDraft();
    selectedVisitId = visitId;
    visitSelectionEpoch += 1;
    clearWorkflowRetry();
    renderAppointmentWorkspace();
    setAppointmentMessage('Visit changed.', 'success');
  }

  function switchAppointmentTab(name) {
    if (!['questions', 'decisions', 'followups'].includes(name)) return;
    captureAppointmentDraft();
    activeAppointmentTab = name;
    for (const tabName of ['questions', 'decisions', 'followups']) {
      const active = tabName === name;
      const tab = document.getElementById(`appointment-tab-${tabName}`);
      const panel = document.getElementById(`appointment-panel-${tabName}`);
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    }
  }

  function handleAppointmentTabKeydown(event) {
    const names = ['questions', 'decisions', 'followups'];
    const tabs = names.map(name => document.getElementById(`appointment-tab-${name}`));
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    switchAppointmentTab(names[next]);
    tabs[next].focus();
  }

  function renderAppointmentWorkspace() {
    if (!appointmentDialogOpen) return;
    const visit = currentVisit();
    if (!visit) return;
    document.getElementById('appointment-dialog-title').textContent = visit.title || 'Visit';
    document.getElementById('appointment-dialog-meta').textContent = [
      visit.date ? fmtDate(visit.date) : 'Date pending',
      visit.time,
      visit.clinician,
      visit.location,
    ].filter(Boolean).join(' · ');
    const status = document.getElementById('visit-status-badge');
    status.textContent = visitStatusLabel(visit.status);
    status.className = `visit-status-badge ${safeClassToken(visit.status, 'planned')}`;

    const selector = document.getElementById('appointment-visit-select');
    if (selector) {
      selector.innerHTML = [...visitsById.values()].map(item =>
        `<option value="${escHtml(item.id)}">${escHtml(item.title)} · ${escHtml(visitStatusLabel(item.status))}</option>`
      ).join('');
      selector.value = visit.id;
    }

    document.getElementById('visit-start-button').hidden = visit.status !== 'planned';
    document.getElementById('visit-complete-button').hidden =
      !['planned', 'in_progress'].includes(visit.status);
    document.getElementById('visit-cancel-button').hidden =
      !['planned', 'in_progress'].includes(visit.status);

    renderVisitSourceQuestions();
    renderVisitQuestions();
    renderVisitDecisions();
    renderVisitFollowUps();
    restoreAppointmentDraft(visit);
    switchAppointmentTab(activeAppointmentTab);
  }

  async function saveVisitDetails() {
    const visit = currentVisit();
    if (!visit) return;
    const title = (document.getElementById('visit-edit-title')?.value || '').trim();
    if (!title) {
      setFormError('visit-details-error', 'Enter a visit title.');
      return;
    }
    const body = {
      expected_token: visit.token,
      title,
      date: document.getElementById('visit-edit-date')?.value || null,
      time: (document.getElementById('visit-edit-time')?.value || '').trim() || null,
      clinician: (document.getElementById('visit-edit-clinician')?.value || '').trim() || null,
      location: (document.getElementById('visit-edit-location')?.value || '').trim() || null,
    };
    const unchanged = body.title === visit.title
      && body.date === (visit.date || null)
      && body.time === (visit.time || null)
      && body.clinician === (visit.clinician || null)
      && body.location === (visit.location || null);
    if (unchanged) {
      setFormError('visit-details-error', 'Change at least one visit detail before saving.');
      return;
    }
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}`,
      body,
      visit.id,
      'PATCH',
    );
    if (result) {
      appointmentDrafts.delete(visit.id);
      setFormError('visit-details-error', '');
      renderAppointmentWorkspace();
    }
  }

  async function changeVisitStatus(targetStatus) {
    const visit = currentVisit();
    if (!visit) return;
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}`,
      { expected_token: visit.token, status: targetStatus },
      visit.id,
      'PATCH',
    );
    if (result) {
      appointmentDrafts.delete(visit.id);
      renderAppointmentWorkspace();
    }
  }

  function renderVisitSourceQuestions() {
    const container = document.getElementById('visit-source-questions');
    if (!container) return;
    const generated = appointmentQuestionSources.filter(
      question => question.source === 'ai' && generatedQuestionIsCurrent(question)
    );
    if (!generated.length && !generatedQuestionsUnavailable) {
      container.innerHTML = '<div class="empty-state">No generated questions available.</div>';
      return;
    }
    const currentRows = generated.map(question =>
      `<div class="visit-source-question" data-source-question-id="${escHtml(question.id)}" data-source-token="${escHtml(question.source_token)}">
        <div><strong>${escHtml(question.text)}</strong><span>Current generated question</span></div>
        <button class="button secondary" onclick="addGeneratedVisitQuestion(this.closest('.visit-source-question'))">Add</button>
      </div>`
    );
    if (generatedQuestionsUnavailable) {
      currentRows.push(`<div class="visit-source-question unavailable">
        <div><strong>Generated questions unavailable</strong><span>Reload the current questions before adding a generated choice.</span></div>
        <button class="button secondary" onclick="loadQuestions()">Retry</button>
      </div>`);
    }
    container.innerHTML = currentRows.join('');
  }

  async function addGeneratedVisitQuestion(row) {
    const visit = currentVisit();
    const sourceId = row?.dataset.sourceQuestionId;
    const sourceToken = row?.dataset.sourceToken;
    if (!visit || !sourceId || !sourceToken) return;
    await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/questions`,
      {
        expected_visit_token: visit.token,
        source_kind: 'generated',
        source_question_id: sourceId,
        expected_source_token: sourceToken,
        pinned: false,
        order: visit.question_snapshots.length,
      },
      visit.id,
    );
  }

  async function addManualVisitQuestion() {
    const visit = currentVisit();
    const text = (document.getElementById('visit-manual-question')?.value || '').trim();
    if (!visit || !text) {
      setFormError('visit-question-error', 'Enter a manual caregiver question.');
      updateAppointmentFormValidity();
      return;
    }
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/questions`,
      {
        expected_visit_token: visit.token,
        source_kind: 'manual',
        text,
        category: document.getElementById('visit-manual-category')?.value || 'Other',
        priority: document.getElementById('visit-manual-priority')?.value || 'medium',
        pinned: false,
        order: visit.question_snapshots.length,
      },
      visit.id,
    );
    if (result) {
      document.getElementById('visit-manual-question').value = '';
      const draft = appointmentDrafts.get(visit.id);
      if (draft) draft.manualQuestion = '';
      setFormError('visit-question-error', '');
      updateAppointmentFormValidity();
    }
  }

  function renderVisitQuestions() {
    const visit = currentVisit();
    const list = document.getElementById('visit-question-list');
    if (!visit || !list) return;
    const questions = sortedVisitQuestions(visit);
    if (!questions.length) {
      list.innerHTML = '<div class="empty-state">Add questions before or during the appointment.</div>';
      return;
    }
    list.innerHTML = questions.map((question, index) => {
      const sameGroup = questions.filter(item => Boolean(item.pinned) === Boolean(question.pinned));
      const groupIndex = sameGroup.findIndex(item => item.id === question.id);
      const sourceLabel = question.source_kind === 'generated'
        ? `Generated snapshot · generation ${question.source_generation_id || 'unavailable'} · record revision ${question.source_profile_revision ?? 'unavailable'}`
        : 'Manual caregiver question';
      const answer = question.answer;
      return `<article class="visit-question" data-visit-question-id="${escHtml(question.id)}" data-question-token="${escHtml(question.token)}">
        <div class="visit-question-heading">
          <span class="visit-question-rank">${index + 1}</span>
          <div><strong>${escHtml(question.text)}</strong><span>${escHtml(sourceLabel)}</span></div>
          <button class="icon-button visit-pin-button ${question.pinned ? 'pinned' : ''}" onclick="toggleVisitQuestionPin(this.closest('.visit-question'))" aria-label="${question.pinned ? 'Unpin' : 'Pin'} question" title="${question.pinned ? 'Unpin' : 'Pin'}">${question.pinned ? '★' : '☆'}</button>
        </div>
        <div class="visit-question-order">
          <button class="button secondary" onclick="moveVisitQuestion(this.closest('.visit-question'),-1)" ${groupIndex === 0 ? 'disabled' : ''}>Move up</button>
          <button class="button secondary" onclick="moveVisitQuestion(this.closest('.visit-question'),1)" ${groupIndex === sameGroup.length - 1 ? 'disabled' : ''}>Move down</button>
          <label><span>Rank</span><select onchange="rankVisitQuestion(this.closest('.visit-question'),Number(this.value))">${sameGroup.map((item, rank) => `<option value="${rank}" ${item.id === question.id ? 'selected' : ''}>${rank + 1}</option>`).join('')}</select></label>
        </div>
        ${answer ? `<div class="visit-answer captured">
          <strong>${answer.status === 'unknown' ? 'Clinician answer explicitly unknown' : 'Captured answer'}</strong>
          ${answer.text ? `<p>${escHtml(answer.text)}</p>` : ''}
          <span class="capture-provenance">Caregiver-entered · attributed to clinician · unverified</span>
        </div>` : `<div class="visit-answer">
          <label><span>Answer status</span><select class="visit-answer-status" onchange="toggleVisitAnswerText(this)"><option value="answered">Answered</option><option value="unknown">Explicitly unknown</option></select></label>
          <label class="visit-answer-text-label"><span>Clinician-attributed answer</span><textarea class="visit-answer-text" maxlength="4000" rows="3"></textarea></label>
          <button class="button primary" onclick="saveVisitAnswer(this.closest('.visit-question'))">Save answer</button>
        </div>`}
      </article>`;
    }).join('');
  }

  function toggleVisitAnswerText(select) {
    const row = select.closest('.visit-question');
    const text = row?.querySelector('.visit-answer-text');
    const label = row?.querySelector('.visit-answer-text-label');
    const unknown = select.value === 'unknown';
    if (text) {
      text.disabled = unknown;
      if (unknown) text.value = '';
    }
    if (label) label.hidden = unknown;
  }

  async function toggleVisitQuestionPin(row) {
    const visit = currentVisit();
    const id = row?.dataset.visitQuestionId;
    const token = row?.dataset.questionToken;
    const question = visit?.question_snapshots.find(item => item.id === id);
    if (!visit || !question || !token) return;
    await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/questions/${encodeURIComponent(id)}`,
      { expected_token: token, pinned: !question.pinned },
      visit.id,
      'PATCH',
    );
  }

  async function persistVisitQuestionOrder(ordered) {
    const visit = currentVisit();
    if (!visit || ordered.length !== visit.question_snapshots.length) return;
    const currentIds = sortedVisitQuestions(visit).map(question => question.id);
    if (currentIds.every((id, index) => id === ordered[index]?.id)) return;
    await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/questions/order`,
      {
        expected_visit_token: visit.token,
        questions: ordered.map(question => ({
          id: question.id,
          expected_token: question.token,
        })),
      },
      visit.id,
      'PATCH',
    );
  }

  function reorderedQuestionList(questionId, destination) {
    const visit = currentVisit();
    const all = sortedVisitQuestions(visit);
    const question = all.find(item => item.id === questionId);
    if (!question) return all;
    const pinned = all.filter(item => item.pinned);
    const unpinned = all.filter(item => !item.pinned);
    const group = question.pinned ? pinned : unpinned;
    const sourceIndex = group.findIndex(item => item.id === questionId);
    const target = Math.max(0, Math.min(destination, group.length - 1));
    if (sourceIndex === target) return all;
    group.splice(sourceIndex, 1);
    group.splice(target, 0, question);
    return [...pinned, ...unpinned];
  }

  async function moveVisitQuestion(row, delta) {
    const visit = currentVisit();
    const question = visit?.question_snapshots.find(
      item => item.id === row?.dataset.visitQuestionId
    );
    if (!question) return;
    const group = sortedVisitQuestions(visit).filter(
      item => Boolean(item.pinned) === Boolean(question.pinned)
    );
    const current = group.findIndex(item => item.id === question.id);
    await persistVisitQuestionOrder(reorderedQuestionList(question.id, current + delta));
  }

  async function rankVisitQuestion(row, rank) {
    const id = row?.dataset.visitQuestionId;
    if (!id || !Number.isInteger(rank)) return;
    await persistVisitQuestionOrder(reorderedQuestionList(id, rank));
  }

  async function saveVisitAnswer(row) {
    const visit = currentVisit();
    const questionId = row?.dataset.visitQuestionId;
    const expectedToken = row?.dataset.questionToken;
    const status = row?.querySelector('.visit-answer-status')?.value;
    const text = (row?.querySelector('.visit-answer-text')?.value || '').trim();
    if (!visit || !questionId || !expectedToken) return;
    if (status === 'answered' && !text) {
      setFormError('visit-question-error', 'Enter the clinician-attributed answer.');
      return;
    }
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/questions/${encodeURIComponent(questionId)}`,
      {
        expected_token: expectedToken,
        answer: { status, text: status === 'answered' ? text : null },
      },
      visit.id,
      'PATCH',
    );
    if (result) {
      const draft = appointmentDrafts.get(visit.id);
      if (draft?.answers) delete draft.answers[questionId];
    }
  }

  function decisionLifecyclePresentation(status, correctionBlocked = false) {
    if (status === 'active') {
      return {
        copy: correctionBlocked
          ? 'Reload this changed decision before creating a correction.'
          : 'Active decisions can be marked for confirmation, corrected with an immutable successor, or retracted.',
        controls: `<button class="button secondary" onclick="changeDecisionStatus(this.closest('.visit-decision'),'needs_confirmation')">Needs confirmation</button>
          ${correctionBlocked ? '' : `<button class="button secondary" onclick="prepareDecisionSuccessor(this.closest('.visit-decision'))">Correct with successor</button>`}
          <button class="button secondary danger" onclick="changeDecisionStatus(this.closest('.visit-decision'),'retracted')">Retract</button>`,
      };
    }
    if (status === 'needs_confirmation') {
      return {
        copy: 'Confirm this decision as active or retract it. Correction is available only after confirmation.',
        controls: `<button class="button secondary" onclick="changeDecisionStatus(this.closest('.visit-decision'),'active')">Confirm active</button>
          <button class="button secondary danger" onclick="changeDecisionStatus(this.closest('.visit-decision'),'retracted')">Retract</button>`,
      };
    }
    if (status === 'superseded') {
      return {
        copy: 'This superseded decision is immutable history; no further lifecycle actions are available.',
        controls: '',
      };
    }
    if (status === 'retracted') {
      return {
        copy: 'This retracted decision is immutable history; no further lifecycle actions are available.',
        controls: '',
      };
    }
    return {
      copy: 'This decision has an unavailable lifecycle state; no actions are available.',
      controls: '',
    };
  }

  function renderVisitDecisions() {
    const visit = currentVisit();
    const list = document.getElementById('visit-decision-list');
    const select = document.getElementById('visit-followup-decision');
    if (!visit || !list || !select) return;
    const decisions = [...(visit.decisions || [])].reverse();
    select.innerHTML = '<option value="">No linked decision</option>' + (visit.decisions || [])
      .filter(item => ['active', 'needs_confirmation'].includes(item.status))
      .map(item => `<option value="${escHtml(item.id)}">${escHtml(item.text.slice(0, 100))}</option>`)
      .join('');
    if (!decisions.length) {
      list.innerHTML = '<div class="empty-state">No clinician-attributed decisions captured.</div>';
      return;
    }
    list.innerHTML = decisions.map(decision => {
      const lifecycle = decisionLifecyclePresentation(
        decision.status,
        decisionSuccessorConflicts.has(decision.id)
      );
      return `<article class="visit-decision" data-decision-id="${escHtml(decision.id)}" data-decision-token="${escHtml(decision.token)}">
        <div class="visit-decision-heading"><strong>${escHtml(decision.text)}</strong><span class="visit-status-badge ${safeClassToken(decision.status, 'active')}">${escHtml(decision.status.replaceAll('_', ' '))}</span></div>
        <p class="capture-provenance">Caregiver-entered · attributed to clinician · unverified</p>
        ${decision.supersedes_id ? `<p class="visit-source-label">Successor to ${escHtml(decision.supersedes_id)}</p>` : ''}
        <p class="visit-decision-lifecycle">${escHtml(lifecycle.copy)}</p>
        ${lifecycle.controls ? `<div class="visit-form-actions">${lifecycle.controls}</div>` : ''}
      </article>`;
    }).join('');
  }

  function prepareDecisionSuccessor(row) {
    const visit = currentVisit();
    const id = row?.dataset.decisionId;
    const decision = (visit?.decisions || []).find(item => item.id === id);
    if (!visit || !decision || decision.status !== 'active' || decisionSuccessorConflicts.has(id)) {
      if (visit) clearDecisionSuccessorState(visit.id);
      setAppointmentMessage('Reload this changed decision before creating a correction.', 'conflict');
      loadVisits();
      return;
    }
    document.getElementById('visit-decision-supersedes').value = id;
    document.getElementById('visit-decision-label').textContent = 'Correct with a successor decision';
    document.getElementById('visit-decision-cancel-supersede').hidden = false;
    document.getElementById('visit-decision-text').focus();
    captureAppointmentDraft();
  }

  function cancelDecisionSuccessor() {
    document.getElementById('visit-decision-supersedes').value = '';
    document.getElementById('visit-decision-label').textContent =
      'Caregiver-entered decision attributed to the clinician';
    document.getElementById('visit-decision-cancel-supersede').hidden = true;
    captureAppointmentDraft();
  }

  async function addVisitDecision() {
    const visit = currentVisit();
    const text = (document.getElementById('visit-decision-text')?.value || '').trim();
    if (!visit || !text) {
      setFormError('visit-decision-error', 'Enter the clinician-attributed decision.');
      updateAppointmentFormValidity();
      return;
    }
    const supersedesId = document.getElementById('visit-decision-supersedes')?.value || null;
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/decisions`,
      {
        expected_visit_token: visit.token,
        text,
        supersedes_id: supersedesId,
      },
      visit.id,
    );
    if (result) {
      document.getElementById('visit-decision-text').value = '';
      cancelDecisionSuccessor();
      const draft = appointmentDrafts.get(visit.id);
      if (draft) {
        draft.decisionText = '';
        draft.supersedesId = '';
      }
      setFormError('visit-decision-error', '');
      updateAppointmentFormValidity();
    }
  }

  async function changeDecisionStatus(row, status) {
    const visit = currentVisit();
    const id = row?.dataset.decisionId;
    const token = row?.dataset.decisionToken;
    if (!visit || !id || !token) return;
    await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/decisions/${encodeURIComponent(id)}`,
      { expected_token: token, status },
      visit.id,
      'PATCH',
    );
  }

  function renderVisitFollowUps() {
    const visit = currentVisit();
    const list = document.getElementById('visit-followup-list');
    if (!visit || !list) return;
    const items = followUpItems().filter(item =>
      item.visit_id === visit.id || (visit.follow_up_ids || []).includes(item.id)
    );
    const staleNotice = followUpProjectionStale
      ? '<div class="follow-up-stale-note compact" role="status"><div><strong>Offline snapshot · read-only</strong><span>Reload actions before adding or changing follow-through.</span></div></div>'
      : '';
    if (!items.length) {
      list.innerHTML = `${staleNotice}<div class="empty-state">No resulting follow-ups for this visit.</div>`;
      return;
    }
    list.innerHTML = staleNotice + items.map(item => {
      const outcome = followUpOutcomePresentation(item.outcome);
      return `<article class="visit-followup" data-followup-id="${escHtml(item.id)}">
      <div class="visit-decision-heading"><strong>${escHtml(item.text)}</strong><span class="visit-status-badge ${safeClassToken(item.status, 'open')}">${escHtml(item.status.replaceAll('_', ' '))}</span></div>
      <p>${escHtml([item.owner && `Owner: ${item.owner}`, item.due_date && `Due ${fmtDate(item.due_date)}`].filter(Boolean).join(' · ') || 'Owner and due date not set')}</p>
      ${item.decision_id ? `<p class="visit-source-label">Linked to visit decision ${escHtml(item.decision_id)}</p>` : ''}
      ${item.outcome?.text ? `<p>${escHtml(item.outcome.text)}</p>` : ''}
      ${outcome ? `<p class="capture-provenance">${escHtml(outcome.label)}</p>` : ''}
    </article>`;
    }).join('');
  }

  async function createVisitFollowUp() {
    if (followUpProjectionStale) {
      setAppointmentMessage('Reload the current action list before creating a follow-up.', 'offline');
      return;
    }
    const visit = currentVisit();
    const text = (document.getElementById('visit-followup-text')?.value || '').trim();
    if (!visit || !text) {
      setFormError('visit-followup-error', 'Enter a follow-up using contact, ask, discuss, or confirm wording.');
      updateAppointmentFormValidity();
      return;
    }
    if (/^(start|stop|hold|pause|resume|switch|increase|decrease|administer|take|skip|discontinue|withhold)\b/i.test(text)) {
      setFormError('visit-followup-error', 'Use contact, ask, discuss, or confirm wording with the treating team.');
      return;
    }
    const decisionId = document.getElementById('visit-followup-decision')?.value || null;
    const result = await submitWorkflowMutation(
      `/api/visits/${encodeURIComponent(visit.id)}/follow-ups`,
      {
        expected_visit_token: visit.token,
        decision_id: decisionId,
        origin_kind: decisionId ? 'visit_decision' : 'manual',
        text,
        owner: (document.getElementById('visit-followup-owner')?.value || '').trim() || null,
        due_date: document.getElementById('visit-followup-due')?.value || null,
      },
      visit.id,
    );
    if (result) {
      for (const id of [
        'visit-followup-text', 'visit-followup-owner',
        'visit-followup-due', 'visit-followup-decision'
      ]) {
        const input = document.getElementById(id);
        if (input) input.value = '';
      }
      const draft = appointmentDrafts.get(visit.id);
      if (draft) {
        draft.followUpText = '';
        draft.followUpOwner = '';
        draft.followUpDue = '';
        draft.followUpDecision = '';
      }
      setFormError('visit-followup-error', '');
      updateAppointmentFormValidity();
    }
  }

  // ── Questions ────────────────────────────────────────────────────────────
  let questionsOpen = true;

  function toggleQuestions() {
    questionsOpen = !questionsOpen;
    document.getElementById('q-body').classList.toggle('hidden', !questionsOpen);
    const caret = document.getElementById('q-caret');
    if (caret) caret.textContent = questionsOpen ? '▼' : '▶';
    if (questionsOpen) loadQuestions();
  }

  function generatedQuestionIsCurrent(question) {
    if (!question || question.source !== 'ai' || question.stale !== false) return false;
    if (
      typeof question.id !== 'string' || !question.id.trim()
      || typeof question.text !== 'string' || !question.text.trim()
      || typeof question.source_token !== 'string' || !question.source_token.trim()
      || typeof question.generation_job_id !== 'string' || !question.generation_job_id.trim()
      || question.source_profile_revision == null
      || latestProfileRevision == null
    ) {
      return false;
    }
    return String(question.source_profile_revision) === String(latestProfileRevision);
  }

  function projectQuestionChoices(questions) {
    const projected = [];
    let unavailable = false;
    for (const question of Array.isArray(questions) ? questions : []) {
      if (question?.source !== 'ai') {
        projected.push({ ...question });
      } else if (generatedQuestionIsCurrent(question)) {
        projected.push({ ...question });
      } else {
        unavailable = true;
      }
    }
    return { items: projected, unavailable };
  }

  function redactGeneratedQuestionChoices() {
    questionLoadEpoch += 1;
    appointmentQuestionSources = appointmentQuestionSources.filter(
      question => question?.source !== 'ai'
    );
    generatedQuestionsUnavailable = true;
    renderQuestions(appointmentQuestionSources);
    renderVisitSourceQuestions();
  }

  async function loadQuestions() {
    const request = capturePatientRequest();
    const requestQuestionEpoch = ++questionLoadEpoch;
    const requestProfileRevision = latestProfileRevision == null
      ? null
      : String(latestProfileRevision);
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request)
      && requestQuestionEpoch === questionLoadEpoch
      && (
        requestProfileRevision == null
        || String(latestProfileRevision) === requestProfileRevision
      )
    );
    try {
      const r = await fetch('/api/questions');
      if (!requestIsCurrent()) return null;
      const qs = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      if (!authorizePatientResponse(request, qs).accepted) return [];
      const projection = projectQuestionChoices(qs);
      appointmentQuestionSources = projection.items;
      generatedQuestionsUnavailable = projection.unavailable;
      appointmentQuestionSources.profileRevision = requestProfileRevision;
      renderQuestions(appointmentQuestionSources);
      renderVisitSourceQuestions();
      reportLoadSuccess('questions');
      return appointmentQuestionSources;
    } catch(e) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(e)) {
        reportLoadError('questions', e);
        if (requestIsCurrent()) evictClientPhi(e);
        return null;
      } else {
        redactGeneratedQuestionChoices();
      }
      reportLoadError('questions', e);
      return null;
    }
  }

  function renderQuestions(qs) {
    const current = (Array.isArray(qs) ? qs : []).filter(
      q => q.source !== 'ai' || generatedQuestionIsCurrent(q)
    );
    const urgent = current.filter(q => !q.asked && q.priority === 'urgent');
    const high   = current.filter(q => !q.asked && q.priority === 'high');
    const medium = current.filter(q => !q.asked && (q.priority === 'medium' || !q.priority));
    const asked  = current.filter(q => q.asked);

    const badge = document.getElementById('q-count-badge');
    if (badge) {
      const unasked = current.filter(q => !q.asked).length;
      badge.textContent = unasked;
      badge.hidden = unasked === 0;
    }

    const qRow = (q) => {
      return `
      <div class="q-item${q.asked?' asked':''}" data-question-id="${escHtml(q.id)}">
        <div class="q-priority-dot ${safeClassToken(q.priority, 'medium')}"></div>
        <button class="q-checkbox${q.asked?' checked':''}" onclick="toggleQuestion(this.closest('.q-item').dataset.questionId)" aria-label="${q.asked ? 'Mark question as not asked' : 'Mark question as asked'}">${q.asked?'✓':''}</button>
        <div class="q-text-wrap">
          <div class="q-text${q.asked?' asked':''}">${escHtml(q.text)}</div>
          <div class="q-meta">
            <span class="q-cat ${safeClassToken(q.category, 'Other')}">${escHtml(translateCategory(q.category||'Other'))}</span>
            ${q.rationale ? `<span class="q-rationale">${escHtml(q.rationale)}</span>` : ''}
          </div>
        </div>
        <button class="q-delete" onclick="deleteQuestion(this.closest('.q-item').dataset.questionId)" aria-label="Delete question" title="Delete">✕</button>
      </div>`;
    };

    const grpHdr = (label, color) =>
      `<div style="font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:${color};padding:8px 16px 2px;border-bottom:1px solid var(--border)">${label}</div>`;

    let html = '';
    if (urgent.length) { html += grpHdr('Urgent', 'var(--red)'); html += urgent.map(qRow).join(''); }
    if (high.length)   { html += grpHdr('Important', 'var(--amber)'); html += high.map(qRow).join(''); }
    if (medium.length) { html += grpHdr('Other', 'var(--text2)'); html += medium.map(qRow).join(''); }
    if (asked.length)  { html += grpHdr('Already asked', 'var(--text2)'); html += asked.map(qRow).join(''); }
    if (generatedQuestionsUnavailable) {
      html += grpHdr('Generated questions unavailable', 'var(--amber)');
      html += `<div class="q-item stale generated-question-unavailable">
        <div class="q-text-wrap">
          <div class="q-text">Generated questions unavailable</div>
          <div class="q-meta"><span class="q-stale-label">Reload current questions before using a generated choice.</span></div>
        </div>
        <button class="button secondary" onclick="loadQuestions()">Retry</button>
      </div>`;
    }
    if (!html) html = '<div class="q-empty">No questions yet. Generate suggestions or add your own.</div>';

    const list = document.getElementById('q-list');
    if (list) list.innerHTML = html;
  }

  async function generateQuestions() {
    const request = capturePatientRequest();
    const btnId    = 'q-gen-btn';
    const apptType = 'oncology follow-up';
    const btn = document.getElementById(btnId);
    if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }

    if (!questionsOpen) toggleQuestions();

    try {
      const r = await fetch('/api/questions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ appointment_type: apptType }),
      });
      const submitted = await readJobSubmission(r);
      const completed = await waitForJob(submitted.job_id);
      if (!authorizePatientResponse(request, completed).accepted) return;
      await loadQuestions();
      if (patientRequestIsCurrent(request)) reportLoadSuccess('action');
    } catch(e) {
      if (!patientRequestIsCurrent(request)) return;
      reportLoadError('action', e);
    }
    finally {
      if (patientRequestIsCurrent(request) && btn) {
        btn.disabled = false;
        btn.textContent = '✦ Generate questions';
      }
    }
  }

  async function addQuestion() {
    const request = capturePatientRequest();
    const inputId = 'q-add-input';
    const input = document.getElementById(inputId);
    const text = (input?.value || '').trim();
    if (!text) {
      setFormError('q-form-error', 'Enter a question before adding it.');
      updateFormValidity();
      return;
    }
    input.value = '';
    try {
      const result = await readJsonResponse(await fetch('/api/questions/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }));
      if (!authorizePatientResponse(request, result).accepted) return;
      await loadQuestions();
      if (!patientRequestIsCurrent(request)) return;
      setFormError('q-form-error', '');
    } catch(e) {
      if (!patientRequestIsCurrent(request)) return;
      input.value = text;
      setFormError('q-form-error', e.message || 'The question could not be added.');
      reportLoadError('action', e);
    }
    if (patientRequestIsCurrent(request)) updateFormValidity();
  }

  async function toggleQuestion(qid) {
    try {
      await readJsonResponse(await fetch(`/api/questions/${encodeURIComponent(qid)}/toggle`, { method: 'POST' }));
      await loadQuestions();
    } catch(e) {
      reportLoadError('action', e);
    }
  }

  async function deleteQuestion(qid) {
    try {
      await readJsonResponse(await fetch(`/api/questions/${encodeURIComponent(qid)}`, { method: 'DELETE' }));
      await loadQuestions();
    } catch(e) {
      reportLoadError('action', e);
    }
  }

  // ── Chat ─────────────────────────────────────────────────────────────────
  let chatHistory = [];
  let chatHistoryRevision = null;
  let chatOpen = false;

  function syncChatRevision(revision, forceNotice = false, reloadQuestions = true) {
    const priorProfileRevision = latestProfileRevision == null
      ? null
      : normalizedRevision(latestProfileRevision);
    if (revision == null) {
      return false;
    }
    const normalized = normalizedRevision(revision);
    if (!Number.isSafeInteger(normalized)) return false;
    if (Number.isSafeInteger(priorProfileRevision) && normalized < priorProfileRevision) {
      return false;
    }
    if (chatHistoryRevision == null) {
      chatHistoryRevision = normalized;
      latestProfileRevision = normalized;
      if (priorProfileRevision != null && priorProfileRevision !== normalized) {
        redactGeneratedQuestionChoices();
        redactGeneratedSummaryActions();
      }
      const generatedChoicesNeedAuthority = generatedQuestionsUnavailable
        || appointmentQuestionSources.some(question => question?.source === 'ai');
      if (generatedChoicesNeedAuthority) {
        redactGeneratedQuestionChoices();
        if (reloadQuestions) loadQuestions();
      }
      return false;
    }
    const currentChatRevision = normalizedRevision(chatHistoryRevision);
    if (Number.isSafeInteger(currentChatRevision) && normalized < currentChatRevision) {
      return false;
    }
    const changed = currentChatRevision !== normalized;
    latestProfileRevision = normalized;
    if (changed) {
      redactGeneratedQuestionChoices();
      redactGeneratedSummaryActions();
      if (reloadQuestions) loadQuestions();
    }
    if (!changed && !forceNotice) return false;
    chatHistoryRevision = normalized;
    chatHistory = [];
    const msgs = document.getElementById('chat-messages');
    if (msgs) {
      msgs.innerHTML = `<div class="chat-revision-notice" role="status">
        Patient record changed. Prior chat history was cleared before new answers.
      </div>`;
    }
    return changed;
  }

  function toggleChat() {
    chatOpen = !chatOpen;
    const panel = document.getElementById('chat-panel');
    panel.style.display = chatOpen ? 'flex' : 'none';
    panel.setAttribute('aria-hidden', String(!chatOpen));
    if (chatOpen) {
      const trigger = document.activeElement;
      activateDialog(panel, trigger);
      setTimeout(() => document.getElementById('chat-input')?.focus(), 50);
    } else {
      deactivateDialog(panel);
    }
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
    updateFormValidity();
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
    const request = capturePatientRequest();
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('chat-send-btn');
    const text = (input?.value || '').trim();
    if (!text) {
      setFormError('chat-form-error', 'Enter a question before sending.');
      updateFormValidity();
      return;
    }
    if (btn.dataset.busy === 'true') return;

    input.value = '';
    appendMsg('user', text);
    chatHistory.push({ role: 'user', content: text });

    btn.disabled = true;
    btn.dataset.busy = 'true';
    btn.textContent = '…';
    const thinkingDiv = appendMsg('assistant', 'Thinking…');
    thinkingDiv.querySelector('.chat-bubble').classList.add('thinking');

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: chatHistory.slice(0, -1),
          history_revision: chatHistoryRevision,
        }),
      });
      const data = await readJsonResponse(r);
      const authority = authorizePatientResponse(request, data);
      if (!authority.accepted || authority.profileAdvanced) return;
      const completed = await waitForJob(data.job_id);
      if (!authorizePatientResponse(request, completed).accepted) return;
      const reply = (completed.result || {}).reply;
      if (!reply) throw new Error('No response was produced.');

      thinkingDiv.querySelector('.chat-bubble').classList.remove('thinking');
      updateLastMsg(thinkingDiv, reply);
      chatHistory.push({ role: 'assistant', content: reply });
      setFormError('chat-form-error', '');
    } catch(e) {
      if (!patientRequestIsCurrent(request)) return;
      if (e.status === 409) {
        authorizePatientResponse(request, e.data || {});
      }
      if (!patientRequestIsCurrent(request)) return;
      thinkingDiv.querySelector('.chat-bubble').classList.remove('thinking');
      updateLastMsg(thinkingDiv, `Error: ${e.message}`);
      setFormError('chat-form-error', e.message || 'The question could not be sent.');
    } finally {
      if (patientRequestIsCurrent(request)) {
        delete btn.dataset.busy;
        btn.textContent = 'Send';
        input.focus();
        updateFormValidity();
      }
    }
  }

  // ── Init ────────────────────────────────────────────────────────────────
  loadStatus();
  loadTasks();
  loadSummary();
  loadQuestions();
  loadJudgments();
  loadSymptoms();
  loadPatientEvidence();
  loadVisits();
  loadFollowUps();
  ['q-add-input', 'judgment-input', 'sym-name', 'chat-input'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateFormValidity);
  });
  [
    'visit-create-title', 'visit-manual-question',
    'visit-decision-text', 'visit-followup-text'
  ].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateAppointmentFormValidity);
  });
  const createSurface = document.getElementById('visit-create-panel');
  createSurface?.addEventListener('input', invalidateWorkflowRetryOnDraftChange);
  createSurface?.addEventListener('change', invalidateWorkflowRetryOnDraftChange);
  const appointmentSurface = document.getElementById('appointment-dialog');
  const handleAppointmentDraftChange = () => {
    invalidateWorkflowRetryOnDraftChange();
    captureAppointmentDraft();
  };
  appointmentSurface?.addEventListener('input', handleAppointmentDraftChange);
  appointmentSurface?.addEventListener('change', handleAppointmentDraftChange);
  const followUpSurface = document.getElementById('follow-up-dialog');
  followUpSurface?.addEventListener('input', invalidateFollowUpRetryOnDraftChange);
  followUpSurface?.addEventListener('change', invalidateFollowUpRetryOnDraftChange);
  updateFormValidity();
  startPolling();
  const requestedView = window.location.hash.replace('#', '');
  if (['today', 'patient', 'questions', 'activity'].includes(requestedView) && requestedView !== 'today') {
    switchView(requestedView, document.getElementById(`nav-${requestedView}`));
  }
