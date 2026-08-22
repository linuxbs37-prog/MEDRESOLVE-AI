/**
 * MedSafety RAG Knowledge Base Server v4.5
 * =========================================
 * Multi-Source: Local KB + OpenFDA + RxNorm + RxImage + DailyMed
 * Run: node medication_verify_api.js
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8000;
const KB_DIR = path.join(__dirname, 'AI Hackathon Comp', 'datasets', 'drug_knowledge_base');

// ========== LOAD KNOWLEDGE BASE ==========
const drugDB = {};
let totalLoaded = 0;

try {
  const files = fs.readdirSync(KB_DIR).filter(f => f.endsWith('.json') && !['extraction_report.json', 'rag_chunks.json', 'master_knowledge_base.json'].includes(f));
  for (const file of files) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(KB_DIR, file), 'utf8'));
      if (data.drug_id) {
        drugDB[data.drug_id.toLowerCase()] = data;
        if (data.drug_name) drugDB[data.drug_name.toLowerCase()] = data;
        if (data.aliases) for (const a of data.aliases) drugDB[a.toLowerCase()] = data;
        totalLoaded++;
      }
    } catch (e) {}
  }
  console.log(`✅ Loaded ${totalLoaded} drugs from local KB`);
} catch (e) {
  console.error('⚠️ KB load error:', e.message);
}

function truncate(str, len = 300) {
  if (!str) return '';
  const s = Array.isArray(str) ? str.join(' ') : String(str);
  return s.length > len ? s.substring(0, len) + '...' : s;
}

function findDrug(name) {
  const norm = name.toLowerCase().trim().replace(/[^a-z0-9_ ]/g, '');
  if (drugDB[norm]) return drugDB[norm];
  for (const key of Object.keys(drugDB)) {
    if (key.includes(norm) || norm.includes(key)) return drugDB[key];
  }
  return null;
}

// ========== EXTERNAL API HELPERS ==========
function fetchJson(url) {
  return new Promise((resolve) => {
    try {
      const proto = url.startsWith('https') ? https : http;
      const req = proto.get(url, { timeout: 5000 }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => { try { resolve(JSON.parse(body)); } catch(e) { resolve(null); } });
      });
      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
    } catch(e) {
      resolve(null);
    }
  });
}

async function getRxImageUrl(drugName) {
  try {
    const url = `https://rximage.nlm.nih.gov/api/rximage/1/rxbase?name=${encodeURIComponent(drugName)}&resolution=600`;
    const data = await fetchJson(url);
    if (data && data.nlmRxImages && data.nlmRxImages.length > 0) {
      return data.nlmRxImages[0].imageUrl || null;
    }
  } catch(e) {}
  return null;
}

async function getOpenFDAFallback(drugName) {
  try {
    const url = `https://api.fda.gov/drug/label.json?search=openfda.generic_name:"${encodeURIComponent(drugName)}"+openfda.brand_name:"${encodeURIComponent(drugName)}"&limit=1`;
    const data = await fetchJson(url);
    if (data && data.results && data.results.length > 0) {
      return data.results[0];
    }
  } catch(e) {}
  return null;
}

async function getRxNormId(drugName) {
  try {
    const url = `https://rxnav.nlm.nih.gov/REST/rxcui.json?name=${encodeURIComponent(drugName)}`;
    const data = await fetchJson(url);
    if (data && data.idGroup && data.idGroup.rxnormId && data.idGroup.rxnormId.length > 0) {
      return data.idGroup.rxnormId[0];
    }
  } catch(e) {}
  return null;
}

function buildSafetyReport(drug, patientContext) {
  const warnings = [];
  const g = drug.patient_safety_guardrails || {};
  const p = drug.patient_population_profiles || {};

  if (g.boxed_warning && !g.boxed_warning.toLowerCase().includes('no boxed warning')) {
    warnings.push({ severity: 'critical', section: 'Black Box Warning ⬛', text: truncate(g.boxed_warning, 200) });
  }
  if (g.contraindications) {
    warnings.push({ severity: 'high', section: 'Contraindications', text: truncate(g.contraindications, 200) });
  }

  if (patientContext) {
    const pc = patientContext;
    if ((pc.pregnancy_trimester || pc.is_pregnant) && p.pregnancy_and_teratogenicity) {
      const pt = p.pregnancy_and_teratogenicity.toLowerCase();
      const sev = (pt.includes('contraindicated') || pt.includes('category x') || pt.includes('category d')) ? 'critical' : 'moderate';
      warnings.push({ severity: sev, section: 'Pregnancy Risk 🤰', text: truncate(p.pregnancy_and_teratogenicity, 150) });
    }
    if (pc.age && parseInt(pc.age) < 18 && p.pediatric_use) warnings.push({ severity: 'high', section: 'Pediatric Use 👶', text: truncate(p.pediatric_use, 150) });
    if (pc.age && parseInt(pc.age) >= 65 && p.geriatric_use) warnings.push({ severity: 'high', section: 'Geriatric Use 👴', text: truncate(p.geriatric_use, 150) });
    if (pc.chronic_conditions) {
      const cc = pc.chronic_conditions.toLowerCase();
      if ((cc.includes('كلى') || cc.includes('renal') || cc.includes('kidney')) && p.renal_impairment) warnings.push({ severity: 'high', section: 'Renal 🩺', text: truncate(p.renal_impairment, 150) });
      if ((cc.includes('كبد') || cc.includes('hepat') || cc.includes('liver')) && p.hepatic_impairment) warnings.push({ severity: 'high', section: 'Hepatic 🩺', text: truncate(p.hepatic_impairment, 150) });
    }
  }
  return warnings;
}

// ========== HTTP SERVER ==========
const server = http.createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(200); return res.end(); }

  if (req.method === 'GET' && req.url === '/') {
    res.writeHead(200);
    return res.end(JSON.stringify({ status: 'online', service: 'MedSafety Multi-Source RAG Server', version: '4.5.0', drugs_loaded: totalLoaded, sources: ['Local DailyMed KB', 'OpenFDA API', 'RxNorm API', 'RxImage NLM', 'FAERS DB'] }));
  }

  if (req.method === 'GET' && req.url === '/drugs') {
    const uniqueDrugs = [...new Set(Object.values(drugDB).map(d => d.drug_name))];
    res.writeHead(200);
    return res.end(JSON.stringify({ count: uniqueDrugs.length, drugs: uniqueDrugs }));
  }

  if (req.method === 'POST' && req.url === '/verify') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const data = JSON.parse(body || '{}');
        const medName = (data.medication_name || '').trim();
        const patientContext = data.patient_context || null;
        if (!medName) { res.writeHead(400); return res.end(JSON.stringify({ verification: { status: 'UNVERIFIED' } })); }

        const drug = findDrug(medName);

        if (drug) {
          const warnings = buildSafetyReport(drug, patientContext);
          const g = drug.patient_safety_guardrails || {};
          const u = drug.clinical_usage_guidance || {};
          const p = drug.patient_population_profiles || {};

          // Fetch pill image from RxImage NLM
          const pillImageUrl = await getRxImageUrl(drug.drug_name);

          // Get RxNorm ID for cross-referencing
          const rxnormId = await getRxNormId(drug.drug_name);

          // Build all sources used
          const sources = [drug.data_source || 'DailyMed (NLM/NIH)'];
          if (pillImageUrl) sources.push('RxImage NLM (Pill Photo)');
          if (rxnormId) sources.push('RxNorm (NLM)');

          res.writeHead(200);
          return res.end(JSON.stringify({
            verification: { status: 'VERIFIED', source: 'multi_source' },
            image_url: pillImageUrl,
            rxnorm_id: rxnormId,
            medication: {
              drug_id: drug.drug_id,
              drug_name: drug.drug_name,
              generic_name: drug.drug_name,
              aliases: drug.aliases || [],
              category: drug.category,
              tier: drug.tier,
              primary_indication: drug.primary_indication,
              known_critical_risks: drug.known_critical_risks || [],
              active_ingredient: drug.drug_name,
              rxcui: drug.drug_id,
              dosage: truncate(u.dosage_and_administration, 350),
              contraindications: truncate(g.contraindications, 300),
              interactions: truncate(g.drug_interactions, 300),
              boxed_warning: g.boxed_warning || 'No boxed warning',
              adverse_reactions: truncate(u.adverse_reactions, 300),
              patient_counseling: truncate(u.patient_counseling_information, 400),
              indications: truncate(u.indications_and_usage, 250),
              mechanism: truncate(u.mechanism_of_action, 150),
              storage: truncate(u.storage_and_handling, 150),
              pregnancy: truncate(p.pregnancy_and_teratogenicity, 200),
              pediatric: truncate(p.pediatric_use, 200),
              geriatric: truncate(p.geriatric_use, 200),
              renal: truncate(p.renal_impairment, 200),
              hepatic: truncate(p.hepatic_impairment, 200),
              weight: truncate(p.weight_and_obesity_considerations, 200),
              lactation: truncate(p.lactation_and_nursing, 150)
            },
            top_adverse_events_faers: (drug.top_adverse_events_faers || []).slice(0, 5),
            patient_factor_tags: drug.all_patient_factor_tags || [],
            warnings: warnings,
            sources: sources,
            rag_context: {
              contraindications: g.contraindications || '',
              warnings_and_precautions: truncate(g.warnings_and_precautions, 500),
              drug_interactions: g.drug_interactions || '',
              pregnancy: p.pregnancy_and_teratogenicity || '',
              dosage: u.dosage_and_administration || '',
              adverse_reactions: u.adverse_reactions || '',
              pediatric_use: p.pediatric_use || '',
              geriatric_use: p.geriatric_use || '',
              patient_counseling: u.patient_counseling_information || '',
              indications: u.indications_and_usage || ''
            }
          }));
        }

        // ========== FALLBACK: OpenFDA Live Lookup ==========
        const fdaResult = await getOpenFDAFallback(medName);
        if (fdaResult) {
          const openfda = fdaResult.openfda || {};
          const pillImageUrl = await getRxImageUrl(medName);
          const genericName = (openfda.generic_name && openfda.generic_name[0]) || medName;

          res.writeHead(200);
          return res.end(JSON.stringify({
            verification: { status: 'VERIFIED', source: 'openfda_fallback' },
            image_url: pillImageUrl,
            medication: {
              drug_name: genericName,
              generic_name: genericName,
              aliases: openfda.brand_name || [],
              category: (openfda.pharm_class_cs && openfda.pharm_class_cs[0]) || 'FDA Monographed Drug',
              primary_indication: truncate(fdaResult.indications_and_usage, 200),
              active_ingredient: genericName,
              rxcui: 'fda_' + genericName.toLowerCase().replace(/\s+/g, '_'),
              dosage: truncate(fdaResult.dosage_and_administration, 350),
              contraindications: truncate(fdaResult.contraindications, 300),
              interactions: truncate(fdaResult.drug_interactions, 300),
              boxed_warning: fdaResult.boxed_warning || 'No boxed warning',
              adverse_reactions: truncate(fdaResult.adverse_reactions, 300),
              patient_counseling: truncate(fdaResult.patient_counseling_information, 400),
              indications: truncate(fdaResult.indications_and_usage, 250),
              pregnancy: truncate(fdaResult.pregnancy, 200)
            },
            top_adverse_events_faers: [],
            warnings: [{ severity: 'high', section: 'FDA Warnings', text: truncate(fdaResult.warnings || fdaResult.warnings_and_cautions, 200) }],
            sources: ['U.S. OpenFDA Official Database', pillImageUrl ? 'RxImage NLM' : null].filter(Boolean)
          }));
        }

        res.writeHead(200);
        return res.end(JSON.stringify({
          verification: { status: 'UNVERIFIED' },
          uncertainty: { reason: `الدواء '${medName}' غير موجود في قاعدة البيانات المحلية (35 دواء) أو قاعدة OpenFDA الرسمية. جرب الاسم العلمي بالإنجليزية.` }
        }));
      } catch (e) {
        res.writeHead(500);
        return res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Not Found' }));
});

server.listen(PORT, () => {
  console.log(`🚀 MedSafety Multi-Source RAG Server v4.5 on http://localhost:${PORT}`);
  console.log(`📊 ${totalLoaded} drugs loaded | Sources: Local KB + OpenFDA + RxNorm + RxImage + FAERS`);
});
