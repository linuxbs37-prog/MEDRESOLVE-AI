"""
MEDRESOLVE AI — Personalized Drug Safety Intelligence Platform
Premium Streamlit Interface — v2.0 Drug-Only System
Two modes: Risk Report (form-based) + Chat (multi-turn)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import streamlit as st
import json
import time
from pathlib import Path

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MEDRESOLVE AI | Drug Safety Intelligence",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --primary:        #1a6fcf;
        --primary-light:  #3b8fe8;
        --accent:         #00c6a2;
        --accent-dark:    #009e82;
        --bg-dark:        #070c18;
        --bg-card:        #0d1326;
        --bg-card2:       #111829;
        --bg-card3:       #161e35;
        --text-primary:   #e8edf8;
        --text-secondary: #8d9ab0;
        --border:         #1a2840;
        --border-light:   #1e3154;
        --risk-high:      #e53e3e;
        --risk-moderate:  #f5a623;
        --risk-safe:      #38a169;
        --risk-nodata:    #718096;
        --drug-color:     #00c6a2;
        --purple:         #9f7aea;
    }

    * { font-family: 'Inter', sans-serif !important; }

    .stApp { background: var(--bg-dark); color: var(--text-primary); }

    /* ── Header ── */
    .main-header {
        background: linear-gradient(135deg, #070c18 0%, #0a1428 50%, #081020 100%);
        border-bottom: 1px solid var(--border);
        padding: 1.75rem 0 1.25rem 0;
        margin-bottom: 1.5rem;
    }
    .logo-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #3b8fe8 0%, #00c6a2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.5px;
    }
    .logo-subtitle {
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 400;
        margin-top: 0.2rem;
        letter-spacing: 0.4px;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        background: var(--bg-card) !important;
        border-radius: 12px !important;
        padding: 4px !important;
        border: 1px solid var(--border) !important;
        gap: 4px !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: var(--text-secondary) !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.25rem !important;
    }
    .stTabs [aria-selected="true"] {
        color: white !important;
        background: linear-gradient(135deg, var(--primary) 0%, var(--accent-dark) 100%) !important;
        border-radius: 8px !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        background: linear-gradient(135deg, var(--primary) 0%, var(--accent-dark) 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.65rem 1.75rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 15px rgba(26, 111, 207, 0.25) !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(26, 111, 207, 0.38) !important;
    }

    /* ── Form inputs ── */
    .stTextArea textarea, .stTextInput input, .stSelectbox select {
        background: var(--bg-card2) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 10px !important;
        color: var(--text-primary) !important;
        font-size: 0.9rem !important;
        transition: border-color 0.2s ease !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important;
    }
    .stMultiSelect [data-baseweb="select"] {
        background: var(--bg-card2) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 10px !important;
    }
    .stSelectbox [data-baseweb="select"] {
        background: var(--bg-card2) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 10px !important;
    }

    /* ── Cards ── */
    .card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.25rem;
        margin: 0.6rem 0;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .card:hover { border-color: var(--border-light); box-shadow: 0 4px 20px rgba(0,0,0,0.25); }

    /* ── Risk Tier Rows ── */
    .risk-row {
        display: flex;
        align-items: flex-start;
        gap: 1rem;
        padding: 1rem 1.25rem;
        border-radius: 12px;
        margin: 0.5rem 0;
        border: 1px solid;
        transition: all 0.15s ease;
    }
    .risk-row:hover { transform: translateX(2px); }

    .risk-high {
        background: rgba(229,62,62,0.08);
        border-color: rgba(229,62,62,0.35);
    }
    .risk-moderate {
        background: rgba(245,166,35,0.08);
        border-color: rgba(245,166,35,0.35);
    }
    .risk-safe {
        background: rgba(56,161,105,0.08);
        border-color: rgba(56,161,105,0.3);
    }
    .risk-nodata {
        background: rgba(113,128,150,0.06);
        border-color: rgba(113,128,150,0.25);
    }
    .risk-tier-icon { font-size: 1.4rem; flex-shrink: 0; margin-top: 0.1rem; }
    .risk-tier-label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        margin-bottom: 0.15rem;
    }
    .risk-factor { font-weight: 600; font-size: 0.95rem; color: var(--text-primary); }
    .risk-summary { color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.2rem; line-height: 1.5; }
    .risk-citation {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.72rem;
        color: var(--text-secondary);
        margin-top: 0.3rem;
        opacity: 0.8;
    }

    /* ── Drug Overview Card ── */
    .drug-overview-card {
        background: linear-gradient(135deg, rgba(0,198,162,0.06) 0%, rgba(26,111,207,0.06) 100%);
        border: 1px solid rgba(0,198,162,0.25);
        border-radius: 14px;
        padding: 1.25rem;
        margin-bottom: 1.25rem;
    }
    .drug-overview-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--accent);
        margin-bottom: 0.75rem;
    }
    .drug-overview-row {
        display: flex;
        gap: 1.5rem;
        flex-wrap: wrap;
    }
    .drug-overview-item { flex: 1; min-width: 150px; }
    .drug-overview-label {
        color: var(--text-secondary);
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 0.2rem;
    }
    .drug-overview-value { color: var(--text-primary); font-size: 0.9rem; font-weight: 500; }

    /* ── Metric cards ── */
    .metric-card {
        background: var(--bg-card2);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.85rem;
        text-align: center;
    }
    .metric-value { font-size: 1.7rem; font-weight: 700; color: var(--accent); }
    .metric-label { color: var(--text-secondary); font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

    /* ── Citation item ── */
    .citation-item {
        background: var(--bg-card2);
        border-left: 3px solid var(--primary);
        padding: 0.45rem 0.75rem;
        margin: 0.25rem 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.8rem;
        font-family: 'JetBrains Mono', monospace !important;
        color: var(--text-secondary);
    }

    /* ── Chat messages ── */
    .chat-message-user {
        background: rgba(26,111,207,0.12);
        border: 1px solid rgba(26,111,207,0.25);
        border-radius: 12px 12px 4px 12px;
        padding: 0.85rem 1rem;
        margin: 0.5rem 0;
        text-align: right;
        color: var(--text-primary);
        font-size: 0.9rem;
    }
    .chat-message-assistant {
        background: var(--bg-card2);
        border: 1px solid var(--border);
        border-radius: 4px 12px 12px 12px;
        padding: 0.85rem 1rem;
        margin: 0.5rem 0;
        color: var(--text-primary);
        font-size: 0.9rem;
        line-height: 1.65;
    }

    /* ── Sidebar ── */
    div[data-testid="stSidebar"] {
        background: var(--bg-card) !important;
        border-right: 1px solid var(--border) !important;
    }

    /* ── Expanders ── */
    .stExpander {
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        background: var(--bg-card2) !important;
    }
    .stExpander summary { color: var(--text-primary) !important; font-weight: 500 !important; }

    /* ── Disclaimer ── */
    .disclaimer-box {
        background: rgba(26, 111, 207, 0.06);
        border: 1px solid rgba(26, 111, 207, 0.2);
        border-radius: 10px;
        padding: 0.9rem;
        margin-top: 1.5rem;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.65;
    }

    /* ── Warning box ── */
    .warning-box {
        background: rgba(245,166,35,0.08);
        border: 1px solid rgba(245,166,35,0.3);
        border-radius: 10px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        font-size: 0.88rem;
        color: #f5a623;
    }

    /* ── Section badge ── */
    .section-badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }
    .badge-drug {
        background: rgba(0,198,162,0.15);
        border: 1px solid rgba(0,198,162,0.35);
        color: #00c6a2;
    }
    .badge-risk {
        background: rgba(159,122,234,0.15);
        border: 1px solid rgba(159,122,234,0.35);
        color: #9f7aea;
    }
    .badge-chat {
        background: rgba(59,143,232,0.15);
        border: 1px solid rgba(59,143,232,0.35);
        color: #3b8fe8;
    }

    /* Typography overrides */
    h1, h2, h3, h4 { color: var(--text-primary) !important; }
    p, li { color: var(--text-primary) !important; }
    .stMarkdown { color: var(--text-primary) !important; }
    label { color: var(--text-secondary) !important; font-size: 0.85rem !important; }
</style>
""", unsafe_allow_html=True)


# ─── Session State Initialization ─────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # list of {role, content, citations}
if "last_risk_result" not in st.session_state:
    st.session_state.last_risk_result = None
if "last_chat_result" not in st.session_state:
    st.session_state.last_chat_result = None


# ─── Header ──────────────────────────────────────────────────────────────────
col_logo, col_status = st.columns([3, 1])
with col_logo:
    st.markdown("""
    <div class="main-header">
        <div class="logo-title">💊 MEDRESOLVE AI</div>
        <div class="logo-subtitle">Personalized Drug Safety Intelligence Platform</div>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("⚙️ KB Status"):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from medresolve.config import get_settings
            cfg = get_settings()
            client = chromadb.PersistentClient(
                path=str(cfg.chroma_persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            dr = client.get_or_create_collection(cfg.chroma_drug_collection)
            st.success(f"✅ Drug KB: {dr.count()} chunks indexed")
        except Exception as e:
            st.error(f"⚠️ {e}")


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💊 MEDRESOLVE AI")
    st.markdown("---")

    with st.expander("📋 Drug Knowledge Base", expanded=False):
        st.markdown("""
        **Primary Drug Classes:**
        - ACE Inhibitors (Lisinopril)
        - ARBs (Losartan)
        - Calcium Channel Blockers (Amlodipine)
        - Beta-blockers (Metoprolol, Labetalol)
        - Statins (Atorvastatin, Rosuvastatin)
        - Antidiabetics (Metformin, Insulin Glargine)
        - Anticoagulants (Warfarin)
        - Diuretics (Hydrochlorothiazide)
        - Pregnancy antihypertensives (Methyldopa, Labetalol)

        **Disease Scope:**
        Hypertension • Diabetes • CVD • CKD • Pregnancy

        **35+ drug profiles** sourced from DailyMed (NLM/NIH) + openFDA
        """)

    with st.expander("💡 Example Queries", expanded=True):
        examples = [
            ("💊 Drug Safety", "What are the contraindications of lisinopril in patients with renal impairment?"),
            ("🔬 Patient Population", "Is metformin safe in patients with CKD and what monitoring is required?"),
            ("⚠️ Drug Interaction", "What interactions should be monitored with warfarin in elderly patients?"),
            ("🤰 Pregnancy", "Which antihypertensive drugs are safe to use during pregnancy?"),
            ("📊 Dosage Info", "What is the documented dosage range for atorvastatin in cardiovascular patients?"),
            ("🏥 CKD + Diabetes", "What considerations apply to metformin use in diabetic patients with CKD?"),
        ]
        for label, query in examples:
            if st.button(label, key=f"ex_{label}", use_container_width=True):
                st.session_state["prefill_chat_query"] = query

    st.markdown("---")
    st.markdown("""
    <div style="color: #8d9ab0; font-size: 0.75rem; line-height: 1.7;">
    <b>Drug KB:</b> 35+ drugs from DailyMed/openFDA<br>
    <b>Stack:</b> LangGraph • Gemini • ChromaDB • BGE<br>
    <b>Safety:</b> Grounded claims • Mandatory disclaimer<br>
    <b>Version:</b> 2.0.0 Drug-Only System
    </div>
    """, unsafe_allow_html=True)


# ─── Main Interface: Two-Mode Tabs ────────────────────────────────────────────
tab_risk, tab_chat = st.tabs(["🔬 Risk Report", "💬 Chat"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: RISK REPORT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_risk:
    st.markdown("""
    <div style="color: var(--text-secondary); font-size: 0.88rem; margin-bottom: 1.25rem; line-height: 1.6;">
    Submit a patient profile to receive a personalized drug safety assessment.
    Each finding is tiered <b style="color:#e53e3e">🔴 High Warning</b> /
    <b style="color:#f5a623">🟠 Moderate Caution</b> / <b style="color:#38a169">🟢 Safe</b>
    and grounded against the drug knowledge base.
    </div>
    """, unsafe_allow_html=True)

    # ── Form ──────────────────────────────────────────────────────────────────
    with st.form("risk_report_form", clear_on_submit=False):
        col_drug, col_age = st.columns([2, 1])

        with col_drug:
            drug_options = [
                "Lisinopril", "Losartan", "Amlodipine", "Labetalol", "Methyldopa",
                "Metoprolol", "Hydrochlorothiazide",
                "Metformin", "Insulin Glargine",
                "Atorvastatin", "Rosuvastatin", "Simvastatin",
                "Warfarin",
                "Ibuprofen", "Doxycycline", "Nitrofurantoin", "Methimazole",
                "Levothyroxine", "Sertraline", "Folic Acid", "Amoxicillin",
                "Methotrexate", "Isotretinoin", "Valproic Acid", "Thalidomide",
            ]
            target_drug = st.selectbox(
                "Target Drug *",
                options=drug_options,
                index=0,
                help="Select the drug to assess",
                key="rr_drug",
            )

        with col_age:
            age_range = st.selectbox(
                "Age Range",
                options=["adult", "elderly", "pediatric"],
                index=0,
                key="rr_age",
            )

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            comorbidities = st.multiselect(
                "Comorbidities",
                options=[
                    "renal_impairment", "chronic_kidney_disease", "diabetes",
                    "type_2_diabetes", "hypertension", "cardiovascular_disease",
                    "heart_failure", "hepatic_impairment", "liver_disease",
                    "obesity", "dyslipidemia", "anemia", "gout",
                ],
                default=[],
                help="Select all that apply",
                key="rr_comorbidities",
            )

        with col_c2:
            patient_factors = st.multiselect(
                "Patient Factors",
                options=[
                    "pregnancy", "lactation", "breastfeeding",
                    "planning_pregnancy", "post_partum",
                    "elderly", "frailty", "pediatric",
                    "immunocompromised",
                ],
                default=[],
                key="rr_factors",
            )

        col_meds, col_allergies = st.columns(2)
        with col_meds:
            current_meds_input = st.text_input(
                "Current Medications (comma-separated)",
                placeholder="e.g. metformin, atorvastatin",
                key="rr_meds",
            )
        with col_allergies:
            allergies_input = st.text_input(
                "Allergies (comma-separated)",
                placeholder="e.g. penicillin, sulfa",
                key="rr_allergies",
            )

        kidney_function = st.selectbox(
            "Kidney Function",
            options=["normal", "eGFR 60-89 (mild)", "eGFR 30-59 (moderate)", "eGFR 15-29 (severe)", "eGFR < 15 (kidney failure)", "dialysis"],
            index=0,
            key="rr_kidney",
        )

        additional_q = st.text_input(
            "Additional Question (optional)",
            placeholder="e.g. What monitoring is needed?",
            key="rr_extra_q",
        )

        submit_risk = st.form_submit_button("🔬 Generate Risk Report", use_container_width=True)

    # ── Risk Report Processing ─────────────────────────────────────────────────
    if submit_risk:
        from medresolve.models import PatientProfile

        current_medications = [m.strip() for m in current_meds_input.split(",") if m.strip()]
        allergies = [a.strip() for a in allergies_input.split(",") if a.strip()]

        if not comorbidities and not patient_factors and not current_medications and not allergies:
            st.warning("⚠️ Please add at least one comorbidity, patient factor, or medication to personalize the risk assessment.")
        else:
            profile = PatientProfile(
                target_drug=target_drug,
                target_drug_id=target_drug.lower().replace(" ", "_"),
                comorbidities=comorbidities,
                patient_factors=patient_factors,
                current_medications=current_medications,
                allergies=allergies,
                age_range=age_range,
                kidney_function=kidney_function if kidney_function != "normal" else None,
            )

            with st.spinner(""):
                progress_ph = st.empty()
                with progress_ph.container():
                    st.markdown("""
                    <div style="background:#0d1326; border:1px solid #1a2840; border-radius:12px; padding:1.5rem; margin:0.75rem 0;">
                        <div style="color:#3b8fe8; font-weight:600; margin-bottom:0.75rem;">⚡ Generating Personalized Risk Report...</div>
                        <div style="color:#8d9ab0; font-size:0.85rem;">
                            ✦ Classifying patient profile...<br>
                            ✦ Planning drug evidence retrieval...<br>
                            ✦ Retrieving contraindications &amp; patient population sections...<br>
                            ✦ Scanning metadata for boxed warnings...<br>
                            ✦ Running LLM-structured risk grading...<br>
                            ✦ Validating chunk citations...<br>
                            ✦ Applying safety checks...
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                try:
                    from medresolve.agents.graph import run_risk_report
                    start_time = time.time()
                    final_state = run_risk_report(patient_profile=profile, additional_query=additional_q)
                    elapsed = time.time() - start_time

                    st.session_state.last_risk_result = {
                        "state": final_state,
                        "elapsed": elapsed,
                        "drug": target_drug,
                    }
                except Exception as e:
                    st.error(f"**Pipeline Error:** {e}")
                    st.stop()

                progress_ph.empty()

    # ── Risk Report Results ────────────────────────────────────────────────────
    if st.session_state.last_risk_result:
        result = st.session_state.last_risk_result
        final_state = result["state"]
        elapsed = result["elapsed"]

        response = final_state.get("final_response")
        if not response:
            st.error("No response generated.")
            st.stop()

        if response.is_refused:
            st.markdown(f"""
            <div style="background:rgba(229,62,62,0.08); border:1px solid rgba(229,62,62,0.3); border-radius:12px; padding:1.5rem; margin:0.75rem 0;">
                <div style="color:#e53e3e; font-weight:700; font-size:1rem; margin-bottom:0.5rem;">⛔ Request Not Processed</div>
                <div style="color:#e8edf8;">{response.main_response}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Context header row
            ctx_cols = st.columns(4)
            with ctx_cols[0]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Drug</div>
                    <div style="color:#00c6a2; font-weight:700; font-size:1rem; margin-top:0.3rem;">{', '.join(response.detected_drugs) or result['drug']}</div>
                </div>""", unsafe_allow_html=True)
            with ctx_cols[1]:
                risk_findings = response.risk_findings
                high_count = sum(1 for f in risk_findings if f.tier.value == "high_warning")
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">High Warnings</div>
                    <div style="color:#e53e3e; font-weight:700; font-size:1.6rem; margin-top:0.3rem;">{high_count}</div>
                </div>""", unsafe_allow_html=True)
            with ctx_cols[2]:
                moderate_count = sum(1 for f in risk_findings if f.tier.value == "moderate_caution")
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Cautions</div>
                    <div style="color:#f5a623; font-weight:700; font-size:1.6rem; margin-top:0.3rem;">{moderate_count}</div>
                </div>""", unsafe_allow_html=True)
            with ctx_cols[3]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Analysis Time</div>
                    <div class="metric-value">{elapsed:.1f}s</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Drug Overview card
            if response.drug_overview:
                ov = response.drug_overview
                st.markdown(f"""
                <div class="drug-overview-card">
                    <div class="drug-overview-title">💊 {ov.drug_name} — Drug Overview</div>
                    <div class="drug-overview-row">
                        <div class="drug-overview-item">
                            <div class="drug-overview-label">Drug Class</div>
                            <div class="drug-overview-value">{ov.drug_class or '—'}</div>
                        </div>
                        <div class="drug-overview-item">
                            <div class="drug-overview-label">Primary Indication</div>
                            <div class="drug-overview-value">{ov.primary_indication or '—'}</div>
                        </div>
                        <div class="drug-overview-item" style="flex:2">
                            <div class="drug-overview-label">Mechanism of Action</div>
                            <div class="drug-overview-value">{ov.mechanism or '—'}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Risk Findings
            if risk_findings:
                st.markdown('<div class="section-badge badge-risk">🔬 Personalized Risk Findings</div>', unsafe_allow_html=True)
                st.markdown(f"*{len(risk_findings)} patient factors assessed — grounded against drug knowledge base*")

                tier_icons = {
                    "high_warning": ("🔴", "risk-high", "#e53e3e", "HIGH WARNING"),
                    "moderate_caution": ("🟠", "risk-moderate", "#f5a623", "MODERATE CAUTION"),
                    "safe": ("🟢", "risk-safe", "#38a169", "SAFE"),
                    "no_data": ("⚪", "risk-nodata", "#718096", "NO DATA"),
                }

                # Sort: HIGH first, then MODERATE, then SAFE, then NO_DATA
                tier_order = {"high_warning": 0, "moderate_caution": 1, "safe": 2, "no_data": 3}
                sorted_findings = sorted(risk_findings, key=lambda f: tier_order.get(f.tier.value, 3))

                for finding in sorted_findings:
                    icon, css_class, color, label = tier_icons.get(finding.tier.value, ("⚪", "risk-nodata", "#718096", "NO DATA"))
                    det_badge = ' <span style="font-size:0.65rem; background:rgba(229,62,62,0.15); color:#e53e3e; padding:1px 6px; border-radius:10px; font-weight:700;">CONFIRMED</span>' if finding.is_deterministic else ""
                    citation_str = finding.citation_str() if finding.source_chunks else "No documented source in KB"

                    st.markdown(f"""
                    <div class="risk-row {css_class}">
                        <div class="risk-tier-icon">{icon}</div>
                        <div style="flex:1">
                            <div class="risk-tier-label" style="color:{color};">{label}{det_badge}</div>
                            <div class="risk-factor">{finding.patient_factor.replace('_', ' ').title()}</div>
                            <div class="risk-summary">{finding.summary}</div>
                            <div class="risk-citation">📎 {citation_str}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if finding.rationale and finding.tier.value in ("high_warning", "moderate_caution"):
                        with st.expander(f"↳ Detailed rationale for {finding.patient_factor.replace('_', ' ').title()}", expanded=False):
                            st.markdown(finding.rationale)
            else:
                st.info("No risk findings generated — check that a patient profile was submitted.")

            # Main narrative response
            st.markdown("---")
            st.markdown('<div class="section-badge badge-drug">📋 Evidence Summary</div>', unsafe_allow_html=True)
            st.markdown("""
            <div style="background:var(--bg-card2); border:1px solid var(--border); border-radius:12px; padding:1.25rem 1.5rem; margin-top:0.5rem; line-height:1.75;">
            """, unsafe_allow_html=True)
            st.markdown(response.main_response)
            st.markdown("</div>", unsafe_allow_html=True)

            # Key warnings
            if response.key_warnings:
                st.markdown("### ⚠️ Key Warnings")
                for w in response.key_warnings:
                    st.markdown(f"""
                    <div class="warning-box">⚠️ {w}</div>
                    """, unsafe_allow_html=True)

            # Evidence limitations
            if response.evidence_limitations:
                with st.expander("📊 Evidence Limitations", expanded=False):
                    for lim in response.evidence_limitations:
                        st.markdown(f"• {lim}")

            # Citations
            if response.citations:
                with st.expander("📚 Drug Evidence Sources", expanded=False):
                    for cit in response.citations:
                        st.markdown(f'<div class="citation-item">{cit}</div>', unsafe_allow_html=True)

            # Disclaimer
            st.markdown(f"""
            <div class="disclaimer-box">{response.disclaimer}</div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: CHAT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("""
    <div style="color: var(--text-secondary); font-size: 0.88rem; margin-bottom: 1rem; line-height: 1.6;">
    Multi-turn drug Q&amp;A grounded in the drug knowledge base.
    Ask about safety profiles, contraindications, interactions, or patient populations.
    <b>All responses cite specific drug evidence chunks.</b>
    </div>
    """, unsafe_allow_html=True)

    # Safety notice
    st.markdown("""
    <div style="background:rgba(26,111,207,0.07); border:1px solid rgba(26,111,207,0.2); border-radius:8px; padding:0.6rem 1rem; font-size:0.8rem; color:#8d9ab0; margin-bottom:1rem;">
    🛡️ <b>Safety scope:</b> Responses are grounded in the drug KB only. Personalized prescribing advice is not provided.
    Documented dosage ranges are surfaced as reference information from drug labels — not as individual prescribing guidance.
    </div>
    """, unsafe_allow_html=True)

    # Chat controls
    col_clear_chat, col_toggle_trace = st.columns([1, 1])
    with col_clear_chat:
        if st.button("🗑️ Clear Conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.last_chat_result = None
            st.rerun()
    with col_toggle_trace:
        show_chat_trace = st.toggle("Show execution trace", value=False, key="chat_trace_toggle")

    # Render chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="chat-message-user">
                    <span style="font-size:0.75rem; color:#8d9ab0; display:block; margin-bottom:0.25rem;">You</span>
                    {msg["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message-assistant">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
                        <span style="font-size:0.75rem; color:#00c6a2; font-weight:600;">💊 MEDRESOLVE AI</span>
                        <span style="font-size:0.7rem; color:#8d9ab0;">{msg.get('elapsed', '')}</span>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown(msg["content"])
                st.markdown("</div>", unsafe_allow_html=True)

                # Show citations inline
                if msg.get("citations"):
                    with st.expander("📎 Evidence Citations", expanded=False):
                        for cit in msg["citations"][:8]:
                            st.markdown(f'<div class="citation-item">{cit}</div>', unsafe_allow_html=True)

    # Query input
    prefill = st.session_state.pop("prefill_chat_query", "")
    query_input = st.text_area(
        "Ask a drug safety question",
        value=prefill,
        placeholder="e.g. What are the contraindications of lisinopril in renal impairment?",
        height=90,
        key="chat_query_input",
        label_visibility="visible",
    )

    col_send, col_spacer = st.columns([1, 3])
    with col_send:
        send_btn = st.button("▶ Send", type="primary", use_container_width=True, key="chat_send")

    # Chat processing
    if send_btn and query_input.strip():
        user_query = query_input.strip()

        # Build conversation history for context
        conversation_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in st.session_state.chat_history[-6:]  # Last 3 turns
        ]

        with st.spinner(""):
            try:
                from medresolve.agents.graph import run_query
                start_time = time.time()
                final_state = run_query(
                    query=user_query,
                    conversation_history=conversation_history,
                )
                elapsed = time.time() - start_time

                response = final_state.get("final_response")
                if not response:
                    st.error("No response generated.")
                    st.stop()

                # Append to chat history
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_query,
                })
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response.main_response,
                    "citations": response.citations[:8],
                    "elapsed": f"{elapsed:.1f}s",
                    "is_refused": response.is_refused,
                })

                st.session_state.last_chat_result = {
                    "state": final_state,
                    "elapsed": elapsed,
                    "response": response,
                }

            except Exception as e:
                st.error(f"**Pipeline Error:** {e}")
                st.stop()

        st.rerun()

    # Show last execution trace if toggled
    if show_chat_trace and st.session_state.last_chat_result:
        result = st.session_state.last_chat_result
        response = result.get("response")
        trace = response.execution_trace if response else None

        if trace:
            with st.expander("🔍 Execution Trace", expanded=False):
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    st.markdown("**Pipeline Steps**")
                    for step in trace.processing_steps:
                        st.markdown(f"✓ {step.replace('_', ' ').title()}")
                with col_t2:
                    st.markdown("**Retrieval Stats**")
                    st.markdown(f"""
                    <div style="background:var(--bg-card2); border:1px solid var(--border); border-radius:8px; padding:0.75rem;">
                        <div style="color:#00c6a2; font-weight:600; margin-bottom:0.25rem;">💊 Drug Evidence</div>
                        <div>Chunks: {trace.drug_chunks_retrieved}</div>
                        <div style="color:#8d9ab0; font-size:0.8rem;">Drugs: {', '.join(trace.drug_sources_used) if trace.drug_sources_used else 'None'}</div>
                    </div>
                    <div style="background:var(--bg-card2); border:1px solid var(--border); border-radius:8px; padding:0.75rem; margin-top:0.5rem;">
                        <div style="color:#9f7aea; font-weight:600; margin-bottom:0.25rem;">🔬 Grounding</div>
                        <div>Total: {trace.total_claims} | Grounded: {trace.grounded_claims} | Ungrounded: {trace.ungrounded_claims}</div>
                    </div>
                    <div style="background:var(--bg-card2); border:1px solid var(--border); border-radius:8px; padding:0.75rem; margin-top:0.5rem;">
                        <div style="color:{'#38a169' if trace.safety_decision == 'safe' else '#e53e3e'}; font-weight:600;">
                            🛡️ Safety: {trace.safety_decision.upper() if trace.safety_decision else 'N/A'}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # Empty state
    if not st.session_state.chat_history and not send_btn:
        st.markdown("""
        <div style="text-align:center; padding:2.5rem 1rem; color:#8d9ab0;">
            <div style="font-size:2.5rem; margin-bottom:0.75rem;">💬</div>
            <div style="font-size:1.05rem; font-weight:600; color:#e8edf8; margin-bottom:0.4rem;">
                Drug Safety Q&amp;A
            </div>
            <div style="max-width:520px; margin:0 auto; line-height:1.7; font-size:0.88rem;">
                Ask about drug safety profiles, contraindications, interactions,
                patient population considerations, or documented dosage information.
            </div>
            <div style="margin-top:1.5rem; display:flex; justify-content:center; gap:0.75rem; flex-wrap:wrap;">
                <span style="background:rgba(0,198,162,0.12); border:1px solid rgba(0,198,162,0.25); padding:0.35rem 0.85rem; border-radius:20px; font-size:0.8rem; color:#00c6a2;">35+ Drug Profiles</span>
                <span style="background:rgba(59,143,232,0.12); border:1px solid rgba(59,143,232,0.25); padding:0.35rem 0.85rem; border-radius:20px; font-size:0.8rem; color:#3b8fe8;">Grounded Citations</span>
                <span style="background:rgba(159,122,234,0.12); border:1px solid rgba(159,122,234,0.25); padding:0.35rem 0.85rem; border-radius:20px; font-size:0.8rem; color:#9f7aea;">LangGraph Agents</span>
                <span style="background:rgba(245,166,35,0.12); border:1px solid rgba(245,166,35,0.25); padding:0.35rem 0.85rem; border-radius:20px; font-size:0.8rem; color:#f5a623;">Safety Gate</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
