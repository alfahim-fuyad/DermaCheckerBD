import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  Download,
  FileText,
  Image as ImageIcon,
  Info,
  Layers,
  Printer,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

const probabilities = [
  { code: "nv", name: "Melanocytic nevi", value: 46.46 },
  { code: "mel", name: "Melanoma", value: 31.72 },
  { code: "bkl", name: "Benign keratosis-like lesions", value: 12.83 },
  { code: "df", name: "Dermatofibroma", value: 5.41 },
  { code: "bcc", name: "Basal cell carcinoma", value: 3.32 },
  { code: "akiec", name: "Actinic keratoses", value: 0.26 },
  { code: "vasc", name: "Vascular lesions", value: 0 },
];

const checks = [
  { label: "Resolution", value: "450 px min", message: "Meets the minimum dimension.", passed: true },
  { label: "Sharpness", value: "43.8", message: "Below the 100-point heuristic threshold.", suggestion: "Use a sharper, in-focus image if available.", passed: false },
  { label: "Brightness", value: "169.6", message: "Within the expected range.", passed: true },
  { label: "Exposure", value: "0.4% shadows", message: "Few severely underexposed pixels.", passed: true },
  { label: "Framing", value: "1.33", message: "Lesion occupies a usable area of the frame.", passed: true },
  { label: "Looks like skin", value: "98.5%", message: "Visual heuristic is consistent with skin.", passed: true },
];

const buttonClass = "dc-current-button";

export function Current() {
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const printOrPdf = () => {
    setNotice("Use your browser’s print dialog to print or save this preview as a PDF.");
    window.print();
  };

  const unavailable = (action: string) =>
    setNotice(`${action} is shown for this static preview; no record or page was opened.`);

  return (
    <main className="dc-current">
      <style>{`
        .dc-current {
          --dc-ink: #17334a;
          --dc-muted: #647b89;
          --dc-teal: #168b83;
          --dc-teal-dark: #08736e;
          --dc-border: #dce7e9;
          --dc-soft: #f2f7f7;
          min-height: 100vh;
          padding: 34px 22px 58px;
          color: var(--dc-ink);
          background: #f6f9f8;
          font-family: "DM Sans", "Plus Jakarta Sans", sans-serif;
          font-size: 14px;
          line-height: 1.5;
        }
        .dc-current * { box-sizing: border-box; }
        .dc-current .dc-shell { max-width: 906px; margin: 0 auto; }
        .dc-current .dc-topline { display:flex; justify-content:space-between; align-items:center; gap:14px; margin-bottom:14px; }
        .dc-current .dc-ref { display:inline-flex; align-items:center; gap:8px; padding:7px 11px; color:#315a66; background:#e8f3f2; border:1px solid #d3e8e5; border-radius:5px; font-size:12px; font-weight:700; letter-spacing:.02em; }
        .dc-current .dc-tools { display:flex; flex-wrap:wrap; gap:8px; }
        .dc-current .dc-button { display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:34px; padding:7px 11px; color:#315361; background:#fff; border:1px solid #cbdcdf; border-radius:5px; font:600 12px "DM Sans", sans-serif; cursor:pointer; transition:background .18s ease, transform .18s ease; }
        .dc-current .dc-button:hover { background:#edf5f4; transform:translateY(-1px); }
        .dc-current .dc-button svg { width:14px; height:14px; }
        .dc-current .dc-button-danger { color:#9a494a; border-color:#ebd4d2; }
        .dc-current .dc-date { margin:0 0 22px; color:var(--dc-muted); font-size:12px; }
        .dc-current .dc-grid { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); align-items:start; gap:20px; }
        .dc-current .dc-card { background:#fff; border:1px solid var(--dc-border); border-radius:9px; box-shadow:0 4px 16px rgba(28,65,76,.035); }
        .dc-current .dc-image-card { padding:15px; }
        .dc-current .dc-image-wrap { overflow:hidden; border-radius:6px; background:#e9eeee; }
        .dc-current .dc-image-wrap img { display:block; width:100%; height:auto; aspect-ratio:1.25; object-fit:cover; }
        .dc-current .dc-image-name { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:11px 0 0; color:#647b89; font-size:12px; }
        .dc-current .dc-sample { padding:4px 7px; color:#58747c; background:#f1f6f5; border-radius:4px; font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
        .dc-current .dc-result-banner { display:flex; align-items:center; gap:13px; padding:15px 16px; margin-bottom:15px; border:1px solid #a9d9ca; border-radius:9px; color:#1a6254; background:#eef8f3; }
        .dc-current .dc-result-icon { display:grid; width:38px; height:38px; place-items:center; flex:none; border-radius:50%; color:#1e816c; background:#fff; }
        .dc-current .dc-result-icon svg { width:21px; height:21px; }
        .dc-current .dc-banner-title { margin-bottom:3px; font-size:14px; font-weight:750; }
        .dc-current .dc-banner-sub { color:#55786f; font-size:12px; }
        .dc-current .dc-subcard { padding:16px; }
        .dc-current .dc-h { display:flex; align-items:center; gap:8px; margin:0; color:#213f52; font-size:14px; font-weight:750; }
        .dc-current .dc-h svg { width:16px; height:16px; color:var(--dc-teal); }
        .dc-current .dc-prob-list { display:grid; gap:10px; margin-top:15px; }
        .dc-current .dc-prob-head { display:flex; justify-content:space-between; gap:12px; color:#42606d; font-size:12px; }
        .dc-current .dc-prob-head code { color:#235a62; font:700 11px "Space Mono", monospace; }
        .dc-current .dc-prob-head span:last-child { color:#647b89; font-variant-numeric:tabular-nums; }
        .dc-current .dc-track { height:6px; overflow:hidden; margin-top:4px; border-radius:6px; background:#e9f0f1; }
        .dc-current .dc-fill { height:100%; border-radius:6px; background:#218e87; }
        .dc-current .dc-small-note { display:flex; gap:7px; margin:14px 0 0; color:#667d89; font-size:11px; line-height:1.55; }
        .dc-current .dc-small-note svg { width:14px; height:14px; flex:none; margin-top:1px; color:#5d8b8b; }
        .dc-current .dc-section { margin-top:18px; padding:18px 20px; }
        .dc-current .dc-muted-line { margin:6px 0 14px; color:var(--dc-muted); font-size:12px; }
        .dc-current .dc-quality-score { color:#294a5a; }
        .dc-current .dc-qchecks { display:grid; grid-template-columns:1fr 1fr; column-gap:22px; }
        .dc-current .dc-qcheck { display:flex; gap:10px; padding:11px 0; border-top:1px solid #edf1f1; }
        .dc-current .dc-qcheck-icon { display:grid; width:21px; height:21px; place-items:center; flex:none; margin-top:1px; border-radius:50%; color:#fff; background:#339978; }
        .dc-current .dc-qcheck-icon.fail { background:#c27a55; }
        .dc-current .dc-qcheck-icon svg { width:13px; height:13px; }
        .dc-current .dc-q-label { color:#2c4b59; font-size:12px; font-weight:700; }
        .dc-current .dc-q-value { color:#71848b; font-size:11px; font-weight:500; }
        .dc-current .dc-q-message, .dc-current .dc-q-suggestion { margin-top:2px; color:#71828a; font-size:11px; }
        .dc-current .dc-q-suggestion { color:#a36b4e; }
        .dc-current .dc-disclaimer { padding:13px 15px; color:#5c6f76; background:#f4f7f6; border:1px solid #e1e9e8; border-radius:7px; font-size:11px; line-height:1.55; }
        .dc-current .dc-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:12px; }
        .dc-current .dc-stat { padding:12px 13px; border:1px solid #e2ebea; border-radius:7px; background:#f8fbfa; }
        .dc-current .dc-stat-value { color:#226b66; font:700 22px "Space Mono", monospace; letter-spacing:-.06em; }
        .dc-current .dc-stat-label { margin-top:3px; color:#6b8087; font-size:10px; }
        .dc-current .dc-reliability-copy { margin:12px 0 0; color:#687c83; font-size:12px; }
        .dc-current .dc-medical { margin-top:12px; padding:14px 16px; border-color:#e6dfcb; color:#605c50; background:#faf8f1; }
        .dc-current .dc-medical strong { color:#4d4a40; }
        .dc-current .dc-medical p { margin:6px 0 0; }
        .dc-current .dc-actions { display:flex; flex-wrap:wrap; gap:9px; margin-top:18px; }
        .dc-current .dc-primary { color:#fff; background:#117e78; border-color:#117e78; }
        .dc-current .dc-primary:hover { background:#096d68; }
        .dc-current .dc-actions .dc-button { min-height:38px; padding:8px 13px; }
        .dc-current .dc-notice { position:fixed; right:18px; bottom:18px; z-index:5; max-width:min(430px, calc(100vw - 36px)); padding:12px 15px; color:#fff; background:#183f4b; border-radius:7px; box-shadow:0 8px 24px rgba(22,51,62,.2); font-size:12px; }
        .dc-current .dc-delete-backdrop { position:fixed; inset:0; z-index:10; display:grid; place-items:center; padding:20px; background:rgba(23,45,55,.36); }
        .dc-current .dc-delete-dialog { width:min(400px,100%); padding:22px; border:1px solid #dce7e9; border-radius:10px; background:#fff; box-shadow:0 20px 70px rgba(22,48,58,.18); }
        .dc-current .dc-delete-dialog h2 { margin:0 0 8px; font-size:18px; }
        .dc-current .dc-delete-dialog p { color:#687c83; font-size:13px; }
        .dc-current .dc-dialog-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:18px; }
        @media (max-width:700px) {
          .dc-current { padding:22px 14px 40px; }
          .dc-current .dc-grid { grid-template-columns:1fr; gap:14px; }
          .dc-current .dc-qchecks { grid-template-columns:1fr; }
          .dc-current .dc-section { padding:16px; }
          .dc-current .dc-topline { align-items:flex-start; flex-direction:column; }
        }
        @media print { .dc-current { padding:0; background:#fff; } .dc-current .dc-tools, .dc-current .dc-actions, .dc-current .dc-notice { display:none !important; } }
      `}</style>

      <div className="dc-shell">
        <div className="dc-topline">
          <span className="dc-ref"><FileText aria-hidden="true" size={14} /> Reference DCBD-7F3A2C9B</span>
          <div className="dc-tools" aria-label="Saved prediction actions">
            <button className={`${buttonClass} dc-button`} type="button" onClick={printOrPdf} aria-label="Download PDF"><Download />Download PDF</button>
            <button className={`${buttonClass} dc-button`} type="button" onClick={printOrPdf} aria-label="Print saved prediction"><Printer />Print</button>
            <button className={`${buttonClass} dc-button dc-button-danger`} type="button" onClick={() => setConfirmDelete(true)} aria-label="Delete saved prediction"><Trash2 />Delete</button>
          </div>
        </div>
        <p className="dc-date">2025-02-14 10:32 +06 · <strong>Bundled sample preview</strong></p>

        <div className="dc-grid">
          <section className="dc-card dc-image-card" aria-label="Original sample image">
            <div className="dc-image-wrap">
              <img src="/__mockup/images/lesion-sample.jpg" alt="Bundled dermoscopic sample preview showing a round pink-red lesion on light skin; not a user's case." />
            </div>
            <p className="dc-image-name"><span>lesion-sample.jpg</span><span className="dc-sample">Bundled sample preview</span></p>
          </section>

          <div>
            <section className="dc-result-banner" aria-label="Prediction result">
              <span className="dc-result-icon"><ShieldCheck aria-hidden="true" /></span>
              <div>
                <div className="dc-banner-title">NV — Melanocytic Nevi</div>
                <div className="dc-banner-sub">Category: Benign · Confidence: 46.46%</div>
              </div>
            </section>
            <section className="dc-card dc-subcard">
              <h2 className="dc-h">Class probabilities</h2>
              <div className="dc-prob-list">
                {probabilities.map((item) => (
                  <div key={item.code}>
                    <div className="dc-prob-head"><code>{item.code}</code><span>{item.name}</span><span>{item.value.toFixed(2)}%</span></div>
                    <div className="dc-track" aria-label={`${item.name}: ${item.value.toFixed(2)} percent`}>
                      <div className="dc-fill" style={{ width: `${item.value}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <p className="dc-small-note"><Info aria-hidden="true" /> Confidence is the model’s maximum softmax probability, not a probability of correctness. Backend: <code>keras</code>.</p>
            </section>
          </div>
        </div>

        <section className="dc-card dc-section">
          <h2 className="dc-h"><ImageIcon aria-hidden="true" />Image quality assessment</h2>
          <p className="dc-muted-line">Score: <strong className="dc-quality-score">70.0/100</strong> · Not suitable by heuristic</p>
          <div className="dc-qchecks">
            {checks.map((check) => (
              <div className="dc-qcheck" key={check.label}>
                <span className={`dc-qcheck-icon${check.passed ? "" : " fail"}`}>{check.passed ? <Check /> : <X />}</span>
                <div><div className="dc-q-label">{check.label} <span className="dc-q-value">({check.value})</span></div><div className="dc-q-message">{check.message}</div>{check.suggestion && <div className="dc-q-suggestion">{check.suggestion}</div>}</div>
              </div>
            ))}
          </div>
          <p className="dc-small-note"><Info aria-hidden="true" /> The image-quality score is a heuristic and is not a medical suitability certificate.</p>
        </section>

        <section className="dc-card dc-section">
          <h2 className="dc-h"><Activity aria-hidden="true" />Prediction reliability check</h2>
          <div className="dc-stats">
            <div className="dc-stat"><div className="dc-stat-value">100%</div><div className="dc-stat-label">Stability (agreement)</div></div>
            <div className="dc-stat"><div className="dc-stat-value">46.46%</div><div className="dc-stat-label">Original confidence</div></div>
            <div className="dc-stat"><div className="dc-stat-value">0</div><div className="dc-stat-label">Flipped variants · 5 tested</div></div>
          </div>
          <p className="dc-reliability-copy">Top-class prediction was consistent across all 5 mild image transforms.</p>
          <div className="dc-disclaimer" style={{ marginTop: 13 }}><strong>Agreement measures stability, not correctness.</strong> A 100% agreement score does not mean the prediction is right.</div>
        </section>

        <section className="dc-disclaimer dc-medical" aria-labelledby="dc-current-limitations">
          <h2 className="dc-h" id="dc-current-limitations"><AlertTriangle aria-hidden="true" />Limitations &amp; next steps</h2>
          <p>This system is developed for educational/research purposes and is not a medical diagnostic tool. The prediction should not be considered a medical diagnosis. The model can be wrong even when confidence and stability are high.</p>
          <p>Please consult a qualified dermatologist or healthcare professional for proper evaluation. If the lesion is changing, bleeding, growing, or painful, do not delay professional care based on this output.</p>
        </section>

        <nav className="dc-actions" aria-label="Next steps">
          <button className="dc-button dc-primary" type="button" onClick={() => unavailable("Analyze another image")} aria-label="Analyze another image"><RefreshCw />Analyze another image</button>
          <button className="dc-button" type="button" onClick={() => unavailable("Standalone reliability check")} aria-label="Open standalone reliability check"><Activity />Standalone reliability check</button>
          <button className="dc-button" type="button" onClick={() => unavailable("Compare multiple images")} aria-label="Compare multiple images"><Layers />Compare multiple images</button>
        </nav>
        {notice && <div className="dc-notice" role="status" aria-live="polite" onClick={() => setNotice("")}>{notice}</div>}
      </div>

      {confirmDelete && (
        <div className="dc-delete-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setConfirmDelete(false); }}>
          <section className="dc-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="dc-delete-title">
            <h2 id="dc-delete-title">Delete this saved prediction?</h2>
            <p>This is a static sample preview. No record will be deleted.</p>
            <div className="dc-dialog-actions">
              <button className="dc-button" type="button" onClick={() => setConfirmDelete(false)}>Cancel</button>
              <button className="dc-button dc-button-danger" type="button" onClick={() => { setConfirmDelete(false); setNotice("Static sample preview only—no record was deleted."); }}>Confirm delete</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
