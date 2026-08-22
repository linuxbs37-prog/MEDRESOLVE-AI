/**
 * ============================================================================
 * AuraMed AI — Drug Risk Report Controller
 * ============================================================================
 * Handles the dedicated report form, API calls to /risk-report,
 * and rendering of risk assessment results with tiered risk visualization.
 * ============================================================================
 */

// ============================================================================
// 1. Tag Manager — Reusable tag input system for conditions, meds, allergies
// ============================================================================

const TagManager = {
  _tags: {},

  init(group) {
    if (!this._tags[group]) this._tags[group] = [];
  },

  add(group, value) {
    this.init(group);
    const clean = value.trim().toLowerCase().replace(/\s+/g, '_');
    if (!clean || this._tags[group].includes(clean)) return false;
    this._tags[group].push(clean);
    return true;
  },

  remove(group, value) {
    this.init(group);
    this._tags[group] = this._tags[group].filter(t => t !== value);
  },

  getAll(group) {
    return this._tags[group] || [];
  },

  clear(group) {
    this._tags[group] = [];
  },

  renderTags(group, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    for (const tag of this.getAll(group)) {
      const el = document.createElement('span');
      el.className = 'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#5B65DC]/10 dark:bg-[#5B65DC]/20 text-[#5B65DC] dark:text-[#8F9AF0] border border-[#5B65DC]/20 dark:border-[#5B65DC]/30 message-enter';
      el.innerHTML = `
        <span>${tag.replace(/_/g, ' ')}</span>
        <button type="button" data-remove-tag="${tag}" data-tag-group="${group}" class="hover:text-rose-500 transition-colors ml-0.5" aria-label="Remove">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
      `;
      container.appendChild(el);
    }

    // Bind remove buttons
    container.querySelectorAll('[data-remove-tag]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const tagVal = btn.getAttribute('data-remove-tag');
        const tagGroup = btn.getAttribute('data-tag-group');
        this.remove(tagGroup, tagVal);
        this.renderTags(tagGroup, containerId);

        // Re-enable preset pill if it was toggled
        document.querySelectorAll(`[data-tag-value="${tagVal}"][data-tag-group="${tagGroup}"]`).forEach(pill => {
          pill.classList.remove('bg-[#5B65DC]', 'text-white', 'border-[#5B65DC]');
          pill.classList.add('bg-[#EEEFFD]', 'dark:bg-[#1C2555]', 'text-[#122056]', 'dark:text-[#FAFAFD]', 'border-[#E3E5F8]', 'dark:border-[#1E285C]');
        });
      });
    });
  }
};


// ============================================================================
// 2. Report UI Controller
// ============================================================================

const ReportUI = {

  async init() {
    const user = await AuthService.requireAuth();
    if (!user) return;

    this.form = document.getElementById('reportForm');
    this.submitBtn = document.getElementById('reportSubmitBtn');
    this.spinner = document.getElementById('reportSpinner');
    this.btnIcon = document.getElementById('reportBtnIcon');
    this.btnText = document.getElementById('reportBtnText');
    this.resultsSection = document.getElementById('reportResultsSection');
    this.loadingOverlay = document.getElementById('reportLoadingOverlay');
    this.errorSection = document.getElementById('reportErrorSection');

    this.bindEvents();
    await this.autoFillFromProfile();
  },

  // ── Event Binding ─────────────────────────────────────────────────────────

  bindEvents() {
    // Form submit
    if (this.form) {
      this.form.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleGenerateReport();
      });
    }

    // Quick select drug pills
    document.querySelectorAll('.quick-drug-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        e.preventDefault();
        const drug = pill.getAttribute('data-drug');
        const input = document.getElementById('reportTargetDrug');
        if (input && drug) {
          input.value = drug;
          input.focus();
          // Highlight input briefly
          input.classList.add('border-[#5B65DC]', 'ring-2', 'ring-[#5B65DC]/30');
          setTimeout(() => {
            input.classList.remove('ring-2', 'ring-[#5B65DC]/30');
          }, 1500);
        }
      });
    });

    // Preset tag pills (conditions & allergies)
    document.querySelectorAll('.report-tag-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        e.preventDefault();
        const value = pill.getAttribute('data-tag-value');
        const group = pill.getAttribute('data-tag-group');
        const containerMap = {
          conditions: 'reportConditionsContainer',
          allergies: 'reportAllergiesContainer',
        };

        if (TagManager.getAll(group).includes(value)) {
          TagManager.remove(group, value);
          pill.classList.remove('bg-[#5B65DC]', 'text-white', 'border-[#5B65DC]');
          pill.classList.add('bg-[#EEEFFD]', 'dark:bg-[#1C2555]', 'text-[#122056]', 'dark:text-[#FAFAFD]', 'border-[#E3E5F8]', 'dark:border-[#1E285C]');
        } else {
          TagManager.add(group, value);
          pill.classList.add('bg-[#5B65DC]', 'text-white', 'border-[#5B65DC]');
          pill.classList.remove('bg-[#EEEFFD]', 'dark:bg-[#1C2555]', 'text-[#122056]', 'dark:text-[#FAFAFD]', 'border-[#E3E5F8]', 'dark:border-[#1E285C]');
        }

        TagManager.renderTags(group, containerMap[group]);
      });
    });

    // Custom condition add
    const addCondBtn = document.getElementById('reportAddConditionBtn');
    const condInput = document.getElementById('reportCustomCondition');
    if (addCondBtn && condInput) {
      addCondBtn.addEventListener('click', () => {
        if (condInput.value.trim()) {
          TagManager.add('conditions', condInput.value);
          TagManager.renderTags('conditions', 'reportConditionsContainer');
          condInput.value = '';
        }
      });
      condInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); addCondBtn.click(); }
      });
    }

    // Custom medication add
    const addMedBtn = document.getElementById('reportAddMedBtn');
    const medInput = document.getElementById('reportCustomMed');
    if (addMedBtn && medInput) {
      addMedBtn.addEventListener('click', () => {
        if (medInput.value.trim()) {
          TagManager.add('medications', medInput.value);
          TagManager.renderTags('medications', 'reportMedsContainer');
          medInput.value = '';
        }
      });
      medInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); addMedBtn.click(); }
      });
    }

    // Custom allergy add
    const addAllergyBtn = document.getElementById('reportAddAllergyBtn');
    const allergyInput = document.getElementById('reportCustomAllergy');
    if (addAllergyBtn && allergyInput) {
      addAllergyBtn.addEventListener('click', () => {
        if (allergyInput.value.trim()) {
          TagManager.add('allergies', allergyInput.value);
          TagManager.renderTags('allergies', 'reportAllergiesContainer');
          allergyInput.value = '';
        }
      });
      allergyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); addAllergyBtn.click(); }
      });
    }

    // Pregnancy checkbox → show trimester select
    const pregnancyCheckboxes = document.querySelectorAll('input[name="patient_factors"][value="pregnancy"]');
    pregnancyCheckboxes.forEach(cb => {
      cb.addEventListener('change', () => {
        const trimesterGroup = document.getElementById('reportPregnancyTrimesterGroup');
        if (trimesterGroup) {
          trimesterGroup.classList.toggle('hidden', !cb.checked);
        }
      });
    });

    // Print button
    const printBtn = document.getElementById('reportPrintBtn');
    if (printBtn) printBtn.addEventListener('click', () => window.print());

    // New report button
    const newBtn = document.getElementById('reportNewBtn');
    if (newBtn) newBtn.addEventListener('click', () => this.resetToForm());

    // Retry button
    const retryBtn = document.getElementById('reportRetryBtn');
    if (retryBtn) retryBtn.addEventListener('click', () => this.handleGenerateReport());
  },

  // ── Auto-fill from saved patient profile ────────────────────────────────────

  async autoFillFromProfile() {
    try {
      const profile = await PatientService.loadPatientProfile();
      const medicines = await MedicineService.loadMedicines();

      if (profile) {
        if (profile.fullName) document.getElementById('reportFullName').value = profile.fullName;
        if (profile.dateOfBirth) document.getElementById('reportDOB').value = profile.dateOfBirth;
        if (profile.gender) document.getElementById('reportGender').value = profile.gender;
        if (profile.height) document.getElementById('reportHeight').value = profile.height;
        if (profile.weight) document.getElementById('reportWeight').value = profile.weight;
        if (profile.bloodType) document.getElementById('reportBlood').value = profile.bloodType;

        // Load chronic conditions as tags
        if (profile.chronicConditions && profile.chronicConditions.length > 0) {
          for (const cond of profile.chronicConditions) {
            TagManager.add('conditions', cond);
          }
          TagManager.renderTags('conditions', 'reportConditionsContainer');

          // Activate matching preset pills
          document.querySelectorAll('[data-tag-group="conditions"]').forEach(pill => {
            const val = pill.getAttribute('data-tag-value');
            if (TagManager.getAll('conditions').includes(val)) {
              pill.classList.add('bg-[#5B65DC]', 'text-white', 'border-[#5B65DC]');
              pill.classList.remove('bg-[#EEEFFD]', 'dark:bg-[#1C2555]', 'text-[#122056]', 'dark:text-[#FAFAFD]', 'border-[#E3E5F8]', 'dark:border-[#1E285C]');
            }
          });
        }

        // Load allergies as tags
        if (profile.allergies && profile.allergies.length > 0) {
          for (const allergy of profile.allergies) {
            TagManager.add('allergies', allergy);
          }
          TagManager.renderTags('allergies', 'reportAllergiesContainer');
        }
      }

      // Load medicines as medication tags
      if (medicines && medicines.length > 0) {
        for (const med of medicines) {
          if (med.name) TagManager.add('medications', med.name);
        }
        TagManager.renderTags('medications', 'reportMedsContainer');
      }

    } catch (err) {
      console.warn('Report auto-fill notice:', err);
    }
  },

  // ── Build Patient Profile for API ──────────────────────────────────────────

  buildPatientProfile() {
    const targetDrug = document.getElementById('reportTargetDrug').value.trim();
    const fullName = document.getElementById('reportFullName').value.trim();
    const dob = document.getElementById('reportDOB').value;
    const gender = document.getElementById('reportGender').value;
    const height = document.getElementById('reportHeight').value;
    const weight = document.getElementById('reportWeight').value;
    const bloodType = document.getElementById('reportBlood').value;
    const kidneyFunction = document.getElementById('reportKidneyFunction').value;
    const pregnancyTrimester = document.getElementById('reportPregnancyTrimester').value;

    // Get patient factors from checkboxes
    const patientFactors = [];
    document.querySelectorAll('input[name="patient_factors"]:checked').forEach(cb => {
      patientFactors.push(cb.value);
    });

    const conditions = TagManager.getAll('conditions');
    const medications = TagManager.getAll('medications');
    const allergies = TagManager.getAll('allergies');

    return {
      full_name: fullName,
      date_of_birth: dob || null,
      gender: gender || null,
      blood_type: bloodType || null,
      height_cm: height ? parseFloat(height) : null,
      weight_kg: weight ? parseFloat(weight) : null,
      target_drug: targetDrug,
      target_drug_id: targetDrug.toLowerCase().replace(/\s+/g, '_'),
      target_drugs: [targetDrug, ...medications.filter(m => m.toLowerCase() !== targetDrug.toLowerCase())],
      chronic_conditions: conditions,
      comorbidities: conditions,
      patient_factors: patientFactors,
      current_medications: medications,
      allergies: allergies,
      pregnancy_trimester: pregnancyTrimester || null,
      kidney_function: kidneyFunction || null,
    };
  },

  // ── Generate Report Handler ─────────────────────────────────────────────────

  async handleGenerateReport() {
    const targetDrug = document.getElementById('reportTargetDrug').value.trim();
    if (!targetDrug) {
      document.getElementById('reportTargetDrug').focus();
      document.getElementById('reportTargetDrug').classList.add('border-rose-500', 'ring-2', 'ring-rose-500/20');
      setTimeout(() => {
        document.getElementById('reportTargetDrug').classList.remove('border-rose-500', 'ring-2', 'ring-rose-500/20');
      }, 3000);
      return;
    }

    const additionalQuery = document.getElementById('reportAdditionalQuery').value.trim();
    const patientProfile = this.buildPatientProfile();

    // Show loading state
    this.showLoading(true);
    this.hideError();
    this.hideResults();

    try {
      // Animate loading steps
      this.animateLoadingSteps();

      const response = await MedResolveAPI._post('/risk-report', {
        patient_profile: patientProfile,
        additional_query: additionalQuery || '',
      });

      if (!response || !response.success) {
        throw new Error(response?.refusal_reason || 'No response from backend');
      }

      this.showLoading(false);
      this.renderReport(response, patientProfile);

    } catch (err) {
      console.error('Report generation failed:', err);
      this.showLoading(false);
      this.showError(err.message);
    }
  },

  // ── Render Report Results ──────────────────────────────────────────────────

  renderReport(response, profile) {
    // Drug title
    const drugTitle = document.getElementById('reportDrugTitle');
    if (drugTitle) {
      drugTitle.textContent = `${profile.target_drug} — Personalized Risk Assessment`;
    }

    // Patient Summary
    this.renderPatientSummary(response.patient_profile_summary || profile);

    // Drug Overview
    this.renderDrugOverview(response.drug_overview);

    // Risk Findings
    this.renderRiskFindings(response.risk_findings || []);

    // Evidence Summary
    this.renderEvidenceSummary(response.main_response);

    // Disclaimer
    if (response.disclaimer) {
      const disc = document.getElementById('reportDisclaimer');
      if (disc) disc.textContent = response.disclaimer;
    }

    // Show results
    this.showResults();

    // Scroll to results
    setTimeout(() => {
      document.getElementById('reportResultsSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);

    // Re-init icons
    if (window.lucide) window.lucide.createIcons();
  },

  renderPatientSummary(profile) {
    const container = document.getElementById('reportPatientSummary');
    if (!container) return;

    const items = [];
    if (profile.full_name) items.push(`<span class="font-semibold">Name:</span> ${profile.full_name}`);
    if (profile.gender) items.push(`<span class="font-semibold">Gender:</span> ${profile.gender}`);
    if (profile.date_of_birth) items.push(`<span class="font-semibold">DOB:</span> ${profile.date_of_birth}`);
    if (profile.blood_type) items.push(`<span class="font-semibold">Blood:</span> ${profile.blood_type}`);
    if (profile.height_cm) items.push(`<span class="font-semibold">Height:</span> ${profile.height_cm} cm`);
    if (profile.weight_kg) items.push(`<span class="font-semibold">Weight:</span> ${profile.weight_kg} kg`);
    if (profile.kidney_function) items.push(`<span class="font-semibold">Kidney:</span> ${profile.kidney_function}`);

    const conditions = profile.comorbidities || profile.chronic_conditions || [];
    if (conditions.length > 0) {
      items.push(`<span class="font-semibold">Conditions:</span> ${conditions.map(c => c.replace(/_/g, ' ')).join(', ')}`);
    }
    const meds = profile.current_medications || [];
    if (meds.length > 0) {
      items.push(`<span class="font-semibold">Current Meds:</span> ${meds.map(m => m.replace(/_/g, ' ')).join(', ')}`);
    }
    const allergies = profile.allergies || [];
    if (allergies.length > 0) {
      items.push(`<span class="font-semibold">Allergies:</span> ${allergies.map(a => a.replace(/_/g, ' ')).join(', ')}`);
    }
    const factors = profile.patient_factors || [];
    if (factors.length > 0) {
      items.push(`<span class="font-semibold">Factors:</span> ${factors.map(f => f.replace(/_/g, ' ')).join(', ')}`);
    }

    container.innerHTML = `
      <div class="flex items-center gap-2 mb-3">
        <i data-lucide="user-check" class="w-4 h-4 text-[#5B65DC] dark:text-[#8F9AF0]"></i>
        <span class="text-xs font-bold uppercase tracking-wider text-[#122056] dark:text-[#BAC4E6]">Patient Profile Summary</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1.5 text-xs text-[#47547E] dark:text-[#BAC4E6]">
        ${items.map(item => `<div>${item}</div>`).join('')}
      </div>
    `;
  },

  renderDrugOverview(overview) {
    const container = document.getElementById('reportDrugOverview');
    if (!container) return;

    if (!overview) {
      container.classList.add('hidden');
      return;
    }

    container.classList.remove('hidden');
    container.innerHTML = `
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-100 to-indigo-50 dark:from-indigo-950 dark:to-indigo-900 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
          <i data-lucide="pill" class="w-5 h-5"></i>
        </div>
        <div>
          <h3 class="text-base font-bold text-[#122056] dark:text-white font-sans">${overview.drug_name || 'Drug'} — Overview</h3>
          <p class="text-xs text-[#828EA8]">Extracted from knowledge base evidence</p>
        </div>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        ${overview.drug_class ? `
          <div class="p-3 rounded-xl bg-[#EEEFFD]/50 dark:bg-[#1C2555]/50 border border-[#E3E5F8] dark:border-[#1E285C]">
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#828EA8]">Drug Class</span>
            <p class="text-sm font-semibold text-[#122056] dark:text-white mt-1">${overview.drug_class}</p>
          </div>
        ` : ''}
        ${overview.primary_indication ? `
          <div class="p-3 rounded-xl bg-[#EEEFFD]/50 dark:bg-[#1C2555]/50 border border-[#E3E5F8] dark:border-[#1E285C]">
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#828EA8]">Primary Indication</span>
            <p class="text-sm font-semibold text-[#122056] dark:text-white mt-1">${overview.primary_indication}</p>
          </div>
        ` : ''}
        ${overview.mechanism ? `
          <div class="p-3 rounded-xl bg-[#EEEFFD]/50 dark:bg-[#1C2555]/50 border border-[#E3E5F8] dark:border-[#1E285C]">
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#828EA8]">Mechanism</span>
            <p class="text-sm font-semibold text-[#122056] dark:text-white mt-1">${overview.mechanism}</p>
          </div>
        ` : ''}
      </div>
    `;
  },

  renderRiskFindings(findings) {
    const container = document.getElementById('reportRiskFindings');
    if (!container) return;
    container.innerHTML = '';

    if (!findings || findings.length === 0) {
      container.innerHTML = `
        <div class="bg-white dark:bg-[#111736] rounded-2xl border border-[#E3E5F8] dark:border-[#1E285C] shadow-sm p-6 text-center">
          <i data-lucide="search-x" class="w-8 h-8 text-[#828EA8] mx-auto mb-2"></i>
          <p class="text-sm text-[#828EA8]">No specific risk findings were generated for this assessment.</p>
        </div>
      `;
      return;
    }

    // Tier styling config
    const tierConfig = {
      high_warning: {
        icon: '🔴',
        label: 'HIGH WARNING',
        bgClass: 'bg-rose-50 dark:bg-rose-950/30',
        borderClass: 'border-rose-200 dark:border-rose-800',
        labelClass: 'bg-rose-100 dark:bg-rose-900 text-rose-700 dark:text-rose-300',
        barClass: 'bg-rose-500',
        barWidth: '100%',
      },
      moderate_caution: {
        icon: '🟠',
        label: 'MODERATE CAUTION',
        bgClass: 'bg-amber-50 dark:bg-amber-950/30',
        borderClass: 'border-amber-200 dark:border-amber-800',
        labelClass: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300',
        barClass: 'bg-amber-500',
        barWidth: '65%',
      },
      safe: {
        icon: '🟢',
        label: 'SAFE',
        bgClass: 'bg-emerald-50 dark:bg-emerald-950/30',
        borderClass: 'border-emerald-200 dark:border-emerald-800',
        labelClass: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300',
        barClass: 'bg-emerald-500',
        barWidth: '25%',
      },
      no_data: {
        icon: '⚪',
        label: 'NO DATA',
        bgClass: 'bg-slate-50 dark:bg-slate-900/30',
        borderClass: 'border-slate-200 dark:border-slate-700',
        labelClass: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400',
        barClass: 'bg-slate-400',
        barWidth: '10%',
      },
    };

    // Sort: high first
    const tierOrder = { high_warning: 0, moderate_caution: 1, safe: 2, no_data: 3 };
    const sorted = [...findings].sort((a, b) => (tierOrder[a.tier] ?? 3) - (tierOrder[b.tier] ?? 3));

    // Header
    const allNoData = sorted.length > 0 && sorted.every(f => f.tier === 'no_data');
    const header = document.createElement('div');
    header.className = 'bg-white dark:bg-[#111736] rounded-2xl border border-[#E3E5F8] dark:border-[#1E285C] shadow-sm p-6 transition-colors';
    header.innerHTML = `
      <h3 class="text-base font-bold text-[#122056] dark:text-white font-sans flex items-center gap-2 mb-1">
        <i data-lucide="shield-alert" class="w-5 h-5 text-[#5B65DC] dark:text-[#8F9AF0]"></i>
        <span>Personalized Risk Findings</span>
      </h3>
      <p class="text-xs text-[#828EA8] mb-4">${sorted.length} risk factor(s) assessed across patient profile</p>

      <!-- Risk Overview Bar -->
      <div class="flex items-center gap-2 mb-2">
        ${this._buildRiskOverviewPills(sorted, tierConfig)}
      </div>

      ${allNoData ? `
        <div class="mt-4 p-4 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-900 dark:text-amber-200">
          <div class="font-bold flex items-center gap-1.5 text-sm mb-1 text-amber-800 dark:text-amber-300">
            <i data-lucide="alert-triangle" class="w-4 h-4 text-amber-600"></i>
            <span>Drug Not Indexed in Knowledge Base</span>
          </div>
          <p class="mb-2">No evidence was retrieved for the entered drug name. Try testing with an indexed drug from our clinical database:</p>
          <div class="flex flex-wrap gap-1.5">
            <button type="button" onclick="document.getElementById('reportTargetDrug').value='Lisinopril'; document.getElementById('reportForm').requestSubmit();" class="px-2.5 py-1 rounded-lg bg-amber-200 dark:bg-amber-900/60 font-semibold hover:bg-amber-300 transition-colors">Test with Lisinopril</button>
            <button type="button" onclick="document.getElementById('reportTargetDrug').value='Metformin'; document.getElementById('reportForm').requestSubmit();" class="px-2.5 py-1 rounded-lg bg-amber-200 dark:bg-amber-900/60 font-semibold hover:bg-amber-300 transition-colors">Test with Metformin</button>
            <button type="button" onclick="document.getElementById('reportTargetDrug').value='Warfarin'; document.getElementById('reportForm').requestSubmit();" class="px-2.5 py-1 rounded-lg bg-amber-200 dark:bg-amber-900/60 font-semibold hover:bg-amber-300 transition-colors">Test with Warfarin</button>
            <button type="button" onclick="document.getElementById('reportTargetDrug').value='Atorvastatin'; document.getElementById('reportForm').requestSubmit();" class="px-2.5 py-1 rounded-lg bg-amber-200 dark:bg-amber-900/60 font-semibold hover:bg-amber-300 transition-colors">Test with Atorvastatin</button>
          </div>
        </div>
      ` : ''}
    `;
    container.appendChild(header);

    // Individual finding cards
    for (let i = 0; i < sorted.length; i++) {
      const finding = sorted[i];
      const config = tierConfig[finding.tier] || tierConfig.no_data;
      const detBadge = finding.is_deterministic
        ? '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-200 dark:bg-rose-800 text-rose-700 dark:text-rose-300 ml-1">CONFIRMED</span>'
        : '';

      const card = document.createElement('div');
      card.className = `${config.bgClass} rounded-2xl border ${config.borderClass} p-5 transition-colors message-enter`;
      card.style.animationDelay = `${i * 0.08}s`;

      card.innerHTML = `
        <div class="flex items-start justify-between gap-3 mb-3">
          <div class="flex items-center gap-2">
            <span class="text-lg">${config.icon}</span>
            <div>
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-bold uppercase tracking-wider ${config.labelClass}">
                ${config.label}${detBadge}
              </span>
              <h4 class="text-sm font-bold text-[#122056] dark:text-white mt-1">${(finding.patient_factor || 'General').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h4>
            </div>
          </div>
          <!-- Risk Level Bar -->
          <div class="flex-shrink-0 w-20">
            <div class="w-full h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
              <div class="h-full rounded-full ${config.barClass} transition-all duration-700 risk-bar-animate" style="width: 0%;" data-target-width="${config.barWidth}"></div>
            </div>
          </div>
        </div>

        ${finding.summary ? `<p class="text-sm text-[#47547E] dark:text-[#BAC4E6] mb-2 leading-relaxed">${finding.summary}</p>` : ''}
        ${finding.rationale ? `
          <details class="text-xs mt-2">
            <summary class="cursor-pointer font-semibold text-[#5B65DC] dark:text-[#8F9AF0] hover:underline">View Rationale & Evidence</summary>
            <div class="mt-2 p-3 rounded-lg bg-white/70 dark:bg-[#111736]/70 border border-[#E3E5F8] dark:border-[#1E285C] text-[#47547E] dark:text-[#BAC4E6] leading-relaxed">
              ${finding.rationale}
              ${finding.exact_quote ? `<blockquote class="mt-2 pl-3 border-l-2 border-[#5B65DC] italic text-[#828EA8]">"${finding.exact_quote}"</blockquote>` : ''}
            </div>
          </details>
        ` : ''}
        ${finding.citations && finding.citations.length > 0 ? `
          <div class="mt-2 text-[11px] text-[#828EA8]">📎 ${finding.citations.join('; ')}</div>
        ` : ''}
      `;

      container.appendChild(card);
    }

    // Animate risk bars
    setTimeout(() => {
      document.querySelectorAll('.risk-bar-animate').forEach(bar => {
        bar.style.width = bar.getAttribute('data-target-width');
      });
    }, 200);
  },

  _buildRiskOverviewPills(findings, tierConfig) {
    const counts = { high_warning: 0, moderate_caution: 0, safe: 0, no_data: 0 };
    for (const f of findings) {
      if (counts[f.tier] !== undefined) counts[f.tier]++;
    }

    let html = '';
    for (const [tier, count] of Object.entries(counts)) {
      if (count === 0) continue;
      const cfg = tierConfig[tier];
      html += `<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold ${cfg.labelClass}">${cfg.icon} ${count} ${cfg.label}</span>`;
    }
    return html;
  },

  renderEvidenceSummary(mainResponse) {
    const container = document.getElementById('reportEvidenceContent');
    if (!container) return;

    if (!mainResponse) {
      container.innerHTML = '<p class="text-[#828EA8] italic">No evidence summary available.</p>';
      return;
    }

    // Simple markdown rendering
    container.innerHTML = this.formatMarkdown(mainResponse);
  },

  // ── UI State Helpers ──────────────────────────────────────────────────────

  showLoading(show) {
    if (this.loadingOverlay) this.loadingOverlay.classList.toggle('hidden', !show);
    if (this.form) this.form.classList.toggle('opacity-50', show);
    if (this.form) this.form.classList.toggle('pointer-events-none', show);

    if (this.submitBtn) {
      this.submitBtn.disabled = show;
      if (show) {
        this.spinner?.classList.remove('hidden');
        this.btnIcon?.classList.add('hidden');
        if (this.btnText) this.btnText.textContent = 'Generating Report...';
      } else {
        this.spinner?.classList.add('hidden');
        this.btnIcon?.classList.remove('hidden');
        if (this.btnText) this.btnText.textContent = 'Generate Risk Assessment Report';
      }
    }
  },

  showResults() {
    if (this.resultsSection) this.resultsSection.classList.remove('hidden');
  },

  hideResults() {
    if (this.resultsSection) this.resultsSection.classList.add('hidden');
  },

  showError(message) {
    if (this.errorSection) {
      this.errorSection.classList.remove('hidden');
      const msgEl = document.getElementById('reportErrorMessage');
      if (msgEl) msgEl.textContent = message;
    }
  },

  hideError() {
    if (this.errorSection) this.errorSection.classList.add('hidden');
  },

  resetToForm() {
    this.hideResults();
    this.hideError();
    if (this.form) {
      this.form.classList.remove('opacity-50', 'pointer-events-none');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  animateLoadingSteps() {
    const step1 = document.querySelector('#loadingStep1 span:first-child');
    const step2 = document.querySelector('#loadingStep2 span:first-child');
    const step3 = document.querySelector('#loadingStep3 span:first-child');

    // Step 1 active immediately
    if (step1) step1.className = 'w-2 h-2 rounded-full bg-[#5B65DC] animate-pulse';

    // Step 2 after 3s
    setTimeout(() => {
      if (step1) step1.className = 'w-2 h-2 rounded-full bg-emerald-500';
      if (step2) step2.className = 'w-2 h-2 rounded-full bg-[#5B65DC] animate-pulse';
    }, 3000);

    // Step 3 after 6s
    setTimeout(() => {
      if (step2) step2.className = 'w-2 h-2 rounded-full bg-emerald-500';
      if (step3) step3.className = 'w-2 h-2 rounded-full bg-[#5B65DC] animate-pulse';
    }, 6000);
  },

  // ── Markdown Formatter (same as assistant.js) ─────────────────────────────

  formatMarkdown(text) {
    if (!text) return '';
    let html = text;

    html = html.replace(/^### (.*$)/gim, '<h3 class="text-base font-bold text-slate-900 dark:text-white mt-3 mb-1.5 flex items-center gap-1.5">$1</h3>');
    html = html.replace(/^#### (.*$)/gim, '<h4 class="text-sm font-semibold text-slate-800 dark:text-slate-200 mt-2 mb-1">$1</h4>');

    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-[#122056] dark:text-white">$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em class="italic text-slate-600 dark:text-slate-400">$1</em>');

    html = html.replace(/^\s*-\s+(.*)$/gim, '<li class="ml-4 list-disc text-[#47547E] dark:text-[#BAC4E6] text-sm mb-1">$1</li>');
    html = html.replace(/^\s*(\d+)\.\s+(.*)$/gim, '<li class="ml-4 list-decimal text-[#47547E] dark:text-[#BAC4E6] text-sm mb-1">$2</li>');

    html = html.replace(/(<li class="ml-4 list-disc[^>]*>.*?<\/li>\s*)+/g, '<ul class="my-2 space-y-1">$&</ul>');
    html = html.replace(/(<li class="ml-4 list-decimal[^>]*>.*?<\/li>\s*)+/g, '<ol class="my-2 space-y-1">$&</ol>');

    html = html.split('\n\n').map(p => {
      if (p.startsWith('<h3') || p.startsWith('<h4') || p.startsWith('<ul') || p.startsWith('<ol')) return p;
      return `<p class="mb-2 text-[#47547E] dark:text-[#BAC4E6] leading-relaxed text-sm">${p.replace(/\n/g, '<br/>')}</p>`;
    }).join('');

    return html;
  },
};


// ============================================================================
// 3. Initialize on page load
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('reportForm')) {
    ReportUI.init();
  }
});
