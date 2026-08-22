/**
 * ============================================================================
 * AuraMed AI — Backend API Client (MEDRESOLVE AI Adapter)
 * ============================================================================
 * Connects the AuraMed AI frontend to the MEDRESOLVE AI FastAPI backend.
 * Handles data mapping between frontend schemas and backend PatientProfile.
 * ============================================================================
 */

const API_CONFIG = {
  BASE_URL: "http://localhost:8000",
  TIMEOUT_MS: 120000, // 2 minutes — RAG pipeline can be slow on first run
  RETRY_COUNT: 1,
};

// ============================================================================
// 1. Core API Client
// ============================================================================

const MedResolveAPI = {

  // ── Connection Status ────────────────────────────────────────────────────

  _connected: false,
  _lastCheck: 0,

  /**
   * Check if the backend is reachable.
   * @returns {Promise<{connected: boolean, data?: object, error?: string}>}
   */
  async healthCheck() {
    try {
      const res = await fetch(`${API_CONFIG.BASE_URL}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        this._connected = true;
        this._lastCheck = Date.now();
        return { connected: true, data };
      }
      this._connected = false;
      return { connected: false, error: `HTTP ${res.status}` };
    } catch (err) {
      this._connected = false;
      return { connected: false, error: err.message };
    }
  },

  /**
   * Returns cached connection status (non-blocking).
   */
  isConnected() {
    return this._connected;
  },

  // ── Chat Q&A ─────────────────────────────────────────────────────────────

  /**
   * Send a chat query to the RAG pipeline.
   * @param {string} query - User's question
   * @param {Array<{role: string, content: string}>} conversationHistory - Previous messages
   * @returns {Promise<object>} ChatResponse from backend
   */
  async chatQuery(query, conversationHistory = []) {
    const payload = {
      query: query.trim(),
      conversation_history: conversationHistory,
    };

    const res = await this._post("/query", payload);
    return res;
  },

  // ── Risk Report ──────────────────────────────────────────────────────────

  /**
   * Generate a personalized risk report.
   * @param {object} frontendProfile - Patient profile from PatientService
   * @param {Array<object>} medicines - Active medicines from MedicineService
   * @param {string} targetDrug - The specific drug to assess (optional, uses first medicine if not provided)
   * @param {string} additionalQuery - Optional extra question
   * @returns {Promise<object>} RiskReportResponse from backend
   */
  async generateRiskReport(frontendProfile, medicines = [], targetDrug = "", additionalQuery = "") {
    const backendProfile = this._mapProfileToBackend(frontendProfile, medicines, targetDrug);

    const payload = {
      patient_profile: backendProfile,
      additional_query: additionalQuery || "",
    };

    const res = await this._post("/risk-report", payload);
    return res;
  },

  // ── Drug List ────────────────────────────────────────────────────────────

  /**
   * List all drugs available in the knowledge base.
   * @returns {Promise<{drugs: Array<object>, total: number}>}
   */
  async listDrugs() {
    const res = await this._get("/drugs");
    return res;
  },

  // ── KB Status ────────────────────────────────────────────────────────────

  /**
   * Get knowledge base status (chunk counts, model info).
   * @returns {Promise<object>}
   */
  async getKBStatus() {
    const res = await this._get("/status");
    return res;
  },

  // ── Data Mapping ─────────────────────────────────────────────────────────

  /**
   * Maps frontend patient profile + medicines to backend PatientProfile schema.
   *
   * Frontend fields (from PatientService):
   *   fullName, dateOfBirth, gender, bloodType, height, weight,
   *   chronicConditions[], allergies[], medicalHistory,
   *   isPregnant, pregnancyWeeks, pregnancyTrimester
   *
   * Backend fields (PatientProfile in models.py):
   *   full_name, date_of_birth, gender, blood_type, height_cm, weight_kg,
   *   target_drug, target_drug_id, target_drugs[], comorbidities[],
   *   patient_factors[], current_medications[], allergies[],
   *   pregnancy_trimester, age_range, kidney_function
   */
  _mapProfileToBackend(frontendProfile, medicines = [], targetDrug = "") {
    const profile = frontendProfile || {};
    const meds = medicines || [];

    // Determine target drug
    const resolvedTargetDrug = targetDrug
      || (meds.length > 0 ? meds[0].name : "")
      || "";

    // Map chronic conditions → comorbidities
    const comorbidities = (profile.chronicConditions || []).map(c =>
      c.toLowerCase().replace(/\s+/g, "_").replace(/\//g, "_")
    );

    // Derive patient factors from structured fields
    const patientFactors = [];

    // Pregnancy factor
    if (profile.isPregnant) {
      patientFactors.push("pregnancy");
    }

    // Age-derived factor
    if (profile.dateOfBirth) {
      try {
        const dob = new Date(profile.dateOfBirth);
        const today = new Date();
        const ageYears = Math.floor((today - dob) / (365.25 * 24 * 60 * 60 * 1000));
        if (ageYears >= 65) patientFactors.push("elderly");
        else if (ageYears < 18) patientFactors.push("pediatric");
      } catch (e) {
        // ignore
      }
    }

    // Pregnancy trimester mapping
    let pregnancyTrimester = null;
    if (profile.isPregnant && profile.pregnancyTrimester) {
      const trimStr = profile.pregnancyTrimester.toLowerCase();
      if (trimStr.includes("1st") || trimStr.includes("first") || trimStr.includes("الأول")) {
        pregnancyTrimester = "first";
      } else if (trimStr.includes("2nd") || trimStr.includes("second") || trimStr.includes("الثاني")) {
        pregnancyTrimester = "second";
      } else if (trimStr.includes("3rd") || trimStr.includes("third") || trimStr.includes("الثالث")) {
        pregnancyTrimester = "third";
      } else {
        pregnancyTrimester = trimStr;
      }
    }

    // Age range
    let ageRange = null;
    if (profile.dateOfBirth) {
      try {
        const dob = new Date(profile.dateOfBirth);
        const today = new Date();
        const ageYears = Math.floor((today - dob) / (365.25 * 24 * 60 * 60 * 1000));
        if (ageYears >= 65) ageRange = "elderly";
        else if (ageYears < 18) ageRange = "pediatric";
        else ageRange = "adult";
      } catch (e) {
        ageRange = "adult";
      }
    }

    // Build current_medications from medicines list
    const currentMedications = meds.map(m => m.name).filter(Boolean);

    // Build target_drugs
    const targetDrugs = resolvedTargetDrug
      ? [resolvedTargetDrug, ...currentMedications.filter(m => m.toLowerCase() !== resolvedTargetDrug.toLowerCase())]
      : currentMedications;

    return {
      full_name: profile.fullName || "",
      date_of_birth: profile.dateOfBirth || null,
      gender: profile.gender || null,
      blood_type: profile.bloodType || null,
      height_cm: profile.height ? parseFloat(profile.height) : null,
      weight_kg: profile.weight ? parseFloat(profile.weight) : null,
      target_drug: resolvedTargetDrug,
      target_drug_id: resolvedTargetDrug.toLowerCase().replace(/\s+/g, "_"),
      target_drugs: targetDrugs.length > 0 ? targetDrugs : [resolvedTargetDrug].filter(Boolean),
      chronic_conditions: profile.chronicConditions || [],
      comorbidities: comorbidities,
      patient_factors: patientFactors,
      current_medications: currentMedications,
      allergies: profile.allergies || [],
      pregnancy_trimester: pregnancyTrimester,
      age_range: ageRange,
      kidney_function: null,
    };
  },

  // ── Chat Context Builder ─────────────────────────────────────────────────

  /**
   * Build enriched query with patient + medicine context for chat mode.
   * This embeds the patient context into the conversation history so the
   * RAG pipeline can use it for retrieval.
   */
  buildConversationHistory(messages, patientContext = "", medicineContext = "") {
    const history = [];

    // Add patient/medicine context as a system-like initial message
    if (patientContext || medicineContext) {
      const contextParts = [];
      if (patientContext) contextParts.push(patientContext);
      if (medicineContext) contextParts.push(medicineContext);

      history.push({
        role: "system",
        content: contextParts.join("\n\n"),
      });
    }

    // Add actual conversation messages
    for (const msg of messages) {
      if (msg.sender === "user") {
        history.push({ role: "user", content: msg.content });
      } else if (msg.sender === "assistant" && !msg.metadata?.isGreeting) {
        history.push({ role: "assistant", content: msg.content });
      }
    }

    return history;
  },

  // ── Response Formatters ──────────────────────────────────────────────────

  /**
   * Format a ChatResponse into markdown for the assistant chat UI.
   */
  formatChatResponse(response) {
    let formatted = "";

    // Main response content
    if (response.main_response) {
      formatted += response.main_response;
    }

    // Key warnings
    if (response.key_warnings && response.key_warnings.length > 0) {
      formatted += "\n\n#### ⚠️ Key Warnings\n";
      response.key_warnings.forEach(w => {
        formatted += `- ⚠️ ${w}\n`;
      });
    }

    // Key points
    if (response.key_points && response.key_points.length > 0) {
      formatted += "\n\n#### 📌 Key Points\n";
      response.key_points.forEach(p => {
        formatted += `- ${p}\n`;
      });
    }

    // Evidence quality badge
    if (response.evidence_quality) {
      const qualityEmoji = {
        high: "🟢",
        medium: "🟡",
        low: "🔴",
      };
      const emoji = qualityEmoji[response.evidence_quality] || "⚪";
      formatted += `\n\n---\n*${emoji} Evidence Quality: **${response.evidence_quality.toUpperCase()}***`;
    }

    // Citations (collapsed)
    if (response.citations && response.citations.length > 0) {
      formatted += `\n\n*📎 ${response.citations.length} evidence source(s) cited*`;
    }

    return formatted;
  },

  /**
   * Format a RiskReportResponse into structured markdown.
   */
  formatRiskReportResponse(response) {
    let formatted = "";

    // Drug overview
    if (response.drug_overview) {
      const ov = response.drug_overview;
      formatted += `### 💊 ${ov.drug_name} — Drug Overview\n`;
      if (ov.drug_class) formatted += `- **Drug Class:** ${ov.drug_class}\n`;
      if (ov.primary_indication) formatted += `- **Primary Indication:** ${ov.primary_indication}\n`;
      if (ov.mechanism) formatted += `- **Mechanism:** ${ov.mechanism}\n`;
      formatted += "\n";
    }

    // Risk findings
    if (response.risk_findings && response.risk_findings.length > 0) {
      formatted += "### 🔬 Personalized Risk Findings\n\n";

      const tierInfo = {
        high_warning: { icon: "🔴", label: "HIGH WARNING" },
        moderate_caution: { icon: "🟠", label: "MODERATE CAUTION" },
        safe: { icon: "🟢", label: "SAFE" },
        no_data: { icon: "⚪", label: "NO DATA" },
      };

      // Sort: high first
      const tierOrder = { high_warning: 0, moderate_caution: 1, safe: 2, no_data: 3 };
      const sorted = [...response.risk_findings].sort(
        (a, b) => (tierOrder[a.tier] || 3) - (tierOrder[b.tier] || 3)
      );

      for (const finding of sorted) {
        const info = tierInfo[finding.tier] || tierInfo.no_data;
        const detBadge = finding.is_deterministic ? " **[CONFIRMED]**" : "";
        formatted += `${info.icon} **${info.label}${detBadge}** — ${finding.patient_factor.replace(/_/g, " ")}\n`;
        if (finding.summary) formatted += `> ${finding.summary}\n`;
        if (finding.citations && finding.citations.length > 0) {
          formatted += `> *📎 ${finding.citations.join("; ")}*\n`;
        }
        formatted += "\n";
      }
    }

    // Main response
    if (response.main_response) {
      formatted += `\n### 📋 Evidence Summary\n\n${response.main_response}\n`;
    }

    // Disclaimer
    if (response.disclaimer) {
      formatted += `\n\n---\n*${response.disclaimer}*`;
    }

    return formatted;
  },

  // ── Internal HTTP Helpers ────────────────────────────────────────────────

  async _post(endpoint, body) {
    try {
      const res = await fetch(`${API_CONFIG.BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(API_CONFIG.TIMEOUT_MS),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Backend error: HTTP ${res.status}`);
      }

      return await res.json();
    } catch (err) {
      if (err.name === "TimeoutError" || err.name === "AbortError") {
        throw new Error("Backend request timed out. The RAG pipeline may be loading models for the first time — please try again.");
      }
      if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
        this._connected = false;
        throw new Error("Cannot connect to MEDRESOLVE AI backend. Make sure it's running on http://localhost:8000");
      }
      throw err;
    }
  },

  async _get(endpoint) {
    try {
      const res = await fetch(`${API_CONFIG.BASE_URL}${endpoint}`, {
        method: "GET",
        signal: AbortSignal.timeout(10000),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Backend error: HTTP ${res.status}`);
      }

      return await res.json();
    } catch (err) {
      if (err.name === "TimeoutError" || err.name === "AbortError") {
        throw new Error("Backend request timed out.");
      }
      if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
        this._connected = false;
        throw new Error("Cannot connect to MEDRESOLVE AI backend.");
      }
      throw err;
    }
  },
};

// ============================================================================
// 2. Connection Status Monitor
// ============================================================================

const ConnectionMonitor = {
  _interval: null,
  _statusEl: null,

  /**
   * Start periodic health checks and update the UI indicator.
   * @param {string} statusElementId - DOM element ID for the status indicator
   * @param {number} intervalMs - Check interval (default 30s)
   */
  start(statusElementId = "backendStatusIndicator", intervalMs = 30000) {
    this._statusEl = document.getElementById(statusElementId);
    this._check(); // Immediate first check
    this._interval = setInterval(() => this._check(), intervalMs);
  },

  stop() {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  },

  async _check() {
    const result = await MedResolveAPI.healthCheck();
    this._updateUI(result.connected, result.data);
  },

  _updateUI(connected, data) {
    if (!this._statusEl) return;

    if (connected) {
      this._statusEl.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span class="text-xs font-medium text-emerald-600 dark:text-emerald-400">RAG Connected</span>
      `;
      this._statusEl.title = `MEDRESOLVE AI v${data?.version || '3.0.0'} — ${data?.service || 'Backend'} running`;
      this._statusEl.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 transition-all";
    } else {
      this._statusEl.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-rose-500"></span>
        <span class="text-xs font-medium text-rose-600 dark:text-rose-400">RAG Offline</span>
      `;
      this._statusEl.title = "MEDRESOLVE AI backend is not reachable. Start the backend server.";
      this._statusEl.className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 transition-all cursor-help";
    }
  },
};
