/* Extracted from static/index.html (Phase 4 UI split). */
  let selectedTaskId = null;
  let pollingInterval = null;
  let currentReportText = '';
  let activeView = 'today';
  let researchProjection = null;
  let researchResponseOwner = null;
  let researchProjectionState = 'idle';
  let researchNetworkAmbiguous = false;
  let researchLoadEpoch = 0;
  let researchSelectionEpoch = 0;
  let researchDialogEpoch = 0;
  let researchMutationEpoch = 0;
  let researchRequestController = null;
  let researchMutationController = null;
  let researchActiveTab = 'current';
  let researchDialogOpen = false;
  let researchDialogMode = null;
  let researchSelection = null;
  let researchMutationOwner = null;
  let researchMutationPending = false;
  let activeResearchIntent = null;
  let pendingResearchSubmission = null;
  let pendingResearchCompletion = null;
  let researchDraft = null;
  let researchConflictRequiresReselection = false;
  const researchControlAuthority = new WeakMap();
  const researchActionOptionAuthority = new WeakMap();
  let lastDialogTrigger = null;
  let hadActiveJobs = false;
  let pendingSummary = null;
  let activeDialogSurface = null;
  let currentReceipt = null;
  let patientEvidence = null;
  let sourceHistoryExpanded = false;
  let imagingProjection = null;
  let imagingResponseOwner = null;
  let selectedImagingRecordIds = [];
  let comparedImagingRecordIds = [];
  let imagingLoadEpoch = 0;
  let imagingSelectionEpoch = 0;
  let imagingComparisonEpoch = 0;
  let imagingRequestController = null;
  let imagingProjectionState = 'idle';
  let imagingNetworkAmbiguous = false;
  let symptomProjection = null;
  let symptomResponseOwner = null;
  let symptomProjectionState = 'idle';
  let symptomNetworkAmbiguous = false;
  let symptomLoadEpoch = 0;
  let symptomSelectionEpoch = 0;
  let symptomDialogEpoch = 0;
  let symptomMutationEpoch = 0;
  let symptomRequestController = null;
  let symptomMutationController = null;
  let symptomActiveTab = 'current';
  let symptomDialogOpen = false;
  let symptomDialogMode = null;
  let selectedSymptomEpisodeId = null;
  let selectedSymptomEpisodeToken = null;
  let selectedSymptomActionId = null;
  let selectedSymptomActionToken = null;
  let symptomMutationOwner = null;
  let symptomMutationPending = false;
  let activeSymptomIntent = null;
  let pendingSymptomIntent = null;
  let pendingSymptomCompletion = null;
  let symptomDrafts = new Map();
  let treatmentProjection = null;
  let treatmentResponseOwner = null;
  let treatmentProjectionState = 'idle';
  let treatmentNetworkAmbiguous = false;
  let treatmentLoadEpoch = 0;
  let treatmentSelectionEpoch = 0;
  let treatmentDialogEpoch = 0;
  let treatmentMutationEpoch = 0;
  let treatmentRequestController = null;
  let treatmentMutationController = null;
  let treatmentActiveTab = 'records';
  let treatmentDialogOpen = false;
  let treatmentDialogMode = null;
  let treatmentSelection = null;
  let treatmentMutationOwner = null;
  let treatmentMutationPending = false;
  let activeTreatmentIntent = null;
  let pendingTreatmentRetry = null;
  let pendingTreatmentCompletion = null;
  let treatmentDraft = null;
  let biomarkerProjection = null;
  let biomarkerResponseOwner = null;
  let selectedBiomarkerAnalyteId = null;
  let biomarkerLoadEpoch = 0;
  let biomarkerSelectionEpoch = 0;
  let biomarkerRequestController = null;
  let biomarkerProjectionState = 'idle';
  let biomarkerNetworkAmbiguous = false;
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
  let visitRecapLoadEpoch = 0;
  let visitRecapProjection = null;
  let visitRecapAuthority = null;
  let visitRecapExportText = '';
  let visitRecapStale = false;
  let visitRecapState = 'idle';
  let visitRecapMessage = '';
  let visitRecapDownloadUrl = null;
  let visitRecapExportOwner = null;
  let visitRecapExportEpoch = 0;
  let visitRecapNetworkAmbiguous = false;
  let pendingWorkflowIntent = null;
  let activeWorkflowIntent = null;
  let workflowMutationPending = false;
  let workflowMutationOwner = null;
  let appointmentDrafts = new Map();
  let decisionSuccessorConflicts = new Set();
  let alertsById = new Map();
  let alertProjectionStale = false;
  let alertLinkSourcesStale = false;
  let selectedAlertId = null;
  let selectedAlertToken = null;
  let selectedAlertProfileRevision = null;
  let alertSelectionEpoch = 0;
  let alertResolutionDialogOpen = false;
  let alertResolutionIntentOwner = null;
  let alertResolutionMutationPending = false;
  let pendingAlertResolutionIntent = null;
  let activeAlertResolutionIntent = null;
  let alertResolutionDrafts = new Map();
  let alertResolutionResult = null;
  const ALERT_RESOLUTION_OUTCOME_KINDS = new Set([
    'administrative',
    'caregiver_reported',
    'clinician_attributed',
  ]);
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
        typeof alertResolutionMutationPending !== 'undefined'
        && alertResolutionMutationPending
      )
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
    if (options.alertSelection) {
      request.requestAlertEpoch = alertSelectionEpoch;
      request.requestAlertId = selectedAlertId;
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
    if (
      request.requestAlertEpoch != null
      && (
        request.requestAlertEpoch !== alertSelectionEpoch
        || request.requestAlertId !== selectedAlertId
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

  function advancePatientAuthority(profileRevision, options = {}) {
    const revision = normalizedRevision(profileRevision);
    const current = normalizedRevision(latestProfileRevision);
    if (
      !Number.isSafeInteger(revision)
      || (Number.isSafeInteger(current) && revision <= current)
    ) return false;
    if (typeof markVisitRecapStale === 'function') {
      markVisitRecapStale(
        'The patient record changed. Reload the recap before exporting.',
        'stale',
        options.preserveVisitRecapExportOwner === true,
      );
    }
    const biomarkerWasLoaded = (
      typeof biomarkerProjection !== 'undefined'
      && biomarkerProjection !== null
    );
    const biomarkerRequestWasActive = (
      typeof biomarkerRequestController !== 'undefined'
      && biomarkerRequestController !== null
    );
    const imagingWasLoaded = (
      typeof imagingProjection !== 'undefined'
      && imagingProjection !== null
    );
    const imagingRequestWasActive = (
      typeof imagingRequestController !== 'undefined'
      && imagingRequestController !== null
    );
    const symptomWasLoaded = (
      typeof symptomProjection !== 'undefined'
      && symptomProjection !== null
    );
    const symptomRequestWasActive = (
      typeof symptomRequestController !== 'undefined'
      && symptomRequestController !== null
    );
    const treatmentWasLoaded = (
      typeof treatmentProjection !== 'undefined'
      && treatmentProjection !== null
    );
    const treatmentRequestWasActive = (
      typeof treatmentRequestController !== 'undefined'
      && treatmentRequestController !== null
    );
    const researchWasLoaded = (
      typeof researchProjection !== 'undefined'
      && researchProjection !== null
    );
    const researchRequestWasActive = (
      typeof researchRequestController !== 'undefined'
      && researchRequestController !== null
    );
    phiEpoch += 1;
    if (typeof markBiomarkerProjectionStale === 'function') {
      markBiomarkerProjectionStale(
        'The patient record changed. Reload biomarker history before relying on this snapshot.',
        {
          abortRequest: options.preserveBiomarkerRequest !== true,
          ownerPhiEpoch: phiEpoch,
        },
      );
    }
    if (
      (imagingWasLoaded || imagingRequestWasActive)
      && typeof markImagingProjectionStale === 'function'
    ) {
      markImagingProjectionStale(
        'The patient record changed. Imaging is read-only until the authoritative record reloads.',
        {
          abortRequest: options.preserveImagingRequest !== true,
          ownerPhiEpoch: phiEpoch,
        },
      );
    }
    if (
      (symptomWasLoaded || symptomRequestWasActive)
      && typeof markSymptomProjectionStale === 'function'
    ) {
      markSymptomProjectionStale(
        'The patient record changed. Symptoms are read-only until the authoritative record reloads.',
        {
          abortRequest: options.preserveSymptomRequest !== true,
          ownerPhiEpoch: phiEpoch,
          preserveMutation: options.preserveSymptomMutation === true,
        },
      );
    }
    if (
      (treatmentWasLoaded || treatmentRequestWasActive)
      && typeof markTreatmentProjectionStale === 'function'
    ) {
      markTreatmentProjectionStale(
        'The patient record changed. Treatment information is read-only until the authoritative record reloads.',
        {
          abortRequest: options.preserveTreatmentRequest !== true,
          ownerPhiEpoch: phiEpoch,
          preserveMutation: options.preserveTreatmentMutation === true,
        },
      );
      if (
        options.preserveTreatmentRequest !== true
        && typeof ensureTreatmentReconciliation === 'function'
      ) {
        Promise.resolve().then(() => ensureTreatmentReconciliation());
      }
    }
    if (
      options.preserveResearchRequest !== true
      && (researchWasLoaded || researchRequestWasActive)
      && typeof markResearchProjectionStale === 'function'
    ) {
      markResearchProjectionStale(
        'The patient record changed. Research is read-only until the authoritative workspace reloads.',
      );
      if (typeof loadResearchWorkspace === 'function') {
        Promise.resolve().then(() => loadResearchWorkspace({ force: true }));
      }
    }
    taskSelectionEpoch += 1;
    if (
      typeof alertResolutionDialogOpen !== 'undefined'
      && alertResolutionDialogOpen
    ) {
      redactAlertResolutionContext(
        options.preserveAlertIntent
          ? 'Saving the authoritative resolution…'
          : 'The patient record changed. Reload the alert before continuing.'
      );
      if (!options.preserveAlertIntent) {
        captureAlertResolutionDraft();
        if (pendingAlertResolutionIntent?.body) pendingAlertResolutionIntent.body = {};
        if (activeAlertResolutionIntent?.body) activeAlertResolutionIntent.body = {};
        alertSelectionEpoch += 1;
        alertResolutionIntentOwner = null;
        alertResolutionMutationPending = false;
        pendingAlertResolutionIntent = null;
        activeAlertResolutionIntent = null;
      }
    }
    syncChatRevision(revision, true, false);
    if (!options.deferConvergence) requestClinicalConvergence(revision);
    if (
      options.preserveBiomarkerRequest !== true
      && (biomarkerWasLoaded || biomarkerRequestWasActive)
      && typeof activeView !== 'undefined'
      && activeView === 'patient'
      && typeof loadBiomarkerSeries === 'function'
    ) {
      Promise.resolve().then(() => loadBiomarkerSeries());
    }
    if (
      options.preserveImagingRequest !== true
      && (imagingWasLoaded || imagingRequestWasActive)
      && typeof activeView !== 'undefined'
      && activeView === 'patient'
      && typeof ensureImagingSeries === 'function'
    ) {
      Promise.resolve().then(() => ensureImagingSeries());
    }
    if (
      options.preserveSymptomRequest !== true
      && options.preserveSymptomMutation !== true
      && (symptomWasLoaded || symptomRequestWasActive)
      && typeof ensureSymptomEpisodes === 'function'
    ) {
      Promise.resolve().then(() => ensureSymptomEpisodes());
    }
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
    const targetedWorkflowResponse = options.workflow === 'targeted';
    const staleWorkflowProjection = strictWorkflowProjection
      && Number.isSafeInteger(currentWorkflowRevision)
      && (
        !Number.isSafeInteger(responseWorkflowRevision)
        || responseWorkflowRevision < currentWorkflowRevision
      );
    const staleTargetedWorkflow = targetedWorkflowResponse
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
      advancePatientAuthority(responseProfileRevision, {
        preserveAlertIntent: options.alertResolution === true,
        preserveBiomarkerRequest: options.biomarkerProjection === true,
        preserveImagingRequest: options.imagingProjection === true,
        preserveSymptomRequest: options.symptomProjection === true,
        preserveSymptomMutation: options.symptomMutation === true,
        preserveTreatmentRequest: (
          options.treatmentProjection === true
          || options.treatmentMutation === true
        ),
        preserveTreatmentMutation: options.treatmentMutation === true,
        preserveResearchRequest: options.researchProjection === true,
        deferConvergence: options.alertResolution === true,
        preserveVisitRecapExportOwner: options.preserveVisitRecapExportOwner === true,
      });
    }
    if (staleWorkflowProjection || staleTargetedWorkflow) {
      if (profileAdvanced) requestClinicalConvergence(responseProfileRevision);
      return { accepted: false, profileAdvanced };
    }
    const workflowAdvanced = Number.isSafeInteger(responseWorkflowRevision)
      && (
        !Number.isSafeInteger(currentWorkflowRevision)
        || responseWorkflowRevision > currentWorkflowRevision
      );
    if (workflowAdvanced) {
      if (typeof markVisitRecapStale === 'function') {
        markVisitRecapStale(
          'The visit workflow changed. Reload the recap before exporting.',
          'stale',
          options.preserveVisitRecapExportOwner === true,
        );
      }
      workflowRevision = responseWorkflowRevision;
      const biomarkerNeedsWorkflowRefresh = (
        options.biomarkerProjection !== true
        && !profileAdvanced
        && (
          (
            typeof biomarkerProjection !== 'undefined'
            && biomarkerProjection !== null
          )
          || (
            typeof biomarkerRequestController !== 'undefined'
            && biomarkerRequestController !== null
          )
        )
      );
      if (
        biomarkerNeedsWorkflowRefresh
        && typeof markBiomarkerProjectionStale === 'function'
      ) {
        markBiomarkerProjectionStale(
          'The patient workflow changed. Reload biomarker history before relying on this snapshot.',
        );
        if (
          typeof activeView !== 'undefined'
          && activeView === 'patient'
          && typeof loadBiomarkerSeries === 'function'
        ) {
          Promise.resolve().then(() => loadBiomarkerSeries());
        }
      }
      const imagingNeedsWorkflowRefresh = (
        options.imagingProjection !== true
        && !profileAdvanced
        && (
          (
            typeof imagingProjection !== 'undefined'
            && imagingProjection !== null
          )
          || (
            typeof imagingRequestController !== 'undefined'
            && imagingRequestController !== null
          )
        )
      );
      if (
        imagingNeedsWorkflowRefresh
        && typeof markImagingProjectionStale === 'function'
      ) {
        markImagingProjectionStale(
          'The patient workflow changed. Imaging is read-only until the authoritative record reloads.',
        );
        if (
          typeof activeView !== 'undefined'
          && activeView === 'patient'
          && typeof ensureImagingSeries === 'function'
        ) {
          Promise.resolve().then(() => ensureImagingSeries());
        }
      }
      const symptomNeedsWorkflowRefresh = (
        options.symptomProjection !== true
        && options.symptomMutation !== true
        && !profileAdvanced
        && (
          (
            typeof symptomProjection !== 'undefined'
            && symptomProjection !== null
          )
          || (
            typeof symptomRequestController !== 'undefined'
            && symptomRequestController !== null
          )
        )
      );
      if (
        symptomNeedsWorkflowRefresh
        && typeof markSymptomProjectionStale === 'function'
      ) {
        markSymptomProjectionStale(
          'The patient workflow changed. Symptoms are read-only until the authoritative record reloads.',
        );
        if (typeof ensureSymptomEpisodes === 'function') {
          Promise.resolve().then(() => ensureSymptomEpisodes());
        }
      }
      const treatmentNeedsWorkflowRefresh = (
        options.treatmentProjection !== true
        && options.treatmentMutation !== true
        && !profileAdvanced
        && (
          (
            typeof treatmentProjection !== 'undefined'
            && treatmentProjection !== null
          )
          || (
            typeof treatmentRequestController !== 'undefined'
            && treatmentRequestController !== null
          )
        )
      );
      if (
        treatmentNeedsWorkflowRefresh
        && typeof markTreatmentProjectionStale === 'function'
      ) {
        markTreatmentProjectionStale(
          'The patient workflow changed. Treatment information is read-only until the authoritative record reloads.',
        );
        if (typeof ensureTreatmentReconciliation === 'function') {
          Promise.resolve().then(() => ensureTreatmentReconciliation());
        }
      }
      const researchNeedsWorkflowRefresh = (
        options.researchProjection !== true
        && options.researchMutation !== true
        && !profileAdvanced
        && (
          (
            typeof researchProjection !== 'undefined'
            && researchProjection !== null
          )
          || (
            typeof researchRequestController !== 'undefined'
            && researchRequestController !== null
          )
        )
      );
      if (
        researchNeedsWorkflowRefresh
        && typeof markResearchProjectionStale === 'function'
      ) {
        markResearchProjectionStale(
          'The caregiver workflow changed. Research is read-only until the authoritative workspace reloads.',
        );
        if (typeof loadResearchWorkspace === 'function') {
          Promise.resolve().then(() => loadResearchWorkspace({ force: true }));
        }
      }
      if (
        !options.alertResolution
        && !profileAdvanced
        && Number.isSafeInteger(currentProfileRevision)
      ) {
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

  function beginWorkflowMutation() {
    if (followUpControlsLocked()) return null;
    const owner = {};
    workflowMutationOwner = owner;
    workflowMutationPending = true;
    return owner;
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
      mutationOwner: null,
    };
  }

  function workflowIntentCanRender(
    intent,
    expectedPhiEpoch = intent.pendingPhiEpoch ?? intent.requestPhiEpoch,
  ) {
    if (expectedPhiEpoch !== phiEpoch) return false;
    if (intent.requestVisitEpoch !== visitSelectionEpoch) return false;
    return !intent.visitId || intent.visitId === selectedVisitId;
  }

  function workflowIntentOwnsMutation(intent) {
    return workflowMutationPending
      && workflowMutationOwner === intent.mutationOwner
      && workflowIntentCanRender(intent);
  }

  function releaseWorkflowMutation(intent) {
    if (
      !workflowMutationPending
      || workflowMutationOwner !== intent.mutationOwner
    ) return false;
    workflowMutationPending = false;
    workflowMutationOwner = null;
    if (activeWorkflowIntent === intent) activeWorkflowIntent = null;
    setFollowUpMutationBusy(false);
    setAppointmentMutationBusy(false);
    refreshGeneratedActionControls();
    updateFollowUpFormValidity();
    updateAppointmentFormValidity();
    return true;
  }

  async function refreshClinicalWorkflowState(
    profileRevision,
    expectedWorkflowRevision = null,
    options = {},
  ) {
    const responseGuard = options.responseGuard || (() => true);
    if (!responseGuard()) return false;
    redactGeneratedQuestionChoices();
    redactGeneratedSummaryActions();
    const refreshPhiEpoch = phiEpoch;
    taskSelectionEpoch += 1;
    const guardedOptions = {
      responseGuard,
      authorizationOptions: options.authorizationOptions || {},
    };
    const status = await loadStatus(guardedOptions);
    if (
      !responseGuard()
      || refreshPhiEpoch !== phiEpoch
      || status?.profile_revision == null
    ) return false;
    const statusRevision = status.profile_revision;
    syncChatRevision(statusRevision, true, false);
    const refreshResults = await Promise.allSettled([
      loadSummary(guardedOptions),
      loadQuestions(guardedOptions),
      loadTasks(guardedOptions),
      loadVisits(guardedOptions),
      loadFollowUps(guardedOptions),
    ]);
    if (!responseGuard() || refreshPhiEpoch !== phiEpoch) return false;
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
    if (!workflowIntentOwnsMutation(intent)) return false;
    const authority = authorizePatientResponse(intent, data, { workflow: 'targeted' });
    if (!authority.accepted) return false;
    intent.pendingPhiEpoch = phiEpoch;
    if (!workflowIntentOwnsMutation(intent)) return false;
    const responseVisitEpoch = visitSelectionEpoch;
    const responseVisitId = selectedVisitId;
    if (appointmentDialogOpen) captureAppointmentDraft();
    if (data.visit?.id) {
      if (data.visit.id === selectedVisitId) {
        scrubVisitRecapBeforeSelectionChange(data.visit.id, data.visit.token);
      }
      visitsById.set(data.visit.id, data.visit);
      revalidateDecisionSuccessorState(data.visit);
    }
    if (data.item?.question_snapshots && data.item.id) {
      if (data.item.id === selectedVisitId) {
        scrubVisitRecapBeforeSelectionChange(data.item.id, data.item.token);
      }
      visitsById.set(data.item.id, data.item);
    }
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
        && workflowIntentOwnsMutation(intent)
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
    if (!workflowIntentOwnsMutation(intent)) return false;
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
    if (!workflowIntentOwnsMutation(intent)) return null;
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
      if (!workflowIntentOwnsMutation(intent)) return null;
      const data = await readJsonResponse(
        response,
        () => workflowIntentOwnsMutation(intent),
      );
      if (!workflowIntentOwnsMutation(intent)) return null;
      const consumed = await consumeWorkflowResponse(data, intent);
      if (!consumed || !workflowIntentOwnsMutation(intent)) return null;
      clearWorkflowRetry();
      if (workflowIntentOwnsMutation(intent)) setAppointmentMessage('Saved.', 'success');
      return data;
    } catch (error) {
      if (!workflowIntentOwnsMutation(intent)) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('appointment-workflow', error);
        if (workflowIntentOwnsMutation(intent)) evictClientPhi(error);
        return null;
      }
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
      releaseWorkflowMutation(intent);
    }
  }

  async function submitWorkflowMutation(url, body, visitId = selectedVisitId, method = 'POST') {
    const mutationOwner = beginWorkflowMutation();
    if (!mutationOwner) return null;
    const intent = createWorkflowIntent(url, body, visitId);
    intent.method = method;
    intent.mutationOwner = mutationOwner;
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
    const mutationOwner = beginWorkflowMutation();
    if (!mutationOwner) return;
    intent.mutationOwner = mutationOwner;
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
    const chat = (document.getElementById('chat-input')?.value || '').trim();
    const questionButton = document.getElementById('q-add-btn');
    const judgmentButton = document.getElementById('judgment-add-btn');
    const chatButton = document.getElementById('chat-send-btn');
    if (questionButton) questionButton.disabled = !question;
    if (judgmentButton) judgmentButton.disabled = !judgment;
    if (chatButton && !chatButton.dataset.busy) chatButton.disabled = !chat;
    if (question) setFormError('q-form-error', '');
    if (judgment) setFormError('judgment-form-error', '');
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

  function appIsOffline() {
    return navigator.onLine === false || visitRecapNetworkAmbiguous;
  }

  function handleOfflineTransition() {
    if (typeof markBiomarkerProjectionStale === 'function') {
      biomarkerNetworkAmbiguous = true;
      markBiomarkerProjectionStale(
        biomarkerProjection
          ? 'Offline snapshot · read-only. Reconnect to reload the current biomarker record.'
          : 'Biomarker history is offline and no prior snapshot is available.',
      );
    }
    if (typeof markVisitRecapStale === 'function') {
      visitRecapNetworkAmbiguous = true;
      markVisitRecapStale(
        'Offline snapshot · read-only. Export is disabled until the recap reloads.',
        'offline',
      );
    }
    renderAppState();
  }

  async function retryInitialLoad(options = {}) {
    failedLoads.clear();
    renderAppState();
    const refreshes = [
      loadStatus(),
      loadTasks(),
      loadSummary(),
      loadQuestions(),
      loadJudgments(),
      loadPatientEvidence(),
      loadVisits(),
      loadFollowUps(),
    ];
    if (activeView === 'patient' || biomarkerProjection || biomarkerNetworkAmbiguous) {
      refreshes.push(loadBiomarkerSeries());
    }
    if (
      imagingProjectionState === 'stale'
      || imagingNetworkAmbiguous
      || (
        options.onlineRecovery !== true
        && activeView === 'patient'
        && !imagingProjection
      )
    ) {
      refreshes.push(ensureImagingSeries());
    }
    if (
      symptomNetworkAmbiguous
      || (
        options.onlineRecovery !== true
        && ['today', 'patient'].includes(activeView)
        && !symptomProjection
      )
    ) {
      refreshes.push(ensureSymptomEpisodes());
    }
    if (
      treatmentNetworkAmbiguous
      || (
        options.onlineRecovery !== true
        && ['today', 'patient'].includes(activeView)
        && !treatmentProjection
      )
    ) {
      refreshes.push(ensureTreatmentReconciliation());
    }
    if (
      researchNetworkAmbiguous
      || (
        options.onlineRecovery !== true
        && ['today', 'research'].includes(activeView)
        && !researchProjection
      )
    ) {
      refreshes.push(loadResearchWorkspace({ force: true }));
    }
    if (appointmentDialogOpen && activeAppointmentTab === 'recap') {
      refreshes.push(loadVisitRecap());
    }
    await Promise.allSettled(refreshes);
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
      loadStatus().finally(() => ensureTreatmentReconciliation());
      loadPatientEvidence();
      loadBiomarkerSeries();
      ensureImagingSeries();
      ensureSymptomEpisodes();
      ensureTreatmentReconciliation();
    } else if (name === 'activity') {
      loadTasks();
    } else if (name === 'research') {
      if (!researchProjection || researchProjectionState === 'stale') {
        loadResearchWorkspace({ force: true });
      }
    } else if (name === 'today') {
      loadStatus();
      loadSummary();
      loadFollowUps();
      ensureSymptomEpisodes();
      if (!researchProjection || researchProjectionState === 'stale') {
        loadResearchWorkspace({ force: true });
      }
    }
    if (window.location.hash !== `#${name}`) {
      history.replaceState(null, '', `#${name}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (!trigger) document.getElementById(`nav-${name}`)?.focus();
  }

  window.addEventListener('online', () => retryInitialLoad({ onlineRecovery: true }));
  window.addEventListener('offline', handleOfflineTransition);

  function refreshAfterVisibilityRestore() {
    if (document.hidden) return;
    const refreshes = [loadTasks(), loadStatus()];
    if (activeView === 'today') {
      refreshes.push(
        loadSummary(),
        loadFollowUps(),
        ensureSymptomEpisodes(),
        ensureTreatmentReconciliation(),
      );
    }
    if (activeView === 'questions' || appointmentDialogOpen) {
      refreshes.push(loadVisits(), loadFollowUps(), loadQuestions());
    }
    if (activeView === 'patient') {
      refreshes.push(
        loadBiomarkerSeries(),
        loadPatientEvidence(),
        ensureImagingSeries(),
        ensureSymptomEpisodes(),
        ensureTreatmentReconciliation(),
      );
    }
    if (appointmentDialogOpen && activeAppointmentTab === 'recap') {
      refreshes.push(loadVisitRecap());
    }
    if (researchNetworkAmbiguous) {
      refreshes.push(loadResearchWorkspace({ force: true }));
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

  function safeBiomarkerEvidenceUrl(value) {
    if (!value) return '';
    try {
      const base = document.baseURI || window.location.href || window.location.origin;
      const pageOrigin = new URL(base).origin;
      const url = new URL(String(value), base);
      const allowedPath = /^\/api\/(?:evidence|sources)\//.test(url.pathname);
      return url.origin === pageOrigin && allowedPath
        ? `${url.pathname}${url.search}`
        : '';
    } catch (_) {
      return '';
    }
  }

  function biomarkerScalar(value, fallback = 'Not recorded') {
    if (value == null) return fallback;
    return value === '' ? 'Empty string ("")' : String(value);
  }

  function biomarkerProjectionPayloadIsValid(data) {
    if (
      !data
      || typeof data !== 'object'
      || Array.isArray(data)
      || !Number.isSafeInteger(normalizedRevision(data.profile_revision))
      || !Number.isSafeInteger(normalizedRevision(data.workflow_revision))
      || typeof data.projection_token !== 'string'
      || !data.projection_token
      || !Number.isSafeInteger(data.observation_count)
      || data.observation_count < 0
      || !Number.isSafeInteger(data.source_row_count)
      || data.source_row_count < 0
      || !Array.isArray(data.analytes)
    ) return false;

    const analyteIds = new Set();
    let projectedObservationCount = 0;
    for (const analyte of data.analytes) {
      if (
        !analyte
        || typeof analyte !== 'object'
        || typeof analyte.id !== 'string'
        || !analyte.id
        || analyteIds.has(analyte.id)
        || typeof analyte.token !== 'string'
        || !analyte.token
        || typeof analyte.display_name !== 'string'
        || !Array.isArray(analyte.observed_aliases)
        || !analyte.observed_aliases.every(alias => typeof alias === 'string')
        || !Number.isSafeInteger(analyte.observation_count)
        || analyte.observation_count < 0
        || !Number.isSafeInteger(analyte.source_row_count)
        || analyte.source_row_count < 0
        || !Array.isArray(analyte.series)
        || !Array.isArray(analyte.observations)
        || analyte.observation_count !== analyte.observations.length
      ) return false;
      analyteIds.add(analyte.id);

      const seriesById = new Map();
      for (const series of analyte.series) {
        if (
          !series
          || typeof series !== 'object'
          || typeof series.id !== 'string'
          || !series.id
          || seriesById.has(series.id)
          || typeof series.token !== 'string'
          || !series.token
          || typeof series.label !== 'string'
          || typeof series.comparable !== 'boolean'
          || !Array.isArray(series.observation_ids)
          || !series.observation_ids.every(id => typeof id === 'string' && id)
          || new Set(series.observation_ids).size !== series.observation_ids.length
          || !Array.isArray(series.comparability_notes)
          || !series.comparability_notes.every(note => typeof note === 'string')
          || (series.comparable && series.observation_ids.length < 2)
        ) return false;
        seriesById.set(series.id, series);
      }

      const observationsById = new Map();
      for (const observation of analyte.observations) {
        if (
          !observation
          || typeof observation !== 'object'
          || typeof observation.id !== 'string'
          || !observation.id
          || observationsById.has(observation.id)
          || typeof observation.token !== 'string'
          || !observation.token
          || typeof observation.series_id !== 'string'
          || !seriesById.has(observation.series_id)
          || typeof observation.comparable !== 'boolean'
          || !Number.isSafeInteger(observation.duplicate_count)
          || observation.duplicate_count < 1
          || !Array.isArray(observation.source_row_ids)
          || !observation.source_row_ids.every(id => typeof id === 'string' && id)
          || observation.source_row_ids.length !== observation.duplicate_count
          || !Array.isArray(observation.comparability_notes)
          || !observation.comparability_notes.every(note => typeof note === 'string')
          || !observation.date
          || typeof observation.date !== 'object'
          || !observation.value
          || typeof observation.value !== 'object'
          || !observation.provenance
          || typeof observation.provenance !== 'object'
          || typeof observation.provenance.status !== 'string'
          || typeof observation.provenance.label !== 'string'
          || !Array.isArray(observation.provenance.source_document_ids)
          || !observation.provenance.source_document_ids.every(id => typeof id === 'string')
          || !Array.isArray(observation.provenance.evidence)
          || !observation.provenance.evidence.every(item => (
            item
            && typeof item === 'object'
            && typeof item.id === 'string'
            && typeof item.status === 'string'
          ))
        ) return false;
        if (!seriesById.get(observation.series_id).observation_ids.includes(observation.id)) {
          return false;
        }
        observationsById.set(observation.id, observation);
      }
      for (const series of analyte.series) {
        for (const observationId of series.observation_ids) {
          const observation = observationsById.get(observationId);
          if (
            !observation
            || observation.series_id !== series.id
            || observation.comparable !== series.comparable
            || (
              series.comparable
              && (
                typeof observation.value.numeric_value !== 'number'
                || !Number.isFinite(observation.value.numeric_value)
              )
            )
          ) return false;
        }
      }
      projectedObservationCount += analyte.observations.length;
    }
    return projectedObservationCount === data.observation_count;
  }

  function selectedBiomarkerAnalyte() {
    if (!biomarkerProjection || !selectedBiomarkerAnalyteId) return null;
    return biomarkerProjection.analytes.find(
      analyte => analyte.id === selectedBiomarkerAnalyteId
    ) || null;
  }

  function newBiomarkerResponseOwner(projection, analyte, ownerPhiEpoch = phiEpoch) {
    return {
      requestPhiEpoch: ownerPhiEpoch,
      loadEpoch: biomarkerLoadEpoch,
      selectionEpoch: biomarkerSelectionEpoch,
      profileRevision: projection.profile_revision,
      workflowRevision: projection.workflow_revision,
      projectionToken: projection.projection_token,
      analyteId: analyte?.id || null,
      analyteToken: analyte?.token || null,
      seriesTokens: new Map((analyte?.series || []).map(series => [series.id, series.token])),
    };
  }

  function biomarkerResponseOwnerIsCurrent(owner) {
    if (
      !owner
      || owner !== biomarkerResponseOwner
      || owner.requestPhiEpoch !== phiEpoch
      || owner.loadEpoch !== biomarkerLoadEpoch
      || owner.selectionEpoch !== biomarkerSelectionEpoch
      || !biomarkerProjection
      || owner.projectionToken !== biomarkerProjection.projection_token
      || String(owner.profileRevision) !== String(biomarkerProjection.profile_revision)
      || String(owner.workflowRevision) !== String(biomarkerProjection.workflow_revision)
      || (
        biomarkerProjectionState !== 'stale'
        && Number.isSafeInteger(normalizedRevision(workflowRevision))
        && String(owner.workflowRevision) !== String(workflowRevision)
      )
      || owner.analyteId !== selectedBiomarkerAnalyteId
    ) return false;
    const analyte = selectedBiomarkerAnalyte();
    return Boolean(
      analyte
      && owner.analyteToken === analyte.token
      && analyte.series.every(series => owner.seriesTokens.get(series.id) === series.token)
    );
  }

  function abortBiomarkerRequest() {
    const controller = biomarkerRequestController;
    biomarkerRequestController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function biomarkerFocusFallback() {
    const explorer = document.getElementById('biomarker-explorer');
    if (!explorer?.contains(document.activeElement)) return;
    document.activeElement?.blur();
    const fallback = activeView === 'patient'
      ? document.getElementById('nav-patient')
      : document.getElementById('main-content');
    fallback?.focus();
  }

  function setBiomarkerFreshness(state, text) {
    const freshness = document.getElementById('biomarker-freshness');
    if (!freshness) return;
    freshness.className = `biomarker-freshness ${safeClassToken(state, 'error')}`;
    freshness.textContent = text;
  }

  function setBiomarkerStatus(message, state = '', retry = false) {
    const status = document.getElementById('biomarker-status');
    if (status) {
      status.className = `biomarker-status ${safeClassToken(state)}`;
      status.textContent = message || '';
    }
    const retrySurface = document.getElementById('biomarker-retry');
    if (retrySurface) retrySurface.hidden = !retry;
  }

  function renderBiomarkerUnavailable(message, state, statusLabel, retry = true) {
    const select = document.getElementById('biomarker-analyte-select');
    if (select) {
      select.innerHTML = '<option value="">No biomarker history available</option>';
      select.value = '';
      select.disabled = true;
    }
    const context = document.getElementById('biomarker-context');
    if (context) context.textContent = 'No biomarker values are retained in this view.';
    const caption = document.getElementById('biomarker-table-caption');
    if (caption) caption.textContent = 'Complete observations for the selected biomarker';
    const table = document.getElementById('biomarker-table-body');
    if (table) {
      table.innerHTML = `<tr><td colspan="7"><div class="empty-state">${escHtml(message)}</div></td></tr>`;
    }
    const charts = document.getElementById('biomarker-chart-region');
    if (charts) charts.innerHTML = '<div class="empty-state">No comparable chart is available.</div>';
    setBiomarkerFreshness(state, statusLabel);
    setBiomarkerStatus(message, state, retry);
  }

  function clearBiomarkerProjection(options = {}) {
    biomarkerLoadEpoch += 1;
    biomarkerSelectionEpoch += 1;
    abortBiomarkerRequest();
    biomarkerProjection = null;
    biomarkerResponseOwner = null;
    selectedBiomarkerAnalyteId = null;
    biomarkerNetworkAmbiguous = false;
    biomarkerProjectionState = options.state || 'error';
    biomarkerFocusFallback();
    renderBiomarkerUnavailable(
      options.message || 'Biomarker history could not be loaded.',
      biomarkerProjectionState,
      options.statusLabel || 'Unavailable',
      options.retry !== false,
    );
  }

  function biomarkerListMarkup(values, emptyText) {
    if (!Array.isArray(values) || !values.length) {
      return `<span class="biomarker-missing">${escHtml(emptyText)}</span>`;
    }
    return `<ul>${values.map(value => `<li>${escHtml(value)}</li>`).join('')}</ul>`;
  }

  function biomarkerEvidenceMarkup(observation) {
    const evidence = observation.provenance.evidence || [];
    const evidenceItems = evidence.map(item => {
      const evidenceUrl = safeBiomarkerEvidenceUrl(item.evidence_url);
      const sourceUrl = safeBiomarkerEvidenceUrl(item.source_url);
      return `<li>
        <span><strong>${escHtml(item.status)}</strong> · evidence ID ${escHtml(item.id)}</span>
        <span class="biomarker-evidence-actions">
          ${evidenceUrl ? `<a href="${escHtml(evidenceUrl)}" target="_blank" rel="noopener">Open exact span</a>` : ''}
          ${sourceUrl ? `<a href="${escHtml(sourceUrl)}" target="_blank" rel="noopener">Open source</a>` : ''}
        </span>
      </li>`;
    }).join('');
    return `<details class="biomarker-source-details">
      <summary>Source details</summary>
      <div>
        <p><strong>${escHtml(observation.provenance.label)}</strong> · ${escHtml(observation.provenance.status)}</p>
        <p>Observation ID: <code>${escHtml(observation.id)}</code></p>
        <p>Source row IDs:</p>
        ${biomarkerListMarkup(observation.source_row_ids, 'No source row ID supplied')}
        <p>Source document IDs:</p>
        ${biomarkerListMarkup(
          observation.provenance.source_document_ids,
          'No source document linked',
        )}
        <p>Evidence records:</p>
        ${evidenceItems ? `<ul class="biomarker-evidence-list">${evidenceItems}</ul>` : '<span class="biomarker-missing">No evidence record supplied</span>'}
      </div>
    </details>`;
  }

  function biomarkerObservationRow(analyte, observation) {
    const date = observation.date || {};
    const sourceDate = date.source_document_date == null
      ? ''
      : `<span>Source document date: ${escHtml(biomarkerScalar(date.source_document_date))} · precision ${escHtml(biomarkerScalar(date.source_document_date_precision))}</span>`;
    const unit = observation.unit == null || observation.unit === ''
      ? ''
      : ` ${escHtml(observation.unit)}`;
    const rangeComparison = observation.report_range_comparison == null
      ? '<span class="biomarker-missing">No report-range comparison supplied</span>'
      : `<span>${escHtml(biomarkerScalar(observation.report_range_label))}: <strong>${escHtml(observation.report_range_comparison)}</strong></span>`;
    const series = analyte.series.find(item => item.id === observation.series_id);
    const chartLabel = observation.comparable
      ? escHtml(series?.label || 'Server-declared comparable')
      : 'Not charted';
    const notes = biomarkerListMarkup(
      observation.comparability_notes,
      observation.comparable
        ? 'No comparability limitation supplied'
        : 'No comparability reason supplied',
    );
    const duplicateLabel = observation.duplicate_count === 1
      ? '1 recorded source row'
      : `${observation.duplicate_count} recorded source rows`;
    return `<tr data-observation-id="${escHtml(observation.id)}">
      <td>
        <strong>${escHtml(biomarkerScalar(date.value))}</strong>
        <span>Precision: ${escHtml(biomarkerScalar(date.precision))}</span>
        <span>Date kind: ${escHtml(biomarkerScalar(date.kind))}</span>
        ${sourceDate}
      </td>
      <td>
        <strong>${escHtml(biomarkerScalar(observation.value.raw))}${unit}</strong>
        <span>Value kind: ${escHtml(biomarkerScalar(observation.value.kind))}</span>
      </td>
      <td>
        <strong>${escHtml(biomarkerScalar(observation.reference_range))}</strong>
        ${rangeComparison}
      </td>
      <td>
        <strong>${escHtml(biomarkerScalar(observation.reported_flag))}</strong>
        <span>Authority: ${escHtml(biomarkerScalar(observation.reported_flag_authority))}</span>
      </td>
      <td>
        <span><strong>Specimen:</strong> ${escHtml(biomarkerScalar(observation.specimen))}</span>
        <span><strong>Assay:</strong> ${escHtml(biomarkerScalar(observation.assay))}</span>
        <span><strong>Method:</strong> ${escHtml(biomarkerScalar(observation.method))}</span>
      </td>
      <td>
        <strong>${chartLabel}</strong>
        ${notes}
      </td>
      <td>
        <span class="biomarker-duplicate-count">${escHtml(duplicateLabel)}</span>
        ${biomarkerEvidenceMarkup(observation)}
      </td>
    </tr>`;
  }

  function biomarkerSeriesChart(analyte, series, chartIndex) {
    const observationsById = new Map(
      analyte.observations.map(observation => [observation.id, observation])
    );
    const points = series.observation_ids.map(id => observationsById.get(id)).filter(
      observation => (
        observation
        && observation.series_id === series.id
        && observation.comparable === true
      )
    );
    if (points.length < 2) return '';

    const width = Math.max(640, points.length * 96);
    const height = 250;
    const left = 58;
    const right = 24;
    const top = 28;
    const bottom = 58;
    const values = points.map(point => Number(point.value.numeric_value));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = max - min;
    const xStep = (width - left - right) / (points.length - 1);
    const y = value => spread === 0
      ? top + ((height - top - bottom) / 2)
      : top + ((max - value) / spread) * (height - top - bottom);
    const chartId = `biomarker-chart-${chartIndex}`;
    const first = points[0];
    const context = [
      ['Unit', series.unit],
      ['Specimen', series.specimen],
      ['Assay', series.assay],
      ['Method', series.method],
      ['Date kind', series.date_kind],
      ['Recorded reference', first.reference_range],
    ];
    const pointMarkup = points.map((point, index) => {
      const x = left + (index * xStep);
      const pointY = y(Number(point.value.numeric_value));
      const displayResult = `${biomarkerScalar(point.value.raw)}${
        point.unit == null || point.unit === '' ? '' : ` ${point.unit}`
      }`;
      return `<g>
        <circle cx="${x}" cy="${pointY}" r="6">
          <title>${escHtml(`${biomarkerScalar(point.date.value)} · ${displayResult}`)}</title>
        </circle>
        <text class="biomarker-chart-value" x="${x}" y="${Math.max(16, pointY - 12)}" text-anchor="middle">${escHtml(displayResult)}</text>
        <text class="biomarker-chart-date" x="${x}" y="${height - 26}" text-anchor="middle">${escHtml(biomarkerScalar(point.date.value))}</text>
      </g>`;
    }).join('');
    return `<figure class="biomarker-chart-card" data-series-id="${escHtml(series.id)}">
      <figcaption>
        <strong>${escHtml(series.label)}</strong>
        <span>${context.map(([label, value]) => `${escHtml(label)}: ${escHtml(biomarkerScalar(value))}`).join(' · ')}</span>
      </figcaption>
      <div class="biomarker-chart-scroll" role="region" aria-label="${escHtml(`${analyte.display_name}, ${series.label} point chart`)}" tabindex="0">
        <svg
          viewBox="0 0 ${width} ${height}"
          width="${width}"
          height="${height}"
          role="img"
          aria-labelledby="${chartId}-title ${chartId}-description"
        >
          <title id="${chartId}-title">${escHtml(`${analyte.display_name}: ${series.label}`)}</title>
          <desc id="${chartId}-description">Isolated recorded points in one exact server-declared comparable group. No connecting line or trend is inferred. Complete values are in the table above.</desc>
          <line class="biomarker-chart-axis" x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}"></line>
          ${pointMarkup}
        </svg>
      </div>
    </figure>`;
  }

  function renderBiomarkerProjection(owner) {
    if (!biomarkerResponseOwnerIsCurrent(owner)) return false;
    const analyte = selectedBiomarkerAnalyte();
    if (!analyte || owner.analyteToken !== analyte.token) return false;

    const select = document.getElementById('biomarker-analyte-select');
    if (select) {
      select.innerHTML = biomarkerProjection.analytes.map(item => (
        `<option value="${escHtml(item.id)}">${escHtml(item.display_name)} (${item.observation_count})</option>`
      )).join('');
      select.value = analyte.id;
      select.disabled = false;
    }
    const context = document.getElementById('biomarker-context');
    if (context) {
      context.innerHTML = `<strong>${escHtml(analyte.display_name)}</strong>
        <span>${analyte.observation_count} observations from ${analyte.source_row_count} source rows · ${analyte.series_count} exact comparison groups</span>
        <span>Recorded aliases:</span>
        ${biomarkerListMarkup(analyte.observed_aliases, 'No recorded alias supplied')}`;
    }
    const caption = document.getElementById('biomarker-table-caption');
    if (caption) {
      caption.textContent = `Complete recorded observations for ${analyte.display_name}`;
    }
    const table = document.getElementById('biomarker-table-body');
    if (table) {
      table.innerHTML = analyte.observations.length
        ? analyte.observations.map(observation => (
            biomarkerObservationRow(analyte, observation)
          )).join('')
        : '<tr><td colspan="7"><div class="empty-state">No observations are recorded for this biomarker.</div></td></tr>';
    }

    const comparableSeries = analyte.series.filter(series => series.comparable === true);
    const charts = document.getElementById('biomarker-chart-region');
    if (charts) {
      const chartMarkup = comparableSeries.map((series, index) => {
        if (owner.seriesTokens.get(series.id) !== series.token) return '';
        return biomarkerSeriesChart(analyte, series, index);
      }).filter(Boolean).join('');
      charts.innerHTML = chartMarkup || `<div class="empty-state">
        No chart is shown because this biomarker has fewer than two observations in any exact server-declared comparable group. Every recorded observation remains in the table.
      </div>`;
    }

    if (biomarkerProjectionState === 'stale') {
      setBiomarkerFreshness('stale', 'Stale snapshot');
    } else {
      setBiomarkerFreshness('current', 'Current');
      setBiomarkerStatus(
        `Authoritative record loaded · patient revision ${biomarkerProjection.profile_revision} · workflow revision ${biomarkerProjection.workflow_revision}.`,
        'current',
        false,
      );
    }
    return true;
  }

  function selectBiomarkerAnalyte(analyteId) {
    if (!biomarkerProjection) return false;
    const analyte = biomarkerProjection.analytes.find(item => item.id === analyteId);
    if (!analyte) return false;
    biomarkerSelectionEpoch += 1;
    selectedBiomarkerAnalyteId = analyte.id;
    biomarkerResponseOwner = newBiomarkerResponseOwner(biomarkerProjection, analyte);
    return renderBiomarkerProjection(biomarkerResponseOwner);
  }

  function markBiomarkerProjectionStale(message, options = {}) {
    if (options.abortRequest !== false) {
      biomarkerLoadEpoch += 1;
      abortBiomarkerRequest();
    }
    biomarkerProjectionState = 'stale';
    if (!biomarkerProjection) {
      renderBiomarkerUnavailable(
        message || 'Biomarker history is offline and no prior snapshot is available.',
        'stale',
        'Offline',
        true,
      );
      return;
    }
    const analyte = selectedBiomarkerAnalyte()
      || biomarkerProjection.analytes[0]
      || null;
    if (!analyte) {
      renderBiomarkerUnavailable(
        message || 'The prior biomarker snapshot is empty.',
        'stale',
        'Stale snapshot',
        true,
      );
      return;
    }
    if (selectedBiomarkerAnalyteId !== analyte.id) biomarkerSelectionEpoch += 1;
    selectedBiomarkerAnalyteId = analyte.id;
    biomarkerResponseOwner = newBiomarkerResponseOwner(
      biomarkerProjection,
      analyte,
      options.ownerPhiEpoch ?? phiEpoch,
    );
    if (!renderBiomarkerProjection(biomarkerResponseOwner)) return;
    setBiomarkerFreshness('stale', 'Stale snapshot');
    setBiomarkerStatus(
      message || 'Offline snapshot · read-only. Reload before relying on it.',
      'stale',
      true,
    );
  }

  function renderBiomarkerLoading() {
    biomarkerProjectionState = 'loading';
    if (biomarkerProjection) {
      setBiomarkerFreshness('loading', 'Checking…');
      setBiomarkerStatus(
        'Checking the current authoritative biomarker record…',
        'loading',
        false,
      );
      return;
    }
    const select = document.getElementById('biomarker-analyte-select');
    if (select) {
      select.innerHTML = '<option value="">Loading recorded biomarkers…</option>';
      select.disabled = true;
    }
    setBiomarkerFreshness('loading', 'Loading…');
    setBiomarkerStatus('Loading the authoritative biomarker record…', 'loading', false);
  }

  function biomarkerTransportRequestIsCurrent(request, acceptedPhiEpoch = null) {
    const phiOwner = acceptedPhiEpoch ?? request.requestPhiEpoch;
    return Boolean(
      request
      && request.controller === biomarkerRequestController
      && !request.controller.signal.aborted
      && request.loadEpoch === biomarkerLoadEpoch
      && phiOwner === phiEpoch
    );
  }

  async function loadBiomarkerSeries() {
    const previousController = biomarkerRequestController;
    const controller = new AbortController();
    const request = {
      ...capturePatientRequest(),
      loadEpoch: ++biomarkerLoadEpoch,
      controller,
    };
    biomarkerRequestController = controller;
    if (previousController && !previousController.signal.aborted) previousController.abort();
    renderBiomarkerLoading();

    try {
      const response = await fetch('/api/patient/biomarker-series', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      const requestIsCurrent = () => biomarkerTransportRequestIsCurrent(request);
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      if (!biomarkerProjectionPayloadIsValid(data)) {
        const invalid = new Error('Biomarker history could not be verified safely.');
        invalid.status = 422;
        invalid.data = { code: 'biomarker_projection_invalid_response' };
        throw invalid;
      }
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        biomarkerProjection: true,
      });
      if (!authority.accepted) {
        if (biomarkerTransportRequestIsCurrent(request)) {
          markBiomarkerProjectionStale(
            'A newer patient or workflow revision is available. Reload biomarker history.',
          );
        }
        return null;
      }
      request.acceptedPhiEpoch = authority.requestPhiEpoch;
      if (!biomarkerTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;

      const retainedSelection = selectedBiomarkerAnalyteId;
      const analyte = data.analytes.find(item => item.id === retainedSelection)
        || data.analytes[0]
        || null;
      biomarkerSelectionEpoch += 1;
      biomarkerProjection = data;
      selectedBiomarkerAnalyteId = analyte?.id || null;
      biomarkerNetworkAmbiguous = false;
      biomarkerProjectionState = data.analytes.length ? 'current' : 'empty';
      biomarkerResponseOwner = analyte
        ? newBiomarkerResponseOwner(data, analyte, request.acceptedPhiEpoch)
        : null;
      if (!biomarkerTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;

      if (!analyte) {
        const select = document.getElementById('biomarker-analyte-select');
        if (select) {
          select.innerHTML = '<option value="">No biomarkers recorded</option>';
          select.value = '';
          select.disabled = true;
        }
        const context = document.getElementById('biomarker-context');
        if (context) context.textContent = 'No biomarker observations are recorded.';
        const caption = document.getElementById('biomarker-table-caption');
        if (caption) caption.textContent = 'Complete observations for the selected biomarker';
        const table = document.getElementById('biomarker-table-body');
        if (table) {
          table.innerHTML = '<tr><td colspan="7"><div class="empty-state">No biomarker observations are recorded.</div></td></tr>';
        }
        const charts = document.getElementById('biomarker-chart-region');
        if (charts) charts.innerHTML = '<div class="empty-state">No comparable chart is available.</div>';
        setBiomarkerFreshness('current', 'Current · empty');
        setBiomarkerStatus(
          `Authoritative record loaded · patient revision ${data.profile_revision} · no biomarker observations recorded.`,
          'current',
          false,
        );
      } else if (!renderBiomarkerProjection(biomarkerResponseOwner)) {
        return null;
      }
      reportLoadSuccess('biomarkers');
      return data;
    } catch (error) {
      const acceptedPhiEpoch = request.acceptedPhiEpoch ?? null;
      if (
        error?.name === 'AbortError'
        || !biomarkerTransportRequestIsCurrent(request, acceptedPhiEpoch)
      ) return null;
      if (shouldEvictClientPhi(error)) {
        const safeError = new Error(
          error?.status === 401 || error?.status === 403
            ? 'Biomarker authorization is unavailable.'
            : 'Biomarker data could not be loaded safely.',
        );
        safeError.status = error?.status;
        reportLoadError('biomarkers', safeError);
        if (biomarkerTransportRequestIsCurrent(request, acceptedPhiEpoch)) {
          evictClientPhi(safeError);
        }
        return null;
      }
      const ambiguous = error instanceof TypeError || navigator.onLine === false;
      if (ambiguous) {
        biomarkerNetworkAmbiguous = true;
        markBiomarkerProjectionStale(
          biomarkerProjection
            ? 'Offline snapshot · read-only. Reconnect to reload the current biomarker record.'
            : 'Biomarker history is offline and no prior snapshot is available.',
          { abortRequest: false },
        );
        reportLoadError('biomarkers', error);
        return null;
      }
      if (error?.status === 422) {
        clearBiomarkerProjection({
          state: 'corrupt',
          statusLabel: 'Record unavailable',
          message: 'Biomarker history is unavailable because the stored record could not be projected safely.',
        });
        const safeError = new Error(
          'Biomarker history is unavailable because the stored record could not be projected safely.',
        );
        safeError.status = 422;
        reportLoadError('biomarkers', safeError);
      } else {
        clearBiomarkerProjection({
          state: 'error',
          statusLabel: 'Load failed',
          message: 'Biomarker history could not be loaded. No prior biomarker values remain in this view.',
        });
        const safeError = new Error('Biomarker history could not be loaded.');
        safeError.status = error?.status;
        reportLoadError('biomarkers', safeError);
      }
      return null;
    } finally {
      if (
        biomarkerRequestController === controller
        && request.loadEpoch === biomarkerLoadEpoch
      ) {
        biomarkerRequestController = null;
      }
    }
  }

  // ── Imaging longitudinal record ─────────────────────────────────────────
  const IMAGING_MAX_RECORDS = 2000;
  const IMAGING_MAX_AUTHORITY_CHARS = 4000000;
  const IMAGING_DATE_PRECISIONS = new Set(['day', 'month', 'year', 'unknown']);
  const IMAGING_DATE_KINDS = new Set(['study', 'legacy_unknown', 'unknown']);
  const IMAGING_PROVENANCE_STATUSES = new Set([
    'caregiver_corrected_unverified',
    'source_verified',
    'source_unverified',
    'source_unavailable',
    'unverified',
  ]);

  function imagingPlainObject(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  }

  function imagingHasExactKeys(value, keys) {
    if (!imagingPlainObject(value)) return false;
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    return actual.length === expected.length
      && actual.every((key, index) => key === expected[index]);
  }

  function imagingBoundedString(value, maximum, nullable = false) {
    if (nullable && value == null) return true;
    return typeof value === 'string' && value.length <= maximum;
  }

  function imagingRecordUrlParts(value, expectedAction) {
    if (typeof value !== 'string' || !value || value.length > 200) return null;
    try {
      const base = document.baseURI || window.location.href || window.location.origin;
      const pageUrl = new URL(base);
      const url = new URL(value, base);
      const match = url.pathname.match(
        /^\/api\/patient\/imaging-series\/(imref_[0-9a-f]{64})\/(source|evidence)$/,
      );
      if (
        !/^(https?):$/.test(url.protocol)
        || url.origin !== pageUrl.origin
        || url.username
        || url.password
        || url.search
        || url.hash
        || !match
        || match[2] !== expectedAction
      ) return null;
      return { href: url.pathname, recordRef: match[1], action: match[2] };
    } catch (_) {
      return null;
    }
  }

  function safeImagingRecordUrl(value, expectedAction) {
    return imagingRecordUrlParts(value, expectedAction)?.href || '';
  }

  function imagingProjectionPayloadIsValid(data) {
    if (
      !imagingHasExactKeys(data, [
        'profile_revision',
        'workflow_revision',
        'source_row_count',
        'projection_token',
        'records',
      ])
      || !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || !imagingBoundedString(data.projection_token, 200)
      || !data.projection_token
      || !Number.isSafeInteger(data.source_row_count)
      || data.source_row_count < 0
      || data.source_row_count > IMAGING_MAX_RECORDS
      || !Array.isArray(data.records)
      || data.records.length !== data.source_row_count
      || data.records.length > IMAGING_MAX_RECORDS
    ) return false;

    const recordIds = new Set();
    const recordTokens = new Set();
    const recordRefs = new Set();
    let authorityCharacters = data.projection_token.length;
    for (const record of data.records) {
      if (
        !imagingHasExactKeys(record, [
          'id',
          'token',
          'date',
          'modality',
          'findings',
          'impression',
          'provenance',
        ])
        || !imagingBoundedString(record.id, 200)
        || !record.id
        || recordIds.has(record.id)
        || !imagingBoundedString(record.token, 200)
        || !record.token
        || recordTokens.has(record.token)
        || !imagingBoundedString(record.modality, 200, true)
        || !imagingBoundedString(record.findings, 50000, true)
        || !imagingBoundedString(record.impression, 50000, true)
        || !imagingHasExactKeys(record.date, [
          'value',
          'precision',
          'kind',
          'source_document_date',
          'source_document_date_precision',
        ])
        || !imagingBoundedString(record.date.value, 32, true)
        || !IMAGING_DATE_PRECISIONS.has(record.date.precision)
        || !IMAGING_DATE_KINDS.has(record.date.kind)
        || !imagingBoundedString(record.date.source_document_date, 32, true)
        || !IMAGING_DATE_PRECISIONS.has(record.date.source_document_date_precision)
        || !imagingHasExactKeys(record.provenance, [
          'status',
          'label',
          'source_url',
          'evidence_url',
        ])
        || !IMAGING_PROVENANCE_STATUSES.has(record.provenance.status)
        || !imagingBoundedString(record.provenance.label, 200)
        || !record.provenance.label
        || !imagingBoundedString(record.provenance.source_url, 200, true)
        || !imagingBoundedString(record.provenance.evidence_url, 200, true)
      ) return false;

      const source = record.provenance.source_url == null
        ? null
        : imagingRecordUrlParts(record.provenance.source_url, 'source');
      const evidence = record.provenance.evidence_url == null
        ? null
        : imagingRecordUrlParts(record.provenance.evidence_url, 'evidence');
      if (
        (record.provenance.source_url != null && !source)
        || (record.provenance.evidence_url != null && !evidence)
        || (evidence && (!source || evidence.recordRef !== source.recordRef))
        || (source && recordRefs.has(source.recordRef))
      ) return false;

      recordIds.add(record.id);
      recordTokens.add(record.token);
      if (source) recordRefs.add(source.recordRef);
      authorityCharacters += record.id.length
        + record.token.length
        + (record.date.value?.length || 0)
        + (record.date.source_document_date?.length || 0)
        + (record.modality?.length || 0)
        + (record.findings?.length || 0)
        + (record.impression?.length || 0)
        + record.provenance.status.length
        + record.provenance.label.length
        + (record.provenance.source_url?.length || 0)
        + (record.provenance.evidence_url?.length || 0);
      if (authorityCharacters > IMAGING_MAX_AUTHORITY_CHARS) return false;
    }
    return true;
  }

  function newImagingResponseOwner(projection, ownerPhiEpoch = phiEpoch) {
    return {
      requestPhiEpoch: ownerPhiEpoch,
      loadEpoch: imagingLoadEpoch,
      profileRevision: projection.profile_revision,
      workflowRevision: projection.workflow_revision,
      projectionToken: projection.projection_token,
      rowTokens: new Map(projection.records.map(record => [record.id, record.token])),
    };
  }

  function imagingResponseOwnerIsCurrent(owner = imagingResponseOwner) {
    if (
      !owner
      || owner !== imagingResponseOwner
      || owner.requestPhiEpoch !== phiEpoch
      || owner.loadEpoch !== imagingLoadEpoch
      || !imagingProjection
      || owner.projectionToken !== imagingProjection.projection_token
      || owner.profileRevision !== imagingProjection.profile_revision
      || owner.workflowRevision !== imagingProjection.workflow_revision
      || owner.rowTokens.size !== imagingProjection.records.length
      || imagingProjection.records.some(record => owner.rowTokens.get(record.id) !== record.token)
    ) return false;
    if (imagingProjectionState === 'stale') return true;
    const currentProfile = normalizedRevision(latestProfileRevision);
    const currentWorkflow = normalizedRevision(workflowRevision);
    return (
      (!Number.isSafeInteger(currentProfile) || owner.profileRevision === currentProfile)
      && (!Number.isSafeInteger(currentWorkflow) || owner.workflowRevision === currentWorkflow)
    );
  }

  function abortImagingRequest() {
    const controller = imagingRequestController;
    imagingRequestController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function imagingFocusFallback() {
    const explorer = document.getElementById('imaging-explorer');
    if (!explorer?.contains(document.activeElement)) return;
    document.activeElement?.blur();
    const fallback = activeView === 'patient'
      ? document.getElementById('nav-patient')
      : document.getElementById('main-content');
    fallback?.focus();
  }

  function imagingComparisonFocusFallback() {
    const comparison = document.getElementById('imaging-comparison');
    if (!comparison?.contains(document.activeElement)) return;
    document.activeElement?.blur();
    const tableRegion = document.getElementById('imaging-table-region');
    if (tableRegion) tableRegion.focus();
    else document.getElementById('nav-patient')?.focus();
  }

  function imagingElement(tag, className = '', text = null) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
  }

  function imagingScalar(value) {
    if (value == null) return 'Not recorded';
    return value === '' ? 'Empty string recorded' : String(value);
  }

  function setImagingFreshness(state, text) {
    const freshness = document.getElementById('imaging-freshness');
    if (!freshness) return;
    freshness.className = `imaging-freshness ${safeClassToken(state, 'error')}`;
    freshness.textContent = text;
  }

  function setImagingStatus(message, state = '', retry = false) {
    const status = document.getElementById('imaging-status');
    if (status) {
      status.className = `imaging-status${state ? ` ${safeClassToken(state)}` : ''}`;
      status.textContent = message || '';
    }
    const retrySurface = document.getElementById('imaging-retry');
    if (retrySurface) retrySurface.hidden = !retry;
    const refresh = document.getElementById('imaging-refresh-button');
    if (refresh) refresh.disabled = imagingRequestController !== null;
  }

  function imagingDateAuthority(date) {
    const precisionLabels = {
      day: 'day precision',
      month: 'month precision',
      year: 'year precision',
      unknown: 'precision unknown',
    };
    let authority;
    if (date.kind === 'study') {
      authority = 'Study date';
    } else if (date.kind === 'legacy_unknown') {
      authority = 'Legacy date; study-date authority not confirmed';
    } else {
      authority = date.value == null ? 'Study date not recorded' : 'Date authority unknown';
    }
    return {
      value: imagingScalar(date.value),
      context: `${authority} · ${precisionLabels[date.precision]}`,
    };
  }

  function imagingAppendFact(parent, label, value, className = '') {
    const wrapper = imagingElement('div', `imaging-fact${className ? ` ${className}` : ''}`);
    wrapper.append(
      imagingElement('dt', '', label),
      imagingElement('dd'),
    );
    const detail = wrapper.querySelector('dd');
    detail.textContent = imagingScalar(value);
    if (value == null || value === '') detail.classList.add('imaging-missing');
    parent.append(wrapper);
  }

  function imagingSourceDetails(record) {
    const details = imagingElement('details', 'imaging-source-details');
    details.append(imagingElement('summary', '', 'Technical and source details'));
    const content = imagingElement('div');
    const provenance = imagingElement('p');
    provenance.append(
      imagingElement('strong', '', record.provenance.label),
      document.createTextNode(` · ${record.provenance.status}`),
    );
    const identity = imagingElement('p');
    identity.append(
      document.createTextNode('Record ID: '),
      imagingElement('code', '', record.id),
    );
    const sourceDate = imagingElement(
      'p',
      '',
      `Source document date (not used for study chronology): ${
        imagingScalar(record.date.source_document_date)
      } · ${record.date.source_document_date_precision} precision`,
    );
    const actions = imagingElement('div', 'imaging-source-actions');
    const evidenceUrl = safeImagingRecordUrl(record.provenance.evidence_url, 'evidence');
    const sourceUrl = safeImagingRecordUrl(record.provenance.source_url, 'source');
    if (evidenceUrl) {
      const link = imagingElement('a', '', 'Open exact span');
      link.href = evidenceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      actions.append(link);
    }
    if (sourceUrl) {
      const link = imagingElement('a', '', 'Open source');
      link.href = sourceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      actions.append(link);
    }
    if (!actions.childElementCount) {
      actions.append(imagingElement('span', 'imaging-missing', 'No source link supplied'));
    }
    content.append(provenance, identity, sourceDate, actions);
    details.append(content);
    return details;
  }

  function clearImagingComparison(options = {}) {
    if (options.moveFocus !== false) imagingComparisonFocusFallback();
    imagingComparisonEpoch += 1;
    comparedImagingRecordIds = [];
    const comparison = document.getElementById('imaging-comparison');
    const grid = document.getElementById('imaging-comparison-grid');
    if (grid) grid.replaceChildren();
    if (comparison) comparison.hidden = true;
  }

  function imagingComparisonCard(record, index) {
    const card = imagingElement('article', 'imaging-comparison-card');
    const date = imagingDateAuthority(record.date);
    card.append(
      imagingElement('p', 'eyebrow', `Selected record ${index + 1}`),
      imagingElement('h4', '', record.modality == null || record.modality === ''
        ? 'Modality / type not recorded'
        : record.modality),
    );
    const facts = imagingElement('dl', 'imaging-comparison-facts');
    imagingAppendFact(facts, 'Recorded date', record.date.value);
    imagingAppendFact(facts, 'Date context', date.context);
    imagingAppendFact(facts, 'Modality / type', record.modality);
    imagingAppendFact(facts, 'Findings (report wording)', record.findings, 'report-wording');
    imagingAppendFact(
      facts,
      'Impression, including any report-authored comparison wording',
      record.impression,
      'report-wording',
    );
    imagingAppendFact(facts, 'Source authority', record.provenance.label);
    card.append(facts, imagingSourceDetails(record));
    return card;
  }

  function renderImagingComparison() {
    if (
      !imagingResponseOwnerIsCurrent()
      || comparedImagingRecordIds.length !== 2
      || selectedImagingRecordIds.length !== 2
      || comparedImagingRecordIds.some(id => !selectedImagingRecordIds.includes(id))
    ) {
      clearImagingComparison();
      return false;
    }
    const records = comparedImagingRecordIds.map(
      id => imagingProjection.records.find(record => record.id === id),
    );
    if (records.some(record => !record)) {
      clearImagingComparison();
      return false;
    }
    const grid = document.getElementById('imaging-comparison-grid');
    const comparison = document.getElementById('imaging-comparison');
    if (!grid || !comparison) return false;
    grid.replaceChildren(...records.map(imagingComparisonCard));
    comparison.hidden = false;
    comparison.classList.toggle('stale', imagingProjectionState === 'stale');
    return true;
  }

  function updateImagingSelectionControls() {
    const current = (
      ['current', 'empty'].includes(imagingProjectionState)
      && imagingResponseOwnerIsCurrent()
    );
    const selected = new Set(selectedImagingRecordIds);
    const checkboxes = document.querySelectorAll('input[name="imaging-record-select"]');
    checkboxes.forEach((checkbox, index) => {
      const record = imagingProjection?.records[index];
      checkbox.checked = Boolean(record && selected.has(record.id));
      checkbox.disabled = !current || (
        selected.size >= 2
        && record
        && !selected.has(record.id)
      );
    });
    const clearButton = document.getElementById('imaging-clear-selection');
    const compareButton = document.getElementById('imaging-compare-button');
    if (clearButton) clearButton.disabled = !current || selected.size === 0;
    if (compareButton) compareButton.disabled = !current || selected.size !== 2;
    const status = document.getElementById('imaging-selection-status');
    if (status) {
      if (!current && imagingProjection) {
        status.textContent = 'Stale snapshot · selection and comparison changes are read-only until imaging reloads.';
      } else if (imagingProjectionState === 'empty') {
        status.textContent = 'No imaging records are available to select or compare.';
      } else if (selected.size === 2) {
        status.textContent = 'Two records selected. Confirm this exact pair to show their raw report facts side by side.';
      } else {
        status.textContent = `${selected.size} of 2 records selected. Select exactly two current records.`;
      }
    }
  }

  function selectImagingRecord(recordId, checked) {
    if (
      imagingProjectionState !== 'current'
      || !imagingResponseOwnerIsCurrent()
      || !imagingProjection.records.some(record => record.id === recordId)
    ) {
      updateImagingSelectionControls();
      return false;
    }
    const selected = new Set(selectedImagingRecordIds);
    if (checked) {
      if (selected.size >= 2 && !selected.has(recordId)) {
        updateImagingSelectionControls();
        return false;
      }
      selected.add(recordId);
    } else {
      selected.delete(recordId);
    }
    imagingSelectionEpoch += 1;
    selectedImagingRecordIds = imagingProjection.records
      .filter(record => selected.has(record.id))
      .map(record => record.id);
    clearImagingComparison();
    updateImagingSelectionControls();
    return true;
  }

  function clearImagingSelection() {
    if (imagingProjectionState !== 'current' || !imagingResponseOwnerIsCurrent()) return false;
    imagingSelectionEpoch += 1;
    selectedImagingRecordIds = [];
    clearImagingComparison();
    updateImagingSelectionControls();
    return true;
  }

  function compareSelectedImagingRecords() {
    if (
      imagingProjectionState !== 'current'
      || !imagingResponseOwnerIsCurrent()
      || selectedImagingRecordIds.length !== 2
      || selectedImagingRecordIds.some(
        id => !imagingProjection.records.some(record => record.id === id),
      )
    ) return false;
    imagingComparisonEpoch += 1;
    comparedImagingRecordIds = [...selectedImagingRecordIds];
    if (!renderImagingComparison()) return false;
    document.getElementById('imaging-comparison-heading')?.focus();
    return true;
  }

  function imagingRecordRow(record, index) {
    const row = imagingElement('tr');
    const selectCell = imagingElement('td', 'imaging-select-cell');
    const selectLabel = imagingElement('label', 'imaging-select-label');
    const checkbox = imagingElement('input');
    checkbox.type = 'checkbox';
    checkbox.name = 'imaging-record-select';
    checkbox.id = `imaging-record-select-${index}`;
    checkbox.checked = selectedImagingRecordIds.includes(record.id);
    checkbox.addEventListener('change', () => selectImagingRecord(record.id, checkbox.checked));
    selectLabel.append(
      checkbox,
      imagingElement('span', '', `Select record ${index + 1}`),
    );
    selectCell.append(selectLabel);

    const date = imagingDateAuthority(record.date);
    const dateCell = imagingElement('td');
    dateCell.append(
      imagingElement('strong', '', date.value),
      imagingElement('span', '', date.context),
    );
    const modalityCell = imagingElement('td');
    modalityCell.append(imagingElement(
      'strong',
      record.modality == null || record.modality === '' ? 'imaging-missing' : '',
      imagingScalar(record.modality),
    ));
    const findingsCell = imagingElement('td', 'imaging-report-text');
    findingsCell.append(imagingElement(
      'p',
      record.findings == null || record.findings === '' ? 'imaging-missing' : '',
      imagingScalar(record.findings),
    ));
    const impressionCell = imagingElement('td', 'imaging-report-text');
    impressionCell.append(imagingElement(
      'p',
      record.impression == null || record.impression === '' ? 'imaging-missing' : '',
      imagingScalar(record.impression),
    ));
    const sourceCell = imagingElement('td');
    sourceCell.append(
      imagingElement('strong', '', record.provenance.label),
      imagingSourceDetails(record),
    );
    row.append(
      selectCell,
      dateCell,
      modalityCell,
      findingsCell,
      impressionCell,
      sourceCell,
    );
    return row;
  }

  function renderImagingProjection(owner = imagingResponseOwner) {
    if (!imagingResponseOwnerIsCurrent(owner)) return false;
    const summary = document.getElementById('imaging-summary');
    if (summary) {
      summary.textContent = `${imagingProjection.records.length} authoritative records from ${
        imagingProjection.source_row_count
      } source rows. Records remain independent and in server-supplied order; NET/Care does not infer chronology or change.`;
    }
    const caption = document.getElementById('imaging-table-caption');
    if (caption) {
      caption.textContent = 'Complete authoritative imaging records in server-supplied order';
    }
    const table = document.getElementById('imaging-table-body');
    if (table) {
      if (imagingProjection.records.length) {
        table.replaceChildren(...imagingProjection.records.map(imagingRecordRow));
      } else {
        const row = imagingElement('tr');
        const cell = imagingElement('td');
        cell.colSpan = 6;
        cell.append(imagingElement('div', 'empty-state', 'No imaging records are recorded.'));
        row.append(cell);
        table.replaceChildren(row);
      }
    }
    if (imagingProjectionState === 'stale') {
      setImagingFreshness('stale', 'Stale snapshot');
    } else if (imagingProjection.records.length) {
      imagingProjectionState = 'current';
      setImagingFreshness('current', 'Current');
      setImagingStatus(
        `Authoritative imaging loaded · patient revision ${
          imagingProjection.profile_revision
        } · workflow revision ${imagingProjection.workflow_revision}.`,
        'current',
        false,
      );
    } else {
      imagingProjectionState = 'empty';
      setImagingFreshness('current', 'Current · empty');
      setImagingStatus(
        `Authoritative imaging loaded · patient revision ${
          imagingProjection.profile_revision
        } · no imaging records recorded.`,
        'current',
        false,
      );
    }
    updateImagingSelectionControls();
    if (comparedImagingRecordIds.length === 2) renderImagingComparison();
    else clearImagingComparison({ moveFocus: false });
    return true;
  }

  function renderImagingUnavailable(message, state, statusLabel, retry = true) {
    const summary = document.getElementById('imaging-summary');
    if (summary) summary.textContent = 'No imaging facts are retained in this view.';
    const caption = document.getElementById('imaging-table-caption');
    if (caption) {
      caption.textContent = 'Complete authoritative imaging records in server-supplied order';
    }
    const table = document.getElementById('imaging-table-body');
    if (table) {
      const row = imagingElement('tr');
      const cell = imagingElement('td');
      cell.colSpan = 6;
      cell.append(imagingElement('div', 'empty-state', message));
      row.append(cell);
      table.replaceChildren(row);
    }
    setImagingFreshness(state, statusLabel);
    setImagingStatus(message, state, retry);
    updateImagingSelectionControls();
  }

  function clearImagingProjection(options = {}) {
    imagingFocusFallback();
    imagingLoadEpoch += 1;
    imagingSelectionEpoch += 1;
    imagingComparisonEpoch += 1;
    abortImagingRequest();
    imagingProjection = null;
    imagingResponseOwner = null;
    selectedImagingRecordIds = [];
    comparedImagingRecordIds = [];
    imagingNetworkAmbiguous = false;
    imagingProjectionState = options.state || 'error';
    clearImagingComparison({ moveFocus: false });
    renderImagingUnavailable(
      options.message || 'Imaging history could not be loaded.',
      imagingProjectionState,
      options.statusLabel || 'Unavailable',
      options.retry !== false,
    );
  }

  function markImagingProjectionStale(message, options = {}) {
    if (options.abortRequest !== false) {
      imagingLoadEpoch += 1;
      abortImagingRequest();
    }
    imagingProjectionState = 'stale';
    if (!imagingProjection) {
      renderImagingUnavailable(
        message || 'Imaging is unavailable until an authoritative reload succeeds.',
        'stale',
        'Not current',
        true,
      );
      return;
    }
    imagingResponseOwner = newImagingResponseOwner(
      imagingProjection,
      options.ownerPhiEpoch ?? phiEpoch,
    );
    setImagingFreshness('stale', 'Stale snapshot');
    setImagingStatus(
      message || 'Stale snapshot · read-only until imaging reloads.',
      'stale',
      true,
    );
    updateImagingSelectionControls();
    if (comparedImagingRecordIds.length === 2) renderImagingComparison();
  }

  function renderImagingLoading() {
    if (imagingProjection) {
      imagingProjectionState = 'stale';
      setImagingFreshness('loading', 'Checking…');
      setImagingStatus(
        'Checking the authoritative imaging record. The displayed snapshot is read-only.',
        'loading',
        false,
      );
      updateImagingSelectionControls();
      return;
    }
    imagingProjectionState = 'loading';
    renderImagingUnavailable(
      'Loading the complete authoritative imaging record…',
      'loading',
      'Loading…',
      false,
    );
  }

  function imagingTransportRequestIsCurrent(request, acceptedPhiEpoch = null) {
    const phiOwner = acceptedPhiEpoch ?? request.requestPhiEpoch;
    return Boolean(
      request
      && request.controller === imagingRequestController
      && !request.controller.signal.aborted
      && request.loadEpoch === imagingLoadEpoch
      && phiOwner === phiEpoch
    );
  }

  function imagingAuthorityMatchesKnown() {
    if (!imagingProjection || !imagingResponseOwnerIsCurrent()) return false;
    const currentProfile = normalizedRevision(latestProfileRevision);
    const currentWorkflow = normalizedRevision(workflowRevision);
    return (
      (!Number.isSafeInteger(currentProfile)
        || imagingProjection.profile_revision === currentProfile)
      && (!Number.isSafeInteger(currentWorkflow)
        || imagingProjection.workflow_revision === currentWorkflow)
    );
  }

  function ensureImagingSeries(options = {}) {
    const current = (
      imagingProjection
      && ['current', 'empty'].includes(imagingProjectionState)
      && !imagingNetworkAmbiguous
      && imagingAuthorityMatchesKnown()
    );
    if (!options.force && current) return Promise.resolve(imagingProjection);
    if (!options.force && imagingRequestController) return Promise.resolve(null);
    return loadImagingSeries(options);
  }

  async function loadImagingSeries(options = {}) {
    if (!options.force && imagingRequestController) return null;
    const previousController = imagingRequestController;
    const controller = new AbortController();
    const request = {
      ...capturePatientRequest(),
      loadEpoch: ++imagingLoadEpoch,
      controller,
    };
    imagingRequestController = controller;
    if (previousController && !previousController.signal.aborted) previousController.abort();
    renderImagingLoading();

    try {
      const response = await fetch('/api/patient/imaging-series', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      const requestIsCurrent = () => imagingTransportRequestIsCurrent(request);
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, () => false);
      if (!requestIsCurrent()) return null;
      if (!imagingProjectionPayloadIsValid(data)) {
        const invalid = new Error('Imaging history could not be verified safely.');
        invalid.status = 422;
        invalid.data = { code: 'imaging_projection_invalid_response' };
        throw invalid;
      }
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        imagingProjection: true,
      });
      if (!authority.accepted) {
        if (imagingTransportRequestIsCurrent(request)) {
          markImagingProjectionStale(
            'A newer patient or workflow revision is available. Imaging is read-only until reloaded.',
          );
        }
        return null;
      }
      request.acceptedPhiEpoch = authority.requestPhiEpoch;
      if (!imagingTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;

      const recordIds = new Set(data.records.map(record => record.id));
      const retainSelection = (
        selectedImagingRecordIds.length === 2
        && selectedImagingRecordIds.every(id => recordIds.has(id))
      );
      const nextSelection = retainSelection ? [...selectedImagingRecordIds] : [];
      const retainComparison = (
        retainSelection
        && comparedImagingRecordIds.length === 2
        && comparedImagingRecordIds.every(id => nextSelection.includes(id))
      );
      const nextComparison = retainComparison ? [...comparedImagingRecordIds] : [];
      imagingFocusFallback();
      imagingSelectionEpoch += 1;
      imagingComparisonEpoch += 1;
      imagingProjection = data;
      selectedImagingRecordIds = nextSelection;
      comparedImagingRecordIds = nextComparison;
      imagingNetworkAmbiguous = false;
      imagingProjectionState = data.records.length ? 'current' : 'empty';
      imagingResponseOwner = newImagingResponseOwner(data, request.acceptedPhiEpoch);
      if (!imagingTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;
      if (!renderImagingProjection(imagingResponseOwner)) return null;
      reportLoadSuccess('imaging');
      return data;
    } catch (error) {
      const acceptedPhiEpoch = request.acceptedPhiEpoch ?? null;
      if (
        error?.name === 'AbortError'
        || !imagingTransportRequestIsCurrent(request, acceptedPhiEpoch)
      ) return null;
      if (error?.status === 401 || error?.status === 403) {
        const safeError = new Error('Imaging authorization is unavailable.');
        safeError.status = error.status;
        reportLoadError('imaging', safeError);
        if (imagingTransportRequestIsCurrent(request, acceptedPhiEpoch)) {
          evictClientPhi(safeError);
        }
        return null;
      }
      if (error instanceof TypeError) {
        const safeError = new TypeError('The imaging endpoint could not be reached.');
        imagingNetworkAmbiguous = true;
        markImagingProjectionStale(
          imagingProjection
            ? 'Imaging transport is uncertain. The last accepted snapshot is stale and read-only.'
            : 'The imaging endpoint could not be reached and no prior snapshot is available.',
          { abortRequest: false },
        );
        reportLoadError('imaging', safeError);
        return null;
      }
      const corrupt = error?.status === 422;
      clearImagingProjection({
        state: corrupt ? 'corrupt' : 'error',
        statusLabel: corrupt ? 'Record unavailable' : 'Load failed',
        message: corrupt
          ? 'Imaging history is unavailable because the authoritative response could not be verified safely.'
          : 'Imaging history could not be loaded. No prior imaging facts remain in this view.',
      });
      const safeError = new Error(
        corrupt
          ? 'Imaging history could not be verified safely.'
          : 'Imaging history could not be loaded.',
      );
      safeError.status = error?.status;
      reportLoadError('imaging', safeError);
      return null;
    } finally {
      if (
        imagingRequestController === controller
        && request.loadEpoch === imagingLoadEpoch
      ) {
        imagingRequestController = null;
        const refresh = document.getElementById('imaging-refresh-button');
        if (refresh) refresh.disabled = false;
      }
    }
  }

  // ── Status sidebar ──────────────────────────────────────────────────────
  async function loadStatus(options = {}) {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++statusLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
      && requestLoadEpoch === statusLoadEpoch
    );
    try {
      const r = await fetch('/api/status');
      if (!requestIsCurrent()) return null;
      const d = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(
        request,
        d,
        options.authorizationOptions || {},
      );
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
    const alerts = document.getElementById('alerts-list');
    redactGeneratedQuestionChoices();
    clearFreshnessProjection();
    if (patient) patient.textContent = 'Patient profile unavailable';
    if (patientMeta) patientMeta.innerHTML = '';
    if (alerts) alerts.innerHTML = loadFailureMarkup('Alerts', 'loadStatus()');
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
    patientEvidence = null;
    if (typeof clearResearchProjection === 'function') {
      clearResearchProjection({
        state: 'error',
        message: 'Research was cleared because current patient authority is unavailable.',
        retry: false,
        fullEviction: true,
      });
    }
    if (typeof clearSymptomProjection === 'function') {
      clearSymptomProjection({
        state: 'error',
        statusLabel: 'Patient data unavailable',
        message: 'Symptom data was cleared because current authority is unavailable.',
        retry: false,
        fullEviction: true,
      });
    }
    if (typeof clearTreatmentProjection === 'function') {
      clearTreatmentProjection({
        state: 'error',
        statusLabel: 'Patient data unavailable',
        message: 'Treatment data was cleared because current authority is unavailable.',
        retry: false,
        fullEviction: true,
      });
    }
    if (typeof clearImagingProjection === 'function') {
      clearImagingProjection({
        state: 'error',
        statusLabel: 'Patient data unavailable',
        message: 'Imaging data was cleared because current authority is unavailable.',
        retry: false,
      });
    }
    if (typeof clearBiomarkerProjection === 'function') {
      clearBiomarkerProjection({
        state: 'error',
        statusLabel: 'Patient data unavailable',
        message: 'Biomarker data was cleared because current authority is unavailable.',
        retry: false,
      });
    }
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
    if (typeof clearVisitRecap === 'function') clearVisitRecap(true);
    if (pendingWorkflowIntent?.body) pendingWorkflowIntent.body = {};
    if (activeWorkflowIntent?.body) activeWorkflowIntent.body = {};
    pendingWorkflowIntent = null;
    activeWorkflowIntent = null;
    workflowMutationPending = false;
    workflowMutationOwner = null;
    appointmentDrafts = new Map();
    decisionSuccessorConflicts = new Set();
    alertsById = new Map();
    alertProjectionStale = false;
    alertLinkSourcesStale = false;
    selectedAlertId = null;
    selectedAlertToken = null;
    selectedAlertProfileRevision = null;
    alertSelectionEpoch += 1;
    alertResolutionDialogOpen = false;
    alertResolutionIntentOwner = null;
    alertResolutionMutationPending = false;
    if (pendingAlertResolutionIntent?.body) pendingAlertResolutionIntent.body = {};
    if (activeAlertResolutionIntent?.body) activeAlertResolutionIntent.body = {};
    pendingAlertResolutionIntent = null;
    activeAlertResolutionIntent = null;
    alertResolutionDrafts = new Map();
    alertResolutionResult = null;
    chatHistory = [];
    chatHistoryRevision = null;
    document.querySelectorAll('.action-feedback').forEach(editor => editor.remove());
    clearFreshnessProjection();

    const clear = (id, html = '') => {
      const element = document.getElementById(id);
      if (element) element.innerHTML = html;
    };
    const patient = document.getElementById('patient-dx');
    if (patient) patient.textContent = 'Patient data unavailable';
    clear('patient-meta');
    clear('alerts-list');
    clear('source-history');
    clear('q-list');
    clear('visit-list');
    clear('visit-source-questions');
    clear('visit-question-list');
    clear('visit-decision-list');
    clear('visit-followup-list');
    clear('visit-recap-status');
    clear('visit-recap-content');
    clear('follow-up-list');
    clear('follow-up-status');
    clear('follow-up-edit-copy');
    clear('follow-up-outcome-copy');
    clear('follow-up-outcome-guidance');
    clear('follow-up-dialog-status');
    clear('alert-resolution-message');
    clear('alert-resolution-action');
    clear('alert-resolution-status');
    clear('alert-resolution-error');
    clear('alert-resolution-priority');
    clear('alert-resolution-provenance');
    clear('alert-resolution-result-outcome');
    clear('alert-resolution-result-provenance');
    clear('alert-resolution-result-links');
    clear('judgments-list');
    clear('summary-status-inline');
    clear('summary-updated');
    clear('summary-body', '<div class="summary-empty">Patient assessment unavailable.</div>');
    clear('task-list');
    clear('panel-body', '<div class="report-empty">Activity detail unavailable.</div>');

    const appointmentOverlay = document.getElementById('appointment-overlay');
    const appointmentDialog = document.getElementById('appointment-dialog');
    const followUpOverlay = document.getElementById('follow-up-overlay');
    const followUpDialog = document.getElementById('follow-up-dialog');
    const alertResolutionOverlay = document.getElementById('alert-resolution-overlay');
    const alertResolutionDialog = document.getElementById('alert-resolution-dialog');
    if (
      alertResolutionDialog
      && typeof alertResolutionDialog.contains === 'function'
      && alertResolutionDialog.contains(document.activeElement)
    ) {
      document.activeElement?.blur();
    }
    alertResolutionOverlay?.classList.remove('open');
    alertResolutionOverlay?.setAttribute('aria-hidden', 'true');
    if (alertResolutionOverlay) alertResolutionOverlay.inert = true;
    if (alertResolutionDialog) alertResolutionDialog.inert = true;
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
    for (const name of ['questions', 'decisions', 'followups', 'recap']) {
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
      'follow-up-retry', 'follow-up-dialog-retry', 'alert-resolution-retry'
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

    const report = document.getElementById('report-panel');
    report?.classList.add('collapsed');
    report?.setAttribute('aria-hidden', 'true');
    clearReportCopyState();
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
      'judgment-input', 'q-add-input',
      'visit-create-title', 'visit-create-date', 'visit-create-time',
      'visit-create-clinician', 'visit-create-location',
      'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
      'visit-edit-clinician', 'visit-edit-location',
      'visit-manual-question', 'visit-decision-text', 'visit-decision-supersedes',
      'visit-followup-text', 'visit-followup-owner', 'visit-followup-due',
      'follow-up-create-text', 'follow-up-create-owner', 'follow-up-create-due',
      'follow-up-edit-owner', 'follow-up-edit-due', 'follow-up-outcome-text',
      'alert-resolution-outcome-text', 'alert-resolution-follow-up-text',
      'alert-resolution-follow-up-owner', 'alert-resolution-follow-up-due',
      'dismiss-text-0', 'dismiss-text-1', 'dismiss-text-2',
      'dismiss-text-3', 'dismiss-text-4'
    ]) {
      const input = document.getElementById(id);
      if (input) input.value = '';
    }
    for (const id of ['visit-manual-category', 'visit-manual-priority']) {
      const select = document.getElementById(id);
      if (select) select.value = '';
    }
    const outcomeKind = document.getElementById('follow-up-outcome-kind');
    if (outcomeKind) outcomeKind.value = 'administrative';
    const alertOutcomeKind = document.getElementById('alert-resolution-outcome-kind');
    if (alertOutcomeKind) alertOutcomeKind.value = 'administrative';
    for (const id of [
      'alert-resolution-follow-up-select', 'alert-resolution-visit-select',
      'alert-resolution-decision-select'
    ]) {
      const select = document.getElementById(id);
      if (select) {
        select.innerHTML = '';
        select.value = '';
      }
    }
    document.querySelectorAll('input[name="alert-resolution-link-mode"]').forEach(
      input => { input.checked = input.value === 'none'; },
    );
    const alertConfirm = document.getElementById('alert-resolution-confirm');
    if (alertConfirm) alertConfirm.checked = false;
    const alertForm = document.getElementById('alert-resolution-form');
    const alertResult = document.getElementById('alert-resolution-result');
    if (alertForm) alertForm.hidden = false;
    if (alertResult) alertResult.hidden = true;
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
    if (alertResolutionOverlay) alertResolutionOverlay.inert = true;
    if (alertResolutionDialog) alertResolutionDialog.inert = true;
    setAlertResolutionBusy(false);
    setFollowUpMutationBusy(false);
    setAppointmentMutationBusy(false);
    updateAppointmentFormValidity();
  }

  function renderSidebar(d) {
    const p = d.patient || {};
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
    `;

    const alerts = Array.isArray(d.alerts) ? d.alerts : [];
    alertsById = new Map(
      alerts
        .filter(alert => alert && typeof alert.id === 'string')
        .map(alert => [alert.id, alert])
    );
    alertProjectionStale = false;
    renderAlerts();
    if (alertResolutionDialogOpen) {
      const selected = selectedAlertId ? alertsById.get(selectedAlertId) : null;
      const selectionCurrent = selected
        && selected.resolve_token === selectedAlertToken
        && String(latestProfileRevision) === String(selectedAlertProfileRevision);
      if (selectionCurrent && !alertResolutionMutationPending) {
        renderAlertResolutionContext(selected);
      } else if (!selectionCurrent) {
        redactAlertResolutionContext(
          alertResolutionMutationPending
            ? 'Saving the authoritative resolution…'
            : 'This alert changed or is no longer available.'
        );
        if (!alertResolutionMutationPending) {
          alertProjectionStale = true;
          alertLinkSourcesStale = true;
          alertResolutionIntentOwner = null;
          alertSelectionEpoch += 1;
        }
      }
      updateAlertResolutionFormValidity();
    }
  }

  function renderAlerts() {
    const list = document.getElementById('alerts-list');
    if (!list) return;
    const alerts = [...alertsById.values()];
    const staleNotice = alertProjectionStale
      ? '<div class="follow-up-stale-note" role="status">Alerts are offline and read-only until the current record reloads.</div>'
      : '';
    list.innerHTML = staleNotice + (alerts.length
      ? alerts.map(alert => `
        <div class="alert-item ${safeClassToken(alert.priority, 'normal')}" data-alert-id="${escHtml(alert.id)}" data-resolve-token="${escHtml(alert.resolve_token)}">
          <div class="alert-msg">${escHtml(alert.message)}</div>
          ${alert.action_required ? `<div class="alert-action">→ ${escHtml(alert.action_required)}</div>` : ''}
          <div class="alert-meta">
            <span class="alert-priority ${safeClassToken(alert.priority, 'normal')}">${escHtml(alert.priority || '—')}</span>
            <button class="resolve-btn" ${alertProjectionStale || alertResolutionIntentOwner !== null || alertResolutionMutationPending ? 'disabled' : ''} onclick="openAlertResolutionDialog(this, this.closest('.alert-item'))">Resolve alert</button>
          </div>
        </div>`).join('')
      : '<div class="empty-state">No active alerts</div>');
  }

  function alertResolutionProvenanceLabel(provenance = {}, kind = '') {
    if (
      provenance.capture_method === 'caregiver_entered'
      && provenance.attributed_to === 'clinician'
      && provenance.source_verification === 'unverified'
    ) return 'Caregiver-entered · attributed to clinician · unverified';
    if (
      provenance.capture_method === 'caregiver_entered'
      && provenance.attributed_to === 'patient_or_caregiver'
      && provenance.source_verification === 'unverified'
    ) return 'Caregiver-entered · caregiver reported · unverified';
    if (
      provenance.capture_method === 'caregiver_entered'
      && provenance.attributed_to === 'caregiver'
      && provenance.source_verification === 'not_applicable'
    ) return 'Caregiver-entered administrative outcome · not clinical evidence';
    return {
      clinician_attributed: 'Caregiver-entered · attributed to clinician · unverified',
      caregiver_reported: 'Caregiver-entered · caregiver reported · unverified',
      administrative: 'Caregiver-entered administrative outcome · not clinical evidence',
    }[kind] || 'Caregiver-entered outcome · provenance unavailable';
  }

  function updateAlertResolutionProvenance() {
    const kind = document.getElementById('alert-resolution-outcome-kind')?.value;
    const node = document.getElementById('alert-resolution-provenance');
    if (node) node.textContent = alertResolutionProvenanceLabel({}, kind);
  }

  function setAlertResolutionStatus(message, tone = '') {
    const status = document.getElementById('alert-resolution-status');
    if (!status) return;
    status.textContent = message || '';
    status.className = `follow-up-dialog-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
  }

  function selectedAlertResolutionMode() {
    return document.querySelector(
      'input[name="alert-resolution-link-mode"]:checked'
    )?.value || 'none';
  }

  function captureAlertResolutionAuthority(owner = alertResolutionIntentOwner) {
    return {
      owner,
      requestPhiEpoch: phiEpoch,
      requestAlertEpoch: alertSelectionEpoch,
      alertId: selectedAlertId,
      expectedToken: selectedAlertToken,
      expectedProfileRevision: selectedAlertProfileRevision,
    };
  }

  function alertResolutionAuthorityIsCurrent(authority) {
    return Boolean(authority)
      && alertResolutionOwnerIsCurrent(authority.owner, authority.requestPhiEpoch)
      && authority.requestAlertEpoch === alertSelectionEpoch
      && authority.alertId === selectedAlertId
      && authority.expectedToken === selectedAlertToken
      && String(authority.expectedProfileRevision) === String(selectedAlertProfileRevision)
      && String(authority.expectedProfileRevision) === String(latestProfileRevision);
  }

  function alertResolutionDraftKey(alertId = selectedAlertId) {
    return `resolve:${alertId || 'unavailable'}`;
  }

  function captureAlertResolutionDraft() {
    if (!alertResolutionDialogOpen || !selectedAlertId) return;
    const mode = selectedAlertResolutionMode();
    alertResolutionDrafts.set(alertResolutionDraftKey(), {
      outcomeKind: document.getElementById('alert-resolution-outcome-kind')?.value
        || 'administrative',
      outcomeText: document.getElementById('alert-resolution-outcome-text')?.value || '',
      mode: mode === 'inline' ? 'inline' : 'none',
      followUpText: document.getElementById('alert-resolution-follow-up-text')?.value || '',
      followUpOwner: document.getElementById('alert-resolution-follow-up-owner')?.value || '',
      followUpDue: document.getElementById('alert-resolution-follow-up-due')?.value || '',
    });
  }

  function restoreAlertResolutionDraft() {
    const draft = alertResolutionDrafts.get(alertResolutionDraftKey());
    document.getElementById('alert-resolution-outcome-kind').value =
      draft?.outcomeKind || 'administrative';
    document.getElementById('alert-resolution-outcome-text').value =
      draft?.outcomeText || '';
    document.getElementById('alert-resolution-follow-up-text').value =
      draft?.followUpText || '';
    document.getElementById('alert-resolution-follow-up-owner').value =
      draft?.followUpOwner || '';
    document.getElementById('alert-resolution-follow-up-due').value =
      draft?.followUpDue || '';
    const mode = draft?.mode === 'inline' ? 'inline' : 'none';
    const radio = document.querySelector(
      `input[name="alert-resolution-link-mode"][value="${mode}"]`
    );
    if (radio) radio.checked = true;
    document.getElementById('alert-resolution-confirm').checked = false;
    updateAlertResolutionProvenance();
    renderAlertResolutionLinkMode();
  }

  function clearAlertResolutionRetry() {
    if (pendingAlertResolutionIntent?.body) pendingAlertResolutionIntent.body = {};
    pendingAlertResolutionIntent = null;
    const retry = document.getElementById('alert-resolution-retry');
    if (retry) retry.hidden = true;
  }

  function invalidateAlertResolutionRetryOnDraftChange() {
    if (pendingAlertResolutionIntent) {
      clearAlertResolutionRetry();
      setAlertResolutionStatus(
        'The draft changed. Reload the current sources and submit a new request.',
        'conflict',
      );
    }
    captureAlertResolutionDraft();
    updateAlertResolutionFormValidity();
  }

  function redactAlertResolutionContext(message) {
    const contextMessage = document.getElementById('alert-resolution-message');
    const contextAction = document.getElementById('alert-resolution-action');
    const priority = document.getElementById('alert-resolution-priority');
    if (contextMessage) contextMessage.textContent = 'Alert changed or unavailable.';
    if (contextAction) contextAction.textContent = '';
    if (priority) {
      priority.textContent = '';
      priority.className = 'alert-priority';
    }

    setAlertResolutionStatus(message, 'conflict');
    const submit = document.getElementById('alert-resolution-submit');
    if (submit) submit.disabled = true;
  }

  function redactAlertResolutionCard(alertId = selectedAlertId) {
    if (!alertId || !alertsById.has(alertId)) return;
    alertsById.delete(alertId);
    renderAlerts();
  }

  function renderAlertResolutionContext(alert) {
    if (!alert || alert.id !== selectedAlertId) {
      redactAlertResolutionContext('This alert changed or is no longer available.');
      return;
    }
    document.getElementById('alert-resolution-message').textContent =
      alert.message || 'Alert details unavailable';
    document.getElementById('alert-resolution-action').textContent =
      alert.action_required ? `Suggested next step: ${alert.action_required}` : '';
    const priority = document.getElementById('alert-resolution-priority');
    priority.textContent = alert.priority || 'normal';
    priority.className = `alert-priority ${safeClassToken(alert.priority, 'normal')}`;
  }

  function eligibleAlertFollowUps() {
    return [...followUpsById.values()].filter(
      item => item && ['open', 'in_progress'].includes(item.status)
    );
  }

  function eligibleAlertVisits() {
    return [...visitsById.values()].filter(
      item => item && ['planned', 'in_progress'].includes(item.status)
    );
  }

  function renderAlertResolutionSourceOptions() {
    const followUpSelect = document.getElementById('alert-resolution-follow-up-select');
    const visitSelect = document.getElementById('alert-resolution-visit-select');
    const currentFollowUp = followUpSelect.value;
    const currentVisit = visitSelect.value;
    const followUps = eligibleAlertFollowUps();
    const visits = eligibleAlertVisits();
    followUpSelect.innerHTML = '<option value="">Choose an active follow-up</option>'
      + followUps.map(item => {
        const label = [item.text, item.owner ? `Owner: ${item.owner}` : 'Owner not set']
          .filter(Boolean).join(' · ');
        return `<option value="${escHtml(item.id)}">${escHtml(label)}</option>`;
      }).join('');
    visitSelect.innerHTML = '<option value="">Choose a current visit</option>'
      + visits.map(visit => {
        const label = [visit.title, visit.date ? fmtDate(visit.date) : null]
          .filter(Boolean).join(' · ');
        return `<option value="${escHtml(visit.id)}">${escHtml(label)}</option>`;
      }).join('');
    if (followUps.some(item => item.id === currentFollowUp)) {
      followUpSelect.value = currentFollowUp;
    }
    if (visits.some(item => item.id === currentVisit)) visitSelect.value = currentVisit;
    renderAlertResolutionDecisionOptions();
  }

  function renderAlertResolutionDecisionOptions() {
    const visitId = document.getElementById('alert-resolution-visit-select')?.value;
    const decisionSelect = document.getElementById('alert-resolution-decision-select');
    if (!decisionSelect) return;
    const current = decisionSelect.value;
    const visit = visitId ? visitsById.get(visitId) : null;
    const decisions = (visit?.decisions || []).filter(
      item => ['active', 'needs_confirmation'].includes(item.status)
    );
    decisionSelect.innerHTML = '<option value="">No linked decision</option>'
      + decisions.map(item => (
        `<option value="${escHtml(item.id)}">${escHtml(item.text)}</option>`
      )).join('');
    if (decisions.some(item => item.id === current)) decisionSelect.value = current;
    updateAlertResolutionFormValidity();
  }

  function renderAlertResolutionLinkMode() {
    const mode = selectedAlertResolutionMode();
    const panels = [
      ['alert-resolution-existing-follow-up', 'follow_up'],
      ['alert-resolution-inline-follow-up', 'inline'],
      ['alert-resolution-visit-link', 'visit'],
    ];
    for (const [id, panelMode] of panels) {
      const panel = document.getElementById(id);
      const enabled = mode === panelMode
        && !alertResolutionMutationPending
        && (panelMode === 'inline' || !alertLinkSourcesStale);
      if (!panel) continue;
      panel.hidden = mode !== panelMode;
      panel.querySelectorAll('input, textarea, select').forEach(control => {
        control.disabled = !enabled;
      });
    }
    updateAlertResolutionFormValidity();
  }

  function setAlertResolutionProjectionReadOnly(readOnly) {
    const dialog = document.getElementById('alert-resolution-dialog');
    dialog?.classList.toggle('projection-stale', readOnly);
    document.getElementById('alert-resolution-link-modes')?.setAttribute(
      'aria-disabled',
      String(readOnly),
    );
    document.querySelectorAll(
      'input[name="alert-resolution-link-mode"], '
      + '#alert-resolution-follow-up-select, #alert-resolution-visit-select, '
      + '#alert-resolution-decision-select'
    ).forEach(control => {
      control.disabled = readOnly || alertResolutionMutationPending;
    });
    renderAlertResolutionLinkMode();
  }

  function setAlertResolutionBusy(busy) {
    document.querySelectorAll(
      '#alerts-list .resolve-btn, #alert-resolution-dialog button, '
      + '#alert-resolution-dialog input, #alert-resolution-dialog textarea, '
      + '#alert-resolution-dialog select'
    ).forEach(control => {
      if (busy) {
        if (!('alertWasDisabled' in control.dataset)) {
          control.dataset.alertWasDisabled = String(control.disabled);
        }
        control.disabled = true;
      } else if ('alertWasDisabled' in control.dataset) {
        control.disabled = control.dataset.alertWasDisabled === 'true';
        delete control.dataset.alertWasDisabled;
      }
    });
  }

  function updateAlertResolutionFormValidity() {
    const submit = document.getElementById('alert-resolution-submit');
    if (!submit) return;
    const alert = selectedAlertId ? alertsById.get(selectedAlertId) : null;
    const mode = selectedAlertResolutionMode();
    const outcomeText =
      (document.getElementById('alert-resolution-outcome-text')?.value || '').trim();
    const outcomeKind = document.getElementById('alert-resolution-outcome-kind')?.value;
    const outcomeIsValid = !outcomeText
      || ALERT_RESOLUTION_OUTCOME_KINDS.has(outcomeKind);
    const hasModeTarget = mode === 'none'
      || (
        mode === 'follow_up'
        && Boolean(document.getElementById('alert-resolution-follow-up-select')?.value)
      )
      || (
        mode === 'inline'
        && Boolean(
          (document.getElementById('alert-resolution-follow-up-text')?.value || '').trim()
        )
      )
      || (
        mode === 'visit'
        && Boolean(document.getElementById('alert-resolution-visit-select')?.value)
      );
    submit.disabled = alertResolutionMutationPending
      || alertProjectionStale
      || alertLinkSourcesStale
      || !alert
      || !alert.resolve_token
      || latestProfileRevision == null
      || !outcomeIsValid
      || !hasModeTarget
      || !document.getElementById('alert-resolution-confirm')?.checked;
  }

  function beginAlertResolutionOwner() {
    if (
      alertResolutionIntentOwner !== null
      || (
        typeof alertResolutionMutationPending !== 'undefined'
        && alertResolutionMutationPending
      )
      || followUpControlsLocked()
    ) return null;
    const owner = {};
    alertResolutionIntentOwner = owner;
    return owner;
  }

  function alertResolutionOwnerIsCurrent(owner, expectedPhiEpoch = phiEpoch) {
    return alertResolutionIntentOwner === owner
      && alertResolutionDialogOpen
      && expectedPhiEpoch === phiEpoch;
  }

  async function refreshAlertResolutionSources(owner) {
    const authority = captureAlertResolutionAuthority(owner);
    const responseGuard = () => alertResolutionAuthorityIsCurrent(authority);
    alertLinkSourcesStale = true;
    setAlertResolutionProjectionReadOnly(true);
    updateAlertResolutionFormValidity();
    const results = await Promise.allSettled([
      loadFollowUps({ responseGuard }),
      loadVisits({ responseGuard }),
    ]);
    if (!responseGuard()) return false;
    const loaded = results.every(
      result => result.status === 'fulfilled' && result.value !== null
    ) && !followUpProjectionStale;
    alertLinkSourcesStale = !loaded;
    if (!loaded) {
      alertProjectionStale = true;
      renderAlerts();
      setAlertResolutionProjectionReadOnly(true);
      setAlertResolutionStatus(
        'Current link sources could not be verified. The last loaded options are read-only.',
        'offline',
      );
    } else {
      renderAlertResolutionSourceOptions();
      setAlertResolutionProjectionReadOnly(false);
      if (!alertProjectionStale) setAlertResolutionStatus('');
    }
    updateAlertResolutionFormValidity();
    return loaded;
  }

  async function openAlertResolutionDialog(trigger, row) {
    const owner = beginAlertResolutionOwner();
    if (!owner) return;
    const alertId = row?.dataset.alertId;
    const token = row?.dataset.resolveToken;
    const alert = alertId ? alertsById.get(alertId) : null;
    if (
      alertProjectionStale
      || !alert
      || !token
      || token !== alert.resolve_token
      || latestProfileRevision == null
    ) {
      alertResolutionIntentOwner = null;
      renderAlerts();
      return;
    }
    selectedAlertId = alertId;
    selectedAlertToken = token;
    selectedAlertProfileRevision = latestProfileRevision;
    alertSelectionEpoch += 1;
    alertResolutionDialogOpen = true;
    alertLinkSourcesStale = true;
    alertResolutionResult = null;
    clearAlertResolutionRetry();
    setFormError('alert-resolution-error', '');
    setAlertResolutionStatus('Loading current link choices…', 'saving');
    const form = document.getElementById('alert-resolution-form');
    const result = document.getElementById('alert-resolution-result');
    form.hidden = false;
    result.hidden = true;
    renderAlertResolutionContext(alert);
    restoreAlertResolutionDraft();
    const overlay = document.getElementById('alert-resolution-overlay');
    const dialog = document.getElementById('alert-resolution-dialog');
    overlay.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    dialog.inert = false;
    setAlertResolutionProjectionReadOnly(true);
    renderAlerts();
    activateDialog(dialog, trigger);
    await refreshAlertResolutionSources(owner);
  }

  function closeAlertResolutionDialog(preserveDraft = true, force = false) {
    if (!alertResolutionDialogOpen) return;
    if (alertResolutionMutationPending && !force) {
      setAlertResolutionStatus(
        'Saving is still in progress. Wait for the result before closing.',
        'saving',
      );
      return;
    }
    const closingAlertId = selectedAlertId;
    if (preserveDraft && !alertResolutionResult) captureAlertResolutionDraft();
    clearAlertResolutionRetry();
    if (activeAlertResolutionIntent?.body) activeAlertResolutionIntent.body = {};
    activeAlertResolutionIntent = null;
    alertResolutionDialogOpen = false;
    alertResolutionIntentOwner = null;
    alertResolutionMutationPending = false;
    selectedAlertId = null;
    selectedAlertToken = null;
    selectedAlertProfileRevision = null;
    alertSelectionEpoch += 1;
    alertResolutionResult = null;
    const overlay = document.getElementById('alert-resolution-overlay');
    const dialog = document.getElementById('alert-resolution-dialog');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    setAlertResolutionBusy(false);
    renderAlerts();
    if (closingAlertId && lastDialogTrigger) {
      lastDialogTrigger = [...document.querySelectorAll('#alerts-list .resolve-btn')]
        .find(button => button.closest('.alert-item')?.dataset.alertId === closingAlertId)
        || lastDialogTrigger;
    }
    deactivateDialog(dialog);
  }

  function closeAlertResolutionFromBackdrop(event) {
    if (event?.target === document.getElementById('alert-resolution-overlay')) {
      closeAlertResolutionDialog();
    }
  }

  function createAlertResolutionBody(alert) {
    const body = {
      mutation_id: newMutationId(),
      expected_token: alert.resolve_token,
      expected_profile_revision: latestProfileRevision,
    };
    const outcomeText =
      (document.getElementById('alert-resolution-outcome-text')?.value || '').trim();
    if (outcomeText) {
      const kind = document.getElementById('alert-resolution-outcome-kind')?.value;
      if (!ALERT_RESOLUTION_OUTCOME_KINDS.has(kind)) {
        throw new Error('Choose a valid outcome source.');
      }
      body.outcome = {
        kind,
        text: outcomeText,
      };
    }
    const mode = selectedAlertResolutionMode();
    if (mode === 'follow_up') {
      body.follow_up_id =
        document.getElementById('alert-resolution-follow-up-select')?.value;
    } else if (mode === 'inline') {
      body.follow_up = {
        text:
          (document.getElementById('alert-resolution-follow-up-text')?.value || '').trim(),
        owner:
          (document.getElementById('alert-resolution-follow-up-owner')?.value || '').trim()
          || null,
        due_date: document.getElementById('alert-resolution-follow-up-due')?.value || null,
      };
    } else if (mode === 'visit') {
      body.visit_id = document.getElementById('alert-resolution-visit-select')?.value;
      const decisionId =
        document.getElementById('alert-resolution-decision-select')?.value;
      if (decisionId) body.decision_id = decisionId;
    }
    return body;
  }

  function alertResolutionIntentOwnsMutation(
    intent,
    expectedPhiEpoch = intent.pendingPhiEpoch ?? intent.requestPhiEpoch,
  ) {
    const currentAlert = selectedAlertId ? alertsById.get(selectedAlertId) : null;
    return alertResolutionMutationPending
      && alertResolutionIntentOwner === intent.owner
      && alertResolutionOwnerIsCurrent(intent.owner, expectedPhiEpoch)
      && intent.requestAlertEpoch === alertSelectionEpoch
      && intent.alertId === selectedAlertId
      && (
        intent.responseAuthorized
        || (
          currentAlert?.resolve_token === intent.expectedToken
          && String(intent.expectedProfileRevision) === String(latestProfileRevision)
        )
      );
  }

  function releaseAlertResolutionMutation(intent) {
    if (
      !alertResolutionMutationPending
      || alertResolutionIntentOwner !== intent.owner
    ) return false;
    alertResolutionMutationPending = false;
    if (activeAlertResolutionIntent === intent) activeAlertResolutionIntent = null;
    setAlertResolutionBusy(false);
    setAlertResolutionProjectionReadOnly(
      alertProjectionStale || alertLinkSourcesStale,
    );
    renderAlerts();
    updateAlertResolutionFormValidity();
    return true;
  }

  function renderAlertResolutionResult(data) {
    const resolution = data.alert?.resolution || {};
    alertResolutionResult = data;
    document.getElementById('alert-resolution-form').hidden = true;
    document.getElementById('alert-resolution-result').hidden = false;
    document.getElementById('alert-resolution-result-outcome').textContent =
      resolution.outcome_text || 'Marked resolved';
    document.getElementById('alert-resolution-result-provenance').textContent =
      resolution.outcome_text
        ? alertResolutionProvenanceLabel(
            resolution.provenance || {},
            resolution.outcome_kind || '',
          )
        : '';
    const links = [];
    if (resolution.follow_up_id) {
      const followUp = followUpsById.get(resolution.follow_up_id) || data.follow_up;
      links.push(
        followUp
          ? `Follow-up · ${followUp.text}`
          : 'Follow-up linked'
      );
    }
    if (resolution.visit_id) {
      const visit = visitsById.get(resolution.visit_id);
      links.push(visit ? `Visit · ${visit.title}` : 'Visit linked');
      if (resolution.decision_id) {
        const decision = (visit?.decisions || []).find(
          item => item.id === resolution.decision_id
        );
        links.push(
          decision
            ? `Decision · ${decision.text} · caregiver-entered, clinician-attributed, unverified`
            : 'Current visit decision linked'
        );
      }
    }
    document.getElementById('alert-resolution-result-links').innerHTML =
      links.length
        ? links.map(link => `<span>${escHtml(link)}</span>`).join('')
        : '<span>No follow-up or visit link recorded.</span>';
    document.getElementById('alert-resolution-message').textContent = '';
    document.getElementById('alert-resolution-action').textContent = '';
    setAlertResolutionStatus('Resolution saved and current patient views reloaded.', 'success');
  }

  async function handleAlertResolutionConflict(error, intent) {
    if (!alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) return;
    captureAlertResolutionDraft();
    clearAlertResolutionRetry();
    alertProjectionStale = true;
    alertLinkSourcesStale = true;
    redactAlertResolutionCard(intent.alertId);
    redactAlertResolutionContext(
      error.message || 'This alert changed. Reloading the current record.',
    );
    const expectedOwner = intent.owner;
    selectedAlertToken = null;
    selectedAlertProfileRevision = null;
    alertSelectionEpoch += 1;
    intent.requestAlertEpoch = alertSelectionEpoch;
    intent.conflictReloading = true;
    const conflictPhiEpoch = phiEpoch;
    const conflictGuard = () => (
      alertResolutionIntentOwner === expectedOwner
      && alertResolutionDialogOpen
      && alertResolutionMutationPending
      && selectedAlertId === intent.alertId
      && intent.requestAlertEpoch === alertSelectionEpoch
      && selectedAlertToken === null
      && selectedAlertProfileRevision === null
      && conflictPhiEpoch === phiEpoch
    );
    const status = await loadStatus({
      responseGuard: conflictGuard,
      authorizationOptions: { alertResolution: true },
    });
    if (
      alertResolutionIntentOwner !== expectedOwner
      || !alertResolutionDialogOpen
      || !alertResolutionMutationPending
      || selectedAlertId !== intent.alertId
      || intent.requestAlertEpoch !== alertSelectionEpoch
      || status?.profile_revision == null
    ) {
      intent.body = {};
      return;
    }
    intent.pendingPhiEpoch = phiEpoch;
    const alert = alertsById.get(intent.alertId);
    if (!alert?.resolve_token) {
      const absentPhiEpoch = phiEpoch;
      const absentGuard = () => (
        alertResolutionIntentOwner === expectedOwner
        && alertResolutionDialogOpen
        && alertResolutionMutationPending
        && selectedAlertId === intent.alertId
        && intent.requestAlertEpoch === alertSelectionEpoch
        && selectedAlertToken === null
        && selectedAlertProfileRevision === null
        && absentPhiEpoch === phiEpoch
      );
      const refreshed = await refreshClinicalWorkflowState(
        status.profile_revision,
        status.workflow_revision,
        {
          responseGuard: absentGuard,
          authorizationOptions: { alertResolution: true },
        },
      );
      intent.body = {};
      if (!absentGuard()) return;
      alertProjectionStale = refreshed?.verified !== true;
      alertLinkSourcesStale = true;
      setAlertResolutionProjectionReadOnly(true);
      renderAlerts();
      redactAlertResolutionContext('This alert changed or is no longer available.');
      return;
    }
    selectedAlertId = alert.id;
    selectedAlertToken = alert.resolve_token;
    selectedAlertProfileRevision = status.profile_revision;
    const refreshedAuthority = captureAlertResolutionAuthority(expectedOwner);
    const refreshedGuard = () => alertResolutionAuthorityIsCurrent(refreshedAuthority);
    const refreshed = await refreshClinicalWorkflowState(
      status.profile_revision,
      status.workflow_revision,
      {
        responseGuard: refreshedGuard,
        authorizationOptions: { alertResolution: true },
      },
    );
    if (!refreshedGuard()) {
      intent.body = {};
      return;
    }
    const loaded = refreshed?.verified === true && !followUpProjectionStale;
    alertProjectionStale = !loaded;
    alertLinkSourcesStale = !loaded;
    const currentAlert = alertsById.get(intent.alertId);
    if (loaded && currentAlert?.resolve_token === selectedAlertToken) {
      renderAlertResolutionContext(currentAlert);
      restoreAlertResolutionDraft();
      renderAlertResolutionSourceOptions();
      setAlertResolutionProjectionReadOnly(false);
      setAlertResolutionStatus(
        'The alert changed. Review the reloaded alert and submit a new request.',
        'conflict',
      );
    } else {
      setAlertResolutionProjectionReadOnly(true);
      redactAlertResolutionContext(
        currentAlert
          ? 'The current record could not be verified. Retry loading before continuing.'
          : 'This alert changed or is no longer available.',
      );
    }
    renderAlerts();
    updateAlertResolutionFormValidity();
    intent.body = {};
  }

  async function performAlertResolutionIntent(intent, explicitRetry = false) {
    if (!alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
    activeAlertResolutionIntent = intent;
    setAlertResolutionBusy(true);
    if (!explicitRetry) clearAlertResolutionRetry();
    setAlertResolutionStatus(
      explicitRetry ? 'Retrying the unchanged request…' : 'Saving resolution…',
      'saving',
    );
    try {
      const response = await fetch(
        `/api/alerts/${encodeURIComponent(intent.alertId)}/resolve`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(intent.body),
        },
      );
      if (!alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const data = await readJsonResponse(
        response,
        () => alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch),
      );
      if (!alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const authority = authorizePatientResponse(intent, data, {
        workflow: 'targeted',
        alertResolution: true,
      });
      if (!authority.accepted) return null;
      intent.responseAuthorized = true;
      intent.pendingPhiEpoch = phiEpoch;
      if (!alertResolutionIntentOwnsMutation(intent)) return null;
      const refreshed = await refreshClinicalWorkflowState(
        data.profile_revision,
        data.workflow_revision,
        {
          responseGuard: () => alertResolutionIntentOwnsMutation(intent),
          authorizationOptions: { alertResolution: true },
        },
      );
      if (
        refreshed?.verified !== true
        || !alertResolutionIntentOwnsMutation(intent)
      ) {
        if (alertResolutionIntentOwnsMutation(intent)) {
          alertProjectionStale = true;
          alertLinkSourcesStale = true;
          setAlertResolutionProjectionReadOnly(true);
          setAlertResolutionStatus(
            'The resolution was saved, but current patient views could not be verified. Reload before continuing.',
            'offline',
          );
          renderAlerts();
        }
        return null;
      }
      alertResolutionDrafts.delete(intent.draftKey);
      clearAlertResolutionRetry();
      renderAlertResolutionResult(data);
      reportLoadSuccess('alert-resolution');
      releaseAlertResolutionMutation(intent);
      return data;
    } catch (error) {
      if (!alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('alert-resolution', error);
        if (alertResolutionIntentOwnsMutation(intent, intent.requestPhiEpoch)) {
          evictClientPhi(error);
        }
        return null;
      }
      if (error?.status === 409) {
        await handleAlertResolutionConflict(error, intent);
        return null;
      }
      if (
        error instanceof TypeError
        || error?.name === 'AbortError'
        || navigator.onLine === false
      ) {
        pendingAlertResolutionIntent = intent;
        captureAlertResolutionDraft();
        alertProjectionStale = true;
        alertLinkSourcesStale = true;
        renderAlerts();
        setAlertResolutionProjectionReadOnly(true);
        const retry = document.getElementById('alert-resolution-retry');
        if (retry) retry.hidden = false;
        setAlertResolutionStatus(
          'Connection lost. The last alert and link choices are read-only; retry only if the draft is unchanged.',
          'offline',
        );
        reportLoadError('alert-resolution', error);
        return null;
      }
      const message = error?.message || 'The alert resolution could not be saved.';
      setFormError('alert-resolution-error', message);
      setAlertResolutionStatus(message, 'error');
      reportLoadError('alert-resolution', error);
      return null;
    } finally {
      if (activeAlertResolutionIntent === intent) activeAlertResolutionIntent = null;
      releaseAlertResolutionMutation(intent);
    }
  }

  async function submitAlertResolution() {
    if (
      alertResolutionMutationPending
      || alertProjectionStale
      || alertLinkSourcesStale
      || !alertResolutionDialogOpen
    ) return;
    const owner = alertResolutionIntentOwner;
    const alert = selectedAlertId ? alertsById.get(selectedAlertId) : null;
    if (!owner || !alert || !alert.resolve_token || latestProfileRevision == null) return;
    updateAlertResolutionFormValidity();
    if (document.getElementById('alert-resolution-submit')?.disabled) return;
    captureAlertResolutionDraft();
    alertResolutionMutationPending = true;
    const body = createAlertResolutionBody(alert);
    const intent = {
      owner,
      alertId: alert.id,
      expectedToken: alert.resolve_token,
      expectedProfileRevision: latestProfileRevision,
      requestPhiEpoch: phiEpoch,
      requestAlertEpoch: alertSelectionEpoch,
      requestAlertId: alert.id,
      body,
      draftKey: alertResolutionDraftKey(alert.id),
    };
    await performAlertResolutionIntent(intent);
  }

  async function retryAlertResolution() {
    const intent = pendingAlertResolutionIntent;
    if (
      !intent
      || alertResolutionMutationPending
      || alertResolutionIntentOwner !== intent.owner
      || intent.requestAlertEpoch !== alertSelectionEpoch
      || intent.alertId !== selectedAlertId
      || intent.requestPhiEpoch !== phiEpoch
    ) {
      clearAlertResolutionRetry();
      return;
    }
    alertResolutionMutationPending = true;
    await performAlertResolutionIntent(intent, true);
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

  // ── Symptom episodes and source observations ─────────────────────────────
  const SYMPTOM_SAFETY_GUIDANCE =
    'NET/Care records what you enter but does not assess urgency or monitor symptoms. '
    + 'Contact the treating team about symptoms or concerns. If you think this may be a '
    + 'medical emergency, contact local emergency services.';
  const SYMPTOM_MAX_OBSERVATIONS = 2000;
  const SYMPTOM_MAX_EPISODES = 1000;
  const SYMPTOM_MAX_ACTIONS = 500;
  const SYMPTOM_MAX_AUTHORITY_CHARS = 4000000;
  const SYMPTOM_DATE_PRECISIONS = new Set(['day', 'month', 'year', 'unknown']);
  const SYMPTOM_OBSERVATION_DATE_KINDS = new Set(['clinical', 'legacy_unknown', 'unknown']);
  const SYMPTOM_EPISODE_DATE_KINDS = new Set(['caregiver_entered', 'unknown']);
  const SYMPTOM_SEVERITIES = new Set(['mild', 'moderate', 'severe']);
  const SYMPTOM_REPORTED_SUBJECTS = new Set(['patient', 'caregiver', 'unspecified']);
  const SYMPTOM_OBSERVATION_PROVENANCE = new Set([
    'caregiver_corrected_unverified',
    'source_verified',
    'source_unverified',
    'legacy_caregiver_entered_unverified',
    'legacy_model_extracted_unverified',
    'legacy_unknown',
  ]);
  const SYMPTOM_ACTION_STATUSES = new Set(['open', 'in_progress', 'completed', 'cancelled']);

  function symptomPlainObject(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  }

  function symptomHasExactKeys(value, keys, optional = []) {
    if (!symptomPlainObject(value)) return false;
    const actual = Object.keys(value).sort();
    const required = new Set(keys);
    const allowed = new Set([...keys, ...optional]);
    return keys.every(key => Object.prototype.hasOwnProperty.call(value, key))
      && actual.every(key => allowed.has(key))
      && actual.length >= required.size;
  }

  function symptomBoundedString(value, maximum, nullable = false) {
    if (nullable && value == null) return true;
    return typeof value === 'string' && value.length <= maximum;
  }

  function symptomObservationUrlParts(value, expectedAction) {
    if (typeof value !== 'string' || !value || value.length > 220 || value.includes('\\')) return null;
    const match = value.match(
      /^\/api\/patient\/symptom-episodes\/observations\/(symref_[0-9a-f]{64})\/(source|evidence)$/,
    );
    if (!match || match[2] !== expectedAction) return null;
    try {
      const base = document.baseURI || window.location.href || window.location.origin;
      const pageUrl = new URL(base);
      const url = new URL(value, base);
      if (
        !/^(https?):$/.test(url.protocol)
        || url.origin !== pageUrl.origin
        || url.username
        || url.password
        || url.search
        || url.hash
        || url.pathname !== value
      ) return null;
      return { href: value, recordRef: match[1], action: match[2] };
    } catch (_) {
      return null;
    }
  }

  function safeSymptomObservationUrl(value, expectedAction) {
    return symptomObservationUrlParts(value, expectedAction)?.href || '';
  }

  function symptomDateAuthorityIsValid(date, episode = false) {
    const expectedKeys = episode
      ? ['value', 'precision', 'kind']
      : [
        'value',
        'precision',
        'kind',
        'source_document_date',
        'source_document_date_precision',
      ];
    if (
      !symptomHasExactKeys(date, expectedKeys)
      || !symptomBoundedString(date.value, 32, true)
      || !SYMPTOM_DATE_PRECISIONS.has(date.precision)
      || !(episode ? SYMPTOM_EPISODE_DATE_KINDS : SYMPTOM_OBSERVATION_DATE_KINDS).has(date.kind)
      || (date.precision === 'unknown' && date.kind !== 'unknown')
    ) return false;
    const derivedPrecision = symptomDatePrecision(date.value);
    if (date.precision !== derivedPrecision) return false;
    if (!episode && (
      !symptomBoundedString(date.source_document_date, 32, true)
      || !SYMPTOM_DATE_PRECISIONS.has(date.source_document_date_precision)
      || date.source_document_date_precision !== symptomDatePrecision(date.source_document_date)
    )) return false;
    return true;
  }

  function symptomActionIsValid(action, eligible = false) {
    return symptomHasExactKeys(action, ['id', 'token', 'text', 'status', 'owner', 'due_date'])
      && symptomBoundedString(action.id, 200)
      && Boolean(action.id)
      && symptomBoundedString(action.token, 200)
      && Boolean(action.token)
      && symptomBoundedString(action.text, 1000)
      && Boolean(action.text.trim())
      && SYMPTOM_ACTION_STATUSES.has(action.status)
      && (!eligible || ['open', 'in_progress'].includes(action.status))
      && symptomBoundedString(action.owner, 200, true)
      && symptomBoundedString(action.due_date, 10, true);
  }

  function symptomObservationIsValid(observation, refs) {
    if (
      !symptomHasExactKeys(observation, [
        'id',
        'token',
        'date',
        'symptom',
        'severity',
        'note',
        'related_treatment',
        'provenance',
      ])
      || !symptomBoundedString(observation.id, 200)
      || !observation.id
      || !symptomBoundedString(observation.token, 200)
      || !observation.token
      || !symptomDateAuthorityIsValid(observation.date)
      || !symptomBoundedString(observation.symptom, 1000, true)
      || (
        observation.severity != null
        && (
          !Number.isSafeInteger(observation.severity)
          || observation.severity < 1
          || observation.severity > 5
        )
      )
      || !symptomBoundedString(observation.note, 50000, true)
      || !symptomBoundedString(observation.related_treatment, 5000, true)
      || !symptomHasExactKeys(observation.provenance, [
        'status',
        'label',
        'source_url',
        'evidence_url',
      ])
      || !SYMPTOM_OBSERVATION_PROVENANCE.has(observation.provenance.status)
      || !symptomBoundedString(observation.provenance.label, 200)
      || !observation.provenance.label
      || !symptomBoundedString(observation.provenance.source_url, 220, true)
      || !symptomBoundedString(observation.provenance.evidence_url, 220, true)
    ) return false;
    const source = observation.provenance.source_url == null
      ? null
      : symptomObservationUrlParts(observation.provenance.source_url, 'source');
    const evidence = observation.provenance.evidence_url == null
      ? null
      : symptomObservationUrlParts(observation.provenance.evidence_url, 'evidence');
    if (
      (observation.provenance.source_url != null && !source)
      || (observation.provenance.evidence_url != null && !evidence)
      || (evidence && (!source || evidence.recordRef !== source.recordRef))
      || (source && refs.has(source.recordRef))
    ) return false;
    if (source) refs.add(source.recordRef);
    return true;
  }

  function symptomEpisodeIsValid(episode) {
    if (
      !symptomHasExactKeys(episode, [
        'id',
        'token',
        'status',
        'symptom_text',
        'severity',
        'reported_subject',
        'timing_text',
        'frequency_text',
        'triggers_text',
        'notes',
        'onset',
        'resolution',
        'provenance',
        'follow_up',
        'created_at',
        'updated_at',
      ])
      || !/^syme_[0-9a-f]{32}$/.test(episode.id)
      || !symptomBoundedString(episode.token, 200)
      || !episode.token
      || !['current', 'resolved'].includes(episode.status)
      || !symptomBoundedString(episode.symptom_text, 1000)
      || !episode.symptom_text.trim()
      || !symptomHasExactKeys(episode.severity, ['level', 'detail', 'authority'])
      || (
        episode.severity.level != null
        && !SYMPTOM_SEVERITIES.has(episode.severity.level)
      )
      || !symptomBoundedString(episode.severity.detail, 500, true)
      || episode.severity.authority !== 'caregiver_entered_unverified'
      || !SYMPTOM_REPORTED_SUBJECTS.has(episode.reported_subject)
      || !symptomBoundedString(episode.timing_text, 2000, true)
      || !symptomBoundedString(episode.frequency_text, 2000, true)
      || !symptomBoundedString(episode.triggers_text, 2000, true)
      || !symptomBoundedString(episode.notes, 10000, true)
      || !symptomDateAuthorityIsValid(episode.onset, true)
      || !symptomHasExactKeys(episode.provenance, ['status', 'label'])
      || episode.provenance.status !== 'caregiver_entered_unverified'
      || episode.provenance.label !== 'Caregiver-entered · unverified'
      || !symptomBoundedString(episode.created_at, 64)
      || !symptomBoundedString(episode.updated_at, 64)
      || (episode.follow_up != null && !symptomActionIsValid(episode.follow_up))
    ) return false;
    if (episode.status === 'current') return episode.resolution === null;
    return symptomHasExactKeys(episode.resolution, [
      'value',
      'precision',
      'kind',
      'recorded_at',
    ])
      && symptomDateAuthorityIsValid({
        value: episode.resolution.value,
        precision: episode.resolution.precision,
        kind: episode.resolution.kind,
      }, true)
      && symptomBoundedString(episode.resolution.recorded_at, 64);
  }

  function symptomProjectionPayloadIsValid(data) {
    if (
      !symptomHasExactKeys(data, [
        'profile_revision',
        'workflow_revision',
        'projection_token',
        'observation_count',
        'episode_count',
        'observations',
        'episodes',
        'eligible_actions',
        'safety_guidance',
      ])
      || !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || !symptomBoundedString(data.projection_token, 200)
      || !data.projection_token
      || !Number.isSafeInteger(data.observation_count)
      || data.observation_count < 0
      || data.observation_count > SYMPTOM_MAX_OBSERVATIONS
      || !Number.isSafeInteger(data.episode_count)
      || data.episode_count < 0
      || data.episode_count > SYMPTOM_MAX_EPISODES
      || !Array.isArray(data.observations)
      || data.observations.length !== data.observation_count
      || !Array.isArray(data.episodes)
      || data.episodes.length !== data.episode_count
      || !Array.isArray(data.eligible_actions)
      || data.eligible_actions.length > SYMPTOM_MAX_ACTIONS
      || !symptomHasExactKeys(data.safety_guidance, ['kind', 'text'])
      || data.safety_guidance.kind !== 'fixed_non_diagnostic'
      || data.safety_guidance.text !== SYMPTOM_SAFETY_GUIDANCE
    ) return false;

    const observationIds = new Set();
    const observationTokens = new Set();
    const episodeIds = new Set();
    const episodeTokens = new Set();
    const actionIds = new Set();
    const actionTokens = new Set();
    const linkedActionIds = new Set();
    const refs = new Set();
    for (const observation of data.observations) {
      if (
        !symptomObservationIsValid(observation, refs)
        || observationIds.has(observation.id)
        || observationTokens.has(observation.token)
      ) return false;
      observationIds.add(observation.id);
      observationTokens.add(observation.token);
    }
    for (const episode of data.episodes) {
      if (
        !symptomEpisodeIsValid(episode)
        || episodeIds.has(episode.id)
        || episodeTokens.has(episode.token)
      ) return false;
      episodeIds.add(episode.id);
      episodeTokens.add(episode.token);
      if (episode.follow_up) {
        if (
          linkedActionIds.has(episode.follow_up.id)
          || actionIds.has(episode.follow_up.id)
          || actionTokens.has(episode.follow_up.token)
        ) return false;
        linkedActionIds.add(episode.follow_up.id);
        actionIds.add(episode.follow_up.id);
        actionTokens.add(episode.follow_up.token);
      }
    }
    for (const action of data.eligible_actions) {
      if (
        !symptomActionIsValid(action, true)
        || actionIds.has(action.id)
        || actionTokens.has(action.token)
      ) return false;
      actionIds.add(action.id);
      actionTokens.add(action.token);
    }
    return JSON.stringify(data).length <= SYMPTOM_MAX_AUTHORITY_CHARS;
  }

  function symptomMutationPayloadIsValid(data) {
    if (
      !symptomHasExactKeys(
        data,
        ['episode', 'follow_up', 'workflow_revision', 'profile_revision'],
        ['idempotent_replay'],
      )
      || !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || !symptomEpisodeIsValid(data.episode)
      || (data.follow_up != null && !symptomActionIsValid(data.follow_up))
      || (
        data.follow_up == null
          ? data.episode.follow_up !== null
          : (
            data.episode.follow_up == null
            || data.follow_up.id !== data.episode.follow_up.id
            || data.follow_up.token !== data.episode.follow_up.token
          )
      )
      || (
        Object.prototype.hasOwnProperty.call(data, 'idempotent_replay')
        && data.idempotent_replay !== true
      )
    ) return false;
    return true;
  }

  function newSymptomResponseOwner(projection, ownerPhiEpoch = phiEpoch) {
    return {
      requestPhiEpoch: ownerPhiEpoch,
      loadEpoch: symptomLoadEpoch,
      profileRevision: projection.profile_revision,
      workflowRevision: projection.workflow_revision,
      projectionToken: projection.projection_token,
      observationTokens: new Map(
        projection.observations.map(observation => [observation.id, observation.token]),
      ),
      episodeTokens: new Map(
        projection.episodes.map(episode => [episode.id, episode.token]),
      ),
      eligibleActionTokens: new Map(
        projection.eligible_actions.map(action => [action.id, action.token]),
      ),
    };
  }

  function symptomResponseOwnerIsCurrent(owner = symptomResponseOwner) {
    if (
      !owner
      || owner !== symptomResponseOwner
      || owner.requestPhiEpoch !== phiEpoch
      || owner.loadEpoch !== symptomLoadEpoch
      || !symptomProjection
      || owner.projectionToken !== symptomProjection.projection_token
      || owner.profileRevision !== symptomProjection.profile_revision
      || owner.workflowRevision !== symptomProjection.workflow_revision
      || owner.observationTokens.size !== symptomProjection.observations.length
      || owner.episodeTokens.size !== symptomProjection.episodes.length
      || owner.eligibleActionTokens.size !== symptomProjection.eligible_actions.length
      || symptomProjection.observations.some(
        observation => owner.observationTokens.get(observation.id) !== observation.token,
      )
      || symptomProjection.episodes.some(
        episode => owner.episodeTokens.get(episode.id) !== episode.token,
      )
      || symptomProjection.eligible_actions.some(
        action => owner.eligibleActionTokens.get(action.id) !== action.token,
      )
    ) return false;
    if (symptomProjectionState === 'stale') return true;
    const currentProfile = normalizedRevision(latestProfileRevision);
    const currentWorkflow = normalizedRevision(workflowRevision);
    return (
      (!Number.isSafeInteger(currentProfile) || currentProfile === owner.profileRevision)
      && (!Number.isSafeInteger(currentWorkflow) || currentWorkflow === owner.workflowRevision)
    );
  }

  function symptomElement(tag, className = '', text = null) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
  }

  function symptomScalar(value) {
    if (value == null) return 'Not recorded';
    return value === '' ? 'Empty string recorded' : String(value);
  }

  function symptomDatePresentation(date, label) {
    const kind = {
      caregiver_entered: `${label} entered by caregiver`,
      clinical: 'Recorded symptom-event date',
      legacy_unknown: 'Legacy date; symptom-event authority not confirmed',
      unknown: `${label} authority unknown`,
    }[date.kind] || `${label} authority unknown`;
    return `${symptomScalar(date.value)} · ${date.precision} precision · ${kind}`;
  }

  function symptomSeverityPresentation(episode) {
    const label = {
      mild: 'Mild',
      moderate: 'Moderate',
      severe: 'Severe',
    }[episode.severity.level] || 'Not recorded';
    return episode.severity.detail == null
      ? label
      : `${label} · ${symptomScalar(episode.severity.detail)}`;
  }

  function symptomReportedSubjectLabel(value) {
    return {
      patient: 'Patient',
      caregiver: 'Caregiver',
      unspecified: 'Not specified',
    }[value];
  }

  function setSymptomFreshness(state, text) {
    for (const id of ['today-symptom-freshness', 'patient-symptom-freshness']) {
      const node = document.getElementById(id);
      if (!node) continue;
      node.className = `symptom-freshness ${safeClassToken(state, 'error')}`;
      node.textContent = text;
    }
  }

  function setSymptomStatus(message, state = '', retry = false) {
    for (const id of ['today-symptom-status', 'patient-symptom-status']) {
      const node = document.getElementById(id);
      if (!node) continue;
      node.className = `symptom-status${state ? ` ${safeClassToken(state)}` : ''}`;
      node.textContent = message || '';
    }
    const retryNode = document.getElementById('symptom-retry');
    if (retryNode) retryNode.hidden = !retry;
    const refresh = document.getElementById('symptom-refresh-button');
    if (refresh) refresh.disabled = symptomRequestController !== null;
  }

  function symptomEpisodeById(episodeId) {
    return symptomProjection?.episodes.find(episode => episode.id === episodeId) || null;
  }

  function symptomActionById(actionId) {
    if (!actionId || !symptomProjection) return null;
    const eligible = symptomProjection.eligible_actions.find(action => action.id === actionId);
    if (eligible) return eligible;
    for (const episode of symptomProjection.episodes) {
      if (episode.follow_up?.id === actionId) return episode.follow_up;
    }
    return null;
  }

  function symptomAppendFact(parent, label, value) {
    const item = symptomElement('div', 'symptom-fact');
    item.append(
      symptomElement('dt', '', label),
      symptomElement('dd', value == null || value === '' ? 'symptom-missing' : '', symptomScalar(value)),
    );
    parent.append(item);
  }

  function symptomEpisodeCard(episode, compact = false) {
    const card = symptomElement('article', `symptom-episode-card${compact ? ' compact' : ''}`);
    const heading = symptomElement('div', 'symptom-episode-heading');
    heading.append(
      symptomElement('span', `symptom-lifecycle ${episode.status}`, episode.status === 'current'
        ? 'Current episode'
        : 'Resolved episode'),
      symptomElement('span', 'symptom-provenance', episode.provenance.label),
    );
    const title = symptomElement('h3', '', episode.symptom_text);
    const summary = symptomElement('dl', 'symptom-episode-summary');
    symptomAppendFact(summary, 'Severity entered by caregiver', symptomSeverityPresentation(episode));
    symptomAppendFact(
      summary,
      'Reported subject entered by caregiver',
      symptomReportedSubjectLabel(episode.reported_subject),
    );
    symptomAppendFact(summary, 'Onset date authority', symptomDatePresentation(episode.onset, 'Onset date'));
    if (episode.resolution) {
      symptomAppendFact(
        summary,
        'Resolution date authority',
        symptomDatePresentation(episode.resolution, 'Resolution date'),
      );
    }
    if (!compact) {
      symptomAppendFact(summary, 'Timing', episode.timing_text);
      symptomAppendFact(summary, 'Frequency', episode.frequency_text);
      symptomAppendFact(summary, 'Triggers', episode.triggers_text);
      symptomAppendFact(summary, 'Notes', episode.notes);
    }
    card.append(heading, title, summary);
    if (episode.follow_up) {
      const followUp = symptomElement('div', 'symptom-linked-follow-up');
      followUp.append(
        symptomElement('strong', '', 'Linked caregiver follow-up'),
        symptomElement('p', '', episode.follow_up.text),
        symptomElement(
          'span',
          '',
          `${episode.follow_up.status} · ${symptomScalar(episode.follow_up.owner)} · due ${symptomScalar(episode.follow_up.due_date)}`,
        ),
      );
      card.append(followUp);
    }
    if (!compact) {
      const actions = symptomElement('div', 'symptom-episode-actions');
      const edit = symptomElement('button', 'button secondary', 'Edit episode facts');
      edit.type = 'button';
      edit.disabled = symptomProjectionState !== 'current';
      edit.addEventListener('click', () => openSymptomEditDialog(edit, episode.id));
      actions.append(edit);
      if (episode.status === 'current') {
        const resolve = symptomElement('button', 'button secondary', 'Resolve episode');
        resolve.type = 'button';
        resolve.disabled = symptomProjectionState !== 'current';
        resolve.addEventListener('click', () => openSymptomResolveDialog(resolve, episode.id));
        actions.append(resolve);
      }
      const followUp = symptomElement('button', 'button secondary', episode.follow_up
        ? 'Review linked follow-up'
        : 'Add follow-up');
      followUp.type = 'button';
      followUp.disabled = symptomProjectionState !== 'current';
      followUp.addEventListener('click', () => openSymptomFollowUpDialog(followUp, episode.id));
      actions.append(followUp);
      card.append(actions);
    }
    return card;
  }

  function symptomObservationSourceDetails(observation) {
    const details = symptomElement('details', 'symptom-source-details');
    details.append(symptomElement('summary', '', 'Source details'));
    const body = symptomElement('div');
    body.append(
      symptomElement('p', '', `${observation.provenance.label} · ${observation.provenance.status}`),
      symptomElement(
        'p',
        '',
        `Source document date (not symptom chronology): ${
          symptomScalar(observation.date.source_document_date)
        } · ${observation.date.source_document_date_precision} precision`,
      ),
    );
    const links = symptomElement('div', 'symptom-source-actions');
    const evidenceUrl = safeSymptomObservationUrl(
      observation.provenance.evidence_url,
      'evidence',
    );
    const sourceUrl = safeSymptomObservationUrl(observation.provenance.source_url, 'source');
    if (evidenceUrl) {
      const link = symptomElement('a', '', 'Open exact span');
      link.href = evidenceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      links.append(link);
    }
    if (sourceUrl) {
      const link = symptomElement('a', '', 'Open source');
      link.href = sourceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      links.append(link);
    }
    if (!links.childElementCount) {
      links.append(symptomElement('span', 'symptom-missing', 'No source link supplied'));
    }
    body.append(links);
    details.append(body);
    return details;
  }

  function symptomObservationRow(observation) {
    const row = symptomElement('tr');
    const symptomCell = symptomElement('td');
    symptomCell.append(symptomElement(
      'strong',
      observation.symptom == null || observation.symptom === '' ? 'symptom-missing' : '',
      symptomScalar(observation.symptom),
    ));
    const severityCell = symptomElement(
      'td',
      observation.severity == null ? 'symptom-missing' : '',
      symptomScalar(observation.severity),
    );
    const dateCell = symptomElement('td');
    dateCell.append(symptomElement(
      'span',
      '',
      symptomDatePresentation(observation.date, 'Symptom date'),
    ));
    const contextCell = symptomElement('td');
    const context = symptomElement('dl', 'symptom-observation-context');
    symptomAppendFact(context, 'Note', observation.note);
    symptomAppendFact(context, 'Related treatment wording', observation.related_treatment);
    contextCell.append(context);
    const sourceCell = symptomElement('td');
    sourceCell.append(
      symptomElement('strong', '', observation.provenance.label),
      symptomObservationSourceDetails(observation),
    );
    row.append(symptomCell, severityCell, dateCell, contextCell, sourceCell);
    return row;
  }

  function updateSymptomControls() {
    const mutable = (
      ['current', 'empty'].includes(symptomProjectionState)
      && symptomResponseOwnerIsCurrent()
      && !symptomMutationPending
      && !pendingSymptomCompletion
    );
    for (const id of ['today-symptom-add', 'patient-symptom-add']) {
      const button = document.getElementById(id);
      if (button) button.disabled = !mutable;
    }
    document.querySelectorAll(
      '#symptom-workspace .symptom-episode-actions button, #symptom-dialog button, '
      + '#symptom-dialog input, #symptom-dialog textarea, #symptom-dialog select',
    ).forEach(control => {
      if (symptomMutationPending) {
        if (!('symptomWasDisabled' in control.dataset)) {
          control.dataset.symptomWasDisabled = String(control.disabled);
        }
        control.disabled = true;
      } else if ('symptomWasDisabled' in control.dataset) {
        control.disabled = control.dataset.symptomWasDisabled === 'true';
        delete control.dataset.symptomWasDisabled;
      }
    });
    if (!symptomMutationPending) updateSymptomFormValidity();
  }

  function renderSymptomProjection(owner = symptomResponseOwner) {
    if (!symptomResponseOwnerIsCurrent(owner)) return false;
    const current = symptomProjection.episodes.filter(episode => episode.status === 'current');
    const resolved = symptomProjection.episodes.filter(episode => episode.status === 'resolved');
    const today = document.getElementById('today-symptom-list');
    const currentList = document.getElementById('patient-current-symptom-list');
    const resolvedList = document.getElementById('patient-resolved-symptom-list');
    const observations = document.getElementById('symptom-observation-table-body');
    if (today) {
      today.replaceChildren(...(
        current.length
          ? current.map(episode => symptomEpisodeCard(episode, true))
          : [symptomElement('div', 'empty-state', 'No current symptom episodes are recorded.')]
      ));
    }
    if (currentList) {
      currentList.replaceChildren(...(
        current.length
          ? current.map(episode => symptomEpisodeCard(episode))
          : [symptomElement('div', 'empty-state', 'No current symptom episodes are recorded.')]
      ));
    }
    if (resolvedList) {
      resolvedList.replaceChildren(...(
        resolved.length
          ? resolved.map(episode => symptomEpisodeCard(episode))
          : [symptomElement('div', 'empty-state', 'No resolved symptom episodes are recorded.')]
      ));
    }
    if (observations) {
      if (symptomProjection.observations.length) {
        observations.replaceChildren(...symptomProjection.observations.map(symptomObservationRow));
      } else {
        const row = symptomElement('tr');
        const cell = symptomElement('td');
        cell.colSpan = 5;
        cell.append(symptomElement('div', 'empty-state', 'No source observations are recorded.'));
        row.append(cell);
        observations.replaceChildren(row);
      }
    }
    const counts = {
      current: current.length,
      resolved: resolved.length,
      observations: symptomProjection.observations.length,
    };
    Object.entries(counts).forEach(([name, count]) => {
      const node = document.getElementById(`symptom-count-${name}`);
      if (node) node.textContent = String(count);
    });
    if (symptomProjectionState === 'stale') {
      setSymptomFreshness('stale', 'Stale snapshot');
      setSymptomStatus(
        'Stale snapshot · read-only until the authoritative symptom record reloads.',
        'stale',
        true,
      );
    } else {
      symptomProjectionState = symptomProjection.episodes.length
        || symptomProjection.observations.length
        ? 'current'
        : 'empty';
      setSymptomFreshness('current', symptomProjectionState === 'empty' ? 'Current · empty' : 'Current');
      setSymptomStatus(
        `Authoritative symptom record loaded · patient revision ${
          symptomProjection.profile_revision
        } · workflow revision ${symptomProjection.workflow_revision}.`,
        'current',
        false,
      );
    }
    selectSymptomTab(symptomActiveTab, false);
    updateSymptomControls();
    return true;
  }

  function renderSymptomUnavailable(message, state, statusLabel, retry = true) {
    const today = document.getElementById('today-symptom-list');
    const current = document.getElementById('patient-current-symptom-list');
    const resolved = document.getElementById('patient-resolved-symptom-list');
    if (today) today.replaceChildren(symptomElement('div', 'empty-state', message));
    if (current) current.replaceChildren(symptomElement('div', 'empty-state', message));
    if (resolved) resolved.replaceChildren();
    const table = document.getElementById('symptom-observation-table-body');
    if (table) {
      const row = symptomElement('tr');
      const cell = symptomElement('td');
      cell.colSpan = 5;
      cell.append(symptomElement('div', 'empty-state', message));
      row.append(cell);
      table.replaceChildren(row);
    }
    for (const name of ['current', 'resolved', 'observations']) {
      const count = document.getElementById(`symptom-count-${name}`);
      if (count) count.textContent = '0';
    }
    setSymptomFreshness(state, statusLabel);
    setSymptomStatus(message, state, retry);
    updateSymptomControls();
  }

  function symptomFocusFallback() {
    const surfaces = [
      document.getElementById('symptom-workspace'),
      document.getElementById('symptom-today-card'),
      document.getElementById('symptom-dialog'),
    ];
    if (!surfaces.some(surface => surface?.contains(document.activeElement))) return;
    document.activeElement?.blur();
    const target = activeView === 'patient'
      ? document.getElementById('nav-patient')
      : document.getElementById('nav-today');
    target?.focus();
    lastDialogTrigger = null;
  }

  function abortSymptomRequest() {
    const controller = symptomRequestController;
    symptomRequestController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function abortSymptomMutation() {
    const controller = symptomMutationController;
    symptomMutationController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function clearSymptomRetry() {
    if (pendingSymptomIntent) pendingSymptomIntent.bodyText = '';
    if (activeSymptomIntent && activeSymptomIntent !== pendingSymptomIntent) {
      activeSymptomIntent.bodyText = '';
    }
    pendingSymptomIntent = null;
    pendingSymptomCompletion = null;
    const retry = document.getElementById('symptom-dialog-retry');
    if (retry) retry.hidden = true;
  }

  function scrubSymptomDialog(options = {}) {
    const dialog = document.getElementById('symptom-dialog');
    const wasActive = symptomDialogOpen || activeDialogSurface === dialog;
    symptomDialogOpen = false;
    symptomDialogMode = null;
    selectedSymptomEpisodeId = null;
    selectedSymptomEpisodeToken = null;
    selectedSymptomActionId = null;
    selectedSymptomActionToken = null;
    symptomSelectionEpoch += 1;
    symptomDialogEpoch += 1;
    symptomDrafts = new Map();
    clearSymptomRetry();
    for (const id of [
      'symptom-text',
      'symptom-severity-detail',
      'symptom-onset-date',
      'symptom-edit-resolved-date',
      'symptom-timing',
      'symptom-frequency',
      'symptom-triggers',
      'symptom-notes',
      'symptom-resolved-date',
      'symptom-create-follow-up-text',
      'symptom-create-follow-up-owner',
      'symptom-create-follow-up-due',
      'symptom-follow-up-text',
      'symptom-follow-up-owner',
      'symptom-follow-up-due',
    ]) {
      const control = document.getElementById(id);
      if (control) control.value = '';
    }
    for (const id of [
      'symptom-create-existing-action',
      'symptom-existing-action',
    ]) {
      const select = document.getElementById(id);
      if (select) {
        select.replaceChildren();
        select.value = '';
      }
    }
    const severity = document.getElementById('symptom-severity');
    if (severity) severity.value = '';
    const subject = document.getElementById('symptom-reported-subject');
    if (subject) subject.value = 'unspecified';
    const confirm = document.getElementById('symptom-resolve-confirm');
    if (confirm) confirm.checked = false;
    for (const id of [
      'symptom-resolve-copy',
      'symptom-follow-up-copy',
      'symptom-linked-action-copy',
      'symptom-dialog-status',
      'symptom-details-error',
      'symptom-resolve-error',
      'symptom-follow-up-error',
    ]) {
      const node = document.getElementById(id);
      if (node) node.textContent = '';
    }
    const overlay = document.getElementById('symptom-dialog-overlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    if (wasActive) {
      document.activeElement?.blur();
      if (activeDialogSurface === dialog) deactivateDialog(dialog, false);
      lastDialogTrigger = null;
      if (options.moveFocus !== false) {
        document.getElementById(`nav-${activeView}`)?.focus();
      }
    }
  }

  function clearSymptomProjection(options = {}) {
    symptomFocusFallback();
    symptomLoadEpoch += 1;
    symptomMutationEpoch += 1;
    abortSymptomRequest();
    abortSymptomMutation();
    if (activeSymptomIntent) activeSymptomIntent.bodyText = '';
    activeSymptomIntent = null;
    symptomMutationOwner = null;
    symptomMutationPending = false;
    scrubSymptomDialog({ moveFocus: false });
    symptomProjection = null;
    symptomResponseOwner = null;
    symptomNetworkAmbiguous = false;
    symptomProjectionState = options.state || 'error';
    renderSymptomUnavailable(
      options.message || 'Symptom records could not be loaded.',
      symptomProjectionState,
      options.statusLabel || 'Unavailable',
      options.retry !== false,
    );
  }

  function markSymptomProjectionStale(message, options = {}) {
    if (symptomDialogOpen) captureSymptomDraft();
    if (options.abortRequest !== false) {
      symptomLoadEpoch += 1;
      abortSymptomRequest();
    }
    if (options.preserveMutation !== true) abortSymptomMutation();
    symptomProjectionState = 'stale';
    if (!symptomProjection) {
      renderSymptomUnavailable(
        message || 'Symptoms are unavailable until an authoritative reload succeeds.',
        'stale',
        'Not current',
        true,
      );
      return;
    }
    symptomResponseOwner = newSymptomResponseOwner(
      symptomProjection,
      options.ownerPhiEpoch ?? phiEpoch,
    );
    renderSymptomProjection(symptomResponseOwner);
    setSymptomStatus(
      message || 'Stale snapshot · read-only until the authoritative symptom record reloads.',
      'stale',
      true,
    );
  }

  function renderSymptomLoading() {
    if (symptomProjection) {
      symptomProjectionState = 'stale';
      setSymptomFreshness('loading', 'Checking…');
      setSymptomStatus(
        'Checking the authoritative symptom record. The displayed snapshot is read-only.',
        'loading',
        false,
      );
      updateSymptomControls();
      return;
    }
    symptomProjectionState = 'loading';
    renderSymptomUnavailable(
      'Loading the complete authoritative symptom record…',
      'loading',
      'Loading…',
      false,
    );
  }

  function symptomTransportRequestIsCurrent(request, acceptedPhiEpoch = null) {
    const ownerPhiEpoch = acceptedPhiEpoch ?? request.requestPhiEpoch;
    return Boolean(
      request
      && request.controller === symptomRequestController
      && !request.controller.signal.aborted
      && request.loadEpoch === symptomLoadEpoch
      && ownerPhiEpoch === phiEpoch
    );
  }

  function symptomAuthorityMatchesKnown() {
    if (!symptomProjection || !symptomResponseOwnerIsCurrent()) return false;
    const currentProfile = normalizedRevision(latestProfileRevision);
    const currentWorkflow = normalizedRevision(workflowRevision);
    return (
      (!Number.isSafeInteger(currentProfile)
        || symptomProjection.profile_revision === currentProfile)
      && (!Number.isSafeInteger(currentWorkflow)
        || symptomProjection.workflow_revision === currentWorkflow)
    );
  }

  function ensureSymptomEpisodes(options = {}) {
    const current = (
      symptomProjection
      && ['current', 'empty'].includes(symptomProjectionState)
      && !symptomNetworkAmbiguous
      && symptomAuthorityMatchesKnown()
    );
    if (!options.force && current) return Promise.resolve(symptomProjection);
    if (!options.force && symptomRequestController) return Promise.resolve(null);
    return loadSymptomEpisodes(options);
  }

  function symptomSelectionSurvives(projection) {
    if (!symptomDialogOpen || symptomDialogMode === 'add') return true;
    const episode = projection.episodes.find(
      item => item.id === selectedSymptomEpisodeId && item.token === selectedSymptomEpisodeToken,
    );
    if (!episode) return false;
    if (symptomDialogMode === 'resolve' && episode.status !== 'current') return false;
    if (selectedSymptomActionId) {
      const actions = [
        ...projection.eligible_actions,
        ...projection.episodes.map(item => item.follow_up).filter(Boolean),
      ];
      if (!actions.some(
        action => (
          action.id === selectedSymptomActionId
          && action.token === selectedSymptomActionToken
        ),
      )) return false;
    }
    return true;
  }

  async function loadSymptomEpisodes(options = {}) {
    if (!options.force && symptomRequestController) return null;
    const previousController = symptomRequestController;
    const controller = new AbortController();
    const request = {
      ...capturePatientRequest(),
      loadEpoch: ++symptomLoadEpoch,
      controller,
    };
    symptomRequestController = controller;
    if (previousController && !previousController.signal.aborted) previousController.abort();
    renderSymptomLoading();
    try {
      const response = await fetch('/api/patient/symptom-episodes', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      const requestIsCurrent = () => symptomTransportRequestIsCurrent(request);
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, () => false);
      if (!requestIsCurrent()) return null;
      if (!symptomProjectionPayloadIsValid(data)) {
        const invalid = new Error('Symptom records could not be verified safely.');
        invalid.status = 422;
        throw invalid;
      }
      const currentProfile = normalizedRevision(latestProfileRevision);
      const currentWorkflow = normalizedRevision(workflowRevision);
      if (
        (Number.isSafeInteger(currentProfile) && data.profile_revision < currentProfile)
        || (Number.isSafeInteger(currentWorkflow) && data.workflow_revision < currentWorkflow)
      ) {
        markSymptomProjectionStale(
          'A newer patient or workflow revision is available. Symptoms remain read-only while reloading.',
          { abortRequest: false },
        );
        return null;
      }
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        symptomProjection: true,
      });
      if (!authority.accepted) return null;
      request.acceptedPhiEpoch = authority.requestPhiEpoch;
      if (!symptomTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;
      if (!symptomSelectionSurvives(data)) {
        scrubSymptomDialog({ moveFocus: false });
      }
      symptomProjection = data;
      symptomNetworkAmbiguous = false;
      symptomProjectionState = data.episodes.length || data.observations.length
        ? 'current'
        : 'empty';
      symptomResponseOwner = newSymptomResponseOwner(data, request.acceptedPhiEpoch);
      if (!symptomTransportRequestIsCurrent(request, request.acceptedPhiEpoch)) return null;
      if (!renderSymptomProjection(symptomResponseOwner)) return null;
      if (symptomDialogOpen) renderSymptomDialog();
      reportLoadSuccess('symptom-episodes');
      return data;
    } catch (error) {
      const acceptedPhiEpoch = request.acceptedPhiEpoch ?? null;
      if (
        error?.name === 'AbortError'
        || !symptomTransportRequestIsCurrent(request, acceptedPhiEpoch)
      ) return null;
      if (error?.status === 401 || error?.status === 403) {
        const safeError = new Error('Symptom authorization is unavailable.');
        safeError.status = error.status;
        reportLoadError('symptom-episodes', safeError);
        if (symptomTransportRequestIsCurrent(request, acceptedPhiEpoch)) {
          evictClientPhi(safeError);
        }
        return null;
      }
      if (error instanceof TypeError) {
        symptomNetworkAmbiguous = true;
        markSymptomProjectionStale(
          symptomProjection
            ? 'Symptom transport is uncertain. The last accepted snapshot is stale and read-only.'
            : 'The symptom endpoint could not be reached and no prior snapshot is available.',
          { abortRequest: false, preserveMutation: options.preserveMutation === true },
        );
        reportLoadError(
          'symptom-episodes',
          new TypeError('The symptom endpoint could not be reached.'),
        );
        return null;
      }
      const corrupt = error?.status === 422;
      clearSymptomProjection({
        state: corrupt ? 'corrupt' : 'error',
        statusLabel: corrupt ? 'Record unavailable' : 'Load failed',
        message: corrupt
          ? 'Symptom records are unavailable because the authoritative response could not be verified safely.'
          : 'Symptom records could not be loaded. No prior symptom facts remain in this view.',
      });
      const safeError = new Error(
        corrupt
          ? 'Symptom records could not be verified safely.'
          : 'Symptom records could not be loaded.',
      );
      safeError.status = error?.status;
      reportLoadError('symptom-episodes', safeError);
      return null;
    } finally {
      if (
        symptomRequestController === controller
        && request.loadEpoch === symptomLoadEpoch
      ) {
        symptomRequestController = null;
        const refresh = document.getElementById('symptom-refresh-button');
        if (refresh) refresh.disabled = false;
      }
    }
  }

  function selectSymptomTab(name, moveFocus = true) {
    if (!['current', 'resolved', 'observations'].includes(name)) return false;
    symptomActiveTab = name;
    for (const tabName of ['current', 'resolved', 'observations']) {
      const selected = tabName === name;
      const tab = document.getElementById(`symptom-tab-${tabName}`);
      const panel = document.getElementById(`symptom-panel-${tabName}`);
      tab?.classList.toggle('active', selected);
      tab?.setAttribute('aria-selected', String(selected));
      if (tab) tab.tabIndex = selected ? 0 : -1;
      if (panel) panel.hidden = !selected;
    }
    if (moveFocus) document.getElementById(`symptom-tab-${name}`)?.focus();
    return true;
  }

  function handleSymptomTabKeydown(event) {
    const names = ['current', 'resolved', 'observations'];
    const tabs = names.map(name => document.getElementById(`symptom-tab-${name}`));
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      next = (current - 1 + tabs.length) % tabs.length;
    } else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectSymptomTab(names[next]);
  }

  function openPatientSymptoms() {
    switchView('patient', document.getElementById('nav-patient'));
    selectSymptomTab('current', false);
    document.getElementById('symptoms-heading')?.focus();
  }

  function symptomDraftKey() {
    return `${symptomDialogMode || 'closed'}:${selectedSymptomEpisodeId || 'new'}`;
  }

  function captureSymptomDraft() {
    if (!symptomDialogOpen || !symptomDialogMode) return;
    if (symptomDialogMode === 'add' || symptomDialogMode === 'edit') {
      symptomDrafts.set(symptomDraftKey(), {
        text: document.getElementById('symptom-text')?.value || '',
        severity: document.getElementById('symptom-severity')?.value || '',
        severityDetail: document.getElementById('symptom-severity-detail')?.value || '',
        subject: document.getElementById('symptom-reported-subject')?.value || 'unspecified',
        onsetDate: document.getElementById('symptom-onset-date')?.value || '',
        resolvedDate: document.getElementById('symptom-edit-resolved-date')?.value || '',
        timing: document.getElementById('symptom-timing')?.value || '',
        frequency: document.getElementById('symptom-frequency')?.value || '',
        triggers: document.getElementById('symptom-triggers')?.value || '',
        notes: document.getElementById('symptom-notes')?.value || '',
        followUpMode: document.querySelector(
          'input[name="symptom-create-follow-up-mode"]:checked',
        )?.value || 'none',
        actionId: document.getElementById('symptom-create-existing-action')?.value || '',
        followUpText: document.getElementById('symptom-create-follow-up-text')?.value || '',
        followUpOwner: document.getElementById('symptom-create-follow-up-owner')?.value || '',
        followUpDue: document.getElementById('symptom-create-follow-up-due')?.value || '',
      });
    } else if (symptomDialogMode === 'resolve') {
      symptomDrafts.set(symptomDraftKey(), {
        resolvedDate: document.getElementById('symptom-resolved-date')?.value || '',
        confirmed: document.getElementById('symptom-resolve-confirm')?.checked === true,
      });
    } else if (symptomDialogMode === 'follow-up') {
      symptomDrafts.set(symptomDraftKey(), {
        mode: document.querySelector('input[name="symptom-follow-up-mode"]:checked')?.value
          || 'existing',
        actionId: document.getElementById('symptom-existing-action')?.value || '',
        text: document.getElementById('symptom-follow-up-text')?.value || '',
        owner: document.getElementById('symptom-follow-up-owner')?.value || '',
        due: document.getElementById('symptom-follow-up-due')?.value || '',
      });
    }
  }

  function setSymptomDialogStatus(message, tone = '') {
    const node = document.getElementById('symptom-dialog-status');
    if (!node) return;
    node.className = `follow-up-dialog-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
    node.textContent = message || '';
  }

  function populateSymptomActionSelect(selectId, preferredId = '') {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.replaceChildren();
    if (!symptomProjection?.eligible_actions.length) {
      const option = symptomElement('option', '', 'No eligible actions available');
      option.value = '';
      select.append(option);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    for (const action of symptomProjection.eligible_actions) {
      const option = symptomElement(
        'option',
        '',
        `${action.text} · ${action.status} · ${symptomScalar(action.owner)} · due ${symptomScalar(action.due_date)}`,
      );
      option.value = action.id;
      select.append(option);
    }
    select.value = symptomProjection.eligible_actions.some(action => action.id === preferredId)
      ? preferredId
      : symptomProjection.eligible_actions[0].id;
  }

  function restoreSymptomDetailsForm(episode = null) {
    const draft = symptomDrafts.get(symptomDraftKey());
    document.getElementById('symptom-text').value = draft?.text ?? episode?.symptom_text ?? '';
    document.getElementById('symptom-severity').value =
      draft?.severity ?? episode?.severity.level ?? '';
    document.getElementById('symptom-severity-detail').value =
      draft?.severityDetail ?? episode?.severity.detail ?? '';
    document.getElementById('symptom-reported-subject').value =
      draft?.subject ?? episode?.reported_subject ?? 'unspecified';
    document.getElementById('symptom-onset-date').value =
      draft?.onsetDate ?? episode?.onset.value ?? '';
    const resolutionField = document.getElementById('symptom-edit-resolution-field');
    const editResolved = symptomDialogMode === 'edit' && episode?.status === 'resolved';
    if (resolutionField) resolutionField.hidden = !editResolved;
    document.getElementById('symptom-edit-resolved-date').value =
      editResolved ? (draft?.resolvedDate ?? episode?.resolution?.value ?? '') : '';
    document.getElementById('symptom-timing').value =
      draft?.timing ?? episode?.timing_text ?? '';
    document.getElementById('symptom-frequency').value =
      draft?.frequency ?? episode?.frequency_text ?? '';
    document.getElementById('symptom-triggers').value =
      draft?.triggers ?? episode?.triggers_text ?? '';
    document.getElementById('symptom-notes').value =
      draft?.notes ?? episode?.notes ?? '';
    const fieldset = document.getElementById('symptom-create-follow-up-fieldset');
    if (fieldset) fieldset.hidden = symptomDialogMode !== 'add';
    const mode = symptomDialogMode === 'add' ? (draft?.followUpMode || 'none') : 'none';
    const modeControl = document.querySelector(
      `input[name="symptom-create-follow-up-mode"][value="${mode}"]`,
    );
    if (modeControl) modeControl.checked = true;
    populateSymptomActionSelect('symptom-create-existing-action', draft?.actionId);
    document.getElementById('symptom-create-follow-up-text').value = draft?.followUpText || '';
    document.getElementById('symptom-create-follow-up-owner').value = draft?.followUpOwner || '';
    document.getElementById('symptom-create-follow-up-due').value = draft?.followUpDue || '';
    renderSymptomCreateFollowUpMode();
  }

  function renderSymptomDialog() {
    if (!symptomDialogOpen) return;
    const episode = selectedSymptomEpisodeId
      ? symptomEpisodeById(selectedSymptomEpisodeId)
      : null;
    const details = document.getElementById('symptom-details-form');
    const resolve = document.getElementById('symptom-resolve-form');
    const followUp = document.getElementById('symptom-follow-up-form');
    details.hidden = !['add', 'edit'].includes(symptomDialogMode);
    resolve.hidden = symptomDialogMode !== 'resolve';
    followUp.hidden = symptomDialogMode !== 'follow-up';
    const title = document.getElementById('symptom-dialog-title');
    if (symptomDialogMode === 'add') {
      title.textContent = 'Record current symptom episode';
      document.getElementById('symptom-details-submit').textContent = 'Record episode';
      restoreSymptomDetailsForm();
    } else if (!episode || episode.token !== selectedSymptomEpisodeToken) {
      scrubSymptomDialog();
      return;
    } else if (symptomDialogMode === 'edit') {
      title.textContent = 'Edit symptom episode facts';
      document.getElementById('symptom-details-submit').textContent = 'Save episode facts';
      restoreSymptomDetailsForm(episode);
    } else if (symptomDialogMode === 'resolve') {
      title.textContent = 'Resolve symptom episode';
      document.getElementById('symptom-resolve-copy').textContent = episode.symptom_text;
      const draft = symptomDrafts.get(symptomDraftKey());
      document.getElementById('symptom-resolved-date').value = draft?.resolvedDate || '';
      document.getElementById('symptom-resolve-confirm').checked = draft?.confirmed === true;
    } else {
      title.textContent = episode.follow_up ? 'Review linked follow-up' : 'Add symptom follow-up';
      document.getElementById('symptom-follow-up-copy').textContent = episode.symptom_text;
      const linkedPanel = document.getElementById('symptom-linked-action-panel');
      const modes = document.getElementById('symptom-existing-follow-up-modes');
      const existingPanel = document.getElementById('symptom-existing-action-panel');
      const inlinePanel = document.getElementById('symptom-inline-action-panel');
      const submit = document.getElementById('symptom-follow-up-submit');
      const unlink = document.getElementById('symptom-unlink-submit');
      if (episode.follow_up) {
        linkedPanel.hidden = false;
        modes.hidden = true;
        existingPanel.hidden = true;
        inlinePanel.hidden = true;
        submit.hidden = true;
        unlink.hidden = false;
        document.getElementById('symptom-linked-action-copy').textContent =
          `${episode.follow_up.text} · ${episode.follow_up.status} · ${
            symptomScalar(episode.follow_up.owner)
          } · due ${symptomScalar(episode.follow_up.due_date)}`;
        selectedSymptomActionId = episode.follow_up.id;
        selectedSymptomActionToken = episode.follow_up.token;
      } else {
        linkedPanel.hidden = true;
        modes.hidden = false;
        submit.hidden = false;
        unlink.hidden = true;
        const draft = symptomDrafts.get(symptomDraftKey());
        const mode = draft?.mode || 'existing';
        const modeControl = document.querySelector(
          `input[name="symptom-follow-up-mode"][value="${mode}"]`,
        );
        if (modeControl) modeControl.checked = true;
        populateSymptomActionSelect('symptom-existing-action', draft?.actionId);
        document.getElementById('symptom-follow-up-text').value = draft?.text || '';
        document.getElementById('symptom-follow-up-owner').value = draft?.owner || '';
        document.getElementById('symptom-follow-up-due').value = draft?.due || '';
        renderSymptomFollowUpMode();
      }
    }
    updateSymptomFormValidity();
  }

  function openSymptomDialog(mode, trigger, episodeId = null) {
    if (
      !['current', 'empty'].includes(symptomProjectionState)
      || !symptomResponseOwnerIsCurrent()
      || symptomMutationPending
      || pendingSymptomCompletion
    ) {
      setSymptomStatus('Reload the current symptom record before making changes.', 'stale', true);
      return;
    }
    if (!['add', 'edit', 'resolve', 'follow-up'].includes(mode)) return;
    const episode = episodeId ? symptomEpisodeById(episodeId) : null;
    if (episodeId && !episode) {
      markSymptomProjectionStale('This episode is no longer available. Reloading the symptom record.');
      ensureSymptomEpisodes({ force: true });
      return;
    }
    if (mode === 'resolve' && episode?.status !== 'current') return;
    selectedSymptomEpisodeId = episode?.id || null;
    selectedSymptomEpisodeToken = episode?.token || null;
    selectedSymptomActionId = null;
    selectedSymptomActionToken = null;
    symptomSelectionEpoch += 1;
    symptomDialogEpoch += 1;
    symptomDialogMode = mode;
    symptomDialogOpen = true;
    clearSymptomRetry();
    setSymptomDialogStatus('');
    for (const id of ['symptom-details-error', 'symptom-resolve-error', 'symptom-follow-up-error']) {
      setFormError(id, '');
    }
    const overlay = document.getElementById('symptom-dialog-overlay');
    const dialog = document.getElementById('symptom-dialog');
    overlay.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    dialog.inert = false;
    renderSymptomDialog();
    activateDialog(dialog, trigger);
  }

  function openSymptomAddDialog(trigger) {
    openSymptomDialog('add', trigger);
  }

  function openSymptomEditDialog(trigger, episodeId) {
    openSymptomDialog('edit', trigger, episodeId);
  }

  function openSymptomResolveDialog(trigger, episodeId) {
    openSymptomDialog('resolve', trigger, episodeId);
  }

  function openSymptomFollowUpDialog(trigger, episodeId) {
    openSymptomDialog('follow-up', trigger, episodeId);
  }

  function closeSymptomDialog(preserveDraft = true, force = false, restoreFocus = true) {
    if (!symptomDialogOpen) return;
    if (symptomMutationPending && !force) {
      setSymptomDialogStatus('Saving is still in progress. Wait for the result before closing.', 'saving');
      return;
    }
    if (preserveDraft) captureSymptomDraft();
    symptomDialogOpen = false;
    symptomDialogMode = null;
    selectedSymptomEpisodeId = null;
    selectedSymptomEpisodeToken = null;
    selectedSymptomActionId = null;
    selectedSymptomActionToken = null;
    symptomSelectionEpoch += 1;
    symptomDialogEpoch += 1;
    clearSymptomRetry();
    const overlay = document.getElementById('symptom-dialog-overlay');
    const dialog = document.getElementById('symptom-dialog');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    deactivateDialog(dialog, restoreFocus);
  }

  function closeSymptomDialogFromBackdrop(event) {
    if (event?.target === document.getElementById('symptom-dialog-overlay')) {
      closeSymptomDialog();
    }
  }

  function renderSymptomCreateFollowUpMode() {
    const mode = document.querySelector(
      'input[name="symptom-create-follow-up-mode"]:checked',
    )?.value || 'none';
    const existing = document.getElementById('symptom-create-existing-panel');
    const inline = document.getElementById('symptom-create-inline-panel');
    if (existing) existing.hidden = mode !== 'existing';
    if (inline) inline.hidden = mode !== 'inline';
    updateSymptomFormValidity();
  }

  function renderSymptomFollowUpMode() {
    const mode = document.querySelector('input[name="symptom-follow-up-mode"]:checked')?.value
      || 'existing';
    const existing = document.getElementById('symptom-existing-action-panel');
    const inline = document.getElementById('symptom-inline-action-panel');
    if (existing) existing.hidden = mode !== 'existing';
    if (inline) inline.hidden = mode !== 'inline';
    const submit = document.getElementById('symptom-follow-up-submit');
    if (submit) submit.textContent = mode === 'existing'
      ? 'Link existing action'
      : 'Create and link action';
    updateSymptomFormValidity();
  }

  function symptomDatePrecision(value) {
    if (value == null || value === '') return 'unknown';
    const match = value.match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/);
    if (!match) return 'unknown';
    const year = Number(match[1]);
    if (year < 1 || year > 9999) return 'unknown';
    if (match[2] == null) return 'year';
    const month = Number(match[2]);
    if (month < 1 || month > 12) return 'unknown';
    if (match[3] == null) return 'month';
    const day = Number(match[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const maximum = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
    return day >= 1 && day <= maximum ? 'day' : 'unknown';
  }

  function symptomDateInputIsValid(value) {
    return value === '' || symptomDatePrecision(value) !== 'unknown';
  }

  function updateSymptomFormValidity() {
    const locked = (
      symptomMutationPending
      || !['current', 'empty'].includes(symptomProjectionState)
      || !symptomResponseOwnerIsCurrent()
    );
    const text = (document.getElementById('symptom-text')?.value || '').trim();
    const onset = document.getElementById('symptom-onset-date')?.value || '';
    const editResolved = document.getElementById('symptom-edit-resolved-date')?.value || '';
    const detailSubmit = document.getElementById('symptom-details-submit');
    const createMode = document.querySelector(
      'input[name="symptom-create-follow-up-mode"]:checked',
    )?.value || 'none';
    const createAction = document.getElementById('symptom-create-existing-action')?.value || '';
    const createText = (
      document.getElementById('symptom-create-follow-up-text')?.value || ''
    ).trim();
    const createFollowUpValid = symptomDialogMode !== 'add'
      || createMode === 'none'
      || (createMode === 'existing' && Boolean(createAction))
      || (createMode === 'inline' && Boolean(createText));
    if (detailSubmit) {
      detailSubmit.disabled = locked
        || !text
        || !symptomDateInputIsValid(onset)
        || !symptomDateInputIsValid(editResolved)
        || !createFollowUpValid;
    }
    const resolveSubmit = document.getElementById('symptom-resolve-submit');
    const resolvedDate = document.getElementById('symptom-resolved-date')?.value || '';
    if (resolveSubmit) {
      resolveSubmit.disabled = locked
        || document.getElementById('symptom-resolve-confirm')?.checked !== true
        || !symptomDateInputIsValid(resolvedDate);
    }
    const followUpSubmit = document.getElementById('symptom-follow-up-submit');
    const mode = document.querySelector('input[name="symptom-follow-up-mode"]:checked')?.value
      || 'existing';
    const action = document.getElementById('symptom-existing-action')?.value || '';
    const followUpText = (document.getElementById('symptom-follow-up-text')?.value || '').trim();
    if (followUpSubmit) {
      followUpSubmit.disabled = locked
        || (mode === 'existing' ? !action : !followUpText);
    }
    const unlink = document.getElementById('symptom-unlink-submit');
    if (unlink) unlink.disabled = locked;
  }

  function invalidateSymptomRetryOnDraftChange() {
    if (pendingSymptomIntent) {
      pendingSymptomIntent.bodyText = '';
      pendingSymptomIntent = null;
      const retry = document.getElementById('symptom-dialog-retry');
      if (retry) retry.hidden = true;
      setSymptomDialogStatus(
        'The draft changed. Review the latest symptom record and submit a new request.',
        'conflict',
      );
    }
    captureSymptomDraft();
    updateSymptomFormValidity();
  }

  function beginSymptomMutation(options = {}) {
    if (
      symptomMutationPending
      || pendingSymptomCompletion
      || (
        options.allowStale !== true
        && !['current', 'empty'].includes(symptomProjectionState)
      )
      || !symptomResponseOwnerIsCurrent()
    ) return null;
    const owner = {};
    symptomMutationOwner = owner;
    symptomMutationPending = true;
    symptomMutationEpoch += 1;
    const previous = symptomMutationController;
    symptomMutationController = new AbortController();
    if (previous && !previous.signal.aborted) previous.abort();
    updateSymptomControls();
    return owner;
  }

  function releaseSymptomMutation(intent) {
    if (
      !symptomMutationPending
      || symptomMutationOwner !== intent.mutationOwner
    ) return false;
    symptomMutationPending = false;
    symptomMutationOwner = null;
    if (symptomMutationController === intent.controller) symptomMutationController = null;
    if (activeSymptomIntent === intent) activeSymptomIntent = null;
    updateSymptomControls();
    return true;
  }

  function symptomIntentOwnsMutation(intent, expectedPhiEpoch = null) {
    const ownerPhiEpoch = expectedPhiEpoch
      ?? intent.acceptedPhiEpoch
      ?? intent.requestPhiEpoch;
    return Boolean(
      symptomMutationPending
      && symptomMutationOwner === intent.mutationOwner
      && symptomMutationController === intent.controller
      && !intent.controller.signal.aborted
      && intent.mutationEpoch === symptomMutationEpoch
      && ownerPhiEpoch === phiEpoch
      && intent.selectionEpoch === symptomSelectionEpoch
      && (
        intent.targetAccepted === true
        || (
          intent.episodeId === selectedSymptomEpisodeId
          && intent.episodeToken === selectedSymptomEpisodeToken
          && intent.actionId === selectedSymptomActionId
          && intent.actionToken === selectedSymptomActionToken
        )
      )
    );
  }

  function createSymptomIntent(method, url, body, mutationOwner, options = {}) {
    const canonicalBody = { ...body, mutation_id: newMutationId() };
    return {
      method,
      url,
      bodyText: JSON.stringify(canonicalBody),
      mutationOwner,
      controller: symptomMutationController,
      mutationEpoch: symptomMutationEpoch,
      requestPhiEpoch: phiEpoch,
      selectionEpoch: symptomSelectionEpoch,
      dialogEpoch: symptomDialogEpoch,
      episodeId: selectedSymptomEpisodeId,
      episodeToken: selectedSymptomEpisodeToken,
      actionId: selectedSymptomActionId,
      actionToken: selectedSymptomActionToken,
      draftKey: options.draftKey || symptomDraftKey(),
      operation: options.operation || '',
    };
  }

  function symptomMutationMeta() {
    return {
      expected_profile_revision: symptomProjection.profile_revision,
      expected_workflow_revision: symptomProjection.workflow_revision,
      expected_projection_token: symptomProjection.projection_token,
    };
  }

  function symptomOptionalText(id) {
    const value = document.getElementById(id)?.value ?? '';
    return value === '' ? null : value.trim();
  }

  function symptomDetailsBody() {
    const body = {
      ...symptomMutationMeta(),
      symptom_text: document.getElementById('symptom-text').value.trim(),
      severity_level: document.getElementById('symptom-severity').value || null,
      severity_detail: symptomOptionalText('symptom-severity-detail'),
      reported_subject: document.getElementById('symptom-reported-subject').value,
      onset_date: document.getElementById('symptom-onset-date').value || null,
      timing_text: symptomOptionalText('symptom-timing'),
      frequency_text: symptomOptionalText('symptom-frequency'),
      triggers_text: symptomOptionalText('symptom-triggers'),
      notes: symptomOptionalText('symptom-notes'),
    };
    if (symptomDialogMode === 'edit') {
      body.expected_episode_token = selectedSymptomEpisodeToken;
      if (symptomEpisodeById(selectedSymptomEpisodeId)?.status === 'resolved') {
        body.resolved_date = document.getElementById('symptom-edit-resolved-date').value || null;
      }
    } else {
      const mode = document.querySelector(
        'input[name="symptom-create-follow-up-mode"]:checked',
      )?.value || 'none';
      if (mode === 'existing') {
        const action = symptomProjection.eligible_actions.find(
          item => item.id === document.getElementById('symptom-create-existing-action').value,
        );
        if (!action) throw new Error('Select a currently eligible action.');
        body.caregiver_action_id = action.id;
        body.expected_action_token = action.token;
        selectedSymptomActionId = action.id;
        selectedSymptomActionToken = action.token;
      } else if (mode === 'inline') {
        body.follow_up = {
          text: document.getElementById('symptom-create-follow-up-text').value.trim(),
          owner: symptomOptionalText('symptom-create-follow-up-owner'),
          due_date: document.getElementById('symptom-create-follow-up-due').value || null,
        };
      }
    }
    return body;
  }

  async function submitSymptomDetails() {
    const mutationOwner = beginSymptomMutation();
    if (!mutationOwner) return null;
    let intent;
    try {
      const text = (document.getElementById('symptom-text')?.value || '').trim();
      const onset = document.getElementById('symptom-onset-date')?.value || '';
      const editResolved = document.getElementById('symptom-edit-resolved-date')?.value || '';
      if (!text) throw new Error('Enter the symptom description.');
      if (!symptomDateInputIsValid(onset)) {
        throw new Error('Use YYYY, YYYY-MM, or YYYY-MM-DD for the onset date.');
      }
      if (!symptomDateInputIsValid(editResolved)) {
        throw new Error('Use YYYY, YYYY-MM, or YYYY-MM-DD for the resolution date.');
      }
      const body = symptomDetailsBody();
      const creating = symptomDialogMode === 'add';
      intent = createSymptomIntent(
        creating ? 'POST' : 'PATCH',
        creating
          ? '/api/symptom-episodes'
          : `/api/symptom-episodes/${encodeURIComponent(selectedSymptomEpisodeId)}`,
        body,
        mutationOwner,
        { operation: creating ? 'create' : 'edit' },
      );
      return performSymptomIntent(intent);
    } catch (error) {
      setFormError('symptom-details-error', error.message || 'Review the episode fields.');
      releaseSymptomMutation(intent || {
        mutationOwner,
        controller: symptomMutationController,
      });
      return null;
    }
  }

  async function submitSymptomResolution() {
    const mutationOwner = beginSymptomMutation();
    if (!mutationOwner) return null;
    let intent;
    try {
      const episode = symptomEpisodeById(selectedSymptomEpisodeId);
      const date = document.getElementById('symptom-resolved-date')?.value || '';
      if (!episode || episode.status !== 'current') throw new Error('This episode is no longer current.');
      if (document.getElementById('symptom-resolve-confirm')?.checked !== true) {
        throw new Error('Confirm that this episode can be resolved.');
      }
      if (!symptomDateInputIsValid(date)) {
        throw new Error('Use YYYY, YYYY-MM, or YYYY-MM-DD for the resolution date.');
      }
      const body = {
        ...symptomMutationMeta(),
        expected_episode_token: selectedSymptomEpisodeToken,
        resolved_date: date || null,
      };
      intent = createSymptomIntent(
        'POST',
        `/api/symptom-episodes/${encodeURIComponent(selectedSymptomEpisodeId)}/resolve`,
        body,
        mutationOwner,
        { operation: 'resolve' },
      );
      return performSymptomIntent(intent);
    } catch (error) {
      setFormError('symptom-resolve-error', error.message || 'Review the resolution.');
      releaseSymptomMutation(intent || {
        mutationOwner,
        controller: symptomMutationController,
      });
      return null;
    }
  }

  function symptomFollowUpBody(unlink = false) {
    const episode = symptomEpisodeById(selectedSymptomEpisodeId);
    if (!episode) throw new Error('This episode is no longer available.');
    const body = {
      ...symptomMutationMeta(),
      expected_episode_token: selectedSymptomEpisodeToken,
    };
    if (unlink) {
      if (!episode.follow_up) throw new Error('This episode has no linked follow-up.');
      body.caregiver_action_id = null;
      body.expected_action_token = episode.follow_up.token;
      selectedSymptomActionId = episode.follow_up.id;
      selectedSymptomActionToken = episode.follow_up.token;
      return body;
    }
    if (episode.follow_up) throw new Error('Unlink the current follow-up before adding another.');
    const mode = document.querySelector('input[name="symptom-follow-up-mode"]:checked')?.value
      || 'existing';
    if (mode === 'existing') {
      const action = symptomProjection.eligible_actions.find(
        item => item.id === document.getElementById('symptom-existing-action').value,
      );
      if (!action) throw new Error('Select a currently eligible action.');
      body.caregiver_action_id = action.id;
      body.expected_action_token = action.token;
      selectedSymptomActionId = action.id;
      selectedSymptomActionToken = action.token;
    } else {
      const text = (document.getElementById('symptom-follow-up-text')?.value || '').trim();
      if (!text) throw new Error('Enter the manual follow-up text.');
      body.follow_up = {
        text,
        owner: symptomOptionalText('symptom-follow-up-owner'),
        due_date: document.getElementById('symptom-follow-up-due').value || null,
      };
    }
    return body;
  }

  async function submitSymptomFollowUp() {
    return submitSymptomFollowUpOperation(false);
  }

  async function submitSymptomUnlink() {
    return submitSymptomFollowUpOperation(true);
  }

  async function submitSymptomFollowUpOperation(unlink) {
    const mutationOwner = beginSymptomMutation();
    if (!mutationOwner) return null;
    let intent;
    try {
      const body = symptomFollowUpBody(unlink);
      intent = createSymptomIntent(
        'PATCH',
        `/api/symptom-episodes/${encodeURIComponent(selectedSymptomEpisodeId)}/follow-up`,
        body,
        mutationOwner,
        { operation: unlink ? 'unlink' : 'follow-up' },
      );
      return performSymptomIntent(intent);
    } catch (error) {
      setFormError('symptom-follow-up-error', error.message || 'Review the follow-up fields.');
      releaseSymptomMutation(intent || {
        mutationOwner,
        controller: symptomMutationController,
      });
      return null;
    }
  }

  function symptomMutationResultMatchesProjection(data) {
    if (
      !symptomProjection
      || symptomProjection.profile_revision !== data.profile_revision
      || symptomProjection.workflow_revision !== data.workflow_revision
    ) return false;
    const episode = symptomProjection.episodes.find(item => item.id === data.episode.id);
    return Boolean(
      episode
      && episode.token === data.episode.token
      && (
        data.follow_up == null
          ? episode.follow_up === null
          : episode.follow_up?.id === data.follow_up.id
            && episode.follow_up?.token === data.follow_up.token
      )
    );
  }

  async function finalizeSymptomMutation(data, intent) {
    if (!symptomIntentOwnsMutation(intent)) return false;
    symptomDrafts.delete(intent.draftKey);
    pendingSymptomCompletion = null;
    clearSymptomRetry();
    const hadDialog = symptomDialogOpen;
    if (hadDialog) closeSymptomDialog(false, true, false);
    setSymptomStatus('Symptom record saved.', 'current', false);
    reportLoadSuccess('symptom-mutation');
    releaseSymptomMutation(intent);
    const target = document.getElementById(
      activeView === 'patient' ? 'symptoms-heading' : 'today-symptoms-heading',
    );
    target?.focus();
    return true;
  }

  async function consumeSymptomMutationResponse(data, intent) {
    if (!symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) return false;
    if (!symptomMutationPayloadIsValid(data)) {
      clearSymptomProjection({
        state: 'corrupt',
        statusLabel: 'Record unavailable',
        message: 'Symptom records were cleared because a mutation response could not be verified safely.',
      });
      return false;
    }
    const authority = authorizePatientResponse(intent, data, {
      workflow: 'targeted',
      symptomMutation: true,
    });
    if (!authority.accepted) return false;
    intent.acceptedPhiEpoch = authority.requestPhiEpoch;
    if (!symptomIntentOwnsMutation(intent, intent.acceptedPhiEpoch)) return false;
    intent.targetAccepted = true;
    selectedSymptomEpisodeId = data.episode.id;
    selectedSymptomEpisodeToken = data.episode.token;
    selectedSymptomActionId = data.follow_up?.id || null;
    selectedSymptomActionToken = data.follow_up?.token || null;
    markSymptomProjectionStale(
      'The symptom change was accepted. Reloading the authoritative record…',
      {
        abortRequest: true,
        ownerPhiEpoch: phiEpoch,
        preserveMutation: true,
      },
    );
    const reloaded = await loadSymptomEpisodes({ force: true, preserveMutation: true });
    if (
      !symptomIntentOwnsMutation(intent, intent.acceptedPhiEpoch)
      || !reloaded
      || !symptomMutationResultMatchesProjection(data)
    ) {
      if (symptomIntentOwnsMutation(intent, intent.acceptedPhiEpoch)) {
        pendingSymptomCompletion = { data, intent };
        const retry = document.getElementById('symptom-dialog-retry');
        const message = document.getElementById('symptom-dialog-retry-message');
        if (message) {
          message.textContent =
            'The change may be saved, but the authoritative symptom record could not be verified. Retry the reload; the mutation will not be sent again.';
        }
        if (retry) retry.hidden = false;
        setSymptomDialogStatus(
          'The current symptom record could not be verified. Retry the authoritative reload.',
          'offline',
        );
      }
      return false;
    }
    return finalizeSymptomMutation(data, intent);
  }

  async function handleSymptomConflict(intent) {
    if (!symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) return false;
    if (symptomDialogOpen) captureSymptomDraft();
    clearSymptomRetry();
    setSymptomDialogStatus(
      'The symptom record changed. Review the latest authoritative episode before submitting again.',
      'conflict',
    );
    setSymptomStatus(
      'The symptom record changed. Reloading current authority for review.',
      'stale',
      false,
    );
    markSymptomProjectionStale(
      'The symptom record changed. Reloading current authority for review.',
      { preserveMutation: true },
    );
    releaseSymptomMutation(intent);
    await loadSymptomEpisodes({ force: true });
    return true;
  }

  async function performSymptomIntent(intent, explicitRetry = false) {
    if (!symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
    activeSymptomIntent = intent;
    setSymptomDialogStatus(
      explicitRetry ? 'Retrying the unchanged request…' : 'Saving…',
      'saving',
    );
    try {
      const response = await fetch(intent.url, {
        method: intent.method,
        headers: { 'Content-Type': 'application/json' },
        body: intent.bodyText,
        signal: intent.controller.signal,
      });
      if (!symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const data = await readJsonResponse(
        response,
        () => symptomIntentOwnsMutation(intent, intent.requestPhiEpoch),
      );
      if (!symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) return null;
      const consumed = await consumeSymptomMutationResponse(data, intent);
      return consumed ? data : null;
    } catch (error) {
      if (
        error?.name === 'AbortError'
        || !symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)
      ) return null;
      if (error?.status === 401 || error?.status === 403) {
        const safeError = new Error('Symptom authorization is unavailable.');
        safeError.status = error.status;
        reportLoadError('symptom-mutation', safeError);
        if (symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)) {
          evictClientPhi(safeError);
        }
        return null;
      }
      if (error?.status === 409) {
        await handleSymptomConflict(intent);
        return null;
      }
      if (error instanceof TypeError) {
        pendingSymptomIntent = intent;
        symptomNetworkAmbiguous = true;
        markSymptomProjectionStale(
          'Symptom mutation transport is uncertain. The last accepted snapshot is stale and read-only.',
          { abortRequest: false, preserveMutation: true },
        );
        const retry = document.getElementById('symptom-dialog-retry');
        const message = document.getElementById('symptom-dialog-retry-message');
        if (message) {
          message.textContent =
            'The request may not have reached the server. Review and explicitly retry the unchanged request.';
        }
        if (retry) retry.hidden = false;
        setSymptomDialogStatus(
          'Connection lost. The unchanged request is available for explicit retry.',
          'offline',
        );
        reportLoadError(
          'symptom-mutation',
          new TypeError('The symptom endpoint could not be reached.'),
        );
        return null;
      }
      clearSymptomProjection({
        state: error?.status === 422 ? 'corrupt' : 'error',
        statusLabel: 'Record unavailable',
        message: 'Symptom records were cleared because the request failed without safe retry authority.',
      });
      const safeError = new Error('The symptom request could not be saved safely.');
      safeError.status = error?.status;
      reportLoadError('symptom-mutation', safeError);
      return null;
    } finally {
      if (activeSymptomIntent === intent) activeSymptomIntent = null;
      releaseSymptomMutation(intent);
    }
  }

  async function retrySymptomIntent() {
    if (pendingSymptomCompletion) {
      const completion = pendingSymptomCompletion;
      const reloaded = await loadSymptomEpisodes({ force: true });
      if (reloaded && symptomMutationResultMatchesProjection(completion.data)) {
        symptomDrafts.delete(completion.intent.draftKey);
        pendingSymptomCompletion = null;
        clearSymptomRetry();
        if (symptomDialogOpen) closeSymptomDialog(false, true);
        setSymptomStatus('Symptom record saved.', 'current', false);
      }
      return;
    }
    const pending = pendingSymptomIntent;
    if (!pending || !pending.bodyText || !symptomResponseOwnerIsCurrent()) return;
    const owner = beginSymptomMutation({ allowStale: true });
    if (!owner) return;
    const controller = symptomMutationController;
    pending.mutationOwner = owner;
    pending.controller = controller;
    pending.mutationEpoch = symptomMutationEpoch;
    pending.requestPhiEpoch = phiEpoch;
    pending.selectionEpoch = symptomSelectionEpoch;
    pending.dialogEpoch = symptomDialogEpoch;
    pendingSymptomIntent = null;
    return performSymptomIntent(pending, true);
  }

  async function loadSummary(options = {}) {
    const request = capturePatientRequest();
    const requestSummaryEpoch = ++summaryLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
      && requestSummaryEpoch === summaryLoadEpoch
    );
    try {
      const r = await fetch('/api/summary');
      if (!requestIsCurrent()) return null;
      const d = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(
        request,
        d,
        options.authorizationOptions || {},
      );
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

    body.innerHTML = html;
    refreshGeneratedActionControls();
    if (followUpControlsLocked()) setFollowUpMutationBusy(true);
  }

  // ── Research shortlist and disposition workspace ─────────────────────────
  const RESEARCH_SAFETY_GUIDANCE = 'NET/Care records research you choose to follow but does not determine relevance, eligibility, enrollment, or treatment suitability. Confirm clinical questions with the treating team and trial details with the study site.';
  const RESEARCH_AUTHORITY_LABELS = {
    external_facts: 'External registry or bibliographic facts',
    generated_context: 'Machine-generated compatibility context · not relevance, eligibility, enrollment, suitability, or recommendation',
    discovery_provenance: 'Research discovery provenance',
    caregiver_workflow: 'Caregiver-maintained shortlist and disposition workflow',
  };
  const RESEARCH_ATTRIBUTION_LABELS = {
    caregiver: 'Caregiver-entered · unverified',
    clinician: 'Caregiver-entered · attributed to clinician · unverified',
    trial_site: 'Caregiver-entered · attributed to trial site · unverified',
  };
  const RESEARCH_EXTERNAL_FIELDS = {
    trial: new Set(['nct_id', 'title', 'status', 'phase', 'phases', 'countries', 'brief_summary', 'eligibility_excerpt', 'registry_last_update']),
    paper: new Set(['pmid', 'title', 'authors', 'journal', 'date']),
  };
  const RESEARCH_GENERATED_FIELDS = {
    trial: new Set(['eligibility_notes']),
    paper: new Set(['relevance_notes']),
  };
  const RESEARCH_DISCOVERY_FIELDS = {
    trial: new Set(['date_added']),
    paper: new Set(['query', 'date_added']),
  };
  const RESEARCH_EVENT_TYPES = {
    trial: ['caregiver_note', 'next_step_recorded', 'treating_team_communication', 'trial_site_communication'],
    paper: ['caregiver_note', 'next_step_recorded', 'treating_team_communication'],
  };
  const RESEARCH_EVENT_LABELS = {
    caregiver_note: 'Caregiver note',
    next_step_recorded: 'Next step',
    treating_team_communication: 'Treating-team communication',
    trial_site_communication: 'Trial-site communication',
  };

  function researchPlainObject(value) {
    return value !== null
      && typeof value === 'object'
      && !Array.isArray(value)
      && Object.getPrototypeOf(value) === Object.prototype;
  }

  function researchExactKeys(value, keys) {
    return researchPlainObject(value)
      && Object.keys(value).length === keys.length
      && keys.every(key => Object.prototype.hasOwnProperty.call(value, key));
  }

  function researchCanonical(value) {
    if (Array.isArray(value)) return `[${value.map(researchCanonical).join(',')}]`;
    if (researchPlainObject(value)) {
      return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${researchCanonical(value[key])}`).join(',')}}`;
    }
    return JSON.stringify(value);
  }

  function researchNonemptyString(value, max = 100000) {
    return typeof value === 'string' && value.length > 0 && value.length <= max;
  }

  function validateResearchNested(value) {
    const stack = [[value, 0]];
    let nodes = 0;
    while (stack.length) {
      const [current, depth] = stack.pop();
      nodes += 1;
      if (nodes > 200000 || depth > 16) throw new Error('Research authority exceeds the supported limits.');
      if (typeof current === 'string') {
        if (current.length > 100000) throw new Error('Research authority exceeds the supported limits.');
      } else if (Array.isArray(current)) {
        if (current.length > 20000) throw new Error('Research authority exceeds the supported limits.');
        current.forEach(item => stack.push([item, depth + 1]));
      } else if (researchPlainObject(current)) {
        const keys = Object.keys(current);
        if (keys.length > 5000 || keys.some(key => key.length > 500)) {
          throw new Error('Research authority exceeds the supported limits.');
        }
        keys.forEach(key => stack.push([current[key], depth + 1]));
      } else if (
        current !== null
        && typeof current !== 'boolean'
        && !(typeof current === 'number' && Number.isFinite(current))
      ) {
        throw new Error('Research authority contains an unsupported value.');
      }
    }
  }

  function validateResearchAllowedFields(value, allowed) {
    if (!researchPlainObject(value) || Object.keys(value).some(key => !allowed.has(key))) {
      throw new Error('Research authority contains unsupported fields.');
    }
    validateResearchNested(value);
  }

  function researchCanonicalExternalUrl(itemType, externalId, value) {
    const validId = itemType === 'trial'
      ? /^NCT\d{8}$/.test(externalId)
      : /^[1-9]\d{0,8}$/.test(externalId);
    const expected = validId
      ? (
        itemType === 'trial'
          ? `https://clinicaltrials.gov/study/${externalId}`
          : `https://pubmed.ncbi.nlm.nih.gov/${externalId}/`
      )
      : null;
    if (value !== expected) throw new Error('Research contains an unsafe external link.');
    return expected;
  }

  function researchExpectedProvenance(eventType) {
    if (eventType === 'treating_team_communication') {
      return {
        capture_method: 'caregiver_entered',
        attributed_to: 'clinician',
        source_verification: 'unverified',
        label: RESEARCH_ATTRIBUTION_LABELS.clinician,
      };
    }
    if (eventType === 'trial_site_communication') {
      return {
        capture_method: 'caregiver_entered',
        attributed_to: 'trial_site',
        source_verification: 'unverified',
        label: RESEARCH_ATTRIBUTION_LABELS.trial_site,
      };
    }
    return {
      capture_method: 'caregiver_entered',
      source_verification: 'unverified',
      label: RESEARCH_ATTRIBUTION_LABELS.caregiver,
    };
  }

  function researchPartialDatePrecision(value) {
    if (value === null) return 'unknown';
    if (typeof value !== 'string') return null;
    if (/^\d{4}$/.test(value)) return 'year';
    const month = value.match(/^(\d{4})-(\d{2})$/);
    if (month && Number(month[2]) >= 1 && Number(month[2]) <= 12) return 'month';
    const day = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!day) return null;
    const yearNumber = Number(day[1]);
    const monthNumber = Number(day[2]);
    const dayNumber = Number(day[3]);
    if (monthNumber < 1 || monthNumber > 12 || dayNumber < 1) return null;
    const leap = yearNumber % 4 === 0 && (yearNumber % 100 !== 0 || yearNumber % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return dayNumber <= days[monthNumber - 1] ? 'day' : null;
  }

  function validateResearchAction(action, eligible = false) {
    if (!researchExactKeys(action, ['id', 'token', 'text', 'status', 'owner', 'due_date'])) {
      throw new Error('Research follow-up authority is invalid.');
    }
    if (
      !researchNonemptyString(action.id)
      || !researchNonemptyString(action.token)
      || typeof action.text !== 'string'
      || !researchNonemptyString(action.status, 100)
      || (action.owner !== null && typeof action.owner !== 'string')
      || (action.due_date !== null && typeof action.due_date !== 'string')
      || (eligible && !['open', 'in_progress'].includes(action.status))
    ) throw new Error('Research follow-up authority is invalid.');
    validateResearchNested(action);
  }

  function validateResearchEvent(event, itemType) {
    if (!researchExactKeys(event, ['id', 'token', 'event_type', 'note', 'who', 'context', 'occurred_on', 'occurred_on_precision', 'provenance', 'recorded_at'])) {
      throw new Error('Research event authority is invalid.');
    }
    const allowed = RESEARCH_EVENT_TYPES[itemType];
    if (
      !researchNonemptyString(event.id)
      || !researchNonemptyString(event.token)
      || !allowed.includes(event.event_type)
      || typeof event.note !== 'string'
      || !event.note.trim()
      || event.note.length > 20000
      || (event.who !== null && (typeof event.who !== 'string' || !event.who.trim() || event.who.length > 500))
      || (event.context !== null && (typeof event.context !== 'string' || !event.context.trim() || event.context.length > 2000))
      || researchPartialDatePrecision(event.occurred_on) !== event.occurred_on_precision
      || !researchNonemptyString(event.recorded_at)
      || researchCanonical(event.provenance) !== researchCanonical(researchExpectedProvenance(event.event_type))
    ) throw new Error('Research event authority is invalid.');
  }

  function validateResearchSnapshot(snapshot, itemType, recordId, sourceKey) {
    if (!researchExactKeys(snapshot, ['item_type', 'research_record_id', 'source_key', 'external_facts', 'generated_context', 'discovery_provenance'])) {
      throw new Error('Research snapshot authority is invalid.');
    }
    if (
      snapshot.item_type !== itemType
      || snapshot.research_record_id !== recordId
      || snapshot.source_key !== sourceKey
    ) throw new Error('Research snapshot identity is invalid.');
    validateResearchAllowedFields(snapshot.external_facts, RESEARCH_EXTERNAL_FIELDS[itemType]);
    validateResearchAllowedFields(snapshot.generated_context, RESEARCH_GENERATED_FIELDS[itemType]);
    validateResearchAllowedFields(snapshot.discovery_provenance, RESEARCH_DISCOVERY_FIELDS[itemType]);
    const externalId = snapshot.external_facts[itemType === 'trial' ? 'nct_id' : 'pmid'];
    const expectedSource = itemType === 'trial' ? `ctgov:${externalId}` : `pubmed:${externalId}`;
    if (
      !(itemType === 'trial' ? /^NCT\d{8}$/.test(externalId) : /^[1-9]\d{0,8}$/.test(externalId))
      || sourceKey !== expectedSource
    ) throw new Error('Research snapshot source identity is invalid.');
    if (new TextEncoder().encode(JSON.stringify(snapshot)).length > 1500000) {
      throw new Error('Research snapshot exceeds the supported limits.');
    }
  }

  function validateResearchConsideration(consideration) {
    if (!researchExactKeys(consideration, ['id', 'token', 'item_type', 'research_record_id', 'source_key', 'status', 'snapshot', 'current_state', 'events', 'history', 'follow_up', 'eligibility', 'created_at', 'updated_at', 'closed_at'])) {
      throw new Error('Research consideration authority is invalid.');
    }
    const itemType = consideration.item_type;
    if (
      !['trial', 'paper'].includes(itemType)
      || !researchNonemptyString(consideration.id)
      || !researchNonemptyString(consideration.token)
      || !researchNonemptyString(consideration.research_record_id)
      || !researchNonemptyString(consideration.source_key)
      || !['open', 'closed'].includes(consideration.status)
      || !researchNonemptyString(consideration.created_at)
      || !researchNonemptyString(consideration.updated_at)
      || (consideration.closed_at !== null && !researchNonemptyString(consideration.closed_at))
    ) throw new Error('Research consideration authority is invalid.');
    validateResearchSnapshot(
      consideration.snapshot,
      itemType,
      consideration.research_record_id,
      consideration.source_key,
    );
    if (
      !researchExactKeys(consideration.current_state, ['occurrence', 'external_facts', 'generated_context', 'discovery_provenance'])
      || !['present', 'missing'].includes(consideration.current_state.occurrence)
      || ['external_facts', 'generated_context', 'discovery_provenance'].some(key => (
        !['unchanged', 'changed', 'unavailable'].includes(consideration.current_state[key])
      ))
    ) throw new Error('Research current-state authority is invalid.');
    if (
      consideration.current_state.occurrence === 'missing'
      && ['external_facts', 'generated_context', 'discovery_provenance'].some(key => consideration.current_state[key] !== 'unavailable')
    ) throw new Error('Research missing-current authority is invalid.');
    if (!Array.isArray(consideration.events) || consideration.events.length > 5000) {
      throw new Error('Research events exceed the supported limits.');
    }
    consideration.events.forEach(event => validateResearchEvent(event, itemType));
    const eventIds = consideration.events.map(event => event.id);
    if (new Set(eventIds).size !== eventIds.length) throw new Error('Research event identity is duplicated.');
    const historyChanges = {
      created: ['status'],
      event_recorded: ['event_id', 'event_type'],
      closed: ['status'],
      resumed: ['status'],
      follow_up_changed: ['caregiver_action_id'],
    };
    if (!Array.isArray(consideration.history) || consideration.history.some(entry => (
      !researchExactKeys(entry, ['operation', 'at', 'changes'])
      || !Object.prototype.hasOwnProperty.call(historyChanges, entry.operation)
      || !researchNonemptyString(entry.at)
      || !researchExactKeys(entry.changes, historyChanges[entry.operation])
    ))) throw new Error('Research lifecycle history is invalid.');
    if (consideration.follow_up !== null) validateResearchAction(consideration.follow_up);
    const eligibility = consideration.eligibility;
    if (
      !researchExactKeys(eligibility, ['close', 'resume', 'allowed_event_types', 'follow_up_variants'])
      || !researchExactKeys(eligibility.close, ['eligible', 'reason'])
      || !researchExactKeys(eligibility.resume, ['eligible', 'reason'])
      || typeof eligibility.close.eligible !== 'boolean'
      || typeof eligibility.resume.eligible !== 'boolean'
      || JSON.stringify(eligibility.allowed_event_types) !== JSON.stringify(RESEARCH_EVENT_TYPES[itemType])
      || !Array.isArray(eligibility.follow_up_variants)
      || JSON.stringify(eligibility.follow_up_variants) !== JSON.stringify(
        consideration.follow_up === null ? ['link_existing', 'create_and_link'] : ['unlink']
      )
      || eligibility.close.eligible !== (consideration.status === 'open')
      || eligibility.resume.eligible !== (consideration.status === 'closed')
      || eligibility.close.reason !== (consideration.status === 'open' ? null : 'closed')
      || eligibility.resume.reason !== (consideration.status === 'closed' ? null : 'already_open')
    ) throw new Error('Research eligibility authority is invalid.');
    validateResearchNested(consideration);
    return consideration;
  }

  function validateResearchWorkspace(data) {
    const keys = ['profile_revision', 'workflow_revision', 'projection_token', 'item_count', 'consideration_count', 'items', 'considerations', 'eligible_actions', 'attribution_labels', 'authority_labels', 'safety_guidance'];
    if (!researchExactKeys(data, keys)) throw new Error('Research workspace shape is invalid.');
    validateResearchNested(data);
    if (new TextEncoder().encode(JSON.stringify(data)).length > 20000000) {
      throw new Error('Research workspace exceeds the supported limits.');
    }
    if (
      !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || !researchNonemptyString(data.projection_token)
      || !Number.isSafeInteger(data.item_count)
      || !Number.isSafeInteger(data.consideration_count)
      || !Array.isArray(data.items)
      || data.items.length > 2000
      || !Array.isArray(data.considerations)
      || data.considerations.length > 1000
      || !Array.isArray(data.eligible_actions)
      || data.eligible_actions.length > 1000
      || data.item_count !== data.items.length
      || data.consideration_count !== data.considerations.length
      || researchCanonical(data.attribution_labels) !== researchCanonical(RESEARCH_ATTRIBUTION_LABELS)
      || researchCanonical(data.authority_labels) !== researchCanonical(RESEARCH_AUTHORITY_LABELS)
      || !researchExactKeys(data.safety_guidance, ['kind', 'text'])
      || data.safety_guidance.kind !== 'fixed_non_clinical'
      || data.safety_guidance.text !== RESEARCH_SAFETY_GUIDANCE
    ) throw new Error('Research workspace authority is invalid.');

    const itemIds = new Set();
    data.items.forEach(item => {
      if (!researchExactKeys(item, ['id', 'token', 'item_type', 'source_identity', 'external_facts', 'generated_context', 'discovery_provenance', 'external_url', 'latest_batch_member', 'shortlist', 'consideration_id'])) {
        throw new Error('Research occurrence authority is invalid.');
      }
      const itemType = item.item_type;
      if (
        !['trial', 'paper'].includes(itemType)
        || !researchNonemptyString(item.id)
        || !researchNonemptyString(item.token)
        || itemIds.has(item.id)
        || typeof item.latest_batch_member !== 'boolean'
        || !researchExactKeys(item.source_identity, ['external_id', 'source_key', 'authority'])
        || !['validated', 'missing_or_invalid'].includes(item.source_identity.authority)
        || (item.consideration_id !== null && !researchNonemptyString(item.consideration_id))
        || !researchExactKeys(item.shortlist, ['eligible', 'reason'])
        || typeof item.shortlist.eligible !== 'boolean'
        || !['already_shortlisted', 'missing_or_invalid_source_id', 'snapshot_too_large', null].includes(item.shortlist.reason)
        || item.shortlist.eligible !== (item.shortlist.reason === null)
      ) throw new Error('Research occurrence authority is invalid.');
      itemIds.add(item.id);
      validateResearchAllowedFields(item.external_facts, RESEARCH_EXTERNAL_FIELDS[itemType]);
      validateResearchAllowedFields(item.generated_context, RESEARCH_GENERATED_FIELDS[itemType]);
      validateResearchAllowedFields(item.discovery_provenance, RESEARCH_DISCOVERY_FIELDS[itemType]);
      const externalId = item.source_identity.external_id;
      const validId = typeof externalId === 'string' && (
        itemType === 'trial' ? /^NCT\d{8}$/.test(externalId) : /^[1-9]\d{0,8}$/.test(externalId)
      );
      const expectedSource = validId
        ? `${itemType === 'trial' ? 'ctgov' : 'pubmed'}:${externalId}`
        : null;
      if (
        item.source_identity.source_key !== expectedSource
        || item.source_identity.authority !== (validId ? 'validated' : 'missing_or_invalid')
        || item.external_facts[itemType === 'trial' ? 'nct_id' : 'pmid'] !== externalId
      ) throw new Error('Research occurrence source identity is invalid.');
      researchCanonicalExternalUrl(itemType, externalId, item.external_url);
    });

    const considerationIds = new Set();
    const considerationRecords = new Set();
    const eventIds = new Set();
    const linkedActionIds = new Set();
    data.considerations.forEach(consideration => {
      validateResearchConsideration(consideration);
      if (
        considerationIds.has(consideration.id)
        || considerationRecords.has(consideration.research_record_id)
      ) throw new Error('Research consideration identity is duplicated.');
      considerationIds.add(consideration.id);
      considerationRecords.add(consideration.research_record_id);
      consideration.events.forEach(event => {
        if (eventIds.has(event.id)) throw new Error('Research event identity is duplicated.');
        eventIds.add(event.id);
      });
      if (consideration.follow_up) {
        if (linkedActionIds.has(consideration.follow_up.id)) throw new Error('Research follow-up ownership is duplicated.');
        linkedActionIds.add(consideration.follow_up.id);
      }
      const exactItem = data.items.find(item => item.id === consideration.research_record_id);
      if (
        consideration.current_state.occurrence === 'present'
        && (!exactItem || exactItem.item_type !== consideration.item_type)
      ) throw new Error('Research current occurrence reference is invalid.');
      if (consideration.current_state.occurrence === 'missing' && exactItem) {
        throw new Error('Research missing occurrence reference is invalid.');
      }
      if (exactItem) {
        for (const section of ['external_facts', 'generated_context', 'discovery_provenance']) {
          const expectedState = researchCanonical(exactItem[section]) === researchCanonical(consideration.snapshot[section])
            ? 'unchanged'
            : 'changed';
          if (consideration.current_state[section] !== expectedState) {
            throw new Error('Research section-specific current state is invalid.');
          }
        }
      }
    });
    data.items.forEach(item => {
      const expected = data.considerations.find(value => value.research_record_id === item.id);
      if ((expected?.id || null) !== item.consideration_id) {
        throw new Error('Research occurrence consideration reference is invalid.');
      }
    });
    const eligibleActionIds = new Set();
    data.eligible_actions.forEach(action => {
      validateResearchAction(action, true);
      if (eligibleActionIds.has(action.id) || linkedActionIds.has(action.id)) {
        throw new Error('Research follow-up eligibility is invalid.');
      }
      eligibleActionIds.add(action.id);
    });
    return data;
  }

  function validateResearchMutationResponse(data, expectedConsiderationId = null) {
    const keys = ['consideration', 'workflow_revision', 'profile_revision'];
    const replayKeys = [...keys, 'idempotent_replay'];
    if (!researchExactKeys(data, keys) && !researchExactKeys(data, replayKeys)) {
      throw new Error('Research mutation response is invalid.');
    }
    if (
      !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || ('idempotent_replay' in data && data.idempotent_replay !== true)
    ) throw new Error('Research mutation response revisions are invalid.');
    validateResearchConsideration(data.consideration);
    if (expectedConsiderationId && data.consideration.id !== expectedConsiderationId) {
      throw new Error('Research mutation returned a different consideration.');
    }
    return data;
  }

  function researchValueMarkup(value) {
    if (value === null) return '<span class="research-null">Null</span>';
    if (value === '') return '<span class="research-empty-value">Empty string</span>';
    if (Array.isArray(value)) {
      if (!value.length) return '<span class="research-empty-value">Empty list</span>';
      return `<ol class="research-value-list">${value.map(item => `<li>${researchValueMarkup(item)}</li>`).join('')}</ol>`;
    }
    if (researchPlainObject(value)) {
      if (!Object.keys(value).length) return '<span class="research-empty-value">Empty object</span>';
      const exact = JSON.stringify(value, null, 2);
      return `<details class="research-exact-details"><summary>Show exact object</summary><pre>${escHtml(exact)}</pre></details>`;
    }
    const text = String(value);
    if (text.length > 240 || text.includes('\n')) {
      return `<details class="research-exact-details"><summary>Show exact content</summary><div class="research-long-value">${escHtml(text)}</div></details>`;
    }
    return `<span>${escHtml(text)}</span>`;
  }

  function researchAuthorityMarkup(label, value, allowedFields) {
    const rows = [...allowedFields].map(key => {
      const present = Object.prototype.hasOwnProperty.call(value, key);
      return `<div class="research-fact-row"><dt>${escHtml(key.replaceAll('_', ' '))}</dt><dd>${present ? researchValueMarkup(value[key]) : '<span class="research-missing-value">Missing field</span>'}</dd></div>`;
    }).join('');
    return `<section class="research-authority-section"><h4>${escHtml(label)}</h4><dl class="research-fact-list">${rows}</dl></section>`;
  }

  function researchItemTitle(item) {
    const title = item.external_facts.title;
    if (!Object.prototype.hasOwnProperty.call(item.external_facts, 'title')) return 'Title field missing';
    if (title === null) return 'Title is null';
    if (title === '') return 'Title is empty';
    return String(title);
  }

  function researchIdentityLabel(item) {
    const externalId = item.source_identity.external_id;
    if (externalId === null) return 'External identifier is null';
    if (externalId === '') return 'External identifier is empty';
    return externalId == null ? 'External identifier missing' : String(externalId);
  }

  function appendResearchControl(container, label, authority, tone = 'secondary') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `button ${tone} research-mutation-control`;
    button.textContent = label;
    button.disabled = researchProjectionState !== 'current' || researchMutationPending;
    researchControlAuthority.set(button, authority);
    button.addEventListener('click', () => {
      const selected = researchControlAuthority.get(button);
      if (!selected || researchProjectionState !== 'current') return;
      if (selected.kind === 'navigate-consideration') {
        selectResearchTab('considerations');
        document.getElementById('research-workspace-heading')?.focus();
        return;
      }
      openResearchDialog(selected.kind, selected.value, button);
    });
    container.appendChild(button);
  }

  function renderResearchOccurrence(item, compact = false) {
    const article = document.createElement('article');
    article.className = compact ? 'research-compact-item' : 'research-occurrence-card';
    const canonical = item.external_url;
    article.innerHTML = `
      <header class="research-card-header">
        <div>
          <span class="research-type">${escHtml(item.item_type === 'trial' ? 'Clinical trial' : 'Research paper')}</span>
          <h3>${escHtml(researchItemTitle(item))}</h3>
          <p class="research-source-id">${escHtml(researchIdentityLabel(item))}</p>
        </div>
        ${item.latest_batch_member ? '<span class="research-latest-badge">New research</span>' : ''}
      </header>
      ${canonical ? `<p><a class="research-external-link" href="${escHtml(canonical)}" target="_blank" rel="noopener noreferrer">Open exact ${item.item_type === 'trial' ? 'ClinicalTrials.gov' : 'PubMed'} record <span aria-hidden="true">↗</span></a></p>` : '<p class="research-mechanical-reason">No validated canonical external link is available.</p>'}
    `;
    if (!compact) {
      article.insertAdjacentHTML('beforeend', `
        <div class="research-authority-grid">
          ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.external_facts, item.external_facts, RESEARCH_EXTERNAL_FIELDS[item.item_type])}
          ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.generated_context, item.generated_context, RESEARCH_GENERATED_FIELDS[item.item_type])}
          ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.discovery_provenance, item.discovery_provenance, RESEARCH_DISCOVERY_FIELDS[item.item_type])}
        </div>
      `);
    }
    const actions = document.createElement('div');
    actions.className = 'research-card-actions';
    if (item.shortlist.eligible) {
      appendResearchControl(actions, 'Save exact occurrence for consideration', { kind: 'shortlist', value: item }, 'primary');
    } else if (item.consideration_id) {
      appendResearchControl(actions, 'Open existing consideration', { kind: 'navigate-consideration', value: item });
    } else {
      const reasons = {
        missing_or_invalid_source_id: 'Saving is unavailable because this occurrence has no validated source identifier.',
        snapshot_too_large: 'Saving is unavailable because this exact occurrence exceeds the supported snapshot limit.',
        already_shortlisted: 'This exact occurrence already has a caregiver consideration.',
      };
      actions.innerHTML = `<p class="research-mechanical-reason">${escHtml(reasons[item.shortlist.reason] || 'Saving is mechanically unavailable for this exact occurrence.')}</p>`;
    }
    article.appendChild(actions);
    return article;
  }

  function researchCurrentSectionMarkup(consideration, item, section, label, allowedFields) {
    const state = consideration.current_state[section];
    const value = item ? item[section] : {};
    return `<section class="research-current-section">
      <div class="research-current-heading"><h4>${escHtml(label)}</h4><span class="research-change-state ${escHtml(state)}">${escHtml(state)}</span></div>
      ${item ? researchAuthorityMarkup('Current exact section', value, allowedFields) : '<p class="research-missing-value">The exact saved occurrence is not present in the current source rows.</p>'}
    </section>`;
  }

  function renderResearchConsideration(consideration, compact = false) {
    const article = document.createElement('article');
    article.className = compact ? 'research-compact-item' : 'research-consideration-card';
    const currentItem = researchProjection.items.find(item => item.id === consideration.research_record_id) || null;
    const snapshot = consideration.snapshot;
    const snapshotTitle = Object.prototype.hasOwnProperty.call(snapshot.external_facts, 'title')
      ? snapshot.external_facts.title
      : 'Title field missing';
    article.innerHTML = `
      <header class="research-card-header">
        <div>
          <span class="research-type">${escHtml(consideration.item_type === 'trial' ? 'Clinical trial consideration' : 'Research paper consideration')}</span>
          <h3>${escHtml(snapshotTitle === null ? 'Title is null' : snapshotTitle === '' ? 'Title is empty' : String(snapshotTitle))}</h3>
        </div>
        <span class="research-workflow-state ${escHtml(consideration.status)}">${escHtml(consideration.status)}</span>
      </header>
      <p class="research-attribution">${escHtml(RESEARCH_AUTHORITY_LABELS.caregiver_workflow)}</p>
    `;
    if (!compact) {
      article.insertAdjacentHTML('beforeend', `
        <div class="research-snapshot-current-grid">
          <section class="research-snapshot-section" aria-label="Immutable saved snapshot">
            <h3>Immutable saved snapshot</h3>
            ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.external_facts, snapshot.external_facts, RESEARCH_EXTERNAL_FIELDS[consideration.item_type])}
            ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.generated_context, snapshot.generated_context, RESEARCH_GENERATED_FIELDS[consideration.item_type])}
            ${researchAuthorityMarkup(RESEARCH_AUTHORITY_LABELS.discovery_provenance, snapshot.discovery_provenance, RESEARCH_DISCOVERY_FIELDS[consideration.item_type])}
          </section>
          <section class="research-current-section-group" aria-label="Current exact occurrence">
            <div class="research-current-heading"><h3>Current exact occurrence</h3><span class="research-change-state ${escHtml(consideration.current_state.occurrence)}">${escHtml(consideration.current_state.occurrence)}</span></div>
            ${researchCurrentSectionMarkup(consideration, currentItem, 'external_facts', RESEARCH_AUTHORITY_LABELS.external_facts, RESEARCH_EXTERNAL_FIELDS[consideration.item_type])}
            ${researchCurrentSectionMarkup(consideration, currentItem, 'generated_context', RESEARCH_AUTHORITY_LABELS.generated_context, RESEARCH_GENERATED_FIELDS[consideration.item_type])}
            ${researchCurrentSectionMarkup(consideration, currentItem, 'discovery_provenance', RESEARCH_AUTHORITY_LABELS.discovery_provenance, RESEARCH_DISCOVERY_FIELDS[consideration.item_type])}
          </section>
        </div>
        <section class="research-events-section"><h3>Caregiver-entered events</h3>
          ${consideration.events.length ? `<ol class="research-history-list">${consideration.events.map(event => `<li>
            <div class="research-history-heading"><strong>${escHtml(RESEARCH_EVENT_LABELS[event.event_type])}</strong><span>${escHtml(event.occurred_on === null ? 'No event date entered' : event.occurred_on)}</span></div>
            <p class="research-attribution">${escHtml(event.provenance.label)}</p>
            <div class="research-event-note">${researchValueMarkup(event.note)}</div>
            <dl class="research-event-meta"><div><dt>Who</dt><dd>${researchValueMarkup(event.who)}</dd></div><div><dt>Context</dt><dd>${researchValueMarkup(event.context)}</dd></div><div><dt>Recorded</dt><dd>${researchValueMarkup(event.recorded_at)}</dd></div></dl>
          </li>`).join('')}</ol>` : '<p class="research-empty-value">No caregiver events are recorded.</p>'}
        </section>
        <section class="research-events-section"><h3>Lifecycle history</h3>
          ${consideration.history.length ? `<div class="research-scroll-region" role="region" aria-label="Lifecycle history in server order" tabindex="0"><table class="research-history-table"><thead><tr><th>Operation</th><th>Recorded</th><th>Exact changes</th></tr></thead><tbody>${consideration.history.map(entry => `<tr><td>${escHtml(entry.operation)}</td><td>${escHtml(entry.at)}</td><td><pre>${escHtml(JSON.stringify(entry.changes, null, 2))}</pre></td></tr>`).join('')}</tbody></table></div>` : '<p class="research-empty-value">No lifecycle history is recorded.</p>'}
        </section>
        <section class="research-follow-up-summary"><h3>Durable follow-up</h3>
          ${consideration.follow_up ? `<dl class="research-event-meta"><div><dt>Text</dt><dd>${researchValueMarkup(consideration.follow_up.text)}</dd></div><div><dt>Status</dt><dd>${researchValueMarkup(consideration.follow_up.status)}</dd></div><div><dt>Owner</dt><dd>${researchValueMarkup(consideration.follow_up.owner)}</dd></div><div><dt>Due date</dt><dd>${researchValueMarkup(consideration.follow_up.due_date)}</dd></div></dl>` : '<p class="research-empty-value">No caregiver follow-up is linked.</p>'}
        </section>
      `);
    }
    const actions = document.createElement('div');
    actions.className = 'research-card-actions';
    appendResearchControl(actions, 'Record event', { kind: 'event', value: consideration }, 'primary');
    if (consideration.eligibility.close.eligible) {
      appendResearchControl(actions, 'Close consideration', { kind: 'close', value: consideration });
    }
    if (consideration.eligibility.resume.eligible) {
      appendResearchControl(actions, 'Resume consideration', { kind: 'resume', value: consideration });
    }
    if (consideration.eligibility.follow_up_variants.length) {
      appendResearchControl(actions, consideration.follow_up ? 'Unlink follow-up' : 'Link or create follow-up', { kind: 'follow-up', value: consideration });
    }
    article.appendChild(actions);
    return article;
  }

  function setResearchStatus(message, tone = '') {
    for (const id of ['research-status', 'today-research-status']) {
      const node = document.getElementById(id);
      if (!node) continue;
      node.textContent = message || '';
      node.className = `research-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
    }
    const labels = {
      current: 'Current',
      loading: 'Loading',
      stale: 'Stale · read-only',
      error: 'Unavailable',
      idle: 'Not loaded',
    };
    for (const id of ['research-freshness', 'today-research-freshness']) {
      const node = document.getElementById(id);
      if (!node) continue;
      node.textContent = labels[researchProjectionState] || labels.idle;
      node.className = `research-freshness ${safeClassToken(researchProjectionState, 'idle')}`;
    }
  }

  function renderResearchWorkspace() {
    const currentList = document.getElementById('research-occurrence-list');
    const considerationList = document.getElementById('research-consideration-list');
    const todayLatest = document.getElementById('today-latest-research-list');
    const todayOpen = document.getElementById('today-open-consideration-list');
    if (!researchProjection) {
      const copy = researchProjectionState === 'loading'
        ? 'Loading authoritative research…'
        : 'No verified research workspace is available.';
      [currentList, considerationList, todayLatest, todayOpen].forEach(node => {
        if (node) node.innerHTML = `<div class="research-empty-state">${escHtml(copy)}</div>`;
      });
      document.getElementById('research-count-current').textContent = '0';
      document.getElementById('research-count-considerations').textContent = '0';
      document.getElementById('today-latest-research-totals').textContent = 'No latest-batch totals are available.';
      document.getElementById('today-open-consideration-totals').textContent = 'No consideration totals are available.';
      return;
    }
    currentList.replaceChildren();
    considerationList.replaceChildren();
    researchProjection.items.forEach(item => currentList.appendChild(renderResearchOccurrence(item)));
    researchProjection.considerations.forEach(item => considerationList.appendChild(renderResearchConsideration(item)));
    if (!researchProjection.items.length) currentList.innerHTML = '<div class="research-empty-state">No current research occurrences are present in the authoritative workspace.</div>';
    if (!researchProjection.considerations.length) considerationList.innerHTML = '<div class="research-empty-state">No caregiver considerations are recorded.</div>';
    document.getElementById('research-count-current').textContent = String(researchProjection.item_count);
    document.getElementById('research-count-considerations').textContent = String(researchProjection.consideration_count);

    const latest = researchProjection.items.filter(item => item.latest_batch_member);
    const open = researchProjection.considerations.filter(item => item.status === 'open');
    const latestVisible = latest.slice(0, 3);
    const openVisible = open.slice(0, 3);
    todayLatest.replaceChildren();
    todayOpen.replaceChildren();
    latestVisible.forEach(item => todayLatest.appendChild(renderResearchOccurrence(item, true)));
    openVisible.forEach(item => todayOpen.appendChild(renderResearchConsideration(item, true)));
    if (!latestVisible.length) todayLatest.innerHTML = '<div class="research-empty-state">The server reports no current exact latest-batch occurrences.</div>';
    if (!openVisible.length) todayOpen.innerHTML = '<div class="research-empty-state">No open caregiver considerations are recorded.</div>';
    const trialTotal = latest.filter(item => item.item_type === 'trial').length;
    const paperTotal = latest.filter(item => item.item_type === 'paper').length;
    document.getElementById('today-latest-research-totals').textContent =
      `${latest.length} exact latest-batch occurrence${latest.length === 1 ? '' : 's'} (${trialTotal} trial${trialTotal === 1 ? '' : 's'}, ${paperTotal} paper${paperTotal === 1 ? '' : 's'}). Showing ${latestVisible.length}; ${Math.max(0, latest.length - latestVisible.length)} omitted from Today.`;
    document.getElementById('today-open-consideration-totals').textContent =
      `${open.length} open consideration${open.length === 1 ? '' : 's'}. Showing ${openVisible.length}; ${Math.max(0, open.length - openVisible.length)} omitted from Today.`;
    document.querySelectorAll('.research-mutation-control').forEach(control => {
      control.disabled = researchProjectionState !== 'current' || researchMutationPending;
    });
  }

  function selectResearchTab(name, focus = false) {
    if (!['current', 'considerations'].includes(name)) return;
    if (researchActiveTab !== name) {
      researchActiveTab = name;
      researchSelectionEpoch += 1;
      if (researchDialogOpen) closeResearchDialog(false);
    }
    for (const value of ['current', 'considerations']) {
      const active = value === name;
      const tab = document.getElementById(`research-tab-${value}`);
      const panel = document.getElementById(`research-panel-${value}`);
      tab?.classList.toggle('active', active);
      tab?.setAttribute('aria-selected', String(active));
      if (tab) tab.tabIndex = active ? 0 : -1;
      if (panel) panel.hidden = !active;
    }
    if (focus) document.getElementById(`research-tab-${name}`)?.focus();
  }

  function handleResearchTabKeydown(event) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' || event.key === 'ArrowLeft' ? 'current' : 'considerations';
    selectResearchTab(next, true);
  }

  function openResearchWorkspace() {
    switchView('research', document.getElementById('nav-research'));
    document.getElementById('research-workspace-heading')?.focus();
  }

  function markResearchProjectionStale(message, options = {}) {
    researchProjectionState = 'stale';
    researchNetworkAmbiguous = options.networkAmbiguous === true;
    if (options.abortRequest !== false && researchRequestController) {
      researchRequestController.abort();
      researchRequestController = null;
      researchLoadEpoch += 1;
    }
    setResearchStatus(message || 'Research is read-only until the authoritative workspace reloads.', 'stale');
    document.getElementById('research-retry').hidden = false;
    document.getElementById('research-retry-message').textContent = message || 'Research needs a fresh authoritative workspace.';
    document.getElementById('today-research-retry-refresh').hidden = false;
    renderResearchWorkspace();
  }

  function relocateResearchFocus() {
    const researchRoot = document.getElementById('research-workspace');
    const todayRoot = document.getElementById('research-today-card');
    const dialog = document.getElementById('research-dialog');
    if (
      researchRoot?.contains(document.activeElement)
      || todayRoot?.contains(document.activeElement)
      || dialog?.contains(document.activeElement)
    ) {
      (document.getElementById(`nav-${activeView}`) || document.getElementById('nav-today'))?.focus();
    }
  }

  function clearResearchProjection(options = {}) {
    relocateResearchFocus();
    researchLoadEpoch += 1;
    researchSelectionEpoch += 1;
    researchDialogEpoch += 1;
    researchMutationEpoch += 1;
    researchRequestController?.abort();
    researchMutationController?.abort();
    researchRequestController = null;
    researchMutationController = null;
    researchProjection = null;
    researchResponseOwner = null;
    researchProjectionState = options.state || 'error';
    researchNetworkAmbiguous = false;
    researchMutationOwner = null;
    researchMutationPending = false;
    activeResearchIntent = null;
    if (pendingResearchSubmission) pendingResearchSubmission.bodyText = '';
    pendingResearchSubmission = null;
    pendingResearchCompletion = null;
    researchDraft = null;
    closeResearchDialog(false);
    setResearchStatus(
      options.message || 'Research authority could not be verified safely. No prior research content remains in this view.',
      'error',
    );
    const retry = options.retry !== false;
    document.getElementById('research-retry').hidden = !retry;
    document.getElementById('today-research-retry-refresh').hidden = !retry;
    renderResearchWorkspace();
  }

  async function loadResearchWorkspace(options = {}) {
    if (
      researchRequestController
      && options.force !== true
    ) return null;
    if (researchRequestController) researchRequestController.abort();
    const controller = new AbortController();
    const request = capturePatientRequest();
    const loadEpoch = ++researchLoadEpoch;
    researchRequestController = controller;
    const owner = {};
    const current = () => (
      researchRequestController === controller
      && loadEpoch === researchLoadEpoch
      && request.requestPhiEpoch === phiEpoch
    );
    if (!researchProjection) {
      researchProjectionState = 'loading';
      setResearchStatus('Loading the authoritative research workspace…', 'loading');
      renderResearchWorkspace();
    }
    try {
      const response = await fetch('/api/patient/research-workspace', { signal: controller.signal });
      if (!current()) return null;
      const raw = await readJsonResponse(response, current);
      if (!current()) return null;
      const projection = validateResearchWorkspace(raw);
      if (
        researchProjection
        && (
          projection.profile_revision < researchProjection.profile_revision
          || projection.workflow_revision < researchProjection.workflow_revision
        )
      ) return null;
      const authority = authorizePatientResponse(request, projection, {
        workflow: 'projection',
        researchProjection: true,
      });
      request.requestPhiEpoch = authority.requestPhiEpoch;
      if (!authority.accepted || !current()) return null;
      syncChatRevision(projection.profile_revision, false, false);
      const unchangedAuthority = researchProjection?.projection_token === projection.projection_token
        && researchProjection.profile_revision === projection.profile_revision
        && researchProjection.workflow_revision === projection.workflow_revision;
      const wasReadOnly = researchProjectionState !== 'current';
      if (!unchangedAuthority) relocateResearchFocus();
      researchProjection = projection;
      researchResponseOwner = owner;
      researchProjectionState = 'current';
      researchNetworkAmbiguous = false;
      document.getElementById('research-retry').hidden = true;
      document.getElementById('today-research-retry-refresh').hidden = true;
      setResearchStatus(
        projection.items.length || projection.considerations.length
          ? 'Authoritative research workspace loaded.'
          : 'Authoritative research workspace loaded with no current occurrences or considerations.',
        'current',
      );
      if (!unchangedAuthority || wasReadOnly || pendingResearchCompletion) renderResearchWorkspace();
      const verified = verifyResearchCompletion(projection);
      if (!verified && pendingResearchCompletion) {
        markResearchProjectionStale(
          'The mutation response was accepted, but the replacement workspace did not confirm the expected result. Retry refresh only.',
        );
        showResearchRefreshRetry('The save was accepted, but replacement verification is incomplete.');
      }
      if (researchDialogOpen && !pendingResearchCompletion) revalidateResearchDialogSelection();
      reportLoadSuccess('research');
      return projection;
    } catch (error) {
      if (!current() || error?.name === 'AbortError') return null;
      if (error?.status === 401 || error?.status === 403) {
        reportLoadError('research', error);
        evictClientPhi(error);
        return null;
      }
      const ambiguous = error instanceof TypeError || navigator.onLine === false;
      if (ambiguous && researchProjection) {
        markResearchProjectionStale(
          'Research refresh is ambiguous. The last verified workspace remains visible and read-only.',
          { networkAmbiguous: true, abortRequest: false },
        );
      } else {
        clearResearchProjection({
          state: 'error',
          message: error?.status === 422
            ? 'Research authority could not be verified safely. The research workspace was cleared.'
            : 'Research could not be loaded. The research workspace was cleared.',
          retry: true,
        });
      }
      reportLoadError('research', new Error('Research workspace is unavailable.'));
      return null;
    } finally {
      if (researchRequestController === controller && loadEpoch === researchLoadEpoch) {
        researchRequestController = null;
      }
    }
  }

  function researchSelectionStillCurrent(selection) {
    if (!researchProjection || !selection) return false;
    const collection = selection.kind === 'item' ? researchProjection.items : researchProjection.considerations;
    return collection.some(value => value.id === selection.id && value.token === selection.token);
  }

  function revalidateResearchDialogSelection() {
    if (researchConflictRequiresReselection) {
      researchConflictRequiresReselection = false;
      closeResearchDialog(false, true);
      setResearchStatus('Research changed during the request. Select a current row to review the retained caregiver draft.', 'stale');
      return false;
    }
    if (researchSelectionStillCurrent(researchSelection)) return true;
    closeResearchDialog(false);
    setResearchStatus('The selected research authority changed. Select the current row again.', 'stale');
    return false;
  }

  function setResearchDialogStatus(message, tone = '') {
    const node = document.getElementById('research-dialog-status');
    node.textContent = message || '';
    node.className = `follow-up-dialog-status${tone ? ` ${safeClassToken(tone)}` : ''}`;
  }

  function scrubResearchDialogFields() {
    for (const id of [
      'research-event-note', 'research-event-who', 'research-event-context', 'research-event-date',
      'research-follow-up-text', 'research-follow-up-owner', 'research-follow-up-due',
    ]) {
      const input = document.getElementById(id);
      if (input) input.value = '';
    }
    document.getElementById('research-event-type').replaceChildren();
    document.getElementById('research-follow-up-existing-action').replaceChildren();
    document.getElementById('research-follow-up-modes').replaceChildren(
      Object.assign(document.createElement('legend'), { textContent: 'Follow-up operation' })
    );
    for (const id of [
      'research-shortlist-error', 'research-event-error', 'research-lifecycle-error',
      'research-follow-up-error', 'research-dialog-context', 'research-follow-up-linked-copy',
    ]) {
      const node = document.getElementById(id);
      if (node) node.textContent = '';
    }
    setResearchDialogStatus('');
    clearResearchRetry();
  }

  function closeResearchDialog(restoreFocus = true, preserveDraft = false) {
    const overlay = document.getElementById('research-dialog-overlay');
    const dialog = document.getElementById('research-dialog');
    researchDialogOpen = false;
    researchDialogMode = null;
    researchSelection = null;
    researchSelectionEpoch += 1;
    researchDialogEpoch += 1;
    if (!preserveDraft) researchDraft = null;
    researchConflictRequiresReselection = false;
    scrubResearchDialogFields();
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    deactivateDialog(dialog, restoreFocus);
  }

  function closeResearchDialogFromBackdrop(event) {
    if (event.target === document.getElementById('research-dialog-overlay')) closeResearchDialog();
  }

  function researchDialogContextMarkup(value) {
    const item = value.snapshot
      ? { item_type: value.item_type, external_facts: value.snapshot.external_facts, source_identity: { external_id: value.snapshot.external_facts[value.item_type === 'trial' ? 'nct_id' : 'pmid'] } }
      : value;
    return `<h3 id="research-dialog-context-heading">${escHtml(researchItemTitle(item))}</h3>
      <p>${escHtml(item.item_type === 'trial' ? 'Clinical trial' : 'Research paper')} · ${escHtml(researchIdentityLabel(item))}</p>`;
  }

  function openResearchDialog(mode, value, trigger) {
    if (researchProjectionState !== 'current' || researchMutationPending) return;
    const isItem = mode === 'shortlist';
    const current = (isItem ? researchProjection.items : researchProjection.considerations)
      .find(item => item.id === value.id && item.token === value.token);
    if (!current) return;
    researchDialogMode = mode;
    researchDialogOpen = true;
    researchSelectionEpoch += 1;
    researchDialogEpoch += 1;
    researchSelection = {
      kind: isItem ? 'item' : 'consideration',
      id: current.id,
      token: current.token,
    };
    const retainedDraft = researchDraft;
    researchDraft = null;
    scrubResearchDialogFields();
    const titles = {
      shortlist: 'Save exact occurrence',
      event: 'Record caregiver event',
      close: 'Close caregiver consideration',
      resume: 'Resume caregiver consideration',
      'follow-up': current.follow_up ? 'Unlink durable follow-up' : 'Link or create durable follow-up',
    };
    document.getElementById('research-dialog-title').textContent = titles[mode];
    document.getElementById('research-dialog-context').innerHTML = researchDialogContextMarkup(current);
    for (const form of ['shortlist', 'event', 'lifecycle', 'follow-up']) {
      document.getElementById(`research-${form}-form`).hidden = !(
        form === mode || (form === 'lifecycle' && ['close', 'resume'].includes(mode))
      );
    }
    if (mode === 'event') configureResearchEventForm(current);
    if (['close', 'resume'].includes(mode)) configureResearchLifecycleForm(mode, current);
    if (mode === 'follow-up') configureResearchFollowUpForm(current);
    restoreResearchDraft(retainedDraft);
    const overlay = document.getElementById('research-dialog-overlay');
    const dialog = document.getElementById('research-dialog');
    overlay.inert = false;
    dialog.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    activateDialog(dialog, trigger);
  }

  function configureResearchEventForm(consideration) {
    const select = document.getElementById('research-event-type');
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Choose an allowed event type';
    select.appendChild(placeholder);
    consideration.eligibility.allowed_event_types.forEach(type => {
      const option = document.createElement('option');
      option.value = type;
      option.textContent = RESEARCH_EVENT_LABELS[type];
      select.appendChild(option);
    });
    document.getElementById('research-event-submit').disabled = true;
  }

  function clearResearchSubmissionRetryOnly() {
    if (pendingResearchSubmission) pendingResearchSubmission.bodyText = '';
    pendingResearchSubmission = null;
    document.getElementById('research-retry-submission').hidden = true;
    if (!pendingResearchCompletion) document.getElementById('research-dialog-retry').hidden = true;
  }

  function changeResearchEventType() {
    clearResearchSubmissionRetryOnly();
    for (const id of ['research-event-note', 'research-event-who', 'research-event-context', 'research-event-date']) {
      document.getElementById(id).value = '';
    }
    const type = document.getElementById('research-event-type').value;
    const attribution = type === 'treating_team_communication'
      ? RESEARCH_ATTRIBUTION_LABELS.clinician
      : type === 'trial_site_communication'
        ? RESEARCH_ATTRIBUTION_LABELS.trial_site
        : type ? RESEARCH_ATTRIBUTION_LABELS.caregiver : 'Choose an allowed event type.';
    document.getElementById('research-event-attribution').textContent =
      type ? `Attribution preview · ${attribution}` : attribution;
    document.getElementById('research-event-submit').disabled = !type;
    researchDraft = null;
  }

  function configureResearchLifecycleForm(mode, consideration) {
    const close = mode === 'close';
    document.getElementById('research-lifecycle-copy').textContent = close
      ? 'Closing stops active caregiver consideration only. It does not mean this research is irrelevant, unavailable, unsuitable, ineligible, or rejected.'
      : 'Resuming returns this caregiver consideration to the open workflow and preserves every prior event and lifecycle history item.';
    document.getElementById('research-lifecycle-submit').textContent = close ? 'Close consideration' : 'Resume consideration';
    const eligible = close ? consideration.eligibility.close.eligible : consideration.eligibility.resume.eligible;
    document.getElementById('research-lifecycle-submit').disabled = !eligible;
  }

  function configureResearchFollowUpForm(consideration) {
    const fieldset = document.getElementById('research-follow-up-modes');
    const legend = document.createElement('legend');
    legend.textContent = 'Follow-up operation';
    fieldset.replaceChildren(legend);
    consideration.eligibility.follow_up_variants.forEach((variant, index) => {
      const label = document.createElement('label');
      label.className = 'research-follow-up-mode';
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'research-follow-up-mode';
      input.value = variant;
      input.checked = index === 0;
      input.addEventListener('change', updateResearchFollowUpMode);
      label.append(input, document.createTextNode({
        link_existing: 'Link one current eligible action',
        create_and_link: 'Create one manual action and link atomically',
        unlink: 'Unlink the current action',
      }[variant]));
      fieldset.appendChild(label);
    });
    const select = document.getElementById('research-follow-up-existing-action');
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Choose a current eligible action';
    select.appendChild(placeholder);
    researchProjection.eligible_actions.forEach((action, index) => {
      const option = document.createElement('option');
      option.value = String(index + 1);
      option.textContent = action.text;
      researchActionOptionAuthority.set(option, action);
      select.appendChild(option);
    });
    select.onchange = updateResearchFollowUpValidity;
    document.getElementById('research-follow-up-linked-copy').textContent = consideration.follow_up
      ? `Current linked action: ${consideration.follow_up.text}`
      : '';
    updateResearchFollowUpMode();
  }

  function selectedResearchFollowUpMode() {
    return document.querySelector('input[name="research-follow-up-mode"]:checked')?.value || '';
  }

  function updateResearchFollowUpMode() {
    clearResearchSubmissionRetryOnly();
    const mode = selectedResearchFollowUpMode();
    document.getElementById('research-follow-up-existing-panel').hidden = mode !== 'link_existing';
    document.getElementById('research-follow-up-inline-panel').hidden = mode !== 'create_and_link';
    document.getElementById('research-follow-up-unlink-panel').hidden = mode !== 'unlink';
    document.getElementById('research-follow-up-existing-action').selectedIndex = 0;
    for (const id of ['research-follow-up-text', 'research-follow-up-owner', 'research-follow-up-due']) {
      document.getElementById(id).value = '';
    }
    researchDraft = null;
    updateResearchFollowUpValidity();
  }

  function updateResearchFollowUpValidity() {
    const mode = selectedResearchFollowUpMode();
    const valid = mode === 'unlink'
      || (mode === 'link_existing' && document.getElementById('research-follow-up-existing-action').selectedIndex > 0)
      || (mode === 'create_and_link' && Boolean(document.getElementById('research-follow-up-text').value.trim()));
    document.getElementById('research-follow-up-submit').disabled = !valid;
  }

  function captureResearchDraft() {
    if (!researchDialogOpen) return null;
    if (researchDialogMode === 'event') {
      return {
        kind: 'event',
        event_type: document.getElementById('research-event-type').value,
        note: document.getElementById('research-event-note').value,
        who: document.getElementById('research-event-who').value,
        context: document.getElementById('research-event-context').value,
        occurred_on: document.getElementById('research-event-date').value,
      };
    }
    if (researchDialogMode === 'follow-up' && selectedResearchFollowUpMode() === 'create_and_link') {
      return {
        kind: 'follow-up',
        text: document.getElementById('research-follow-up-text').value,
        owner: document.getElementById('research-follow-up-owner').value,
        due_date: document.getElementById('research-follow-up-due').value,
      };
    }
    return null;
  }

  function restoreResearchDraft(draft) {
    if (!draft) return false;
    if (researchDialogMode === 'event' && draft.kind === 'event') {
      const consideration = researchSelectedAuthority();
      if (!consideration?.eligibility.allowed_event_types.includes(draft.event_type)) return false;
      document.getElementById('research-event-type').value = draft.event_type;
      changeResearchEventType();
      document.getElementById('research-event-note').value = draft.note;
      document.getElementById('research-event-who').value = draft.who;
      document.getElementById('research-event-context').value = draft.context;
      document.getElementById('research-event-date').value = draft.occurred_on;
    } else if (researchDialogMode === 'follow-up' && draft.kind === 'follow-up') {
      const mode = document.querySelector('input[name="research-follow-up-mode"][value="create_and_link"]');
      if (!mode) return false;
      mode.checked = true;
      updateResearchFollowUpMode();
      document.getElementById('research-follow-up-text').value = draft.text;
      document.getElementById('research-follow-up-owner').value = draft.owner;
      document.getElementById('research-follow-up-due').value = draft.due_date;
      updateResearchFollowUpValidity();
    } else {
      return false;
    }
    researchDraft = captureResearchDraft();
    setResearchDialogStatus('Caregiver-entered draft restored after authority reload. Review it before submitting.', 'conflict');
    return true;
  }

  function handleResearchDraftChange() {
    if (pendingResearchSubmission) {
      clearResearchSubmissionRetryOnly();
      setResearchDialogStatus('The caregiver draft changed. Submit it as a new request after review.', 'conflict');
    }
    researchDraft = captureResearchDraft();
    if (researchDialogMode === 'follow-up') updateResearchFollowUpValidity();
  }

  function clearResearchRetry() {
    clearResearchSubmissionRetryOnly();
    pendingResearchCompletion = null;
    document.getElementById('research-retry-verification').hidden = true;
    document.getElementById('research-dialog-retry').hidden = true;
    document.getElementById('research-dialog-retry-message').textContent = '';
  }

  function showResearchSubmissionRetry(message) {
    document.getElementById('research-dialog-retry').hidden = false;
    document.getElementById('research-dialog-retry-message').textContent = message;
    document.getElementById('research-retry-submission').hidden = false;
    document.getElementById('research-retry-verification').hidden = true;
  }

  function showResearchRefreshRetry(message) {
    document.getElementById('research-dialog-retry').hidden = false;
    document.getElementById('research-dialog-retry-message').textContent = message;
    document.getElementById('research-retry-submission').hidden = true;
    document.getElementById('research-retry-verification').hidden = false;
  }

  function researchBaseMutationBody() {
    if (!researchProjection) throw new Error('Reload the research workspace before saving.');
    return {
      mutation_id: newMutationId(),
      expected_profile_revision: researchProjection.profile_revision,
      expected_workflow_revision: researchProjection.workflow_revision,
      expected_projection_token: researchProjection.projection_token,
    };
  }

  function beginResearchMutation(allowStale = false) {
    if (
      researchMutationPending
      || (researchProjectionState !== 'current' && !(allowStale && researchProjectionState === 'stale'))
    ) return null;
    const owner = {};
    researchMutationOwner = owner;
    researchMutationPending = true;
    researchMutationEpoch += 1;
    researchMutationController = new AbortController();
    renderResearchWorkspace();
    return owner;
  }

  function releaseResearchMutation(intent) {
    if (researchMutationOwner !== intent.mutationOwner) return false;
    researchMutationOwner = null;
    researchMutationPending = false;
    if (researchMutationController === intent.controller) researchMutationController = null;
    if (activeResearchIntent === intent) activeResearchIntent = null;
    renderResearchWorkspace();
    return true;
  }

  function createResearchIntent(method, url, body, expected) {
    const owner = beginResearchMutation();
    if (!owner) return null;
    const bodyText = JSON.stringify(body);
    return {
      method,
      url,
      bodyText,
      expected,
      mutationOwner: owner,
      mutationEpoch: researchMutationEpoch,
      controller: researchMutationController,
      requestPhiEpoch: phiEpoch,
      selectionEpoch: researchSelectionEpoch,
      dialogEpoch: researchDialogEpoch,
    };
  }

  function researchIntentCurrent(intent) {
    return researchMutationPending
      && researchMutationOwner === intent.mutationOwner
      && researchMutationEpoch === intent.mutationEpoch
      && researchMutationController === intent.controller
      && phiEpoch === intent.requestPhiEpoch
      && researchSelectionEpoch === intent.selectionEpoch
      && researchDialogEpoch === intent.dialogEpoch;
  }

  function expectedResearchCompletion(intent, response) {
    const result = response.consideration;
    const expected = {
      profile_revision: response.profile_revision,
      workflow_revision: response.workflow_revision,
      consideration_id: result.id,
      record_id: result.research_record_id,
      mode: intent.expected.mode,
    };
    if (intent.expected.mode === 'event') {
      const prior = new Set(intent.expected.priorEventIds);
      const added = result.events.filter(event => !prior.has(event.id));
      if (added.length !== 1 || added[0].event_type !== intent.expected.eventType) {
        throw new Error('Research mutation response did not contain the expected event.');
      }
      expected.event_id = added[0].id;
    } else if (['close', 'resume'].includes(intent.expected.mode)) {
      expected.status = intent.expected.mode === 'close' ? 'closed' : 'open';
      if (result.status !== expected.status) throw new Error('Research lifecycle response is inconsistent.');
    } else if (intent.expected.mode === 'follow-up') {
      expected.follow_up_id = result.follow_up?.id || null;
      if (intent.expected.followUpMode === 'unlink' && result.follow_up !== null) {
        throw new Error('Research unlink response is inconsistent.');
      }
      if (intent.expected.followUpMode !== 'unlink' && result.follow_up === null) {
        throw new Error('Research follow-up response is inconsistent.');
      }
    }
    return expected;
  }

  function verifyResearchCompletion(projection) {
    const expected = pendingResearchCompletion;
    if (!expected) return true;
    if (
      projection.profile_revision !== expected.profile_revision
      || projection.workflow_revision !== expected.workflow_revision
    ) return false;
    const consideration = projection.considerations.find(item => item.id === expected.consideration_id);
    if (!consideration || consideration.research_record_id !== expected.record_id) return false;
    if (expected.event_id && !consideration.events.some(event => event.id === expected.event_id)) return false;
    if (expected.status && consideration.status !== expected.status) return false;
    if ('follow_up_id' in expected && (consideration.follow_up?.id || null) !== expected.follow_up_id) return false;
    pendingResearchCompletion = null;
    researchDraft = null;
    closeResearchDialog();
    setResearchStatus('Saved and verified against the complete authoritative research workspace.', 'current');
    return true;
  }

  async function performResearchIntent(intent, explicitRetry = false) {
    if (!intent || !researchIntentCurrent(intent)) return null;
    activeResearchIntent = intent;
    if (explicitRetry) {
      pendingResearchSubmission = null;
      document.getElementById('research-retry-submission').hidden = true;
    } else {
      clearResearchSubmissionRetryOnly();
    }
    setResearchDialogStatus(explicitRetry ? 'Retrying the unchanged request…' : 'Saving…', 'saving');
    try {
      const response = await fetch(intent.url, {
        method: intent.method,
        headers: { 'Content-Type': 'application/json' },
        body: intent.bodyText,
        signal: intent.controller.signal,
      });
      if (!researchIntentCurrent(intent)) return null;
      const raw = await readJsonResponse(response, () => researchIntentCurrent(intent));
      if (!researchIntentCurrent(intent)) return null;
      const expectedId = intent.expected.considerationId || null;
      const data = validateResearchMutationResponse(raw, expectedId);
      if (!researchIntentCurrent(intent)) return null;
      intent.requestPhiEpoch = phiEpoch;
      pendingResearchCompletion = expectedResearchCompletion(intent, data);
      clearResearchSubmissionRetryOnly();
      markResearchProjectionStale(
        'The request was accepted. Research is read-only while the complete workspace verifies the result.',
        { abortRequest: false },
      );
      showResearchRefreshRetry('The request was accepted. Verifying the complete workspace…');
      releaseResearchMutation(intent);
      await loadResearchWorkspace({ force: true });
      return data;
    } catch (error) {
      if (!researchIntentCurrent(intent)) return null;
      if (error?.status === 401 || error?.status === 403) {
        evictClientPhi(error);
        return null;
      }
      if (error?.status === 409) {
        researchDraft = captureResearchDraft();
        researchConflictRequiresReselection = true;
        clearResearchSubmissionRetryOnly();
        setResearchDialogStatus('The research workspace changed. Review the reloaded authority before submitting again.', 'conflict');
        releaseResearchMutation(intent);
        markResearchProjectionStale('Research changed during the request. Reloading authoritative workspace.', { abortRequest: false });
        await loadResearchWorkspace({ force: true });
        return null;
      }
      if (error instanceof TypeError || navigator.onLine === false) {
        researchDraft = captureResearchDraft();
        pendingResearchSubmission = intent;
        markResearchProjectionStale(
          'The submission result is ambiguous. Research remains visible and read-only until authority reloads.',
          { networkAmbiguous: true, abortRequest: false },
        );
        showResearchSubmissionRetry('Submission status is unknown. Retry only the unchanged request.');
        releaseResearchMutation(intent);
        return null;
      }
      if ([400, 404, 422].includes(error?.status)) {
        researchDraft = captureResearchDraft();
        setResearchDialogStatus('The request was not accepted. Review the caregiver-entered fields and current authority.', 'error');
        releaseResearchMutation(intent);
        return null;
      }
      setResearchDialogStatus('The request could not be saved.', 'error');
      releaseResearchMutation(intent);
      return null;
    } finally {
      releaseResearchMutation(intent);
    }
  }

  function researchSelectedAuthority() {
    if (!researchSelection || !researchProjection) return null;
    const collection = researchSelection.kind === 'item'
      ? researchProjection.items
      : researchProjection.considerations;
    return collection.find(value => value.id === researchSelection.id && value.token === researchSelection.token) || null;
  }

  async function submitResearchShortlist() {
    const item = researchSelectedAuthority();
    if (!item || !item.shortlist.eligible) return;
    const body = {
      ...researchBaseMutationBody(),
      research_record_id: item.id,
      expected_item_token: item.token,
    };
    const intent = createResearchIntent('POST', '/api/research-considerations', body, {
      mode: 'shortlist',
      recordId: item.id,
    });
    if (intent) await performResearchIntent(intent);
  }

  async function submitResearchEvent() {
    const consideration = researchSelectedAuthority();
    const eventType = document.getElementById('research-event-type').value;
    const note = document.getElementById('research-event-note').value;
    const who = document.getElementById('research-event-who').value;
    const context = document.getElementById('research-event-context').value;
    const occurredOn = document.getElementById('research-event-date').value;
    if (
      !consideration
      || !consideration.eligibility.allowed_event_types.includes(eventType)
      || !note.trim()
      || note.length > 20000
      || who.length > 500
      || context.length > 2000
      || (occurredOn && researchPartialDatePrecision(occurredOn) === null)
    ) {
      setFormError('research-event-error', 'Enter an allowed event type, a note, and an optional exact partial date.');
      return;
    }
    const body = {
      ...researchBaseMutationBody(),
      expected_consideration_token: consideration.token,
      event_type: eventType,
      note,
      who: who.trim() ? who : null,
      context: context.trim() ? context : null,
      occurred_on: occurredOn || null,
    };
    const intent = createResearchIntent(
      'POST',
      `/api/research-considerations/${encodeURIComponent(consideration.id)}/events`,
      body,
      {
        mode: 'event',
        considerationId: consideration.id,
        eventType,
        priorEventIds: consideration.events.map(event => event.id),
      },
    );
    if (intent) await performResearchIntent(intent);
  }

  async function submitResearchLifecycle() {
    const consideration = researchSelectedAuthority();
    const mode = researchDialogMode;
    const eligibility = mode === 'close' ? consideration?.eligibility.close : consideration?.eligibility.resume;
    if (!consideration || !eligibility?.eligible) return;
    const body = {
      ...researchBaseMutationBody(),
      expected_consideration_token: consideration.token,
    };
    const intent = createResearchIntent(
      'POST',
      `/api/research-considerations/${encodeURIComponent(consideration.id)}/${mode}`,
      body,
      { mode, considerationId: consideration.id },
    );
    if (intent) await performResearchIntent(intent);
  }

  async function submitResearchFollowUp() {
    const consideration = researchSelectedAuthority();
    const mode = selectedResearchFollowUpMode();
    if (!consideration || !consideration.eligibility.follow_up_variants.includes(mode)) return;
    const body = {
      ...researchBaseMutationBody(),
      expected_consideration_token: consideration.token,
    };
    if (mode === 'link_existing') {
      const option = document.getElementById('research-follow-up-existing-action').selectedOptions[0];
      const action = researchActionOptionAuthority.get(option);
      if (!action || !researchProjection.eligible_actions.some(value => value.id === action.id && value.token === action.token)) {
        setFormError('research-follow-up-error', 'Select a current eligible action.');
        return;
      }
      body.caregiver_action_id = action.id;
      body.expected_action_token = action.token;
    } else if (mode === 'create_and_link') {
      const text = document.getElementById('research-follow-up-text').value;
      const owner = document.getElementById('research-follow-up-owner').value;
      const dueDate = document.getElementById('research-follow-up-due').value;
      if (!text.trim() || text.length > 1000 || owner.length > 100) {
        setFormError('research-follow-up-error', 'Enter a bounded caregiver follow-up description.');
        return;
      }
      body.follow_up = {
        text,
        owner: owner.trim() ? owner : null,
        due_date: dueDate || null,
      };
    } else {
      if (!consideration.follow_up) return;
      body.caregiver_action_id = null;
      body.expected_action_token = consideration.follow_up.token;
    }
    const intent = createResearchIntent(
      'PATCH',
      `/api/research-considerations/${encodeURIComponent(consideration.id)}/follow-up`,
      body,
      {
        mode: 'follow-up',
        followUpMode: mode,
        considerationId: consideration.id,
      },
    );
    if (intent) await performResearchIntent(intent);
  }

  async function retryResearchSubmission() {
    const prior = pendingResearchSubmission;
    if (!prior?.bodyText) return;
    if (
      !researchDialogOpen
      || prior.selectionEpoch !== researchSelectionEpoch
      || prior.dialogEpoch !== researchDialogEpoch
    ) {
      clearResearchSubmissionRetryOnly();
      setResearchDialogStatus('Submission retry authority expired. Review and submit a new request.', 'conflict');
      return;
    }
    const owner = beginResearchMutation(true);
    if (!owner) return;
    const intent = {
      ...prior,
      mutationOwner: owner,
      mutationEpoch: researchMutationEpoch,
      controller: researchMutationController,
      requestPhiEpoch: phiEpoch,
    };
    pendingResearchSubmission = intent;
    await performResearchIntent(intent, true);
  }

  async function retryResearchRefresh() {
    if (!pendingResearchCompletion && !researchNetworkAmbiguous) return;
    await loadResearchWorkspace({ force: true });
  }

  // ── Task log ────────────────────────────────────────────────────────────
  async function loadTasks(options = {}) {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++taskLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
      && requestLoadEpoch === taskLoadEpoch
    );
    try {
      const r = await fetch('/api/jobs');
      if (!requestIsCurrent()) return null;
      const tasks = await readJsonResponse(r, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      if (
        !authorizePatientResponse(
          request,
          tasks,
          options.authorizationOptions || {},
        ).accepted
      ) return [];
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
    if (researchDialogOpen) {
      closeResearchDialog();
      return;
    }
    if (treatmentDialogOpen) {
      closeTreatmentDialog();
      return;
    }
    if (symptomDialogOpen) {
      closeSymptomDialog();
      return;
    }
    if (alertResolutionDialogOpen) {
      closeAlertResolutionDialog();
      return;
    }
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
      if (e instanceof TypeError || navigator.onLine === false) {
        markResearchProjectionStale(
          'The document submission result is ambiguous. Research remains read-only until authority reloads.',
          { networkAmbiguous: true },
        );
      }
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
      if (e instanceof TypeError || navigator.onLine === false) {
        markResearchProjectionStale(
          'The document submission result is ambiguous. Research remains read-only until authority reloads.',
          { networkAmbiguous: true },
        );
      }
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
      if (e instanceof TypeError || navigator.onLine === false) {
        markResearchProjectionStale(
          'The digest submission result is ambiguous. Research remains read-only until authority reloads.',
          { networkAmbiguous: true },
        );
      }
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
        markResearchProjectionStale(
          'A manual research source run completed. Reloading the authoritative research workspace.',
        );
        refreshes.push(loadResearchWorkspace({ force: true }));
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

  function revokeVisitRecapDownloadUrl() {
    if (!visitRecapDownloadUrl) return;
    try {
      URL.revokeObjectURL(visitRecapDownloadUrl);
    } finally {
      visitRecapDownloadUrl = null;
    }
  }

  function clearVisitRecap(scrubDom = false) {
    visitRecapLoadEpoch += 1;
    visitRecapExportEpoch += 1;
    visitRecapExportOwner = null;
    visitRecapNetworkAmbiguous = false;
    visitRecapProjection = null;
    visitRecapAuthority = null;
    visitRecapExportText = '';
    visitRecapStale = false;
    visitRecapState = 'idle';
    visitRecapMessage = '';
    revokeVisitRecapDownloadUrl();
    document.body?.classList.remove('visit-recap-printing');
    if (scrubDom) {
      const status = document.getElementById('visit-recap-status');
      const content = document.getElementById('visit-recap-content');
      if (status) {
        status.className = 'visit-recap-status idle';
        status.textContent = '';
      }
      if (content) content.textContent = '';
    }
    updateVisitRecapExportControls();
  }

  function scrubVisitRecapBeforeSelectionChange(nextVisitId, nextVisitToken = null) {
    const selectedVisit = currentVisit();
    const visitIdChanged = nextVisitId !== selectedVisitId;
    const visitTokenChanged = Boolean(
      !visitIdChanged
      && nextVisitId
      && selectedVisit?.token !== nextVisitToken
    );
    if (!visitIdChanged && !visitTokenChanged) return false;
    clearVisitRecap(true);
    return true;
  }

  function markVisitRecapStale(message, state = 'stale', preserveExportOwner = false) {
    visitRecapLoadEpoch += 1;
    if (!preserveExportOwner) {
      visitRecapExportEpoch += 1;
      visitRecapExportOwner = null;
    }
    visitRecapAuthority = null;
    visitRecapExportText = '';
    visitRecapStale = true;
    visitRecapState = state;
    visitRecapMessage = message || 'Reload the current recap before exporting.';
    revokeVisitRecapDownloadUrl();
    if (appointmentDialogOpen && activeAppointmentTab === 'recap') renderVisitRecap();
    else updateVisitRecapExportControls();
  }

  function visitRecapAuthorityIsCurrent(authority = visitRecapAuthority) {
    const visit = currentVisit();
    return Boolean(
      authority
      && visitRecapProjection?.exportable === true
      && visitRecapProjection?.state === 'current'
      && ['in_progress', 'completed'].includes(visitRecapProjection?.visit?.status)
      && visitRecapProjection?.visit?.status === visit?.status
      && !visitRecapStale
      && !appIsOffline()
      && appointmentDialogOpen
      && activeAppointmentTab === 'recap'
      && authority.phiEpoch === phiEpoch
      && authority.visitSelectionEpoch === visitSelectionEpoch
      && authority.requestEpoch === visitRecapLoadEpoch
      && authority.visitId === selectedVisitId
      && authority.visitToken === visit?.token
      && authority.profileRevision === normalizedRevision(latestProfileRevision)
      && authority.workflowRevision === normalizedRevision(workflowRevision)
      && authority.recapState === 'current'
      && authority.exportable === true
      && authority.visitStatus === visitRecapProjection?.visit?.status
      && authority.recapToken
      && authority.recapToken === visitRecapAuthority?.recapToken
      && visitRecapExportText
    );
  }

  function updateVisitRecapExportControls() {
    const actions = document.getElementById('visit-recap-actions');
    const visible = visitRecapAuthorityIsCurrent();
    const enabled = visible && !visitRecapExportOwner;
    if (!visible && actions?.contains?.(document.activeElement)) {
      const fallback = appointmentDialogOpen
        ? document.getElementById('appointment-tab-recap')
        : null;
      if (fallback && !fallback.hidden) fallback.focus({ preventScroll: true });
      else document.activeElement?.blur();
    }
    if (actions) actions.hidden = !visible;
    for (const id of ['visit-recap-copy', 'visit-recap-download', 'visit-recap-print']) {
      const control = document.getElementById(id);
      if (control) control.disabled = !enabled;
    }
  }

  function recapPlainText(value) {
    const normalized = String(value == null ? '' : value).replace(/\r\n?/g, '\n');
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(normalized)) {
      throw new Error('The recap contains unsupported control characters and cannot be exported.');
    }
    return normalized;
  }

  function buildVisitRecapText(recap) {
    if (!recap?.exportable || recap.state !== 'current') {
      throw new Error('This visit recap is not available for export.');
    }
    const lines = ['NET/Care visit recap', '', 'Visit details'];
    const visit = recap.visit || {};
    const detailRows = [
      ['Title', visit.title],
      ['Date', visit.date],
      ['Time', visit.time],
      ['Clinician', visit.clinician],
      ['Location', visit.location],
      ['Lifecycle', visitStatusLabel(visit.status)],
    ];
    detailRows.forEach(([label, value]) => {
      if (value) lines.push(`${label}: ${recapPlainText(value)}`);
    });
    const sections = recap.sections || {};
    const addSection = (title, items, render) => {
      if (!Array.isArray(items) || !items.length) return;
      lines.push('', title);
      items.forEach((item, index) => {
        lines.push(...render(item, index));
      });
    };
    addSection('What was asked', sections.what_was_asked, (item, index) => [
      `${index + 1}. ${recapPlainText(item.text)}`,
      `Status: ${item.status === 'unknown' ? 'Unknown' : 'Answered'}`,
      `Provenance: ${recapPlainText(item.provenance_label)}`,
    ]);
    addSection('What we heard', sections.what_we_heard, (item, index) => [
      `${index + 1}. Question: ${recapPlainText(item.question)}`,
      `Answer: ${recapPlainText(item.text)}`,
      `Provenance: ${recapPlainText(item.provenance_label)}`,
    ]);
    addSection('Decisions / needs confirmation', sections.decisions, (item, index) => [
      `${index + 1}. ${recapPlainText(item.text)}`,
      `Lifecycle: ${item.status === 'needs_confirmation' ? 'Needs confirmation' : 'Active'}`,
      `Provenance: ${recapPlainText(item.provenance_label)}`,
    ]);
    addSection('Follow-ups', sections.follow_ups, (item, index) => {
      const result = [
        `${index + 1}. ${recapPlainText(item.text)}`,
        `Lifecycle: ${recapPlainText(String(item.status).replaceAll('_', ' '))}`,
      ];
      if (item.owner) result.push(`Owner: ${recapPlainText(item.owner)}`);
      if (item.due_date) result.push(`Due date: ${recapPlainText(item.due_date)}`);
      if (item.outcome) {
        result.push(`Outcome: ${recapPlainText(item.outcome.text)}`);
        result.push(`Outcome provenance: ${recapPlainText(item.outcome.provenance_label)}`);
      }
      return result;
    });
    addSection(
      'Related resolved alerts',
      sections.related_resolved_alerts,
      (item, index) => {
        const result = [`${index + 1}. Resolved alert`];
        if (item.resolved_at) result.push(`Resolved: ${recapPlainText(item.resolved_at)}`);
        if (item.visit_id) result.push('Link: this visit');
        if (item.decision_id) result.push(`Linked decision: ${recapPlainText(item.decision_id)}`);
        if (item.follow_up_id) result.push(`Linked follow-up: ${recapPlainText(item.follow_up_id)}`);
        if (item.outcome) {
          result.push(`Outcome: ${recapPlainText(item.outcome.text)}`);
          result.push(`Outcome provenance: ${recapPlainText(item.outcome.provenance_label)}`);
        } else {
          result.push('Outcome: Administrative resolution recorded; no outcome text.');
        }
        return result;
      },
    );
    addSection('Unresolved / unknown items', sections.unresolved, (item, index) => [
      `${index + 1}. ${recapPlainText(item.text)}`,
      `Status: ${item.kind === 'unknown' ? 'Explicitly unknown' : 'No answer recorded'}`,
      `Provenance: ${recapPlainText(item.provenance_label)}`,
    ]);
    return `${lines.join('\n')}\n`;
  }

  function recapSectionMarkup(title, items, renderItem) {
    if (!Array.isArray(items) || !items.length) return '';
    return `<section class="visit-recap-section">
      <h4>${escHtml(title)}</h4>
      <div class="visit-recap-list">${items.map(renderItem).join('')}</div>
    </section>`;
  }

  function renderVisitRecap() {
    const status = document.getElementById('visit-recap-status');
    const content = document.getElementById('visit-recap-content');
    if (!status || !content) return;
    status.className = `visit-recap-status ${safeClassToken(visitRecapState, 'idle')}`;
    status.textContent = visitRecapMessage;
    updateVisitRecapExportControls();
    if (!visitRecapProjection) {
      content.innerHTML = visitRecapState === 'loading'
        ? '<div class="loading-state">Loading the current visit recap…</div>'
        : '<div class="empty-state">Open Recap to load the current visit record.</div>';
      return;
    }
    const recap = visitRecapProjection;
    const visit = recap.visit || {};
    const details = [
      ['Title', visit.title],
      ['Date', visit.date ? fmtDate(visit.date) : null],
      ['Time', visit.time],
      ['Clinician', visit.clinician],
      ['Location', visit.location],
      ['Lifecycle', visitStatusLabel(visit.status)],
    ].filter(([, value]) => value);
    const staleClass = visitRecapStale ? ' stale' : '';
    let html = `<div class="visit-recap-document${staleClass}">
      <section class="visit-recap-section visit-recap-details">
        <h4>Visit details</h4>
        <dl>${details.map(([label, value]) => `<div><dt>${escHtml(label)}</dt><dd>${escHtml(value)}</dd></div>`).join('')}</dl>
      </section>`;
    if (recap.state === 'unavailable') {
      html += '<div class="visit-recap-notice">A recap becomes available after the visit starts.</div></div>';
      content.innerHTML = html;
      return;
    }
    if (recap.state === 'administrative') {
      html += '<div class="visit-recap-notice">Cancelled visit · administrative record only. Copy, download, and print are unavailable.</div></div>';
      content.innerHTML = html;
      return;
    }
    const sections = recap.sections || {};
    html += recapSectionMarkup('What was asked', sections.what_was_asked, item =>
      `<article><strong>${escHtml(item.text)}</strong><span class="visit-recap-meta">${item.status === 'unknown' ? 'Unknown' : 'Answered'}</span><p class="capture-provenance">${escHtml(item.provenance_label)}</p></article>`
    );
    html += recapSectionMarkup('What we heard', sections.what_we_heard, item =>
      `<article><span class="visit-recap-question">${escHtml(item.question)}</span><p>${escHtml(item.text)}</p><p class="capture-provenance">${escHtml(item.provenance_label)}</p></article>`
    );
    html += recapSectionMarkup('Decisions / needs confirmation', sections.decisions, item =>
      `<article><strong>${escHtml(item.text)}</strong><span class="visit-status-badge ${safeClassToken(item.status, 'active')}">${item.status === 'needs_confirmation' ? 'Needs confirmation' : 'Active'}</span><p class="capture-provenance">${escHtml(item.provenance_label)}</p></article>`
    );
    html += recapSectionMarkup('Follow-ups', sections.follow_ups, item => {
      const metadata = [
        String(item.status || '').replaceAll('_', ' '),
        item.owner && `Owner: ${item.owner}`,
        item.due_date && `Due ${fmtDate(item.due_date)}`,
      ].filter(Boolean).join(' · ');
      return `<article><strong>${escHtml(item.text)}</strong><span class="visit-recap-meta">${escHtml(metadata)}</span>${item.outcome ? `<p><b>Outcome:</b> ${escHtml(item.outcome.text)}</p><p class="capture-provenance">${escHtml(item.outcome.provenance_label)}</p>` : ''}</article>`;
    });
    html += recapSectionMarkup(
      'Related resolved alerts',
      sections.related_resolved_alerts,
      item => {
        const links = [
          item.visit_id && 'This visit',
          item.decision_id && `Decision ${item.decision_id}`,
          item.follow_up_id && `Follow-up ${item.follow_up_id}`,
        ].filter(Boolean).join(' · ');
        return `<article><strong>Resolved alert</strong>${item.resolved_at ? `<span class="visit-recap-meta">${escHtml(formatActionTimestamp(item.resolved_at))}</span>` : ''}${links ? `<p>${escHtml(links)}</p>` : ''}${item.outcome ? `<p><b>Outcome:</b> ${escHtml(item.outcome.text)}</p><p class="capture-provenance">${escHtml(item.outcome.provenance_label)}</p>` : '<p class="capture-provenance">Administrative resolution recorded · no outcome text</p>'}</article>`;
      },
    );
    html += recapSectionMarkup('Unresolved / unknown items', sections.unresolved, item =>
      `<article><strong>${escHtml(item.text)}</strong><span class="visit-recap-meta">${item.kind === 'unknown' ? 'Explicitly unknown' : 'No answer recorded'}</span><p class="capture-provenance">${escHtml(item.provenance_label)}</p></article>`
    );
    content.innerHTML = `${html}</div>`;
  }

  function visitRecapResponseAuthority(data) {
    const profileRevision = normalizedRevision(data?.profile_revision);
    const workflowRevision = normalizedRevision(data?.workflow_revision);
    const recap = data?.recap;
    if (
      !data
      || typeof data.visit_id !== 'string'
      || !data.visit_id
      || typeof data.visit_token !== 'string'
      || !data.visit_token
      || typeof data.recap_token !== 'string'
      || !data.recap_token
      || !Number.isSafeInteger(profileRevision)
      || !Number.isSafeInteger(workflowRevision)
      || !recap
      || typeof recap !== 'object'
      || recap.visit?.id !== data.visit_id
      || typeof recap.state !== 'string'
      || typeof recap.exportable !== 'boolean'
      || typeof recap.visit?.status !== 'string'
    ) return null;
    return {
      visitId: data.visit_id,
      visitToken: data.visit_token,
      profileRevision,
      workflowRevision,
      recapToken: data.recap_token,
      recapState: recap.state,
      exportable: recap.exportable,
      visitStatus: recap.visit.status,
    };
  }

  function applyVisitRecapProjection(data, options = {}) {
    const responseAuthority = visitRecapResponseAuthority(data);
    if (!responseAuthority) return false;
    visitRecapNetworkAmbiguous = false;
    visitRecapProjection = data.recap;
    visitRecapStale = false;
    visitRecapState = options.state || data.recap.state || 'error';
    visitRecapMessage = options.message || (
      data.recap.state === 'current'
        ? 'Current authoritative recap.'
        : data.recap.state === 'administrative'
          ? 'Cancelled visit · non-exportable administrative state.'
          : 'Recap is unavailable until this visit starts.'
    );
    visitRecapAuthority = {
      ...responseAuthority,
      phiEpoch,
      visitSelectionEpoch,
      requestEpoch: options.requestEpoch ?? visitRecapLoadEpoch,
    };
    try {
      visitRecapExportText = buildVisitRecapText(data.recap);
    } catch (error) {
      visitRecapExportText = '';
      if (data.recap.exportable) {
        visitRecapAuthority = null;
        visitRecapState = 'error';
        visitRecapMessage = error.message || 'The recap cannot be exported safely.';
      }
    }
    renderVisitRecap();
    return true;
  }

  async function loadVisitRecap() {
    if (!appointmentDialogOpen || activeAppointmentTab !== 'recap') return null;
    const visit = currentVisit();
    if (!visit?.id || !visit.token) {
      markVisitRecapStale('The selected visit is unavailable. Reload visits.', 'conflict');
      return null;
    }
    const request = capturePatientRequest({ visitSelection: true });
    const requestLoadEpoch = ++visitRecapLoadEpoch;
    visitRecapExportEpoch += 1;
    visitRecapExportOwner = null;
    const requestVisitToken = visit.token;
    const requestIsCurrent = () => (
      patientRequestIsCurrent(request)
      && requestLoadEpoch === visitRecapLoadEpoch
      && appointmentDialogOpen
      && activeAppointmentTab === 'recap'
      && currentVisit()?.token === requestVisitToken
    );
    visitRecapState = 'loading';
    visitRecapMessage = visitRecapProjection
      ? 'Refreshing the current recap. Export is disabled until accepted.'
      : 'Loading the current recap…';
    visitRecapAuthority = null;
    visitRecapExportText = '';
    visitRecapStale = Boolean(visitRecapProjection);
    revokeVisitRecapDownloadUrl();
    renderVisitRecap();
    try {
      const response = await fetch(
        `/api/visits/${encodeURIComponent(visit.id)}/recap?expected_visit_token=${encodeURIComponent(requestVisitToken)}`
      );
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, data, { workflow: 'projection' });
      if (!authority.accepted) return null;
      const responseAuthority = visitRecapResponseAuthority(data);
      if (
        !responseAuthority
        || responseAuthority.visitId !== selectedVisitId
        || responseAuthority.visitToken !== currentVisit()?.token
      ) return null;
      if (!applyVisitRecapProjection(data, { requestEpoch: requestLoadEpoch })) return null;
      reportLoadSuccess('visit-recap');
      updateVisitRecapExportControls();
      return data;
    } catch (error) {
      if (!requestIsCurrent()) return null;
      if (shouldEvictClientPhi(error)) {
        reportLoadError('visit-recap', error);
        if (requestIsCurrent()) evictClientPhi(error);
        return null;
      }
      const state = error?.status === 409
        ? 'conflict'
        : (
          navigator.onLine === false
          || error instanceof TypeError
          || error?.name === 'AbortError'
            ? 'offline'
            : 'error'
        );
      if (state === 'offline') visitRecapNetworkAmbiguous = true;
      markVisitRecapStale(
        error?.status === 409
          ? 'The visit changed. Reload the visit and recap before exporting.'
          : state === 'offline'
            ? 'Offline snapshot · read-only. Export is disabled until the recap reloads.'
            : (error.message || 'The recap could not be loaded.'),
        state,
      );
      if (!visitRecapProjection) renderVisitRecap();
      reportLoadError('visit-recap', error);
      return null;
    }
  }

  function requireCurrentVisitRecap() {
    if (visitRecapAuthorityIsCurrent()) return visitRecapAuthority;
    markVisitRecapStale('The recap is no longer current. Reload it before exporting.');
    throw new Error('The recap is no longer current. Reload it before exporting.');
  }

  function beginVisitRecapExport(kind) {
    if (visitRecapExportOwner) return null;
    const authority = requireCurrentVisitRecap();
    const request = capturePatientRequest({ visitSelection: true });
    if (
      request.requestPhiEpoch !== authority.phiEpoch
      || request.requestVisitEpoch !== authority.visitSelectionEpoch
      || request.requestVisitId !== authority.visitId
      || authority.requestEpoch !== visitRecapLoadEpoch
    ) {
      markVisitRecapStale('The recap is no longer current. Reload it before exporting.');
      return null;
    }
    const owner = {
      kind,
      exportEpoch: ++visitRecapExportEpoch,
      request,
      requestEpoch: visitRecapLoadEpoch,
      authority: { ...authority },
      exportText: visitRecapExportText,
      projection: visitRecapProjection,
    };
    visitRecapExportOwner = owner;
    updateVisitRecapExportControls();
    return owner;
  }

  function visitRecapExportSelectionIsCurrent(owner) {
    return Boolean(
      owner
      && visitRecapExportOwner === owner
      && owner.exportEpoch === visitRecapExportEpoch
      && appointmentDialogOpen
      && activeAppointmentTab === 'recap'
      && owner.request.requestVisitEpoch === visitSelectionEpoch
      && owner.request.requestVisitId === selectedVisitId
      && currentVisit()?.token === owner.authority.visitToken
    );
  }

  function visitRecapExportOwnerIsCurrent(owner) {
    return Boolean(
      visitRecapExportSelectionIsCurrent(owner)
      && patientRequestIsCurrent(owner.request)
      && owner.requestEpoch === visitRecapLoadEpoch
      && visitRecapAuthorityIsCurrent(owner.authority)
      && owner.exportText === visitRecapExportText
      && owner.projection === visitRecapProjection
    );
  }

  function releaseVisitRecapExport(owner) {
    if (visitRecapExportOwner !== owner) return;
    const canRender = (
      appointmentDialogOpen
      && activeAppointmentTab === 'recap'
      && owner.request.requestVisitEpoch === visitSelectionEpoch
      && owner.request.requestVisitId === selectedVisitId
    );
    visitRecapExportOwner = null;
    if (canRender) updateVisitRecapExportControls();
  }

  function visitRecapPreflightMatches(owner, data) {
    const responseAuthority = visitRecapResponseAuthority(data);
    const authority = owner.authority;
    return Boolean(
      responseAuthority
      && owner.request.requestPhiEpoch === authority.phiEpoch
      && owner.request.requestVisitEpoch === authority.visitSelectionEpoch
      && owner.request.requestVisitId === authority.visitId
      && owner.requestEpoch === authority.requestEpoch
      && responseAuthority.visitId === authority.visitId
      && responseAuthority.visitToken === authority.visitToken
      && responseAuthority.profileRevision === authority.profileRevision
      && responseAuthority.workflowRevision === authority.workflowRevision
      && responseAuthority.recapToken === authority.recapToken
      && responseAuthority.recapState === authority.recapState
      && responseAuthority.exportable === authority.exportable
      && responseAuthority.visitStatus === authority.visitStatus
      && responseAuthority.recapState === 'current'
      && responseAuthority.exportable === true
    );
  }

  function rejectVisitRecapPreflight(owner, message, state = 'stale') {
    if (!visitRecapExportSelectionIsCurrent(owner)) return;
    markVisitRecapStale(message, state, true);
  }

  function acceptChangedVisitRecapPreflight(owner, data) {
    if (!visitRecapExportOwnerIsCurrent(owner)) return false;
    const responseAuthority = visitRecapResponseAuthority(data);
    rejectVisitRecapPreflight(
      owner,
      'The recap changed. Review the refreshed recap before exporting.',
      'changed',
    );
    const visitChanged = Boolean(
      responseAuthority
      && (
        responseAuthority.visitId !== owner.authority.visitId
        || responseAuthority.visitToken !== currentVisit()?.token
      )
    );
    if (
      !responseAuthority
      || visitChanged
      || responseAuthority.profileRevision < owner.authority.profileRevision
      || responseAuthority.workflowRevision < owner.authority.workflowRevision
    ) {
      visitRecapState = 'conflict';
      visitRecapMessage = visitChanged
        ? 'The selected visit changed. Reload the visit and recap before exporting.'
        : 'The recap preflight returned stale or incomplete authority. Reload before exporting.';
      renderVisitRecap();
      return false;
    }
    const accepted = authorizePatientResponse(owner.request, data, {
      workflow: 'projection',
      preserveVisitRecapExportOwner: true,
    });
    if (!accepted.accepted || !visitRecapExportSelectionIsCurrent(owner)) {
      return false;
    }
    const applied = applyVisitRecapProjection(data, {
      requestEpoch: visitRecapLoadEpoch,
      state: responseAuthority.exportable && responseAuthority.recapState === 'current'
        ? 'changed'
        : responseAuthority.recapState,
      message: responseAuthority.exportable && responseAuthority.recapState === 'current'
        ? 'Recap changed. Review the refreshed recap, then export again.'
        : undefined,
    });
    if (applied) {
      reportLoadSuccess('visit-recap');
      updateVisitRecapExportControls();
    }
    return false;
  }

  async function preflightVisitRecapExport(owner) {
    const response = await fetch(
      `/api/visits/${encodeURIComponent(owner.authority.visitId)}/recap?expected_visit_token=${encodeURIComponent(owner.authority.visitToken)}`,
      {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      },
    );
    if (!visitRecapExportOwnerIsCurrent(owner)) return null;
    const data = await readJsonResponse(response, () => visitRecapExportOwnerIsCurrent(owner));
    if (!visitRecapExportOwnerIsCurrent(owner)) return null;
    if (!visitRecapPreflightMatches(owner, data)) {
      acceptChangedVisitRecapPreflight(owner, data);
      return null;
    }
    const accepted = authorizePatientResponse(owner.request, data, { workflow: 'projection' });
    if (!accepted.accepted || !visitRecapExportOwnerIsCurrent(owner)) return null;
    reportLoadSuccess('visit-recap');
    return {
      authority: owner.authority,
      exportText: owner.exportText,
      projection: owner.projection,
    };
  }

  function handleVisitRecapPreflightError(owner, error) {
    if (!visitRecapExportSelectionIsCurrent(owner)) return;
    if (shouldEvictClientPhi(error)) {
      reportLoadError('visit-recap', error);
      if (visitRecapExportSelectionIsCurrent(owner)) evictClientPhi(error);
      return;
    }
    const ambiguous = (
      error instanceof TypeError
      || error?.name === 'AbortError'
      || navigator.onLine === false
    );
    const state = error?.status === 409 ? 'conflict' : (ambiguous ? 'offline' : 'error');
    const message = error?.status === 409
      ? 'The visit changed. Reload the visit and recap before exporting.'
      : ambiguous
        ? 'The recap could not be rechecked. The visible snapshot is read-only until it reloads.'
        : (error?.message || 'The recap could not be rechecked before export.');
    if (ambiguous) visitRecapNetworkAmbiguous = true;
    rejectVisitRecapPreflight(owner, message, state);
    reportLoadError('visit-recap', error);
  }

  async function performVisitRecapExport(kind) {
    let owner;
    let preflightAccepted = false;
    try {
      owner = beginVisitRecapExport(kind);
      if (!owner) return false;
      const snapshot = await preflightVisitRecapExport(owner);
      if (!snapshot || !visitRecapExportOwnerIsCurrent(owner)) return false;
      preflightAccepted = true;
      if (kind === 'copy') {
        if (!navigator.clipboard?.writeText) {
          throw new Error('Clipboard access is unavailable in this browser.');
        }
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        await navigator.clipboard.writeText(snapshot.exportText);
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        visitRecapMessage = 'Recap copied.';
      } else if (kind === 'download') {
        if (!globalThis.Blob || !globalThis.URL?.createObjectURL) {
          throw new Error('Text download is unavailable in this browser.');
        }
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        const blob = new Blob([snapshot.exportText], { type: 'text/plain;charset=utf-8' });
        revokeVisitRecapDownloadUrl();
        visitRecapDownloadUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const date = /^\d{4}-\d{2}-\d{2}$/.test(snapshot.projection?.visit?.date || '')
          ? snapshot.projection.visit.date
          : null;
        link.href = visitRecapDownloadUrl;
        link.download = date ? `visit-recap-${date}.txt` : 'visit-recap.txt';
        link.rel = 'noopener';
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        link.click();
        visitRecapMessage = 'Recap text downloaded.';
      } else if (kind === 'print') {
        if (typeof window.print !== 'function') {
          throw new Error('Printing is unavailable in this browser.');
        }
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        prepareVisitRecapPrint();
        if (!visitRecapExportOwnerIsCurrent(owner)) return false;
        window.print();
        visitRecapMessage = 'Print dialog opened.';
      } else {
        throw new Error('Unsupported recap export.');
      }
      if (!visitRecapExportOwnerIsCurrent(owner)) return false;
      visitRecapState = 'success';
      renderVisitRecap();
      return true;
    } catch (error) {
      if (!owner || !visitRecapExportSelectionIsCurrent(owner)) return false;
      if (!preflightAccepted) {
        handleVisitRecapPreflightError(owner, error);
        return false;
      }
      visitRecapMessage = error.message || `The recap could not be ${kind === 'copy' ? 'copied' : kind === 'download' ? 'downloaded' : 'printed'}.`;
      visitRecapState = 'error';
      renderVisitRecap();
      return false;
    } finally {
      if (visitRecapExportOwner === owner && kind === 'download') {
        revokeVisitRecapDownloadUrl();
      }
      if (visitRecapExportOwner === owner && kind === 'print') {
        finishVisitRecapPrint();
      }
      if (owner) releaseVisitRecapExport(owner);
    }
  }

  async function copyVisitRecap() {
    return performVisitRecapExport('copy');
  }

  async function downloadVisitRecap() {
    return performVisitRecapExport('download');
  }

  async function printVisitRecap() {
    return performVisitRecapExport('print');
  }

  function prepareVisitRecapPrint() {
    document.body.classList.toggle('visit-recap-printing', visitRecapAuthorityIsCurrent());
  }

  function finishVisitRecapPrint() {
    document.body.classList.remove('visit-recap-printing');
  }

  window.addEventListener('beforeprint', prepareVisitRecapPrint);
  window.addEventListener('afterprint', finishVisitRecapPrint);

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

  async function loadVisits(options = {}) {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++visitLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
      && requestLoadEpoch === visitLoadEpoch
    );
    try {
      const response = await fetch('/api/visits');
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        ...(options.authorizationOptions || {}),
      });
      if (!authority.accepted) return null;
      if (appointmentDialogOpen) captureAppointmentDraft();
      const nextVisitsById = new Map((data.items || []).map(item => [item.id, item]));
      const nextSelectedToken = selectedVisitId
        ? nextVisitsById.get(selectedVisitId)?.token || null
        : null;
      if (selectedVisitId) {
        scrubVisitRecapBeforeSelectionChange(selectedVisitId, nextSelectedToken);
      }
      visitsById = nextVisitsById;
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
      + '#visit-create-panel textarea, #visit-create-panel select, '
      + '#alerts-list .resolve-btn, #alert-resolution-dialog button, '
      + '#alert-resolution-dialog input, #alert-resolution-dialog textarea, '
      + '#alert-resolution-dialog select'
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
    for (const id of [
      'alert-resolution-outcome-text', 'alert-resolution-follow-up-text',
      'alert-resolution-follow-up-owner', 'alert-resolution-follow-up-due'
    ]) {
      const control = document.getElementById(id);
      if (control) control.value = '';
    }
    for (const id of [
      'alert-resolution-follow-up-select', 'alert-resolution-visit-select',
      'alert-resolution-decision-select'
    ]) {
      const select = document.getElementById(id);
      if (select) {
        select.innerHTML = '';
        select.value = '';
      }
    }
    const alertOutcomeKind = document.getElementById('alert-resolution-outcome-kind');
    if (alertOutcomeKind) alertOutcomeKind.value = 'administrative';
    const alertConfirm = document.getElementById('alert-resolution-confirm');
    if (alertConfirm) alertConfirm.checked = false;
    const alertForm = document.getElementById('alert-resolution-form');
    const alertResult = document.getElementById('alert-resolution-result');
    if (alertForm) alertForm.hidden = false;
    if (alertResult) alertResult.hidden = true;
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

  async function loadFollowUps(options = {}) {
    const request = capturePatientRequest();
    const requestLoadEpoch = ++followUpLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
      && requestLoadEpoch === followUpLoadEpoch
    );
    try {
      const response = await fetch('/api/follow-ups');
      if (!requestIsCurrent()) return null;
      const data = await readJsonResponse(response, requestIsCurrent);
      if (!requestIsCurrent()) return null;
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        ...(options.authorizationOptions || {}),
      });
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
      || (
        typeof alertResolutionMutationPending !== 'undefined'
        && alertResolutionMutationPending
      )
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
    scrubVisitRecapBeforeSelectionChange(visitId, visit.token);
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
    clearVisitRecap(true);
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
    const visit = visitsById.get(visitId);
    scrubVisitRecapBeforeSelectionChange(visitId, visit?.token);
    selectedVisitId = visitId;
    visitSelectionEpoch += 1;
    clearWorkflowRetry();
    renderAppointmentWorkspace();
    setAppointmentMessage('Visit changed.', 'success');
  }

  function switchAppointmentTab(name) {
    if (!['questions', 'decisions', 'followups', 'recap'].includes(name)) return;
    captureAppointmentDraft();
    activeAppointmentTab = name;
    for (const tabName of ['questions', 'decisions', 'followups', 'recap']) {
      const active = tabName === name;
      const tab = document.getElementById(`appointment-tab-${tabName}`);
      const panel = document.getElementById(`appointment-panel-${tabName}`);
      tab?.classList.toggle('active', active);
      tab?.setAttribute('aria-selected', String(active));
      if (tab) tab.tabIndex = active ? 0 : -1;
      panel?.classList.toggle('active', active);
      if (panel) panel.hidden = !active;
    }
    if (name === 'recap' && typeof loadVisitRecap === 'function') loadVisitRecap();
  }

  function handleAppointmentTabKeydown(event) {
    const names = ['questions', 'decisions', 'followups', 'recap'];
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

  async function loadQuestions(options = {}) {
    const request = capturePatientRequest();
    const requestQuestionEpoch = ++questionLoadEpoch;
    const responseGuard = options.responseGuard || (() => true);
    const requestProfileRevision = latestProfileRevision == null
      ? null
      : String(latestProfileRevision);
    const requestIsCurrent = () => (
      responseGuard()
      && patientRequestIsCurrent(request)
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
      if (
        !authorizePatientResponse(
          request,
          qs,
          options.authorizationOptions || {},
        ).accepted
      ) return [];
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

  // ── Treatment reconciliation ────────────────────────────────────────────
  const TREATMENT_SAFETY_GUIDANCE = 'NET/Care records what you enter but does not verify treatment details or advise starting, stopping, or changing treatment. Confirm treatment decisions with the treating team.';
  const TREATMENT_CONFIRMATION_LABEL = 'Caregiver-entered · attributed to clinician · unverified';
  const TREATMENT_TODAY_LIMIT = 3;
  const TREATMENT_MAX_AUTHORITY_BYTES = 6000000;
  const TREATMENT_COURSE_FIELDS = [
    'treatment_text', 'treatment_type_text', 'dose_text', 'route_text',
    'frequency_text', 'cycle_text', 'schedule_text', 'formulation_text',
    'indication_text', 'notes', 'start_date', 'stop_date', 'planned_date',
  ];
  const TREATMENT_OPTIONAL_TEXT_FIELDS = new Set([
    'treatment_type_text', 'dose_text', 'route_text', 'frequency_text',
    'cycle_text', 'schedule_text', 'formulation_text', 'indication_text', 'notes',
  ]);
  const TREATMENT_TEXT_LIMITS = {
    treatment_text: 1000,
    treatment_type_text: 500,
    dose_text: 500,
    route_text: 500,
    frequency_text: 500,
    cycle_text: 500,
    schedule_text: 1000,
    formulation_text: 500,
    indication_text: 1000,
    notes: 10000,
    terminal_detail: 1000,
  };
  const TREATMENT_STATUS_LABELS = {
    current: 'Current record',
    planned: 'Planned record',
    past: 'Past record',
  };
  const TREATMENT_TERMINAL_LABELS = {
    ended: 'Ended after it had started',
    not_started: 'Did not start',
    cancelled: 'Plan cancelled before starting',
    other: 'Other recorded outcome',
    legacy_unspecified: 'Earlier record; ending detail not recorded',
  };
  const TREATMENT_RESTART_REASONS = {
    course_not_terminal: 'This record is not past.',
    terminal_qualifier_not_restartable: 'This earlier record was not recorded as having started.',
    no_prior_current_authority: 'The earlier workflow does not establish a prior current record.',
    eligible_prior_current: 'The server permits a new record linked to this past record.',
  };

  function treatmentElement(tag, className = '', text = null) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== null) element.textContent = text;
    return element;
  }

  function treatmentHasExactKeys(value, required, optional = []) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const allowed = new Set([...required, ...optional]);
    const keys = Object.keys(value);
    return required.every(key => Object.prototype.hasOwnProperty.call(value, key))
      && keys.every(key => allowed.has(key));
  }

  function treatmentBoundedString(value, maximum, nullable = false) {
    return (nullable && value === null)
      || (typeof value === 'string' && value.length <= maximum);
  }

  function treatmentSafeNested(value) {
    const stack = [{ value, depth: 0 }];
    let nodes = 0;
    while (stack.length) {
      const item = stack.pop();
      nodes += 1;
      if (nodes > 75000 || item.depth > 12) return false;
      if (typeof item.value === 'string') {
        if (item.value.length > 100000) return false;
      } else if (Array.isArray(item.value)) {
        if (item.value.length > 10000) return false;
        item.value.forEach(value => stack.push({ value, depth: item.depth + 1 }));
      } else if (item.value && typeof item.value === 'object') {
        const keys = Object.keys(item.value);
        if (keys.length > 2000) return false;
        keys.forEach(key => {
          stack.push({ value: key, depth: item.depth + 1 });
          stack.push({ value: item.value[key], depth: item.depth + 1 });
        });
      } else if (
        item.value !== null
        && !['boolean', 'number'].includes(typeof item.value)
      ) return false;
      if (typeof item.value === 'number' && !Number.isFinite(item.value)) return false;
    }
    return true;
  }

  function treatmentDatePrecision(value) {
    if (value === null) return 'unknown';
    if (typeof value !== 'string') return null;
    const match = value.match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/);
    if (!match) return null;
    const year = Number(match[1]);
    if (year < 1 || year > 9999) return null;
    if (match[2] === undefined) return 'year';
    const month = Number(match[2]);
    if (month < 1 || month > 12) return null;
    if (match[3] === undefined) return 'month';
    const day = Number(match[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const maximum = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
    return day >= 1 && day <= maximum ? 'day' : null;
  }

  function treatmentDateInputIsValid(value) {
    return value === '' || treatmentDatePrecision(value) !== null;
  }

  function safeTreatmentSourceUrl(value, expectedRef, kind) {
    if (typeof value !== 'string' || typeof expectedRef !== 'string') return '';
    const expected = `/api/patient/treatment-reconciliation/source-facts/${expectedRef}/${kind}`;
    if (value !== expected) return '';
    if (!/^\/api\/patient\/treatment-reconciliation\/source-facts\/txref_[0-9a-f]{64}\/(?:source|evidence)$/.test(value)) {
      return '';
    }
    try {
      const base = document.baseURI || window.location.href;
      const url = new URL(value, base);
      const origin = new URL(base).origin;
      return (
        url.origin === origin
        && url.username === ''
        && url.password === ''
        && url.search === ''
        && url.hash === ''
        && url.pathname === value
        && `${url.pathname}${url.search}${url.hash}` === value
      ) ? value : '';
    } catch (_) {
      return '';
    }
  }

  function treatmentSourceFactIsValid(source) {
    if (!treatmentHasExactKeys(source, [
      'ref', 'token', 'observed_text', 'record_value', 'operation',
      'review_state', 'receipt_state', 'provenance',
    ])) return false;
    if (
      !/^txref_[0-9a-f]{64}$/.test(source.ref)
      || !treatmentBoundedString(source.token, 200)
      || !source.token
      || typeof source.observed_text !== 'string'
      || !treatmentSafeNested(source.record_value)
      || typeof source.operation !== 'string'
      || typeof source.review_state !== 'string'
      || typeof source.receipt_state !== 'string'
      || !treatmentHasExactKeys(source.provenance, [
        'status', 'label', 'source_url', 'evidence_url',
      ])
      || !['source_verified', 'source_unverified'].includes(source.provenance.status)
      || !['Exact source', 'No exact source'].includes(source.provenance.label)
      || safeTreatmentSourceUrl(source.provenance.source_url, source.ref, 'source') !== source.provenance.source_url
    ) return false;
    if (source.provenance.status === 'source_verified') {
      return safeTreatmentSourceUrl(
        source.provenance.evidence_url,
        source.ref,
        'evidence',
      ) === source.provenance.evidence_url;
    }
    return source.provenance.evidence_url === null;
  }

  function treatmentActionIsValid(action) {
    return treatmentHasExactKeys(action, ['id', 'token', 'text', 'status', 'owner', 'due_date'])
      && treatmentBoundedString(action.id, 200)
      && Boolean(action.id)
      && treatmentBoundedString(action.token, 200)
      && Boolean(action.token)
      && treatmentBoundedString(action.text, 1000)
      && ['open', 'in_progress', 'completed', 'cancelled'].includes(action.status)
      && treatmentBoundedString(action.owner, 100, true)
      && treatmentBoundedString(action.due_date, 32, true);
  }

  function treatmentCourseIsValid(course, componentIds, options = {}) {
    const fields = [
      'id', 'status', ...TREATMENT_COURSE_FIELDS.slice(0, 10),
      'legacy_component_ids',
      'start_date', 'start_date_precision', 'start_date_kind',
      'stop_date', 'stop_date_precision', 'stop_date_kind',
      'planned_date', 'planned_date_precision', 'planned_date_kind',
      'terminal_qualifier', 'terminal_detail', 'previous_course_id',
      'created_at', 'updated_at', 'token', 'lifecycle', 'provenance',
    ];
    const legacySnapshotFields = fields.filter(
      key => !['terminal_qualifier', 'terminal_detail', 'lifecycle'].includes(key),
    );
    const keysValid = options.snapshot
      ? (
        treatmentHasExactKeys(course, fields)
        || treatmentHasExactKeys(course, legacySnapshotFields)
      )
      : treatmentHasExactKeys(course, fields);
    if (
      !keysValid
      || !/^txc_[0-9a-f]{32}$/.test(course.id)
      || !['current', 'past', 'planned'].includes(course.status)
      || !treatmentBoundedString(course.token, 200)
      || !course.token
      || !treatmentBoundedString(course.treatment_text, 1000)
      || !course.treatment_text
    ) return false;
    for (const field of TREATMENT_OPTIONAL_TEXT_FIELDS) {
      if (!treatmentBoundedString(course[field], TREATMENT_TEXT_LIMITS[field], true)) return false;
    }
    if (
      !Array.isArray(course.legacy_component_ids)
      || new Set(course.legacy_component_ids).size !== course.legacy_component_ids.length
      || !course.legacy_component_ids.every(id => (
        typeof id === 'string' && (options.snapshot || componentIds.has(id))
      ))
      || !treatmentBoundedString(course.previous_course_id, 200, true)
      || !treatmentBoundedString(course.created_at, 64)
      || !treatmentBoundedString(course.updated_at, 64)
      || !treatmentHasExactKeys(course.provenance, ['status', 'label'])
      || course.provenance.status !== 'caregiver_entered_unverified'
      || course.provenance.label !== 'Caregiver-entered · unverified'
    ) return false;
    for (const prefix of ['start', 'stop', 'planned']) {
      const value = course[`${prefix}_date`];
      const precision = treatmentDatePrecision(value);
      if (
        precision === null
        || course[`${prefix}_date_precision`] !== precision
        || course[`${prefix}_date_kind`] !== (value === null ? 'unknown' : 'caregiver_entered')
      ) return false;
    }
    if (Object.prototype.hasOwnProperty.call(course, 'terminal_qualifier')) {
      if (course.status !== 'past') {
        if (course.terminal_qualifier !== null || course.terminal_detail !== null) return false;
      } else if (!Object.keys(TREATMENT_TERMINAL_LABELS).includes(course.terminal_qualifier)) {
        return false;
      } else if (course.terminal_qualifier === 'other') {
        if (
          !treatmentBoundedString(course.terminal_detail, 1000)
          || !course.terminal_detail.trim()
        ) return false;
      } else if (course.terminal_detail !== null) return false;
    }
    if (!Object.prototype.hasOwnProperty.call(course, 'lifecycle')) return options.snapshot === true;
    if (!treatmentHasExactKeys(course.lifecycle, ['allowed_transitions', 'restart'])) return false;
    if (
      !Array.isArray(course.lifecycle.allowed_transitions)
      || course.lifecycle.allowed_transitions.length > 2
      || !course.lifecycle.allowed_transitions.every(transition => (
        treatmentHasExactKeys(transition, ['status', 'terminal_qualifiers'])
        && ['current', 'past'].includes(transition.status)
        && Array.isArray(transition.terminal_qualifiers)
        && transition.terminal_qualifiers.length <= 4
        && new Set(transition.terminal_qualifiers).size === transition.terminal_qualifiers.length
        && transition.terminal_qualifiers.every(value => (
          ['ended', 'not_started', 'cancelled', 'other'].includes(value)
        ))
      ))
      || new Set(course.lifecycle.allowed_transitions.map(item => item.status)).size
        !== course.lifecycle.allowed_transitions.length
    ) return false;
    if (
      !treatmentHasExactKeys(course.lifecycle.restart, ['eligible', 'reason'])
      || typeof course.lifecycle.restart.eligible !== 'boolean'
      || !Object.prototype.hasOwnProperty.call(
        TREATMENT_RESTART_REASONS,
        course.lifecycle.restart.reason,
      )
    ) return false;
    return true;
  }

  function treatmentLegacyRowIsValid(row, seenComponents, seenGenerated) {
    if (!treatmentHasExactKeys(row, [
      'id', 'token', 'raw_text', 'source_order', 'components',
      'generated_classification', 'authority_label',
    ])) return false;
    if (
      !treatmentBoundedString(row.id, 200)
      || !row.id
      || !treatmentBoundedString(row.token, 200)
      || !row.token
      || typeof row.raw_text !== 'string'
      || !Number.isSafeInteger(row.source_order)
      || row.source_order < 0
      || !Array.isArray(row.components)
      || !Array.isArray(row.generated_classification)
      || row.authority_label !== 'Legacy/generated · not caregiver lifecycle authority'
    ) return false;
    for (const component of row.components) {
      if (
        !treatmentHasExactKeys(component, ['id', 'text', 'component_order'])
        || !treatmentBoundedString(component.id, 200)
        || !component.id
        || seenComponents.has(component.id)
        || typeof component.text !== 'string'
        || !Number.isSafeInteger(component.component_order)
        || component.component_order < 0
      ) return false;
      seenComponents.add(component.id);
    }
    for (const generated of row.generated_classification) {
      if (
        !treatmentHasExactKeys(generated, [
          'id', 'text', 'label', 'category', 'date', 'source_treatment_ids',
        ])
        || !treatmentBoundedString(generated.id, 200)
        || !generated.id
        || seenGenerated.has(generated.id)
        || typeof generated.text !== 'string'
        || !treatmentBoundedString(generated.label, 1000, true)
        || !treatmentBoundedString(generated.category, 500, true)
        || !treatmentBoundedString(generated.date, 64, true)
        || !Array.isArray(generated.source_treatment_ids)
        || !generated.source_treatment_ids.every(id => typeof id === 'string')
      ) return false;
      seenGenerated.add(generated.id);
    }
    return true;
  }

  function treatmentConfirmationIsValid(confirmation) {
    return treatmentHasExactKeys(confirmation, [
      'outcome', 'note', 'clinician_text', 'context_text', 'date',
      'date_precision', 'date_kind', 'recorded_at', 'provenance_label',
    ])
      && ['confirmed_as_recorded', 'caregiver_record_corrected',
        'source_clarification_needed', 'no_change_documented'].includes(confirmation.outcome)
      && treatmentBoundedString(confirmation.note, 10000)
      && Boolean(confirmation.note)
      && treatmentBoundedString(confirmation.clinician_text, 500, true)
      && treatmentBoundedString(confirmation.context_text, 2000, true)
      && treatmentBoundedString(confirmation.date, 32, true)
      && treatmentDatePrecision(confirmation.date) === confirmation.date_precision
      && confirmation.date_kind === (confirmation.date === null ? 'unknown' : 'caregiver_entered')
      && treatmentBoundedString(confirmation.recorded_at, 64)
      && confirmation.provenance_label === TREATMENT_CONFIRMATION_LABEL;
  }

  function treatmentDiscrepancyIsValid(discrepancy, sources, courses, actions) {
    if (!treatmentHasExactKeys(discrepancy, [
      'id', 'token', 'status', 'category', 'comparison_text', 'citation_kind',
      'citation_authority', 'eligibility', 'citations', 'course_id', 'source_fact',
      'comparison_source_fact', 'course_snapshot', 'recurs_from_id',
      'confirmations', 'follow_up', 'provenance', 'created_at', 'updated_at',
      'resolved_at',
    ])) return false;
    if (
      !/^txd_[0-9a-f]{32}$/.test(discrepancy.id)
      || !treatmentBoundedString(discrepancy.token, 200)
      || !discrepancy.token
      || !['open', 'resolved'].includes(discrepancy.status)
      || !['name_or_type', 'status', 'dose_or_schedule', 'date',
        'source_wording', 'other'].includes(discrepancy.category)
      || !treatmentBoundedString(discrepancy.comparison_text, 10000)
      || !discrepancy.comparison_text
      || !['source_vs_source', 'source_vs_course', 'legacy_incomplete'].includes(discrepancy.citation_kind)
      || !treatmentHasExactKeys(discrepancy.citation_authority, ['state', 'reason'])
      || !treatmentHasExactKeys(discrepancy.eligibility, ['resolve', 'reopen', 'recur'])
      || !Object.values(discrepancy.eligibility).every(value => typeof value === 'boolean')
      || !treatmentHasExactKeys(discrepancy.citations, ['source_a', 'source_b', 'course_b'])
      || !treatmentHasExactKeys(discrepancy.citations.source_a, ['snapshot', 'current'])
      || !Array.isArray(discrepancy.confirmations)
      || !discrepancy.confirmations.every(treatmentConfirmationIsValid)
      || !treatmentHasExactKeys(discrepancy.provenance, ['status', 'label'])
      || discrepancy.provenance.status !== 'caregiver_entered_unverified'
      || discrepancy.provenance.label !== 'Caregiver-entered · unverified'
      || !treatmentBoundedString(discrepancy.created_at, 64)
      || !treatmentBoundedString(discrepancy.updated_at, 64)
      || !treatmentBoundedString(discrepancy.resolved_at, 64, true)
      || !treatmentBoundedString(discrepancy.recurs_from_id, 200, true)
      || (discrepancy.follow_up !== null && !treatmentActionIsValid(discrepancy.follow_up))
    ) return false;
    const sourceA = discrepancy.citations.source_a;
    if (
      !treatmentSourceFactIsValid(sourceA.snapshot)
      || !treatmentSourceFactIsValid(sourceA.current)
      || !sources.has(sourceA.current.ref)
      || sources.get(sourceA.current.ref).token !== sourceA.current.token
      || sourceA.snapshot.ref !== sourceA.current.ref
      || JSON.stringify(discrepancy.source_fact) !== JSON.stringify(sourceA.snapshot)
    ) return false;
    const complete = discrepancy.citation_kind !== 'legacy_incomplete';
    if (
      discrepancy.citation_authority.state !== (complete ? 'complete' : 'legacy_incomplete')
      || discrepancy.citation_authority.reason !== (complete ? null : 'missing_second_citation')
      || discrepancy.eligibility.resolve !== (complete && discrepancy.status === 'open')
      || discrepancy.eligibility.reopen !== (complete && discrepancy.status === 'resolved')
      || discrepancy.eligibility.recur !== (complete && discrepancy.status === 'resolved')
      || (discrepancy.status === 'open') !== (discrepancy.resolved_at === null)
    ) return false;
    if (discrepancy.citation_kind === 'source_vs_source') {
      const side = discrepancy.citations.source_b;
      return Boolean(
        side
        && discrepancy.citations.course_b === null
        && discrepancy.course_id === null
        && discrepancy.course_snapshot === null
        && treatmentHasExactKeys(side, ['snapshot', 'current'])
        && treatmentSourceFactIsValid(side.snapshot)
        && treatmentSourceFactIsValid(side.current)
        && side.current.ref !== sourceA.current.ref
        && sources.get(side.current.ref)?.token === side.current.token
        && side.snapshot.ref === side.current.ref
        && JSON.stringify(discrepancy.comparison_source_fact) === JSON.stringify(side.snapshot)
      );
    }
    if (discrepancy.citation_kind === 'source_vs_course') {
      const side = discrepancy.citations.course_b;
      const componentIds = new Set([
        ...(side?.snapshot?.legacy_component_ids || []),
        ...(side?.current?.legacy_component_ids || []),
      ]);
      return Boolean(
        side
        && discrepancy.citations.source_b === null
        && discrepancy.comparison_source_fact === null
        && typeof discrepancy.course_id === 'string'
        && treatmentHasExactKeys(side, ['snapshot', 'current'])
        && treatmentCourseIsValid(side.snapshot, componentIds, { snapshot: true })
        && treatmentCourseIsValid(side.current, componentIds)
        && side.snapshot.id === discrepancy.course_id
        && side.current.id === discrepancy.course_id
        && courses.get(side.current.id)?.token === side.current.token
        && JSON.stringify(discrepancy.course_snapshot) === JSON.stringify(side.snapshot)
      );
    }
    return discrepancy.citations.source_b === null
      && discrepancy.citations.course_b === null
      && discrepancy.course_id === null
      && discrepancy.comparison_source_fact === null
      && discrepancy.course_snapshot === null
      && !Object.values(discrepancy.eligibility).some(Boolean);
  }

  function treatmentProjectionPayloadIsValid(data) {
    if (
      !treatmentHasExactKeys(data, [
        'profile_revision', 'workflow_revision', 'projection_token',
        'source_fact_count', 'legacy_treatment_count', 'course_count',
        'discrepancy_count', 'source_facts', 'legacy_treatments', 'courses',
        'discrepancies', 'eligible_actions', 'safety_guidance',
      ])
      || !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || !treatmentBoundedString(data.projection_token, 200)
      || !data.projection_token
      || !Number.isSafeInteger(data.source_fact_count)
      || data.source_fact_count < 0
      || data.source_fact_count > 2000
      || !Number.isSafeInteger(data.legacy_treatment_count)
      || data.legacy_treatment_count < 0
      || data.legacy_treatment_count > 2000
      || !Number.isSafeInteger(data.course_count)
      || data.course_count < 0
      || data.course_count > 1000
      || !Number.isSafeInteger(data.discrepancy_count)
      || data.discrepancy_count < 0
      || data.discrepancy_count > 2000
      || !Array.isArray(data.source_facts)
      || data.source_facts.length !== data.source_fact_count
      || !Array.isArray(data.legacy_treatments)
      || data.legacy_treatments.length !== data.legacy_treatment_count
      || !Array.isArray(data.courses)
      || data.courses.length !== data.course_count
      || !Array.isArray(data.discrepancies)
      || data.discrepancies.length !== data.discrepancy_count
      || !Array.isArray(data.eligible_actions)
      || data.eligible_actions.length > 500
      || !treatmentHasExactKeys(data.safety_guidance, ['kind', 'text'])
      || data.safety_guidance.kind !== 'fixed_non_prescriptive'
      || data.safety_guidance.text !== TREATMENT_SAFETY_GUIDANCE
      || !treatmentSafeNested(data)
    ) return false;
    try {
      if (new TextEncoder().encode(JSON.stringify(data)).length > TREATMENT_MAX_AUTHORITY_BYTES) {
        return false;
      }
    } catch (_) {
      return false;
    }
    const sources = new Map();
    const sourceTokens = new Set();
    for (const source of data.source_facts) {
      if (
        !treatmentSourceFactIsValid(source)
        || sources.has(source.ref)
        || sourceTokens.has(source.token)
      ) return false;
      sources.set(source.ref, source);
      sourceTokens.add(source.token);
    }
    const componentIds = new Set();
    const generatedIds = new Set();
    const legacyIds = new Set();
    const legacyTokens = new Set();
    let generatedCount = 0;
    for (const row of data.legacy_treatments) {
      if (
        !treatmentLegacyRowIsValid(row, componentIds, generatedIds)
        || legacyIds.has(row.id)
        || legacyTokens.has(row.token)
      ) return false;
      legacyIds.add(row.id);
      legacyTokens.add(row.token);
      generatedCount += row.generated_classification.length;
      if (generatedCount > 2000 || componentIds.size > 4000) return false;
    }
    const courses = new Map();
    const courseTokens = new Set();
    for (const course of data.courses) {
      if (
        !treatmentCourseIsValid(course, componentIds)
        || courses.has(course.id)
        || courseTokens.has(course.token)
      ) return false;
      courses.set(course.id, course);
      courseTokens.add(course.token);
    }
    for (const course of data.courses) {
      if (
        course.previous_course_id !== null
        && (!courses.has(course.previous_course_id) || course.previous_course_id === course.id)
      ) return false;
      const seen = new Set([course.id]);
      let prior = course.previous_course_id;
      while (prior !== null) {
        if (seen.has(prior)) return false;
        seen.add(prior);
        prior = courses.get(prior)?.previous_course_id ?? null;
      }
    }
    const actions = new Map();
    const actionTokens = new Set();
    for (const action of data.eligible_actions) {
      if (
        !treatmentActionIsValid(action)
        || !['open', 'in_progress'].includes(action.status)
        || actions.has(action.id)
        || actionTokens.has(action.token)
      ) return false;
      actions.set(action.id, action);
      actionTokens.add(action.token);
    }
    const discrepancies = new Map();
    const discrepancyTokens = new Set();
    for (const discrepancy of data.discrepancies) {
      if (
        !treatmentDiscrepancyIsValid(discrepancy, sources, courses, actions)
        || discrepancies.has(discrepancy.id)
        || discrepancyTokens.has(discrepancy.token)
      ) return false;
      if (discrepancy.follow_up) {
        if (
          actions.has(discrepancy.follow_up.id)
          || actionTokens.has(discrepancy.follow_up.token)
        ) return false;
        actions.set(discrepancy.follow_up.id, discrepancy.follow_up);
        actionTokens.add(discrepancy.follow_up.token);
      }
      discrepancies.set(discrepancy.id, discrepancy);
      discrepancyTokens.add(discrepancy.token);
    }
    for (const discrepancy of data.discrepancies) {
      if (
        discrepancy.recurs_from_id !== null
        && (!discrepancies.has(discrepancy.recurs_from_id)
          || discrepancy.recurs_from_id === discrepancy.id)
      ) return false;
      const seen = new Set([discrepancy.id]);
      let prior = discrepancy.recurs_from_id;
      while (prior !== null) {
        if (seen.has(prior)) return false;
        seen.add(prior);
        prior = discrepancies.get(prior)?.recurs_from_id ?? null;
      }
    }
    return true;
  }

  function newTreatmentResponseOwner(projection, ownerPhiEpoch = phiEpoch) {
    return {
      requestPhiEpoch: ownerPhiEpoch,
      loadEpoch: treatmentLoadEpoch,
      profileRevision: projection.profile_revision,
      workflowRevision: projection.workflow_revision,
      projectionToken: projection.projection_token,
      sourceTokens: new Map(projection.source_facts.map(item => [item.ref, item.token])),
      legacyTokens: new Map(projection.legacy_treatments.map(item => [item.id, item.token])),
      courseTokens: new Map(projection.courses.map(item => [item.id, item.token])),
      discrepancyTokens: new Map(projection.discrepancies.map(item => [item.id, item.token])),
      actionTokens: new Map(projection.eligible_actions.map(item => [item.id, item.token])),
    };
  }

  function treatmentResponseOwnerIsCurrent(owner = treatmentResponseOwner) {
    if (
      !owner
      || owner !== treatmentResponseOwner
      || owner.requestPhiEpoch !== phiEpoch
      || owner.loadEpoch !== treatmentLoadEpoch
      || !treatmentProjection
      || owner.projectionToken !== treatmentProjection.projection_token
      || owner.profileRevision !== treatmentProjection.profile_revision
      || owner.workflowRevision !== treatmentProjection.workflow_revision
      || owner.sourceTokens.size !== treatmentProjection.source_facts.length
      || owner.legacyTokens.size !== treatmentProjection.legacy_treatments.length
      || owner.courseTokens.size !== treatmentProjection.courses.length
      || owner.discrepancyTokens.size !== treatmentProjection.discrepancies.length
      || owner.actionTokens.size !== treatmentProjection.eligible_actions.length
      || treatmentProjection.source_facts.some(item => owner.sourceTokens.get(item.ref) !== item.token)
      || treatmentProjection.legacy_treatments.some(item => owner.legacyTokens.get(item.id) !== item.token)
      || treatmentProjection.courses.some(item => owner.courseTokens.get(item.id) !== item.token)
      || treatmentProjection.discrepancies.some(item => owner.discrepancyTokens.get(item.id) !== item.token)
      || treatmentProjection.eligible_actions.some(item => owner.actionTokens.get(item.id) !== item.token)
    ) return false;
    if (treatmentProjectionState === 'stale') return true;
    const profile = normalizedRevision(latestProfileRevision);
    const workflow = normalizedRevision(workflowRevision);
    return (!Number.isSafeInteger(profile) || profile === owner.profileRevision)
      && (!Number.isSafeInteger(workflow) || workflow === owner.workflowRevision);
  }

  function treatmentScalarNode(value, present = true) {
    if (!present) return treatmentElement('span', 'treatment-missing', 'Missing field');
    if (value === null) return treatmentElement('span', 'treatment-missing', 'Null');
    if (value === '') return treatmentElement('span', 'treatment-empty', 'Empty string ("")');
    if (typeof value === 'string') {
      if (value.length <= 160) return treatmentElement('span', 'treatment-exact-value', value);
      const details = treatmentElement('details', 'treatment-exact-details');
      details.append(
        treatmentElement('summary', '', `Show exact text (${value.length} characters)`),
        treatmentElement('pre', 'treatment-exact-value', value),
      );
      return details;
    }
    if (typeof value === 'boolean') {
      return treatmentElement('span', 'treatment-exact-value', `Boolean: ${value}`);
    }
    if (typeof value === 'number') {
      return treatmentElement('span', 'treatment-exact-value', `Number: ${String(value)}`);
    }
    const serialized = JSON.stringify(value, null, 2);
    const details = treatmentElement('details', 'treatment-exact-details');
    details.append(
      treatmentElement('summary', '', Array.isArray(value) ? 'Show exact array' : 'Show exact object'),
      treatmentElement('pre', 'treatment-exact-value', serialized),
    );
    return details;
  }

  function treatmentAppendFact(parent, label, object, key, presentation = null) {
    const row = treatmentElement('div', 'treatment-fact');
    row.append(treatmentElement('dt', '', label));
    const value = treatmentElement('dd');
    const present = Object.prototype.hasOwnProperty.call(object, key);
    value.append(presentation
      ? treatmentScalarNode(presentation(object[key], object), present)
      : treatmentScalarNode(object[key], present));
    row.append(value);
    parent.append(row);
  }

  function treatmentDatePresentation(value, course, prefix) {
    return `${value === null ? 'Null' : value} · ${course[`${prefix}_date_precision`]} precision · ${
      course[`${prefix}_date_kind`] === 'caregiver_entered'
        ? 'Caregiver-entered'
        : 'Authority unknown'
    }`;
  }

  function treatmentCourseById(id) {
    return treatmentProjection?.courses.find(item => item.id === id) || null;
  }

  function treatmentDiscrepancyById(id) {
    return treatmentProjection?.discrepancies.find(item => item.id === id) || null;
  }

  function treatmentCourseCard(course, compact = false) {
    const card = treatmentElement('article', `treatment-course-card ${course.status}${compact ? ' compact' : ''}`);
    const heading = treatmentElement('div', 'treatment-card-heading');
    heading.append(
      treatmentElement('span', `treatment-lifecycle ${course.status}`, TREATMENT_STATUS_LABELS[course.status]),
      treatmentElement('span', 'treatment-provenance', course.provenance.label),
    );
    card.append(heading, treatmentElement('h3', '', course.treatment_text));
    const facts = treatmentElement('dl', 'treatment-facts');
    treatmentAppendFact(facts, 'Type wording', course, 'treatment_type_text');
    treatmentAppendFact(facts, 'Dose wording', course, 'dose_text');
    treatmentAppendFact(facts, 'Schedule wording', course, 'schedule_text');
    if (!compact) {
      treatmentAppendFact(facts, 'Route wording', course, 'route_text');
      treatmentAppendFact(facts, 'Frequency wording', course, 'frequency_text');
      treatmentAppendFact(facts, 'Cycle wording', course, 'cycle_text');
      treatmentAppendFact(facts, 'Formulation wording', course, 'formulation_text');
      treatmentAppendFact(facts, 'Indication wording', course, 'indication_text');
      treatmentAppendFact(facts, 'Notes', course, 'notes');
      treatmentAppendFact(facts, 'Start date', course, 'start_date', (value, row) => treatmentDatePresentation(value, row, 'start'));
      treatmentAppendFact(facts, 'Stop date', course, 'stop_date', (value, row) => treatmentDatePresentation(value, row, 'stop'));
      treatmentAppendFact(facts, 'Planned date', course, 'planned_date', (value, row) => treatmentDatePresentation(value, row, 'planned'));
      treatmentAppendFact(
        facts,
        'Associated earlier components',
        { value: course.legacy_component_ids.length
          ? `${course.legacy_component_ids.length} caregiver-associated · unverified`
          : null },
        'value',
      );
      if (course.status === 'past') {
        treatmentAppendFact(
          facts,
          'Recorded terminal outcome',
          { value: TREATMENT_TERMINAL_LABELS[course.terminal_qualifier] },
          'value',
        );
        treatmentAppendFact(facts, 'Other recorded detail', course, 'terminal_detail');
      }
      if (course.previous_course_id !== null) {
        treatmentAppendFact(
          facts,
          'Linked previous record',
          { value: 'This record was created from server-authorized restart authority.' },
          'value',
        );
      }
    }
    card.append(facts);
    if (!compact) {
      const actions = treatmentElement('div', 'treatment-card-actions');
      const editable = treatmentProjectionState === 'current' && treatmentResponseOwnerIsCurrent();
      const edit = treatmentElement('button', 'button secondary', 'Edit recorded details');
      edit.type = 'button';
      edit.disabled = !editable;
      edit.addEventListener('click', () => openTreatmentCourseDialog('edit', edit, course.id));
      actions.append(edit);
      course.lifecycle.allowed_transitions.forEach(transition => {
        const button = treatmentElement(
          'button',
          'button secondary',
          transition.status === 'current' ? 'Record as current' : 'Record terminal outcome',
        );
        button.type = 'button';
        button.disabled = !editable;
        button.addEventListener('click', () => openTreatmentTransitionDialog(
          button,
          course.id,
          transition.status,
        ));
        actions.append(button);
      });
      if (course.lifecycle.restart.eligible) {
        const restart = treatmentElement('button', 'button secondary', 'Create linked new record');
        restart.type = 'button';
        restart.disabled = !editable;
        restart.addEventListener('click', () => openTreatmentCourseDialog('restart', restart, course.id));
        actions.append(restart);
      } else {
        actions.append(treatmentElement(
          'p',
          'treatment-ineligible-reason',
          TREATMENT_RESTART_REASONS[course.lifecycle.restart.reason],
        ));
      }
      card.append(actions);
    }
    return card;
  }

  function treatmentSourceLinks(source) {
    const links = treatmentElement('div', 'treatment-source-actions');
    const sourceUrl = safeTreatmentSourceUrl(source.provenance.source_url, source.ref, 'source');
    const evidenceUrl = source.provenance.evidence_url === null
      ? ''
      : safeTreatmentSourceUrl(source.provenance.evidence_url, source.ref, 'evidence');
    if (evidenceUrl) {
      const link = treatmentElement('a', '', 'Open exact evidence');
      link.href = evidenceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      links.append(link);
    }
    if (sourceUrl) {
      const link = treatmentElement('a', '', 'Open source');
      link.href = sourceUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      links.append(link);
    }
    return links;
  }

  function treatmentSourceRow(source) {
    const row = treatmentElement('tr');
    const observed = treatmentElement('td');
    observed.append(treatmentScalarNode(source.observed_text));
    const value = treatmentElement('td');
    value.append(treatmentScalarNode(source.record_value));
    const state = treatmentElement(
      'td',
      '',
      `${source.receipt_state} · ${source.review_state} · ${source.operation}`,
    );
    const provenance = treatmentElement('td');
    provenance.append(
      treatmentElement('strong', '', source.provenance.label),
      treatmentSourceLinks(source),
    );
    row.append(observed, value, state, provenance);
    return row;
  }

  function treatmentLegacyCard(row) {
    const card = treatmentElement('article', 'treatment-legacy-card');
    card.append(
      treatmentElement('p', 'treatment-authority-label', 'Earlier app record · read-only · not source-verified'),
      treatmentElement('h3', '', row.raw_text),
    );
    const components = treatmentElement('section', 'treatment-legacy-section');
    components.append(treatmentElement('h4', '', 'Stable earlier components'));
    if (row.components.length) {
      const list = treatmentElement('ol');
      row.components.forEach(component => {
        const item = treatmentElement('li');
        item.append(
          treatmentScalarNode(component.text),
          treatmentElement('span', 'treatment-component-label', 'Earlier app component · not source-verified'),
        );
        list.append(item);
      });
      components.append(list);
    } else {
      components.append(treatmentElement('p', 'treatment-missing', 'No components recorded.'));
    }
    const generated = treatmentElement('section', 'treatment-generated-section');
    generated.append(treatmentElement(
      'h4',
      '',
      'Machine-generated compatibility context · not a treatment record',
    ));
    if (row.generated_classification.length) {
      const list = treatmentElement('ol');
      row.generated_classification.forEach(item => {
        const entry = treatmentElement('li');
        const facts = treatmentElement('dl', 'treatment-facts');
        treatmentAppendFact(facts, 'Generated text', item, 'text');
        treatmentAppendFact(facts, 'Generated label', item, 'label');
        treatmentAppendFact(facts, 'Generated category', item, 'category');
        treatmentAppendFact(facts, 'Generated date', item, 'date');
        entry.append(facts);
        list.append(entry);
      });
      generated.append(list);
    } else {
      generated.append(treatmentElement('p', 'treatment-missing', 'No generated classification recorded.'));
    }
    card.append(components, generated);
    return card;
  }

  function treatmentCitationPanel(label, side, kind) {
    const panel = treatmentElement('section', 'treatment-citation-panel');
    panel.append(treatmentElement('h4', '', label));
    const snapshot = treatmentElement('section', 'treatment-citation-snapshot');
    snapshot.append(treatmentElement('h5', '', 'Immutable snapshot when recorded'));
    const current = treatmentElement('section', 'treatment-citation-current');
    current.append(treatmentElement('h5', '', 'Current side state'));
    if (kind === 'source') {
      const snapshotFacts = treatmentElement('dl', 'treatment-facts');
      treatmentAppendFact(snapshotFacts, 'Observed wording', side.snapshot, 'observed_text');
      treatmentAppendFact(snapshotFacts, 'Recorded value', side.snapshot, 'record_value');
      snapshot.append(snapshotFacts);
      const currentFacts = treatmentElement('dl', 'treatment-facts');
      treatmentAppendFact(currentFacts, 'Observed wording', side.current, 'observed_text');
      treatmentAppendFact(currentFacts, 'Recorded value', side.current, 'record_value');
      current.append(currentFacts);
    } else {
      snapshot.append(treatmentCourseCard(side.snapshot, true));
      current.append(treatmentCourseCard(side.current, true));
    }
    panel.append(snapshot, current);
    return panel;
  }

  function treatmentDiscrepancyCard(discrepancy) {
    const card = treatmentElement('article', `treatment-discrepancy-card ${discrepancy.status}`);
    const heading = treatmentElement('div', 'treatment-card-heading');
    heading.append(
      treatmentElement('span', `treatment-lifecycle ${discrepancy.status}`, discrepancy.status === 'open' ? 'Open difference' : 'Resolved difference'),
      treatmentElement('span', 'treatment-provenance', discrepancy.provenance.label),
    );
    card.append(
      heading,
      treatmentElement('h3', '', discrepancy.category.replace(/_/g, ' ')),
      treatmentScalarNode(discrepancy.comparison_text),
    );
    const citations = treatmentElement('div', 'treatment-citation-grid');
    citations.append(treatmentCitationPanel('Record A', discrepancy.citations.source_a, 'source'));
    if (discrepancy.citations.source_b) {
      citations.append(treatmentCitationPanel('Record B', discrepancy.citations.source_b, 'source'));
    } else if (discrepancy.citations.course_b) {
      citations.append(treatmentCitationPanel('Record B', discrepancy.citations.course_b, 'course'));
    } else {
      const unavailable = treatmentElement('section', 'treatment-citation-panel unavailable');
      unavailable.append(
        treatmentElement('h4', '', 'Record B'),
        treatmentElement('p', '', 'Second citation unavailable · earlier incomplete workflow authority · read-only'),
      );
      citations.append(unavailable);
    }
    card.append(citations);
    if (discrepancy.confirmations.length) {
      const outcomes = treatmentElement('section', 'treatment-outcomes');
      outcomes.append(treatmentElement('h4', '', 'Recorded treating-team outcomes'));
      discrepancy.confirmations.forEach(confirmation => {
        const outcome = treatmentElement('article', 'treatment-outcome');
        outcome.append(
          treatmentElement('p', 'treatment-confirmation-label', TREATMENT_CONFIRMATION_LABEL),
          treatmentElement('strong', '', confirmation.outcome.replace(/_/g, ' ')),
        );
        const facts = treatmentElement('dl', 'treatment-facts');
        treatmentAppendFact(facts, 'Caregiver note', confirmation, 'note');
        treatmentAppendFact(facts, 'Clinician attribution', confirmation, 'clinician_text');
        treatmentAppendFact(facts, 'Context', confirmation, 'context_text');
        treatmentAppendFact(facts, 'Date', confirmation, 'date');
        outcome.append(facts);
        outcomes.append(outcome);
      });
      card.append(outcomes);
    }
    const followUp = treatmentElement('section', 'treatment-linked-follow-up');
    followUp.append(treatmentElement('h4', '', 'Atomic follow-up link'));
    if (discrepancy.follow_up) {
      followUp.append(
        treatmentElement('p', '', discrepancy.follow_up.text),
        treatmentElement('p', '', `${discrepancy.follow_up.status} · owner ${discrepancy.follow_up.owner ?? 'Null'} · due ${discrepancy.follow_up.due_date ?? 'Null'}`),
      );
    } else {
      followUp.append(treatmentElement('p', 'treatment-missing', 'No follow-up linked.'));
    }
    card.append(followUp);
    const actions = treatmentElement('div', 'treatment-card-actions');
    const mutable = treatmentProjectionState === 'current' && treatmentResponseOwnerIsCurrent();
    if (discrepancy.eligibility.resolve) {
      const resolve = treatmentElement('button', 'button secondary', 'Record treating-team outcome');
      resolve.type = 'button';
      resolve.disabled = !mutable;
      resolve.addEventListener('click', () => openTreatmentDiscrepancyDialog('resolve', resolve, discrepancy.id));
      actions.append(resolve);
    }
    if (discrepancy.eligibility.reopen) {
      const reopen = treatmentElement('button', 'button secondary', 'Reopen difference');
      reopen.type = 'button';
      reopen.disabled = !mutable;
      reopen.addEventListener('click', () => openTreatmentDiscrepancyDialog('reopen', reopen, discrepancy.id));
      actions.append(reopen);
    }
    if (discrepancy.eligibility.recur) {
      const recur = treatmentElement('button', 'button secondary', 'Record recurrence');
      recur.type = 'button';
      recur.disabled = !mutable;
      recur.addEventListener('click', () => openTreatmentDiscrepancyDialog('recur', recur, discrepancy.id));
      actions.append(recur);
    }
    if (discrepancy.citation_authority.state === 'complete') {
      const linked = treatmentElement(
        'button',
        'button secondary',
        discrepancy.follow_up ? 'Review linked follow-up' : 'Manage follow-up',
      );
      linked.type = 'button';
      linked.disabled = !mutable;
      linked.addEventListener('click', () => openTreatmentDiscrepancyDialog('follow-up', linked, discrepancy.id));
      actions.append(linked);
    }
    card.append(actions);
    return card;
  }

  function setTreatmentFreshness(state, text) {
    ['today-treatment-freshness', 'patient-treatment-freshness'].forEach(id => {
      const node = document.getElementById(id);
      if (!node) return;
      node.className = `treatment-freshness ${safeClassToken(state, 'error')}`;
      node.textContent = text;
    });
  }

  function setTreatmentStatus(message, state = '', retry = false) {
    ['today-treatment-status', 'patient-treatment-status'].forEach(id => {
      const node = document.getElementById(id);
      if (!node) return;
      node.className = `treatment-status${state ? ` ${safeClassToken(state)}` : ''}`;
      node.textContent = message || '';
    });
    ['today-treatment-retry', 'treatment-retry'].forEach(id => {
      const retryNode = document.getElementById(id);
      if (retryNode) retryNode.hidden = !retry;
    });
    ['today-treatment-retry-refresh', 'treatment-refresh-button'].forEach(id => {
      const refresh = document.getElementById(id);
      if (refresh) refresh.disabled = treatmentRequestController !== null;
    });
  }

  function updateTreatmentControls() {
    const mutable = treatmentProjectionState === 'current'
      && treatmentResponseOwnerIsCurrent()
      && !treatmentMutationPending
      && pendingTreatmentCompletion === null;
    ['today-treatment-add', 'patient-treatment-add', 'treatment-difference-add'].forEach(id => {
      const control = document.getElementById(id);
      if (control) control.disabled = !mutable;
    });
    document.querySelectorAll(
      '#treatment-workspace .treatment-card-actions button, #treatment-dialog input, '
      + '#treatment-dialog textarea, #treatment-dialog select, #treatment-dialog button',
    ).forEach(control => {
      if (['treatment-retry-submit', 'treatment-retry-verification'].includes(control.id)) return;
      if (treatmentMutationPending) {
        if (!Object.prototype.hasOwnProperty.call(control.dataset, 'treatmentWasDisabled')) {
          control.dataset.treatmentWasDisabled = String(control.disabled);
        }
        control.disabled = true;
      } else if (Object.prototype.hasOwnProperty.call(control.dataset, 'treatmentWasDisabled')) {
        control.disabled = control.dataset.treatmentWasDisabled === 'true';
        delete control.dataset.treatmentWasDisabled;
      }
    });
    if (!treatmentMutationPending) updateTreatmentFormValidity();
  }

  function renderTreatmentProjection(owner = treatmentResponseOwner) {
    if (!treatmentResponseOwnerIsCurrent(owner)) return false;
    const active = treatmentProjection.courses.filter(
      course => course.status === 'current' || course.status === 'planned',
    );
    const currentCount = treatmentProjection.courses.filter(course => course.status === 'current').length;
    const plannedCount = treatmentProjection.courses.filter(course => course.status === 'planned').length;
    const pastCount = treatmentProjection.courses.filter(course => course.status === 'past').length;
    const openDifferences = treatmentProjection.discrepancies.filter(item => item.status === 'open').length;
    const generatedCount = treatmentProjection.legacy_treatments.reduce(
      (total, row) => total + row.generated_classification.length,
      0,
    );
    const shown = active.slice(0, TREATMENT_TODAY_LIMIT);
    const omitted = active.length - shown.length;
    const totals = document.getElementById('today-treatment-totals');
    if (totals) {
      totals.textContent = `Showing ${shown.length} of ${active.length} current/planned records in server order (${currentCount} current, ${plannedCount} planned; ${omitted} omitted here). Patient also contains ${pastCount} past records, ${treatmentProjection.source_fact_count} document mentions, ${treatmentProjection.legacy_treatment_count} earlier app records, ${generatedCount} generated classifications, and ${openDifferences} open differences.`;
    }
    const today = document.getElementById('today-treatment-list');
    if (today) {
      today.replaceChildren(...(
        shown.length
          ? shown.map(course => treatmentCourseCard(course, true))
          : [treatmentElement('div', 'empty-state', 'No current or planned caregiver treatment records are recorded.')]
      ));
    }
    const records = document.getElementById('patient-treatment-list');
    if (records) {
      records.replaceChildren(...(
        treatmentProjection.courses.length
          ? treatmentProjection.courses.map(course => treatmentCourseCard(course))
          : [treatmentElement('div', 'empty-state', 'No caregiver treatment records are recorded.')]
      ));
    }
    const discrepancies = document.getElementById('treatment-discrepancy-list');
    if (discrepancies) {
      discrepancies.replaceChildren(...(
        treatmentProjection.discrepancies.length
          ? treatmentProjection.discrepancies.map(treatmentDiscrepancyCard)
          : [treatmentElement('div', 'empty-state', 'No differences are recorded.')]
      ));
    }
    const sourceBody = document.getElementById('treatment-source-table-body');
    if (sourceBody) {
      if (treatmentProjection.source_facts.length) {
        sourceBody.replaceChildren(...treatmentProjection.source_facts.map(treatmentSourceRow));
      } else {
        const row = treatmentElement('tr');
        const cell = treatmentElement('td', 'empty-state', 'No document treatment mentions are recorded.');
        cell.colSpan = 4;
        row.append(cell);
        sourceBody.replaceChildren(row);
      }
    }
    const legacy = document.getElementById('treatment-legacy-list');
    if (legacy) {
      legacy.replaceChildren(...(
        treatmentProjection.legacy_treatments.length
          ? treatmentProjection.legacy_treatments.map(treatmentLegacyCard)
          : [treatmentElement('div', 'empty-state', 'No earlier app treatment records are recorded.')]
      ));
    }
    const counts = {
      records: treatmentProjection.course_count,
      differences: treatmentProjection.discrepancy_count,
      sources: treatmentProjection.source_fact_count,
      earlier: treatmentProjection.legacy_treatment_count,
    };
    Object.entries(counts).forEach(([name, count]) => {
      const node = document.getElementById(`treatment-count-${name}`);
      if (node) node.textContent = String(count);
    });
    setTreatmentFreshness(
      treatmentProjectionState === 'stale' ? 'stale' : 'current',
      treatmentProjectionState === 'stale' ? 'Read-only snapshot' : 'Current',
    );
    setTreatmentStatus(
      treatmentProjectionState === 'stale'
        ? 'Stale snapshot · read-only until the authoritative treatment record reloads.'
        : 'Authoritative treatment reconciliation loaded.',
      treatmentProjectionState === 'stale' ? 'stale' : 'current',
      treatmentProjectionState === 'stale',
    );
    updateTreatmentControls();
    return true;
  }

  function renderTreatmentUnavailable(message, state, statusLabel, retry = true) {
    const today = document.getElementById('today-treatment-list');
    if (today) today.replaceChildren(treatmentElement('div', 'empty-state', message));
    const totals = document.getElementById('today-treatment-totals');
    if (totals) totals.textContent = 'Treatment totals are unavailable.';
    const records = document.getElementById('patient-treatment-list');
    if (records) records.replaceChildren(treatmentElement('div', 'empty-state', message));
    const differences = document.getElementById('treatment-discrepancy-list');
    if (differences) differences.replaceChildren(treatmentElement('div', 'empty-state', message));
    const sources = document.getElementById('treatment-source-table-body');
    if (sources) {
      const row = treatmentElement('tr');
      const cell = treatmentElement('td', 'empty-state', message);
      cell.colSpan = 4;
      row.append(cell);
      sources.replaceChildren(row);
    }
    const legacy = document.getElementById('treatment-legacy-list');
    if (legacy) legacy.replaceChildren(treatmentElement('div', 'empty-state', message));
    ['records', 'differences', 'sources', 'earlier'].forEach(name => {
      const node = document.getElementById(`treatment-count-${name}`);
      if (node) node.textContent = '0';
    });
    setTreatmentFreshness(state, statusLabel);
    setTreatmentStatus(message, state, retry);
    updateTreatmentControls();
  }

  function treatmentOwnsFocus() {
    const workspace = document.getElementById('treatment-workspace');
    const today = document.getElementById('treatment-today-card');
    const dialog = document.getElementById('treatment-dialog');
    return Boolean(
      workspace?.contains(document.activeElement)
      || today?.contains(document.activeElement)
      || dialog?.contains(document.activeElement)
    );
  }

  function abortTreatmentRequest() {
    const controller = treatmentRequestController;
    treatmentRequestController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function abortTreatmentMutation() {
    const controller = treatmentMutationController;
    treatmentMutationController = null;
    if (controller && !controller.signal.aborted) controller.abort();
  }

  function clearTreatmentRetry() {
    if (pendingTreatmentRetry) pendingTreatmentRetry.bodyText = '';
    if (activeTreatmentIntent && activeTreatmentIntent !== pendingTreatmentRetry) {
      activeTreatmentIntent.bodyText = '';
    }
    pendingTreatmentRetry = null;
    const retry = document.getElementById('treatment-retry-submit');
    if (retry) retry.hidden = true;
  }

  function setTreatmentVerificationRetry(visible) {
    const retry = document.getElementById('treatment-retry-verification');
    if (retry) retry.hidden = !visible;
  }

  function scrubTreatmentDialog(options = {}) {
    const dialog = document.getElementById('treatment-dialog');
    const wasActive = treatmentDialogOpen || activeDialogSurface === dialog;
    treatmentDialogOpen = false;
    treatmentDialogMode = null;
    treatmentSelection = null;
    treatmentDraft = null;
    treatmentSelectionEpoch += 1;
    treatmentDialogEpoch += 1;
    clearTreatmentRetry();
    setTreatmentVerificationRetry(false);
    const body = document.getElementById('treatment-dialog-body');
    if (body) body.replaceChildren();
    ['treatment-form-error', 'treatment-dialog-status'].forEach(id => {
      const node = document.getElementById(id);
      if (node) node.textContent = '';
    });
    const overlay = document.getElementById('treatment-dialog-overlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    if (wasActive) {
      if (dialog?.contains(document.activeElement)) document.activeElement.blur();
      if (activeDialogSurface === dialog) deactivateDialog(dialog, false);
      lastDialogTrigger = null;
      if (options.moveFocus !== false) document.getElementById(`nav-${activeView}`)?.focus();
    }
  }

  function clearTreatmentProjection(options = {}) {
    const relocateFocus = treatmentOwnsFocus();
    treatmentLoadEpoch += 1;
    treatmentMutationEpoch += 1;
    abortTreatmentRequest();
    abortTreatmentMutation();
    treatmentMutationOwner = null;
    treatmentMutationPending = false;
    pendingTreatmentCompletion = null;
    activeTreatmentIntent = null;
    scrubTreatmentDialog({ moveFocus: false });
    if (relocateFocus) document.getElementById(`nav-${activeView}`)?.focus();
    treatmentProjection = null;
    treatmentResponseOwner = null;
    treatmentNetworkAmbiguous = false;
    treatmentProjectionState = options.state || 'error';
    renderTreatmentUnavailable(
      options.message || 'Treatment information could not be loaded.',
      treatmentProjectionState,
      options.statusLabel || 'Unavailable',
      options.retry !== false,
    );
  }

  function markTreatmentProjectionStale(message, options = {}) {
    if (treatmentDialogOpen && options.preserveMutation !== true) {
      captureTreatmentDraft({ forReplacement: true });
      const safeDraft = treatmentDraft;
      scrubTreatmentDialog();
      treatmentDraft = safeDraft;
    }
    clearTreatmentRetry();
    if (options.abortRequest !== false) {
      treatmentLoadEpoch += 1;
      abortTreatmentRequest();
    }
    if (options.preserveMutation !== true) abortTreatmentMutation();
    treatmentProjectionState = 'stale';
    if (!treatmentProjection) {
      renderTreatmentUnavailable(
        message || 'Treatment information is unavailable until an authoritative reload succeeds.',
        'stale',
        'Not current',
        true,
      );
      return;
    }
    treatmentResponseOwner = newTreatmentResponseOwner(
      treatmentProjection,
      options.ownerPhiEpoch ?? phiEpoch,
    );
    renderTreatmentProjection(treatmentResponseOwner);
    setTreatmentStatus(
      message || 'Stale snapshot · read-only until the authoritative treatment record reloads.',
      'stale',
      true,
    );
  }

  function renderTreatmentLoading() {
    if (treatmentProjection) {
      if (treatmentDialogOpen && !treatmentMutationPending) {
        captureTreatmentDraft({ forReplacement: true });
        const safeDraft = treatmentDraft;
        scrubTreatmentDialog();
        treatmentDraft = safeDraft;
      }
      treatmentProjectionState = 'stale';
      setTreatmentFreshness('loading', 'Checking…');
      setTreatmentStatus(
        'Checking the authoritative treatment record. The displayed snapshot is read-only.',
        'loading',
        false,
      );
      updateTreatmentControls();
      return;
    }
    treatmentProjectionState = 'loading';
    renderTreatmentUnavailable(
      'Loading the complete authoritative treatment record…',
      'loading',
      'Loading…',
      false,
    );
  }

  function treatmentTransportRequestIsCurrent(request, acceptedPhiEpoch = null) {
    return Boolean(
      request
      && request.controller === treatmentRequestController
      && !request.controller.signal.aborted
      && request.loadEpoch === treatmentLoadEpoch
      && (acceptedPhiEpoch ?? request.requestPhiEpoch) === phiEpoch
    );
  }

  function treatmentAuthorityMatchesKnown() {
    if (!treatmentProjection || !treatmentResponseOwnerIsCurrent()) return false;
    const profile = normalizedRevision(latestProfileRevision);
    const workflow = normalizedRevision(workflowRevision);
    return (!Number.isSafeInteger(profile) || treatmentProjection.profile_revision === profile)
      && (!Number.isSafeInteger(workflow) || treatmentProjection.workflow_revision === workflow);
  }

  function ensureTreatmentReconciliation(options = {}) {
    const current = treatmentProjection
      && ['current', 'empty'].includes(treatmentProjectionState)
      && !treatmentNetworkAmbiguous
      && treatmentAuthorityMatchesKnown();
    if (!options.force && current) return Promise.resolve(treatmentProjection);
    if (!options.force && treatmentRequestController) return Promise.resolve(null);
    return loadTreatmentReconciliation(options);
  }

  function treatmentCompletionMatchesProjection(completion) {
    if (
      !completion
      || !treatmentProjection
      || completion.profileRevision !== treatmentProjection.profile_revision
      || completion.workflowRevision !== treatmentProjection.workflow_revision
    ) return false;
    const semantic = value => {
      if (Array.isArray(value)) return value.map(semantic);
      if (!value || typeof value !== 'object') return value;
      const result = {};
      Object.keys(value).filter(key => key !== 'token').forEach(key => {
        result[key] = semantic(value[key]);
      });
      return result;
    };
    if (completion.course) {
      const course = treatmentCourseById(completion.course.id);
      if (!course || JSON.stringify(semantic(course)) !== JSON.stringify(semantic(completion.course))) {
        return false;
      }
      if (completion.operation === 'restart') {
        if (
          course.id === completion.previousCourseId
          || course.previous_course_id !== completion.previousCourseId
          || !treatmentCourseById(completion.previousCourseId)
        ) return false;
      }
    }
    if (completion.discrepancy) {
      const discrepancy = treatmentDiscrepancyById(completion.discrepancy.id);
      if (
        !discrepancy
        || JSON.stringify(semantic(discrepancy)) !== JSON.stringify(semantic(completion.discrepancy))
      ) return false;
    }
    if (completion.followUp) {
      const discrepancy = treatmentDiscrepancyById(completion.discrepancy.id);
      if (
        discrepancy?.follow_up?.id !== completion.followUp.id
        || JSON.stringify(semantic(discrepancy.follow_up)) !== JSON.stringify(semantic(completion.followUp))
      ) return false;
    }
    if (completion.expectUnlinked) {
      const discrepancy = treatmentDiscrepancyById(completion.discrepancy.id);
      if (discrepancy?.follow_up !== null) return false;
    }
    return true;
  }

  async function loadTreatmentReconciliation(options = {}) {
    if (!options.force && treatmentRequestController) return null;
    const preserveMutation = options.preserveMutation === true
      || pendingTreatmentCompletion !== null;
    const previous = treatmentRequestController;
    const controller = new AbortController();
    const request = {
      ...capturePatientRequest(),
      loadEpoch: ++treatmentLoadEpoch,
      controller,
    };
    treatmentRequestController = controller;
    if (previous && !previous.signal.aborted) previous.abort();
    setTreatmentVerificationRetry(false);
    renderTreatmentLoading();
    try {
      const response = await fetch('/api/patient/treatment-reconciliation', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      const current = () => treatmentTransportRequestIsCurrent(request, request.acceptedPhiEpoch);
      if (!current()) return null;
      const data = await readJsonResponse(response, () => false);
      if (!current()) return null;
      if (!treatmentProjectionPayloadIsValid(data)) {
        const invalid = new Error('Treatment information could not be verified safely.');
        invalid.status = 422;
        throw invalid;
      }
      const knownProfile = normalizedRevision(latestProfileRevision);
      const knownWorkflow = normalizedRevision(workflowRevision);
      if (
        (Number.isSafeInteger(knownProfile) && data.profile_revision < knownProfile)
        || (Number.isSafeInteger(knownWorkflow) && data.workflow_revision < knownWorkflow)
      ) {
        markTreatmentProjectionStale(
          'A newer patient or workflow revision is available. Treatment information remains read-only while reloading.',
          { abortRequest: false, preserveMutation },
        );
        return null;
      }
      const authority = authorizePatientResponse(request, data, {
        workflow: 'projection',
        treatmentProjection: true,
        treatmentMutation: preserveMutation,
      });
      if (!authority.accepted) return null;
      request.acceptedPhiEpoch = authority.requestPhiEpoch;
      if (!current()) return null;
      const completion = pendingTreatmentCompletion;
      treatmentProjection = data;
      treatmentNetworkAmbiguous = false;
      treatmentProjectionState = (
        data.courses.length
        || data.source_facts.length
        || data.legacy_treatments.length
        || data.discrepancies.length
      ) ? 'current' : 'empty';
      treatmentResponseOwner = newTreatmentResponseOwner(data, request.acceptedPhiEpoch);
      if (!current() || !renderTreatmentProjection(treatmentResponseOwner)) return null;
      if (completion) {
        if (treatmentCompletionMatchesProjection(completion)) {
          finalizeTreatmentMutation(completion);
        } else {
          pendingTreatmentCompletion = null;
          treatmentProjectionState = 'stale';
          scrubTreatmentDialog();
          renderTreatmentProjection(treatmentResponseOwner);
          setTreatmentStatus(
            'The saved response did not match the authoritative replacement. Treatment information remains read-only; retry refresh only.',
            'stale',
            true,
          );
          releaseTreatmentMutation(completion.intent);
        }
      } else if (treatmentDialogOpen) {
        scrubTreatmentDialog({ moveFocus: false });
        setTreatmentStatus(
          'The authoritative treatment record changed. Reopen the form and explicitly reselect server-owned records.',
          'current',
          false,
        );
      }
      reportLoadSuccess('treatment-reconciliation');
      return data;
    } catch (error) {
      const accepted = request.acceptedPhiEpoch ?? null;
      if (error?.name === 'AbortError' || !treatmentTransportRequestIsCurrent(request, accepted)) {
        return null;
      }
      if (error?.status === 401 || error?.status === 403) {
        const safeError = new Error('Treatment authorization is unavailable.');
        safeError.status = error.status;
        evictClientPhi(safeError);
        return null;
      }
      if (error instanceof TypeError) {
        treatmentNetworkAmbiguous = true;
        markTreatmentProjectionStale(
          treatmentProjection
            ? 'Treatment transport is uncertain. The last accepted snapshot is stale and read-only.'
            : 'The treatment endpoint could not be reached and no prior snapshot is available.',
          { abortRequest: false, preserveMutation },
        );
        if (pendingTreatmentCompletion) {
          setTreatmentDialogStatus(
            'The save response was valid, but verification refresh is uncertain. Retry refresh only; the mutation will not be submitted again.',
            'offline',
          );
          setTreatmentVerificationRetry(true);
        }
        reportLoadError('treatment-reconciliation', error);
        return null;
      }
      clearTreatmentProjection({
        state: 'corrupt',
        statusLabel: 'Record unavailable',
        message: 'Treatment information was cleared because the authoritative projection could not be verified safely.',
        retry: true,
      });
      reportLoadError('treatment-reconciliation', error);
      return null;
    } finally {
      if (treatmentRequestController === controller) {
        treatmentRequestController = null;
        ['today-treatment-retry-refresh', 'treatment-refresh-button'].forEach(id => {
          const refresh = document.getElementById(id);
          if (refresh) refresh.disabled = false;
        });
      }
    }
  }

  function selectTreatmentTab(name, options = {}) {
    if (!['records', 'differences', 'sources', 'earlier'].includes(name)) return;
    if (name !== treatmentActiveTab) {
      treatmentActiveTab = name;
      treatmentSelectionEpoch += 1;
      clearTreatmentRetry();
      if (treatmentDialogOpen) closeTreatmentDialog(false, true, false);
    }
    ['records', 'differences', 'sources', 'earlier'].forEach(tabName => {
      const selected = tabName === name;
      const tab = document.getElementById(`treatment-tab-${tabName}`);
      const panel = document.getElementById(`treatment-panel-${tabName}`);
      if (tab) {
        tab.classList.toggle('active', selected);
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
      }
      if (panel) panel.hidden = !selected;
    });
    if (options.focus) document.getElementById(`treatment-tab-${name}`)?.focus();
  }

  function handleTreatmentTabKeydown(event) {
    const names = ['records', 'differences', 'sources', 'earlier'];
    const index = names.indexOf(treatmentActiveTab);
    let next = null;
    if (event.key === 'ArrowRight') next = names[(index + 1) % names.length];
    if (event.key === 'ArrowLeft') next = names[(index - 1 + names.length) % names.length];
    if (event.key === 'Home') next = names[0];
    if (event.key === 'End') next = names[names.length - 1];
    if (!next) return;
    event.preventDefault();
    selectTreatmentTab(next, { focus: true });
  }

  function openPatientTreatments() {
    switchView('patient', document.getElementById('nav-patient'));
    selectTreatmentTab('records');
    document.getElementById('treatments-heading')?.focus();
  }

  function treatmentFieldLabel(label, control, helper = '') {
    const wrapper = treatmentElement('label', 'treatment-field');
    wrapper.append(treatmentElement('span', '', label), control);
    if (helper) wrapper.append(treatmentElement('small', '', helper));
    return wrapper;
  }

  function treatmentTextControl(field, value = '') {
    const maximum = TREATMENT_TEXT_LIMITS[field];
    const multiline = ['treatment_text', 'schedule_text', 'indication_text', 'notes'].includes(field);
    const control = treatmentElement(multiline ? 'textarea' : 'input');
    control.id = `treatment-field-${field.replaceAll('_', '-')}`;
    control.name = field;
    control.maxLength = maximum;
    control.value = value ?? '';
    control.dataset.caregiverField = 'true';
    if (multiline) control.rows = field === 'notes' ? 4 : 2;
    return control;
  }

  function treatmentOptionalField(label, field, value) {
    const wrapper = treatmentElement('div', 'treatment-optional-field');
    const control = treatmentTextControl(field, value);
    wrapper.append(treatmentFieldLabel(label, control));
    const emptyLabel = treatmentElement('label', 'treatment-empty-toggle');
    const empty = treatmentElement('input');
    empty.type = 'checkbox';
    empty.id = `treatment-empty-${field.replaceAll('_', '-')}`;
    empty.checked = value === '';
    empty.dataset.caregiverField = 'true';
    empty.addEventListener('change', () => {
      if (empty.checked) control.value = '';
      updateTreatmentFormValidity();
    });
    control.addEventListener('input', () => {
      if (control.value !== '') empty.checked = false;
    });
    emptyLabel.append(empty, treatmentElement('span', '', 'Record an exact empty string instead of Null'));
    wrapper.append(emptyLabel);
    return wrapper;
  }

  function treatmentCourseForm(course = null, options = {}) {
    const fragment = document.createDocumentFragment();
    const grid = treatmentElement('div', 'treatment-form-grid');
    if (options.includeStatus) {
      const status = treatmentElement('select');
      status.id = 'treatment-field-status';
      status.name = 'status';
      status.dataset.caregiverField = 'true';
      const blank = treatmentElement('option', '', 'Choose a record status');
      blank.value = '';
      status.append(blank);
      (options.restart ? ['current', 'planned'] : ['current', 'planned', 'past']).forEach(value => {
        const option = treatmentElement('option', '', TREATMENT_STATUS_LABELS[value]);
        option.value = value;
        status.append(option);
      });
      status.value = options.draft?.status || '';
      status.addEventListener('change', () => {
        const qualifier = document.getElementById('treatment-field-terminal-qualifier');
        const detail = document.getElementById('treatment-field-terminal-detail');
        if (qualifier) qualifier.value = '';
        if (detail) detail.value = '';
        renderTreatmentTerminalFields();
        updateTreatmentFormValidity();
      });
      grid.append(treatmentFieldLabel(
        options.restart ? 'New linked record status' : 'Record status',
        status,
        options.restart
          ? 'A new record is created; the prior past record is not changed.'
          : 'This is caregiver-entered workflow status, not treatment advice.',
      ));
    }
    const labels = {
      treatment_text: 'Treatment wording',
      treatment_type_text: 'Treatment type wording',
      dose_text: 'Dose wording',
      route_text: 'Route wording',
      frequency_text: 'Frequency wording',
      cycle_text: 'Cycle wording',
      schedule_text: 'Schedule wording',
      formulation_text: 'Formulation wording',
      indication_text: 'Indication wording',
      notes: 'Notes',
    };
    const draft = options.draft || {};
    const required = treatmentTextControl(
      'treatment_text',
      Object.prototype.hasOwnProperty.call(draft, 'treatment_text')
        ? draft.treatment_text
        : (course?.treatment_text ?? ''),
    );
    grid.append(treatmentFieldLabel(
      labels.treatment_text,
      required,
      'Required exact caregiver wording. Nothing is copied from document mentions or generated context.',
    ));
    for (const field of TREATMENT_OPTIONAL_TEXT_FIELDS) {
      const value = Object.prototype.hasOwnProperty.call(draft, field)
        ? draft[field]
        : (course?.[field] ?? null);
      grid.append(treatmentOptionalField(labels[field], field, value));
    }
    for (const prefix of ['start', 'stop', 'planned']) {
      const field = `${prefix}_date`;
      const input = treatmentElement('input');
      input.id = `treatment-field-${field.replaceAll('_', '-')}`;
      input.name = field;
      input.maxLength = 10;
      input.inputMode = 'numeric';
      input.placeholder = 'YYYY, YYYY-MM, or YYYY-MM-DD';
      input.value = Object.prototype.hasOwnProperty.call(draft, field)
        ? draft[field]
        : (course?.[field] ?? '');
      input.dataset.caregiverField = 'true';
      grid.append(treatmentFieldLabel(
        `${prefix[0].toUpperCase()}${prefix.slice(1)} date`,
        input,
        'Exact partial date; no date is inferred or defaulted.',
      ));
    }
    fragment.append(grid);
    const componentFieldset = treatmentElement('fieldset', 'treatment-component-fieldset');
    componentFieldset.append(
      treatmentElement('legend', '', 'Associate earlier app components (optional)'),
      treatmentElement(
        'p',
        'helper-text',
        'Caregiver-associated · unverified. Association does not mean equivalence or source verification.',
      ),
    );
    const componentOptions = [];
    treatmentProjection.legacy_treatments.forEach(row => {
      row.components.forEach(component => componentOptions.push(component));
    });
    treatmentSelection.componentOptions = componentOptions;
    if (componentOptions.length) {
      const list = treatmentElement('div', 'treatment-component-options');
      componentOptions.forEach((component, index) => {
        const label = treatmentElement('label');
        const input = treatmentElement('input');
        input.type = 'checkbox';
        input.name = 'treatment-component-choice';
        input.value = String(index);
        input.checked = options.restart
          ? false
          : Boolean(course?.legacy_component_ids.includes(component.id));
        label.append(
          input,
          treatmentElement('span', '', component.text),
          treatmentElement('small', '', 'Caregiver-associated · unverified'),
        );
        list.append(label);
      });
      componentFieldset.append(list);
    } else {
      componentFieldset.append(treatmentElement('p', 'treatment-missing', 'No earlier components are available.'));
    }
    fragment.append(componentFieldset);
    if (options.includeStatus && !options.restart) {
      const terminal = treatmentElement('fieldset', 'treatment-terminal-fieldset');
      terminal.id = 'treatment-terminal-fields';
      terminal.append(treatmentElement('legend', '', 'Neutral terminal outcome'));
      const qualifier = treatmentElement('select');
      qualifier.id = 'treatment-field-terminal-qualifier';
      qualifier.name = 'terminal_qualifier';
      qualifier.dataset.caregiverField = 'true';
      const blank = treatmentElement('option', '', 'Choose an outcome');
      blank.value = '';
      qualifier.append(blank);
      ['ended', 'not_started', 'cancelled', 'other'].forEach(value => {
        const option = treatmentElement('option', '', TREATMENT_TERMINAL_LABELS[value]);
        option.value = value;
        qualifier.append(option);
      });
      qualifier.addEventListener('change', () => {
        const detail = document.getElementById('treatment-terminal-detail-wrap');
        if (detail) detail.hidden = qualifier.value !== 'other';
        if (qualifier.value !== 'other') {
          const input = document.getElementById('treatment-field-terminal-detail');
          if (input) input.value = '';
        }
        updateTreatmentFormValidity();
      });
      terminal.append(treatmentFieldLabel('Recorded terminal outcome', qualifier));
      const detail = treatmentTextControl('terminal_detail', '');
      const detailWrap = treatmentFieldLabel(
        'Other recorded outcome detail',
        detail,
        'Required only for Other recorded outcome; the wording is not interpreted.',
      );
      detailWrap.id = 'treatment-terminal-detail-wrap';
      detailWrap.hidden = true;
      terminal.append(detailWrap);
      fragment.append(terminal);
    }
    return fragment;
  }

  function renderTreatmentTerminalFields() {
    const fieldset = document.getElementById('treatment-terminal-fields');
    if (!fieldset) return;
    fieldset.hidden = document.getElementById('treatment-field-status')?.value !== 'past';
  }

  function treatmentCategorySelect() {
    const select = treatmentElement('select');
    select.id = 'treatment-field-category';
    select.dataset.caregiverField = 'true';
    const blank = treatmentElement('option', '', 'Choose a neutral category');
    blank.value = '';
    select.append(blank);
    [
      ['name_or_type', 'Name or type wording'],
      ['status', 'Recorded status'],
      ['dose_or_schedule', 'Dose or schedule wording'],
      ['date', 'Recorded date'],
      ['source_wording', 'Source wording'],
      ['other', 'Other recorded difference'],
    ].forEach(([value, text]) => {
      const option = treatmentElement('option', '', text);
      option.value = value;
      select.append(option);
    });
    return select;
  }

  function treatmentDifferenceForm() {
    const fragment = document.createDocumentFragment();
    fragment.append(treatmentElement(
      'p',
      'treatment-authority-note',
      'Choose two records explicitly. NET/Care does not compare, rank, or decide which wording is correct.',
    ));
    const sourceA = treatmentElement('select');
    sourceA.id = 'treatment-source-a';
    const blankA = treatmentElement('option', '', 'Choose document Record A');
    blankA.value = '';
    sourceA.append(blankA);
    treatmentProjection.source_facts.forEach((source, index) => {
      const option = treatmentElement('option', '', source.observed_text);
      option.value = String(index);
      sourceA.append(option);
    });
    fragment.append(treatmentFieldLabel('Record A · document mention', sourceA));
    const variant = treatmentElement('fieldset', 'treatment-choice-fieldset');
    variant.append(treatmentElement('legend', '', 'Record B authority'));
    [
      ['source', 'Another document mention'],
      ['course', 'A caregiver treatment record'],
    ].forEach(([value, text]) => {
      const label = treatmentElement('label');
      const input = treatmentElement('input');
      input.type = 'radio';
      input.name = 'treatment-difference-variant';
      input.value = value;
      input.addEventListener('change', renderTreatmentDifferenceVariant);
      label.append(input, treatmentElement('span', '', text));
      variant.append(label);
    });
    fragment.append(variant);
    const sourcePanel = treatmentElement('div');
    sourcePanel.id = 'treatment-source-b-panel';
    sourcePanel.hidden = true;
    const sourceB = treatmentElement('select');
    sourceB.id = 'treatment-source-b';
    const blankB = treatmentElement('option', '', 'Choose distinct document Record B');
    blankB.value = '';
    sourceB.append(blankB);
    treatmentProjection.source_facts.forEach((source, index) => {
      const option = treatmentElement('option', '', source.observed_text);
      option.value = String(index);
      sourceB.append(option);
    });
    sourcePanel.append(treatmentFieldLabel('Record B · document mention', sourceB));
    const coursePanel = treatmentElement('div');
    coursePanel.id = 'treatment-course-b-panel';
    coursePanel.hidden = true;
    const courseB = treatmentElement('select');
    courseB.id = 'treatment-course-b';
    const blankCourse = treatmentElement('option', '', 'Choose caregiver Record B');
    blankCourse.value = '';
    courseB.append(blankCourse);
    treatmentProjection.courses.forEach((course, index) => {
      const option = treatmentElement('option', '', `${TREATMENT_STATUS_LABELS[course.status]} · ${course.treatment_text}`);
      option.value = String(index);
      courseB.append(option);
    });
    coursePanel.append(treatmentFieldLabel('Record B · caregiver treatment record', courseB));
    fragment.append(sourcePanel, coursePanel);
    const category = treatmentCategorySelect();
    const comparison = treatmentTextControl('notes', '');
    comparison.id = 'treatment-field-comparison';
    comparison.maxLength = 10000;
    fragment.append(
      treatmentFieldLabel('Neutral difference category', category),
      treatmentFieldLabel(
        'Caregiver comparison wording',
        comparison,
        'Record the difference without deciding chronology, preference, causality, or correctness.',
      ),
    );
    return fragment;
  }

  function renderTreatmentDifferenceVariant() {
    const variant = document.querySelector(
      'input[name="treatment-difference-variant"]:checked',
    )?.value || '';
    const source = document.getElementById('treatment-source-b-panel');
    const course = document.getElementById('treatment-course-b-panel');
    if (source) source.hidden = variant !== 'source';
    if (course) course.hidden = variant !== 'course';
    updateTreatmentFormValidity();
  }

  function treatmentResolveForm(discrepancy) {
    const fragment = document.createDocumentFragment();
    fragment.append(treatmentElement('p', 'treatment-confirmation-label', TREATMENT_CONFIRMATION_LABEL));
    const outcome = treatmentElement('select');
    outcome.id = 'treatment-field-outcome';
    outcome.dataset.caregiverField = 'true';
    const blank = treatmentElement('option', '', 'Choose the recorded outcome');
    blank.value = '';
    outcome.append(blank);
    [
      ['confirmed_as_recorded', 'Treating-team outcome recorded as confirmed'],
      ['caregiver_record_corrected', 'Caregiver treatment record corrected'],
      ['source_clarification_needed', 'Source clarification still needed'],
      ['no_change_documented', 'No change documented'],
    ].forEach(([value, text]) => {
      if (value === 'caregiver_record_corrected' && !discrepancy.citations.course_b) return;
      const option = treatmentElement('option', '', text);
      option.value = value;
      outcome.append(option);
    });
    outcome.addEventListener('change', () => {
      const patch = document.getElementById('treatment-course-patch');
      if (patch) patch.hidden = outcome.value !== 'caregiver_record_corrected';
      updateTreatmentFormValidity();
    });
    const note = treatmentTextControl('notes', '');
    note.id = 'treatment-field-resolution-note';
    note.maxLength = 10000;
    const clinician = treatmentTextControl('treatment_type_text', '');
    clinician.id = 'treatment-field-clinician';
    const context = treatmentTextControl('schedule_text', '');
    context.id = 'treatment-field-context';
    context.maxLength = 2000;
    const date = treatmentElement('input');
    date.id = 'treatment-field-resolution-date';
    date.maxLength = 10;
    date.placeholder = 'YYYY, YYYY-MM, or YYYY-MM-DD';
    date.dataset.caregiverField = 'true';
    fragment.append(
      treatmentFieldLabel('Outcome', outcome),
      treatmentFieldLabel('Caregiver note', note),
      treatmentFieldLabel('Clinician attribution wording (optional)', clinician),
      treatmentFieldLabel('Context wording (optional)', context),
      treatmentFieldLabel('Recorded date (optional)', date),
    );
    if (discrepancy.citations.course_b) {
      const patch = treatmentElement('section', 'treatment-course-patch');
      patch.id = 'treatment-course-patch';
      patch.hidden = true;
      patch.append(
        treatmentElement('h3', '', 'Atomic caregiver record correction'),
        treatmentElement(
          'p',
          'helper-text',
          'Only explicit changed fields are submitted with this outcome. Source wording is never copied.',
        ),
        treatmentCourseForm(discrepancy.citations.course_b.current),
      );
      fragment.append(patch);
    }
    return fragment;
  }

  function treatmentRecurrenceForm() {
    const fragment = document.createDocumentFragment();
    fragment.append(
      treatmentElement(
        'p',
        'treatment-authority-note',
        'Record a recurrence using the server-owned prior citation authority. The cited sides cannot be replaced here.',
      ),
      treatmentFieldLabel('Neutral difference category', treatmentCategorySelect()),
    );
    const comparison = treatmentTextControl('notes', '');
    comparison.id = 'treatment-field-comparison';
    comparison.maxLength = 10000;
    fragment.append(treatmentFieldLabel('New caregiver comparison wording', comparison));
    return fragment;
  }

  function treatmentFollowUpForm(discrepancy) {
    const fragment = document.createDocumentFragment();
    if (discrepancy.follow_up) {
      fragment.append(
        treatmentElement('p', '', 'This operation only unlinks the displayed follow-up. It does not alter the follow-up record.'),
      );
      const confirm = treatmentElement('label', 'treatment-confirm-row');
      const checkbox = treatmentElement('input');
      checkbox.type = 'checkbox';
      checkbox.id = 'treatment-confirm-unlink';
      checkbox.dataset.caregiverField = 'true';
      confirm.append(checkbox, treatmentElement('span', '', 'Unlink this follow-up'));
      fragment.append(confirm);
      return fragment;
    }
    const modes = treatmentElement('fieldset', 'treatment-choice-fieldset');
    modes.append(treatmentElement('legend', '', 'Choose one atomic follow-up variant'));
    [
      ['existing', 'Link one currently eligible existing follow-up'],
      ['inline', 'Create and link one manual follow-up'],
    ].forEach(([value, text]) => {
      const label = treatmentElement('label');
      const input = treatmentElement('input');
      input.type = 'radio';
      input.name = 'treatment-follow-up-mode';
      input.value = value;
      input.addEventListener('change', renderTreatmentFollowUpVariant);
      label.append(input, treatmentElement('span', '', text));
      modes.append(label);
    });
    fragment.append(modes);
    const existingPanel = treatmentElement('div');
    existingPanel.id = 'treatment-follow-up-existing-panel';
    existingPanel.hidden = true;
    const existing = treatmentElement('select');
    existing.id = 'treatment-follow-up-existing';
    const blank = treatmentElement('option', '', 'Choose an eligible follow-up');
    blank.value = '';
    existing.append(blank);
    treatmentProjection.eligible_actions.forEach((action, index) => {
      const option = treatmentElement('option', '', action.text);
      option.value = String(index);
      existing.append(option);
    });
    existingPanel.append(treatmentFieldLabel('Existing follow-up', existing));
    const inlinePanel = treatmentElement('div');
    inlinePanel.id = 'treatment-follow-up-inline-panel';
    inlinePanel.hidden = true;
    const text = treatmentElement('textarea');
    text.id = 'treatment-follow-up-text';
    text.maxLength = 1000;
    text.rows = 3;
    text.dataset.caregiverField = 'true';
    const owner = treatmentElement('input');
    owner.id = 'treatment-follow-up-owner';
    owner.maxLength = 100;
    owner.dataset.caregiverField = 'true';
    const due = treatmentElement('input');
    due.id = 'treatment-follow-up-due';
    due.maxLength = 10;
    due.placeholder = 'YYYY, YYYY-MM, or YYYY-MM-DD';
    due.dataset.caregiverField = 'true';
    inlinePanel.append(
      treatmentFieldLabel('Manual follow-up text', text),
      treatmentFieldLabel('Owner (optional)', owner),
      treatmentFieldLabel('Due date (optional)', due),
    );
    fragment.append(existingPanel, inlinePanel);
    return fragment;
  }

  function renderTreatmentFollowUpVariant() {
    const mode = document.querySelector('input[name="treatment-follow-up-mode"]:checked')?.value || '';
    const existing = document.getElementById('treatment-follow-up-existing-panel');
    const inline = document.getElementById('treatment-follow-up-inline-panel');
    if (existing) existing.hidden = mode !== 'existing';
    if (inline) inline.hidden = mode !== 'inline';
    updateTreatmentFormValidity();
  }

  function captureTreatmentDraft(options = {}) {
    if (!treatmentDialogOpen) return null;
    if (options.forReplacement && !['add', 'difference'].includes(treatmentDialogMode)) {
      treatmentDraft = null;
      return null;
    }
    const values = {};
    document.querySelectorAll('#treatment-dialog [data-caregiver-field="true"]').forEach(control => {
      if (!control.name && !control.id) return;
      const key = control.name || control.id;
      values[key] = control.type === 'checkbox' ? control.checked : control.value;
    });
    treatmentDraft = {
      mode: treatmentDialogMode,
      values,
    };
    return treatmentDraft;
  }

  function restoreTreatmentDraft(draft) {
    if (!draft?.values) return;
    Object.entries(draft.values).forEach(([key, value]) => {
      const control = document.querySelector(
        `#treatment-dialog [name="${CSS.escape(key)}"], #${CSS.escape(key)}`,
      );
      if (!control || control.name?.startsWith('treatment-component-choice')) return;
      if (control.type === 'checkbox') control.checked = value === true;
      else control.value = String(value ?? '');
    });
    renderTreatmentTerminalFields();
    const qualifier = document.getElementById('treatment-field-terminal-qualifier');
    const detail = document.getElementById('treatment-terminal-detail-wrap');
    if (detail) detail.hidden = qualifier?.value !== 'other';
  }

  function setTreatmentDialogStatus(message, state = '') {
    const node = document.getElementById('treatment-dialog-status');
    if (!node) return;
    node.className = `treatment-dialog-status${state ? ` ${safeClassToken(state)}` : ''}`;
    node.textContent = message || '';
  }

  function openTreatmentDialog(mode, trigger, selection = {}) {
    if (
      treatmentProjectionState !== 'current'
      || !treatmentResponseOwnerIsCurrent()
      || treatmentMutationPending
      || pendingTreatmentCompletion
    ) {
      setTreatmentStatus('Reload the current treatment record before making changes.', 'stale', true);
      return;
    }
    const preservedDraft = treatmentDraft?.mode === mode ? treatmentDraft : null;
    clearTreatmentRetry();
    treatmentSelectionEpoch += 1;
    treatmentDialogEpoch += 1;
    treatmentDialogMode = mode;
    treatmentDialogOpen = true;
    treatmentSelection = { ...selection, componentOptions: [] };
    treatmentDraft = null;
    const body = document.getElementById('treatment-dialog-body');
    body.replaceChildren();
    const title = document.getElementById('treatment-dialog-title');
    const eyebrow = document.getElementById('treatment-dialog-eyebrow');
    const submit = document.getElementById('treatment-submit-button');
    eyebrow.textContent = mode === 'resolve'
      ? TREATMENT_CONFIRMATION_LABEL
      : 'Caregiver-maintained · unverified';
    const course = selection.courseId ? treatmentCourseById(selection.courseId) : null;
    const discrepancy = selection.discrepancyId
      ? treatmentDiscrepancyById(selection.discrepancyId)
      : null;
    if (selection.courseId && !course) return scrubTreatmentDialog();
    if (selection.discrepancyId && !discrepancy) return scrubTreatmentDialog();
    if (mode === 'add') {
      title.textContent = 'Record treatment';
      submit.textContent = 'Save treatment record';
      body.append(treatmentCourseForm(null, { includeStatus: true }));
      renderTreatmentTerminalFields();
    } else if (mode === 'edit') {
      title.textContent = 'Edit recorded treatment details';
      submit.textContent = 'Save explicit changes';
      body.append(treatmentCourseForm(course));
    } else if (mode === 'restart') {
      title.textContent = 'Create linked new treatment record';
      submit.textContent = 'Create new linked record';
      body.append(treatmentCourseForm(null, { includeStatus: true, restart: true }));
    } else if (mode === 'transition') {
      title.textContent = selection.targetStatus === 'past'
        ? 'Record terminal outcome'
        : 'Record as current';
      submit.textContent = 'Save status change';
      body.append(treatmentElement(
        'p',
        'treatment-authority-note',
        `Server-authorized transition from ${course.status} to ${selection.targetStatus}.`,
      ));
      if (selection.qualifiers.length) {
        const qualifier = treatmentElement('select');
        qualifier.id = 'treatment-field-terminal-qualifier';
        qualifier.dataset.caregiverField = 'true';
        const blank = treatmentElement('option', '', 'Choose an outcome');
        blank.value = '';
        qualifier.append(blank);
        selection.qualifiers.forEach(value => {
          const option = treatmentElement('option', '', TREATMENT_TERMINAL_LABELS[value]);
          option.value = value;
          qualifier.append(option);
        });
        qualifier.addEventListener('change', () => {
          const detail = document.getElementById('treatment-terminal-detail-wrap');
          if (detail) detail.hidden = qualifier.value !== 'other';
          const detailInput = document.getElementById('treatment-field-terminal-detail');
          if (qualifier.value !== 'other' && detailInput) detailInput.value = '';
          updateTreatmentFormValidity();
        });
        body.append(treatmentFieldLabel('Recorded terminal outcome', qualifier));
        const detail = treatmentTextControl('terminal_detail', '');
        const wrap = treatmentFieldLabel('Other recorded outcome detail', detail);
        wrap.id = 'treatment-terminal-detail-wrap';
        wrap.hidden = true;
        body.append(wrap);
      }
    } else if (mode === 'difference') {
      title.textContent = 'Record a difference to review';
      submit.textContent = 'Save difference';
      body.append(treatmentDifferenceForm());
    } else if (mode === 'resolve') {
      title.textContent = 'Record treating-team outcome';
      submit.textContent = 'Save outcome atomically';
      body.append(treatmentResolveForm(discrepancy));
    } else if (mode === 'reopen') {
      title.textContent = 'Reopen recorded difference';
      submit.textContent = 'Reopen difference';
      body.append(treatmentElement(
        'p',
        'treatment-authority-note',
        'The prior treating-team outcomes remain visible and are not changed by reopening.',
      ));
    } else if (mode === 'recur') {
      title.textContent = 'Record recurring difference';
      submit.textContent = 'Save recurrence';
      body.append(treatmentRecurrenceForm());
    } else if (mode === 'follow-up') {
      title.textContent = discrepancy.follow_up ? 'Unlink follow-up' : 'Link a follow-up';
      submit.textContent = discrepancy.follow_up ? 'Unlink follow-up' : 'Save atomic follow-up';
      body.append(treatmentFollowUpForm(discrepancy));
    } else {
      return scrubTreatmentDialog();
    }
    restoreTreatmentDraft(preservedDraft);
    setFormError('treatment-form-error', '');
    setTreatmentDialogStatus('');
    const overlay = document.getElementById('treatment-dialog-overlay');
    const dialog = document.getElementById('treatment-dialog');
    overlay.inert = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    dialog.inert = false;
    activateDialog(dialog, trigger);
    document.getElementById('treatment-form')?.addEventListener(
      'input',
      invalidateTreatmentRetryOnDraftChange,
      { once: true },
    );
    updateTreatmentFormValidity();
  }

  function openTreatmentAddDialog(trigger) {
    openTreatmentDialog('add', trigger);
  }

  function openTreatmentCourseDialog(mode, trigger, courseId) {
    const course = treatmentCourseById(courseId);
    if (!course) return;
    if (mode === 'restart' && course.lifecycle.restart.eligible !== true) return;
    openTreatmentDialog(mode, trigger, { courseId, courseToken: course.token });
  }

  function openTreatmentTransitionDialog(trigger, courseId, targetStatus) {
    const course = treatmentCourseById(courseId);
    const transition = course?.lifecycle.allowed_transitions.find(
      item => item.status === targetStatus,
    );
    if (!course || !transition) return;
    openTreatmentDialog('transition', trigger, {
      courseId,
      courseToken: course.token,
      targetStatus,
      qualifiers: [...transition.terminal_qualifiers],
    });
  }

  function openTreatmentDifferenceDialog(trigger) {
    openTreatmentDialog('difference', trigger);
  }

  function openTreatmentDiscrepancyDialog(mode, trigger, discrepancyId) {
    const discrepancy = treatmentDiscrepancyById(discrepancyId);
    if (!discrepancy) return;
    if (mode === 'resolve' && !discrepancy.eligibility.resolve) return;
    if (mode === 'reopen' && !discrepancy.eligibility.reopen) return;
    if (mode === 'recur' && !discrepancy.eligibility.recur) return;
    if (mode === 'follow-up' && discrepancy.citation_authority.state !== 'complete') return;
    openTreatmentDialog(mode, trigger, {
      discrepancyId,
      discrepancyToken: discrepancy.token,
    });
  }

  function closeTreatmentDialog(preserveDraft = true, force = false, restoreFocus = true) {
    if (!treatmentDialogOpen) return;
    if (treatmentMutationPending && !force) {
      setTreatmentDialogStatus('Saving is still in progress. Wait for the result before closing.', 'saving');
      return;
    }
    if (preserveDraft) captureTreatmentDraft();
    treatmentDialogOpen = false;
    treatmentDialogMode = null;
    treatmentSelection = null;
    treatmentDraft = null;
    treatmentSelectionEpoch += 1;
    treatmentDialogEpoch += 1;
    clearTreatmentRetry();
    setTreatmentVerificationRetry(false);
    const body = document.getElementById('treatment-dialog-body');
    if (body) body.replaceChildren();
    const overlay = document.getElementById('treatment-dialog-overlay');
    const dialog = document.getElementById('treatment-dialog');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.inert = true;
    if (dialog) dialog.inert = true;
    deactivateDialog(dialog, restoreFocus);
  }

  function closeTreatmentDialogFromBackdrop(event) {
    if (event?.target === document.getElementById('treatment-dialog-overlay')) {
      closeTreatmentDialog();
    }
  }

  function invalidateTreatmentRetryOnDraftChange() {
    if (pendingTreatmentRetry) {
      clearTreatmentRetry();
      setTreatmentDialogStatus(
        'The draft changed. Submit a new request after reviewing current treatment authority.',
        'conflict',
      );
    }
    captureTreatmentDraft();
    updateTreatmentFormValidity();
    if (treatmentDialogOpen) {
      document.getElementById('treatment-form')?.addEventListener(
        'input',
        invalidateTreatmentRetryOnDraftChange,
        { once: true },
      );
    }
  }

  function updateTreatmentFormValidity() {
    const submit = document.getElementById('treatment-submit-button');
    if (!submit || !treatmentDialogOpen) return;
    let valid = treatmentProjectionState === 'current'
      && treatmentResponseOwnerIsCurrent()
      && !treatmentMutationPending;
    if (['add', 'edit', 'restart'].includes(treatmentDialogMode)) {
      valid = valid
        && Boolean(document.getElementById('treatment-field-treatment-text')?.value)
        && ['start', 'stop', 'planned'].every(prefix => treatmentDateInputIsValid(
          document.getElementById(`treatment-field-${prefix}-date`)?.value || '',
        ));
      if (['add', 'restart'].includes(treatmentDialogMode)) {
        valid = valid && Boolean(document.getElementById('treatment-field-status')?.value);
      }
      if (
        treatmentDialogMode === 'add'
        && document.getElementById('treatment-field-status')?.value === 'past'
      ) {
        const qualifier = document.getElementById('treatment-field-terminal-qualifier')?.value;
        valid = valid && ['ended', 'not_started', 'cancelled', 'other'].includes(qualifier);
        if (qualifier === 'other') {
          valid = valid && Boolean(
            document.getElementById('treatment-field-terminal-detail')?.value.trim(),
          );
        }
      }
    } else if (treatmentDialogMode === 'transition') {
      if (treatmentSelection.qualifiers.length) {
        const qualifier = document.getElementById('treatment-field-terminal-qualifier')?.value;
        valid = valid && treatmentSelection.qualifiers.includes(qualifier);
        if (qualifier === 'other') {
          valid = valid && Boolean(
            document.getElementById('treatment-field-terminal-detail')?.value.trim(),
          );
        }
      }
    } else if (treatmentDialogMode === 'difference') {
      const a = document.getElementById('treatment-source-a')?.value ?? '';
      const variant = document.querySelector(
        'input[name="treatment-difference-variant"]:checked',
      )?.value || '';
      const b = variant === 'source'
        ? (document.getElementById('treatment-source-b')?.value ?? '')
        : (document.getElementById('treatment-course-b')?.value ?? '');
      valid = valid
        && a !== ''
        && b !== ''
        && !(variant === 'source' && a === b)
        && Boolean(document.getElementById('treatment-field-category')?.value)
        && Boolean(document.getElementById('treatment-field-comparison')?.value);
    } else if (treatmentDialogMode === 'resolve') {
      const outcome = document.getElementById('treatment-field-outcome')?.value;
      valid = valid
        && Boolean(outcome)
        && Boolean(document.getElementById('treatment-field-resolution-note')?.value)
        && treatmentDateInputIsValid(
          document.getElementById('treatment-field-resolution-date')?.value || '',
        );
      if (outcome === 'caregiver_record_corrected') {
        try {
          valid = valid && Object.keys(treatmentCoursePatch()).length > 0;
        } catch (_) {
          valid = false;
        }
      }
    } else if (treatmentDialogMode === 'recur') {
      valid = valid
        && Boolean(document.getElementById('treatment-field-category')?.value)
        && Boolean(document.getElementById('treatment-field-comparison')?.value);
    } else if (treatmentDialogMode === 'follow-up') {
      const discrepancy = treatmentDiscrepancyById(treatmentSelection.discrepancyId);
      if (discrepancy?.follow_up) {
        valid = valid && document.getElementById('treatment-confirm-unlink')?.checked === true;
      } else {
        const mode = document.querySelector('input[name="treatment-follow-up-mode"]:checked')?.value;
        valid = valid && (
          (mode === 'existing' && document.getElementById('treatment-follow-up-existing')?.value !== '')
          || (
            mode === 'inline'
            && Boolean(document.getElementById('treatment-follow-up-text')?.value.trim())
            && treatmentDateInputIsValid(
              document.getElementById('treatment-follow-up-due')?.value || '',
            )
          )
        );
      }
    }
    submit.disabled = !valid;
  }

  function treatmentOptionalInputValue(field) {
    const value = document.getElementById(`treatment-field-${field.replaceAll('_', '-')}`)?.value ?? '';
    const exactEmpty = document.getElementById(`treatment-empty-${field.replaceAll('_', '-')}`)?.checked === true;
    if (value === '') return exactEmpty ? '' : null;
    return value;
  }

  function treatmentSelectedComponentIds() {
    const options = treatmentSelection?.componentOptions || [];
    return [...document.querySelectorAll(
      '#treatment-dialog input[name="treatment-component-choice"]:checked',
    )].map(input => options[Number(input.value)]?.id).filter(Boolean);
  }

  function treatmentCourseValues() {
    const body = {
      treatment_text: document.getElementById('treatment-field-treatment-text')?.value ?? '',
      treatment_type_text: treatmentOptionalInputValue('treatment_type_text'),
      dose_text: treatmentOptionalInputValue('dose_text'),
      route_text: treatmentOptionalInputValue('route_text'),
      frequency_text: treatmentOptionalInputValue('frequency_text'),
      cycle_text: treatmentOptionalInputValue('cycle_text'),
      schedule_text: treatmentOptionalInputValue('schedule_text'),
      formulation_text: treatmentOptionalInputValue('formulation_text'),
      indication_text: treatmentOptionalInputValue('indication_text'),
      notes: treatmentOptionalInputValue('notes'),
      start_date: document.getElementById('treatment-field-start-date')?.value || null,
      stop_date: document.getElementById('treatment-field-stop-date')?.value || null,
      planned_date: document.getElementById('treatment-field-planned-date')?.value || null,
      legacy_component_ids: treatmentSelectedComponentIds(),
    };
    if (!body.treatment_text) throw new Error('Enter exact treatment wording.');
    for (const prefix of ['start', 'stop', 'planned']) {
      const value = body[`${prefix}_date`] || '';
      if (!treatmentDateInputIsValid(value)) {
        throw new Error(`Use YYYY, YYYY-MM, or YYYY-MM-DD for the ${prefix} date.`);
      }
    }
    return body;
  }

  function treatmentCoursePatch() {
    const discrepancy = treatmentDiscrepancyById(treatmentSelection?.discrepancyId);
    const course = discrepancy?.citations.course_b?.current;
    if (!course) throw new Error('The cited caregiver treatment record is unavailable.');
    const values = treatmentCourseValues();
    const patch = {};
    TREATMENT_COURSE_FIELDS.forEach(field => {
      if (values[field] !== course[field]) patch[field] = values[field];
    });
    if (JSON.stringify(values.legacy_component_ids) !== JSON.stringify(course.legacy_component_ids)) {
      patch.legacy_component_ids = values.legacy_component_ids;
    }
    return patch;
  }

  function treatmentMutationMeta() {
    if (!treatmentProjection || !treatmentResponseOwnerIsCurrent()) {
      throw new Error('Reload the authoritative treatment record before saving.');
    }
    return {
      expected_profile_revision: treatmentProjection.profile_revision,
      expected_workflow_revision: treatmentProjection.workflow_revision,
      expected_projection_token: treatmentProjection.projection_token,
    };
  }

  function treatmentBodyForDialog() {
    const meta = treatmentMutationMeta();
    if (treatmentDialogMode === 'add') {
      const values = treatmentCourseValues();
      const status = document.getElementById('treatment-field-status')?.value;
      const body = { ...meta, status, ...values };
      if (status === 'past') {
        const qualifier = document.getElementById('treatment-field-terminal-qualifier')?.value;
        body.terminal_qualifier = qualifier;
        body.terminal_detail = qualifier === 'other'
          ? document.getElementById('treatment-field-terminal-detail')?.value
          : null;
      } else {
        body.terminal_qualifier = null;
        body.terminal_detail = null;
      }
      return {
        method: 'POST',
        url: '/api/treatment-reconciliation/courses',
        body,
        operation: 'add',
      };
    }
    if (treatmentDialogMode === 'edit') {
      return {
        method: 'PATCH',
        url: `/api/treatment-reconciliation/courses/${encodeURIComponent(treatmentSelection.courseId)}`,
        body: {
          ...meta,
          expected_course_token: treatmentSelection.courseToken,
          ...treatmentCourseValues(),
        },
        operation: 'edit',
      };
    }
    if (treatmentDialogMode === 'restart') {
      return {
        method: 'POST',
        url: `/api/treatment-reconciliation/courses/${encodeURIComponent(treatmentSelection.courseId)}/restart`,
        body: {
          ...meta,
          expected_course_token: treatmentSelection.courseToken,
          status: document.getElementById('treatment-field-status')?.value,
          ...treatmentCourseValues(),
        },
        operation: 'restart',
      };
    }
    if (treatmentDialogMode === 'transition') {
      const body = {
        ...meta,
        expected_course_token: treatmentSelection.courseToken,
        status: treatmentSelection.targetStatus,
        terminal_qualifier: null,
        terminal_detail: null,
      };
      if (treatmentSelection.qualifiers.length) {
        const qualifier = document.getElementById('treatment-field-terminal-qualifier')?.value;
        if (!treatmentSelection.qualifiers.includes(qualifier)) {
          throw new Error('Choose one server-authorized terminal outcome.');
        }
        body.terminal_qualifier = qualifier;
        body.terminal_detail = qualifier === 'other'
          ? document.getElementById('treatment-field-terminal-detail')?.value
          : null;
      }
      return {
        method: 'POST',
        url: `/api/treatment-reconciliation/courses/${encodeURIComponent(treatmentSelection.courseId)}/transition`,
        body,
        operation: 'transition',
      };
    }
    if (treatmentDialogMode === 'difference') {
      const sourceIndex = Number(document.getElementById('treatment-source-a')?.value);
      const source = treatmentProjection.source_facts[sourceIndex];
      const variant = document.querySelector(
        'input[name="treatment-difference-variant"]:checked',
      )?.value;
      if (!source) throw new Error('Explicitly choose document Record A.');
      const body = {
        ...meta,
        category: document.getElementById('treatment-field-category')?.value,
        comparison_text: document.getElementById('treatment-field-comparison')?.value ?? '',
        source_fact_ref: source.ref,
        expected_source_fact_token: source.token,
      };
      if (variant === 'source') {
        const comparison = treatmentProjection.source_facts[
          Number(document.getElementById('treatment-source-b')?.value)
        ];
        if (!comparison || comparison.ref === source.ref) {
          throw new Error('Explicitly choose a distinct document Record B.');
        }
        body.comparison_source_fact_ref = comparison.ref;
        body.expected_comparison_source_fact_token = comparison.token;
      } else if (variant === 'course') {
        const course = treatmentProjection.courses[
          Number(document.getElementById('treatment-course-b')?.value)
        ];
        if (!course) throw new Error('Explicitly choose a caregiver treatment Record B.');
        body.course_id = course.id;
        body.expected_course_token = course.token;
      } else {
        throw new Error('Choose one Record B authority.');
      }
      return {
        method: 'POST',
        url: '/api/treatment-reconciliation/discrepancies',
        body,
        operation: 'difference',
      };
    }
    const discrepancy = treatmentDiscrepancyById(treatmentSelection.discrepancyId);
    if (!discrepancy || discrepancy.token !== treatmentSelection.discrepancyToken) {
      throw new Error('The selected difference changed. Reload before saving.');
    }
    if (treatmentDialogMode === 'resolve') {
      const outcome = document.getElementById('treatment-field-outcome')?.value;
      const body = {
        ...meta,
        expected_discrepancy_token: discrepancy.token,
        outcome,
        note: document.getElementById('treatment-field-resolution-note')?.value ?? '',
        clinician_text: treatmentOptionalControlValue('treatment-field-clinician'),
        context_text: treatmentOptionalControlValue('treatment-field-context'),
        date: document.getElementById('treatment-field-resolution-date')?.value || null,
      };
      if (outcome === 'caregiver_record_corrected') {
        const patch = treatmentCoursePatch();
        if (!Object.keys(patch).length) {
          throw new Error('Make at least one explicit caregiver record correction.');
        }
        body.course_patch = patch;
        body.expected_course_token = discrepancy.citations.course_b.current.token;
      }
      return {
        method: 'POST',
        url: `/api/treatment-reconciliation/discrepancies/${encodeURIComponent(discrepancy.id)}/resolve`,
        body,
        operation: 'resolve',
      };
    }
    if (treatmentDialogMode === 'reopen') {
      return {
        method: 'POST',
        url: `/api/treatment-reconciliation/discrepancies/${encodeURIComponent(discrepancy.id)}/reopen`,
        body: { ...meta, expected_discrepancy_token: discrepancy.token },
        operation: 'reopen',
      };
    }
    if (treatmentDialogMode === 'recur') {
      return {
        method: 'POST',
        url: '/api/treatment-reconciliation/discrepancies',
        body: {
          ...meta,
          category: document.getElementById('treatment-field-category')?.value,
          comparison_text: document.getElementById('treatment-field-comparison')?.value ?? '',
          recurs_from_id: discrepancy.id,
          expected_recurs_from_token: discrepancy.token,
        },
        operation: 'recur',
      };
    }
    if (treatmentDialogMode === 'follow-up') {
      const body = { ...meta, expected_discrepancy_token: discrepancy.token };
      if (discrepancy.follow_up) {
        if (document.getElementById('treatment-confirm-unlink')?.checked !== true) {
          throw new Error('Confirm unlinking the displayed follow-up.');
        }
        body.caregiver_action_id = null;
        body.expected_action_token = discrepancy.follow_up.token;
      } else {
        const mode = document.querySelector(
          'input[name="treatment-follow-up-mode"]:checked',
        )?.value;
        if (mode === 'existing') {
          const action = treatmentProjection.eligible_actions[
            Number(document.getElementById('treatment-follow-up-existing')?.value)
          ];
          if (!action) throw new Error('Choose a currently eligible follow-up.');
          body.caregiver_action_id = action.id;
          body.expected_action_token = action.token;
        } else if (mode === 'inline') {
          const text = document.getElementById('treatment-follow-up-text')?.value ?? '';
          const dueDate = document.getElementById('treatment-follow-up-due')?.value || null;
          if (!text.trim()) throw new Error('Enter manual follow-up text.');
          if (dueDate !== null && !treatmentDateInputIsValid(dueDate)) {
            throw new Error('Use YYYY, YYYY-MM, or YYYY-MM-DD for the follow-up due date.');
          }
          body.follow_up = {
            text,
            owner: treatmentOptionalControlValue('treatment-follow-up-owner'),
            due_date: dueDate,
          };
        } else {
          throw new Error('Choose one atomic follow-up variant.');
        }
      }
      return {
        method: 'PATCH',
        url: `/api/treatment-reconciliation/discrepancies/${encodeURIComponent(discrepancy.id)}/follow-up`,
        body,
        operation: discrepancy.follow_up ? 'unlink' : 'follow-up',
      };
    }
    throw new Error('Unsupported treatment operation.');
  }

  function treatmentOptionalControlValue(id) {
    const value = document.getElementById(id)?.value ?? '';
    return value === '' ? null : value;
  }

  function treatmentMutationPayloadIsValid(data, intent) {
    const optional = ['idempotent_replay'];
    if (
      !data
      || typeof data !== 'object'
      || Array.isArray(data)
      || !Number.isSafeInteger(data.profile_revision)
      || data.profile_revision < 0
      || !Number.isSafeInteger(data.workflow_revision)
      || data.workflow_revision < 0
      || (
        Object.prototype.hasOwnProperty.call(data, 'idempotent_replay')
        && data.idempotent_replay !== true
      )
    ) return false;
    const componentIds = new Set(
      treatmentProjection?.legacy_treatments.flatMap(row => row.components.map(item => item.id)) || [],
    );
    if (['add', 'edit', 'restart', 'transition'].includes(intent.operation)) {
      return treatmentHasExactKeys(
        data,
        ['course', 'workflow_revision', 'profile_revision'],
        optional,
      ) && treatmentCourseIsValid(data.course, componentIds);
    }
    if (!treatmentHasExactKeys(
      data,
      ['discrepancy', 'course', 'follow_up', 'workflow_revision', 'profile_revision'],
      optional,
    )) return false;
    if (data.course !== null && !treatmentCourseIsValid(data.course, componentIds)) return false;
    if (data.follow_up !== null && !treatmentActionIsValid(data.follow_up)) return false;
    const citationSources = [
      data.discrepancy?.citations?.source_a?.current,
      data.discrepancy?.citations?.source_b?.current,
    ].filter(Boolean);
    const sources = new Map(citationSources.map(item => [item.ref, item]));
    const citationCourses = [
      data.discrepancy?.citations?.course_b?.current,
      data.course,
    ].filter(Boolean);
    const courses = new Map(citationCourses.map(item => [item.id, item]));
    const actions = new Map(data.follow_up ? [[data.follow_up.id, data.follow_up]] : []);
    return treatmentDiscrepancyIsValid(data.discrepancy, sources, courses, actions)
      && (
        data.follow_up === null
          ? data.discrepancy.follow_up === null
          : data.discrepancy.follow_up?.id === data.follow_up.id
      );
  }

  function beginTreatmentMutation() {
    if (
      treatmentMutationPending
      || pendingTreatmentCompletion
      || treatmentProjectionState !== 'current'
      || !treatmentResponseOwnerIsCurrent()
    ) return null;
    const owner = {};
    treatmentMutationOwner = owner;
    treatmentMutationPending = true;
    treatmentMutationEpoch += 1;
    const previous = treatmentMutationController;
    treatmentMutationController = new AbortController();
    if (previous && !previous.signal.aborted) previous.abort();
    updateTreatmentControls();
    return owner;
  }

  function treatmentIntentOwnsMutation(intent, acceptedPhiEpoch = null) {
    return Boolean(
      intent
      && treatmentMutationPending
      && treatmentMutationOwner === intent.mutationOwner
      && treatmentMutationController === intent.controller
      && !intent.controller.signal.aborted
      && intent.mutationEpoch === treatmentMutationEpoch
      && (acceptedPhiEpoch ?? intent.acceptedPhiEpoch ?? intent.requestPhiEpoch) === phiEpoch
      && intent.selectionEpoch === treatmentSelectionEpoch
      && intent.dialogEpoch === treatmentDialogEpoch
    );
  }

  function releaseTreatmentMutation(intent) {
    if (!intent || treatmentMutationOwner !== intent.mutationOwner) return false;
    treatmentMutationPending = false;
    treatmentMutationOwner = null;
    if (treatmentMutationController === intent.controller) treatmentMutationController = null;
    if (activeTreatmentIntent === intent) activeTreatmentIntent = null;
    updateTreatmentControls();
    return true;
  }

  function createTreatmentIntent(specification, mutationOwner) {
    const canonicalBody = { mutation_id: newMutationId(), ...specification.body };
    return {
      method: specification.method,
      url: specification.url,
      operation: specification.operation,
      bodyText: JSON.stringify(canonicalBody),
      mutationOwner,
      controller: treatmentMutationController,
      mutationEpoch: treatmentMutationEpoch,
      requestPhiEpoch: phiEpoch,
      selectionEpoch: treatmentSelectionEpoch,
      dialogEpoch: treatmentDialogEpoch,
      courseId: treatmentSelection?.courseId || null,
      discrepancyId: treatmentSelection?.discrepancyId || null,
      previousCourseId: specification.operation === 'restart'
        ? treatmentSelection?.courseId
        : null,
    };
  }

  function treatmentCompletionFromResponse(data, intent) {
    return {
      intent,
      operation: intent.operation,
      profileRevision: data.profile_revision,
      workflowRevision: data.workflow_revision,
      course: data.course || null,
      discrepancy: data.discrepancy || null,
      followUp: data.follow_up || null,
      expectUnlinked: intent.operation === 'unlink',
      previousCourseId: intent.previousCourseId,
    };
  }

  function finalizeTreatmentMutation(completion) {
    if (!treatmentIntentOwnsMutation(completion.intent)) return false;
    pendingTreatmentCompletion = null;
    clearTreatmentRetry();
    closeTreatmentDialog(false, true, false);
    releaseTreatmentMutation(completion.intent);
    setTreatmentStatus('Treatment reconciliation saved and verified.', 'current', false);
    reportLoadSuccess('treatment-mutation');
    const target = document.getElementById(
      activeView === 'patient' ? 'treatments-heading' : 'today-treatment-heading',
    );
    target?.focus();
    return true;
  }

  async function handleTreatmentConflict(intent) {
    if (!treatmentIntentOwnsMutation(intent)) return;
    captureTreatmentDraft({ forReplacement: true });
    clearTreatmentRetry();
    const safeDraft = treatmentDraft;
    treatmentProjection = null;
    treatmentResponseOwner = null;
    treatmentProjectionState = 'stale';
    scrubTreatmentDialog();
    treatmentDraft = safeDraft;
    renderTreatmentUnavailable(
      'Treatment authority changed. Reloading the complete record; review the preserved caregiver draft and reselect all server-owned records.',
      'stale',
      'Reloading…',
      false,
    );
    releaseTreatmentMutation(intent);
    await loadTreatmentReconciliation({ force: true });
  }

  async function consumeTreatmentMutationResponse(data, intent) {
    if (!treatmentIntentOwnsMutation(intent, intent.requestPhiEpoch)) return false;
    if (!treatmentMutationPayloadIsValid(data, intent)) {
      clearTreatmentProjection({
        state: 'corrupt',
        statusLabel: 'Record unavailable',
        message: 'Treatment information was cleared because a mutation response could not be verified safely.',
        retry: true,
      });
      return false;
    }
    clearTreatmentRetry();
    const authority = authorizePatientResponse(intent, data, {
      workflow: 'targeted',
      treatmentMutation: true,
    });
    if (!authority.accepted) return false;
    intent.acceptedPhiEpoch = authority.requestPhiEpoch;
    if (!treatmentIntentOwnsMutation(intent)) return false;
    pendingTreatmentCompletion = treatmentCompletionFromResponse(data, intent);
    markTreatmentProjectionStale(
      'Saved response received. Reloading the complete authoritative treatment record before confirming.',
      {
        preserveMutation: true,
        ownerPhiEpoch: authority.requestPhiEpoch,
      },
    );
    await loadTreatmentReconciliation({ force: true, preserveMutation: true });
    return pendingTreatmentCompletion === null;
  }

  async function performTreatmentIntent(intent, explicitRetry = false) {
    if (!treatmentIntentOwnsMutation(intent)) return null;
    activeTreatmentIntent = intent;
    setTreatmentDialogStatus(
      explicitRetry ? 'Retrying the exact unchanged request…' : 'Saving…',
      'saving',
    );
    try {
      const response = await fetch(intent.url, {
        method: intent.method,
        headers: { 'Content-Type': 'application/json' },
        body: intent.bodyText,
        signal: intent.controller.signal,
      });
      if (!treatmentIntentOwnsMutation(intent)) return null;
      const data = await readJsonResponse(response, () => false);
      if (!treatmentIntentOwnsMutation(intent)) return null;
      await consumeTreatmentMutationResponse(data, intent);
      return data;
    } catch (error) {
      if (error?.name === 'AbortError' || !treatmentIntentOwnsMutation(intent)) return null;
      if (error?.status === 401 || error?.status === 403) {
        const safeError = new Error('Treatment authorization is unavailable.');
        safeError.status = error.status;
        evictClientPhi(safeError);
        return null;
      }
      if (error?.status === 409) {
        await handleTreatmentConflict(intent);
        return null;
      }
      if (error instanceof TypeError) {
        pendingTreatmentRetry = intent;
        treatmentNetworkAmbiguous = true;
        treatmentProjectionState = 'stale';
        renderTreatmentProjection(treatmentResponseOwner);
        setTreatmentDialogStatus(
          'Submission status is unknown. The exact request can be retried unchanged; editing or closing destroys that retry.',
          'offline',
        );
        const retry = document.getElementById('treatment-retry-submit');
        if (retry) retry.hidden = false;
        setTreatmentStatus(
          'Treatment submission transport is uncertain. The last accepted projection is stale and read-only.',
          'stale',
          false,
        );
        return null;
      }
      if ([400, 422].includes(error?.status)) {
        captureTreatmentDraft();
        setTreatmentDialogStatus(
          'The submitted fields were not accepted. Review the caregiver-entered draft; the current treatment record remains authoritative.',
          'error',
        );
        setFormError('treatment-form-error', 'Review the supported fields and mechanical limits.');
        reportLoadError('treatment-mutation', error);
        return null;
      }
      setTreatmentDialogStatus(
        'The request was not saved. The current treatment record remains unchanged.',
        'error',
      );
      reportLoadError('treatment-mutation', error);
      return null;
    } finally {
      if (!pendingTreatmentRetry && !pendingTreatmentCompletion) releaseTreatmentMutation(intent);
    }
  }

  async function submitTreatmentDialog(event) {
    event?.preventDefault();
    const mutationOwner = beginTreatmentMutation();
    if (!mutationOwner) return null;
    let intent;
    try {
      const specification = treatmentBodyForDialog();
      intent = createTreatmentIntent(specification, mutationOwner);
      setFormError('treatment-form-error', '');
      return performTreatmentIntent(intent);
    } catch (error) {
      setFormError('treatment-form-error', error.message || 'Review the treatment fields.');
      releaseTreatmentMutation(intent || {
        mutationOwner,
        controller: treatmentMutationController,
      });
      return null;
    }
  }

  async function retryTreatmentSubmission() {
    const intent = pendingTreatmentRetry;
    if (!intent || !intent.bodyText) return;
    if (
      !treatmentDialogOpen
      || intent.selectionEpoch !== treatmentSelectionEpoch
      || intent.dialogEpoch !== treatmentDialogEpoch
    ) {
      clearTreatmentRetry();
      setTreatmentStatus(
        'Submission retry authority expired. Review the current record and submit a new request.',
        'stale',
        true,
      );
      return;
    }
    const owner = {};
    treatmentMutationOwner = owner;
    treatmentMutationPending = true;
    treatmentMutationEpoch += 1;
    treatmentMutationController = new AbortController();
    intent.mutationOwner = owner;
    intent.mutationEpoch = treatmentMutationEpoch;
    intent.controller = treatmentMutationController;
    intent.requestPhiEpoch = phiEpoch;
    intent.acceptedPhiEpoch = null;
    await performTreatmentIntent(intent, true);
  }

  // ── Init ────────────────────────────────────────────────────────────────
  loadStatus().finally(() => ensureTreatmentReconciliation());
  loadTasks();
  loadSummary();
  loadQuestions();
  loadJudgments();
  ensureSymptomEpisodes();
  loadPatientEvidence();
  loadVisits();
  loadFollowUps();
  ['q-add-input', 'judgment-input', 'chat-input'].forEach(id => {
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
  const alertResolutionSurface = document.getElementById('alert-resolution-dialog');
  alertResolutionSurface?.addEventListener('input', invalidateAlertResolutionRetryOnDraftChange);
  alertResolutionSurface?.addEventListener('change', invalidateAlertResolutionRetryOnDraftChange);
  const symptomSurface = document.getElementById('symptom-dialog');
  symptomSurface?.addEventListener('input', invalidateSymptomRetryOnDraftChange);
  symptomSurface?.addEventListener('change', invalidateSymptomRetryOnDraftChange);
  const researchSurface = document.getElementById('research-dialog');
  researchSurface?.addEventListener('input', event => {
    if (event.target?.id !== 'research-event-type') handleResearchDraftChange();
  });
  researchSurface?.addEventListener('change', event => {
    if (event.target?.id !== 'research-event-type') handleResearchDraftChange();
  });
  updateFormValidity();
  startPolling();
  const requestedView = window.location.hash.replace('#', '');
  if (['today', 'patient', 'research', 'questions', 'activity'].includes(requestedView) && requestedView !== 'today') {
    switchView(requestedView, document.getElementById(`nav-${requestedView}`));
  }
