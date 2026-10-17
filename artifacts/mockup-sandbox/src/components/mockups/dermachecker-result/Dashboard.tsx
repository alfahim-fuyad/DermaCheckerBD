import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleHelp,
  Download,
  FileText,
  Image as ImageIcon,
  Info,
  Layers,
  Printer,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

const classProbabilities = [
  { code: "nv", name: "Melanocytic nevi", value: 46.46 },
  { code: "mel", name: "Melanoma", value: 31.72 },
  { code: "bkl", name: "Benign keratosis-like lesions", value: 12.83 },
  { code: "df", name: "Dermatofibroma", value: 5.41 },
  { code: "bcc", name: "Basal cell carcinoma", value: 3.32 },
  { code: "akiec", name: "Actinic keratoses", value: 0.26 },
  { code: "vasc", name: "Vascular lesions", value: 0 },
];

const qualityChecks = [
  { label: "Resolution", value: "450 px min dimension", passed: true, message: "At the minimum image size." },
  { label: "Sharpness", value: "43.8 / threshold 100", passed: false, message: "Soft focus may limit useful detail.", suggestion: "Prefer an in-focus image when available." },
  { label: "Brightness", value: "169.6", passed: true, message: "Within the expected range." },
  { label: "Exposure", value: "0.4% shadows", passed: true, message: "Very few severely dark pixels." },
  { label: "Framing", value: "1.33", passed: true, message: "Framing heuristic passed." },
  { label: "Looks like skin", value: "98.5%", passed: true, message: "Skin-like image heuristic passed." },
];

type NoticeProps = { message: string; onDismiss: () => void };

function Notice({ message, onDismiss }: NoticeProps) {
  return <div className="dc-dashboard-notice" role="status" aria-live="polite" onClick={onDismiss}>{message}<span aria-hidden="true">×</span></div>;
}

export function Dashboard() {
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const printOrPdf = () => {
    setNotice("Use the browser print dialog to print this page or save it as a PDF.");
    window.print();
  };

  const unavailable = (action: string) =>
    setNotice(`${action} is a represented page action; this static mockup does not navigate or submit data.`);

  return (
    <main className="dc-dashboard">
      <style>{`
        .dc-dashboard {
          --navy:#16354a; --navy-2:#214b60; --ink:#203e50; --muted:#71858e;
          --teal:#157e79; --teal-2:#27a49a; --teal-pale:#e9f5f2; --line:#dce7e7;
          --canvas:#f3f7f6; --white:#fff; --copper:#bb7553;
          min-height:100vh; color:var(--ink); background:var(--canvas);
          font-family:"DM Sans","Plus Jakarta Sans",sans-serif; font-size:14px; line-height:1.5;
        }
        .dc-dashboard *{box-sizing:border-box}
        .dc-dashboard button{font:inherit}
        .dc-dashboard .dc-bar{height:66px; display:flex; align-items:center; justify-content:space-between; gap:22px; padding:0 max(24px,calc((100vw - 1240px)/2)); background:#fff; border-bottom:1px solid #e4ecea}
        .dc-dashboard .dc-brand{display:flex; align-items:center; gap:11px; min-width:0}
        .dc-dashboard .dc-brand-mark{display:grid; place-items:center; width:34px; height:34px; border-radius:9px; color:#fff; background:var(--navy)}
        .dc-dashboard .dc-brand-mark svg{width:18px;height:18px}
        .dc-dashboard .dc-brand-name{color:var(--navy); font-size:15px; font-weight:800; letter-spacing:-.03em}
        .dc-dashboard .dc-brand-sub{color:#809198; font-size:10px; letter-spacing:.07em; text-transform:uppercase}
        .dc-dashboard .dc-topright{display:flex; align-items:center; gap:14px}
        .dc-dashboard .dc-research-tag{display:inline-flex; align-items:center; gap:7px; padding:6px 9px; color:#416c6d; background:#edf6f3; border:1px solid #dcebe7; border-radius:5px; font-size:10px; font-weight:700; letter-spacing:.04em}
        .dc-dashboard .dc-research-tag svg{width:13px;height:13px}
        .dc-dashboard .dc-icon-btn{display:inline-grid; place-items:center; width:34px; height:34px; color:#52707b; background:#fff; border:1px solid var(--line); border-radius:6px; cursor:pointer}
        .dc-dashboard .dc-icon-btn:hover{background:#f1f7f6;color:var(--teal)}
        .dc-dashboard .dc-icon-btn svg{width:16px;height:16px}
        .dc-dashboard .dc-main{width:min(1240px,calc(100% - 48px)); margin:0 auto; padding:31px 0 64px}
        .dc-dashboard .dc-breadcrumb{display:flex; align-items:center; gap:8px; margin-bottom:18px; color:#7b8d92; font-size:11px}
        .dc-dashboard .dc-breadcrumb svg{width:13px;height:13px}
        .dc-dashboard .dc-breadcrumb strong{color:#45616d;font-weight:700}
        .dc-dashboard .dc-heading-row{display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:22px}
        .dc-dashboard .dc-eyebrow{margin:0 0 5px; color:var(--teal); font-size:10px; font-weight:800; letter-spacing:.14em; text-transform:uppercase}
        .dc-dashboard h1{margin:0; color:var(--navy); font-size:clamp(26px,3vw,36px); line-height:1.12; letter-spacing:-.055em}
        .dc-dashboard .dc-created{margin:8px 0 0; color:#758890; font-size:12px}
        .dc-dashboard .dc-ref-chip{display:flex; align-items:center; gap:8px; padding:10px 12px; color:#39596a; background:#fff; border:1px solid var(--line); border-radius:7px; font:700 11px "Space Mono",monospace}
        .dc-dashboard .dc-ref-chip svg{width:14px;height:14px;color:#538583}
        .dc-dashboard .dc-layout{display:grid; grid-template-columns:minmax(0,1.1fr) minmax(370px,.9fr); align-items:start; gap:18px}
        .dc-dashboard .dc-panel{background:var(--white); border:1px solid var(--line); border-radius:10px; box-shadow:0 5px 20px rgba(29,67,74,.035)}
        .dc-dashboard .dc-image-panel{overflow:hidden}
        .dc-dashboard .dc-panel-head{display:flex; justify-content:space-between; align-items:center; gap:12px; min-height:51px; padding:0 17px; border-bottom:1px solid #e9efee}
        .dc-dashboard .dc-panel-title{display:flex; align-items:center; gap:8px; margin:0; color:#315264; font-size:12px; font-weight:750}
        .dc-dashboard .dc-panel-title svg{width:15px;height:15px;color:#39877e}
        .dc-dashboard .dc-sample-label{padding:4px 7px; color:#58796f; background:#eff6f2; border-radius:4px; font-size:9px; font-weight:800; letter-spacing:.08em; text-transform:uppercase}
        .dc-dashboard .dc-lesion-img{display:block; width:100%; height:auto; aspect-ratio:1.24; object-fit:cover; background:#e9efed}
        .dc-dashboard .dc-image-meta{display:flex; justify-content:space-between; align-items:center; gap:12px; padding:12px 16px; color:#71848c; border-top:1px solid #e9efee; font-size:11px}
        .dc-dashboard .dc-image-name{display:flex; align-items:center; gap:7px}
        .dc-dashboard .dc-image-name svg{width:14px;height:14px}
        .dc-dashboard .dc-muted-small{color:#92a0a3}
        .dc-dashboard .dc-result-panel{padding:20px}
        .dc-dashboard .dc-category{display:flex; align-items:center; gap:7px; width:max-content; padding:5px 9px; color:#276c5e; background:#ebf7f1; border:1px solid #d3ecdf; border-radius:20px; font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase}
        .dc-dashboard .dc-category svg{width:13px;height:13px}
        .dc-dashboard .dc-result-heading{display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin:16px 0 10px}
        .dc-dashboard .dc-result-heading h2{margin:0; color:var(--navy); font-size:27px; line-height:1.05; letter-spacing:-.055em}
        .dc-dashboard .dc-class-name{margin:5px 0 0; color:#617984; font-size:13px}
        .dc-dashboard .dc-conf{flex:none; text-align:right}
        .dc-dashboard .dc-conf strong{display:block; color:#286b69; font:700 22px "Space Mono",monospace; letter-spacing:-.08em}
        .dc-dashboard .dc-conf span{color:#7e9094; font-size:9px; font-weight:700; letter-spacing:.09em; text-transform:uppercase}
        .dc-dashboard .dc-callout{display:flex; gap:9px; padding:10px 11px; margin:14px 0 18px; color:#5e737d; background:#f5f8f7; border-left:3px solid #86bbb2; border-radius:3px; font-size:11px; line-height:1.5}
        .dc-dashboard .dc-callout svg{width:15px;height:15px;flex:none;color:#4d8d86}
        .dc-dashboard .dc-section-title{display:flex; justify-content:space-between; align-items:center; gap:12px; margin:0 0 11px; color:#28495c; font-size:12px; font-weight:800}
        .dc-dashboard .dc-section-title em{color:#8b9a9e;font-size:9px;font-style:normal;font-weight:600}
        .dc-dashboard .dc-probs{display:grid; gap:10px}
        .dc-dashboard .dc-prob-row{display:grid; grid-template-columns:minmax(0,1fr) 54px; column-gap:10px; row-gap:5px; align-items:center}
        .dc-dashboard .dc-prob-label{display:flex; align-items:baseline; gap:7px; min-width:0}
        .dc-dashboard .dc-prob-code{width:34px; color:#32716f; font:700 10px "Space Mono",monospace}
        .dc-dashboard .dc-prob-name{overflow:hidden;color:#617882;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
        .dc-dashboard .dc-prob-pct{text-align:right;color:#45616c;font:700 10px "Space Mono",monospace}
        .dc-dashboard .dc-prob-track{grid-column:1/-1;height:6px;overflow:hidden;border-radius:5px;background:#eaf0ef}
        .dc-dashboard .dc-prob-fill{height:100%;min-width:0;border-radius:5px;background:linear-gradient(90deg,#238f86,#54b7a7)}
        .dc-dashboard .dc-prob-row:first-child .dc-prob-fill{background:#167e79}
        .dc-dashboard .dc-prob-row:nth-child(2) .dc-prob-fill{background:#719b98}
        .dc-dashboard .dc-backend{display:flex;justify-content:space-between;gap:12px;padding-top:13px;margin-top:15px;border-top:1px solid #e9efee;color:#75878d;font-size:10px}
        .dc-dashboard .dc-backend code{color:#446675;font:700 10px "Space Mono",monospace}
        .dc-dashboard .dc-lower-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;margin-top:18px}
        .dc-dashboard .dc-quality{padding:20px}
        .dc-dashboard .dc-quality-top{display:flex;justify-content:space-between;align-items:center;gap:16px;padding-bottom:16px;border-bottom:1px solid #e9efee}
        .dc-dashboard .dc-quality-heading{display:flex;align-items:center;gap:10px}
        .dc-dashboard .dc-heading-icon{display:grid;place-items:center;width:34px;height:34px;color:#277b77;background:#e9f5f2;border-radius:8px}
        .dc-dashboard .dc-heading-icon svg{width:17px;height:17px}
        .dc-dashboard .dc-heading-text h2{margin:0;color:#27485b;font-size:14px;letter-spacing:-.02em}
        .dc-dashboard .dc-heading-text p{margin:3px 0 0;color:#7b8d92;font-size:10px}
        .dc-dashboard .dc-score{position:relative;display:grid;place-items:center;width:58px;height:58px;flex:none}
        .dc-dashboard .dc-score svg{position:absolute;inset:0;width:58px;height:58px;transform:rotate(-90deg)}
        .dc-dashboard .dc-score circle{fill:none;stroke-width:5}
        .dc-dashboard .dc-score .dc-score-bg{stroke:#e7efed}
        .dc-dashboard .dc-score .dc-score-fg{stroke:#c07e56;stroke-linecap:round;stroke-dasharray:70 100}
        .dc-dashboard .dc-score span{color:#805b43;font:700 13px "Space Mono",monospace}
        .dc-dashboard .dc-unsuitable{display:flex;align-items:center;gap:6px;margin:12px 0 6px;color:#9a694d;font-size:10px;font-weight:750}
        .dc-dashboard .dc-unsuitable svg{width:13px;height:13px}
        .dc-dashboard .dc-quality-list{display:grid;grid-template-columns:1fr 1fr;column-gap:20px}
        .dc-dashboard .dc-qrow{display:flex;gap:9px;padding:11px 0;border-bottom:1px solid #edf1f0}
        .dc-dashboard .dc-qicon{display:grid;place-items:center;width:19px;height:19px;flex:none;margin-top:1px;color:#fff;background:#38977e;border-radius:50%}
        .dc-dashboard .dc-qicon.fail{background:#bd7954}
        .dc-dashboard .dc-qicon svg{width:12px;height:12px}
        .dc-dashboard .dc-qrow-title{color:#3d5966;font-size:10px;font-weight:750}
        .dc-dashboard .dc-qrow-value{display:block;margin-top:1px;color:#789097;font:9px "Space Mono",monospace}
        .dc-dashboard .dc-qrow-message{margin-top:3px;color:#849399;font-size:9px;line-height:1.4}
        .dc-dashboard .dc-suggestion{margin-top:3px;color:#a36f52;font-size:9px}
        .dc-dashboard .dc-heu-note{display:flex;gap:7px;margin:13px 0 0;color:#7b8b90;font-size:10px;line-height:1.5}
        .dc-dashboard .dc-heu-note svg{width:14px;height:14px;flex:none;color:#73928d}
        .dc-dashboard .dc-reliability{overflow:hidden}
        .dc-dashboard .dc-reliability-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:19px 20px 15px;border-bottom:1px solid #e9efee}
        .dc-dashboard .dc-reliability-title{display:flex;gap:10px}
        .dc-dashboard .dc-reliability-title h2{margin:0;color:#27485b;font-size:14px}
        .dc-dashboard .dc-reliability-title p{margin:4px 0 0;color:#7b8d92;font-size:10px}
        .dc-dashboard .dc-stable-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;color:#267363;background:#edf7f2;border:1px solid #dbeee5;border-radius:20px;font-size:9px;font-weight:800}
        .dc-dashboard .dc-stable-pill svg{width:12px;height:12px}
        .dc-dashboard .dc-reliability-body{padding:18px 20px}
        .dc-dashboard .dc-agreement{display:flex;align-items:flex-end;justify-content:space-between;gap:14px}
        .dc-dashboard .dc-agreement strong{color:#236f6b;font:700 32px "Space Mono",monospace;letter-spacing:-.09em;line-height:1}
        .dc-dashboard .dc-agreement span{display:block;margin-top:5px;color:#758990;font-size:10px}
        .dc-dashboard .dc-variants{padding:8px 9px;color:#5e7881;background:#f3f7f6;border-radius:5px;font-size:9px;font-weight:700}
        .dc-dashboard .dc-agreement-track{height:6px;overflow:hidden;margin:14px 0 15px;border-radius:5px;background:#e9f0ef}
        .dc-dashboard .dc-agreement-fill{width:100%;height:100%;border-radius:5px;background:#2a9588}
        .dc-dashboard .dc-reliability-stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}
        .dc-dashboard .dc-mini-stat{padding:10px 11px;background:#f6f9f8;border:1px solid #e8efed;border-radius:6px}
        .dc-dashboard .dc-mini-stat strong{display:block;color:#35596a;font:700 13px "Space Mono",monospace}
        .dc-dashboard .dc-mini-stat span{display:block;margin-top:3px;color:#7a8d93;font-size:9px}
        .dc-dashboard .dc-stable-explain{display:flex;gap:8px;margin:13px 0 0;color:#6c8087;font-size:10px;line-height:1.5}
        .dc-dashboard .dc-stable-explain svg{width:14px;height:14px;flex:none;color:#559189}
        .dc-dashboard .dc-disclaimer{display:grid;grid-template-columns:auto 1fr;gap:13px;padding:19px 21px;margin-top:18px;color:#665f51;background:#faf8f1;border:1px solid #e9e2d2;border-radius:9px}
        .dc-dashboard .dc-disclaimer-icon{display:grid;place-items:center;width:32px;height:32px;color:#9b7850;background:#f2eadb;border-radius:8px}
        .dc-dashboard .dc-disclaimer-icon svg{width:17px;height:17px}
        .dc-dashboard .dc-disclaimer h2{margin:0 0 4px;color:#554e42;font-size:13px}
        .dc-dashboard .dc-disclaimer p{margin:0;color:#777064;font-size:11px;line-height:1.6}
        .dc-dashboard .dc-disclaimer p+p{margin-top:5px}
        .dc-dashboard .dc-action-row{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-top:19px}
        .dc-dashboard .dc-action-links{display:flex;flex-wrap:wrap;gap:8px}
        .dc-dashboard .dc-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:8px 12px;color:#496875;background:#fff;border:1px solid #cfdddf;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;transition:background .18s ease,transform .18s ease}
        .dc-dashboard .dc-btn:hover{background:#f0f7f5;transform:translateY(-1px)}
        .dc-dashboard .dc-btn svg{width:14px;height:14px}
        .dc-dashboard .dc-btn-primary{color:#fff;background:#137d77;border-color:#137d77}
        .dc-dashboard .dc-btn-primary:hover{background:#0d6e69}
        .dc-dashboard .dc-btn-danger{color:#a5514e;border-color:#e6d4d1}
        .dc-dashboard .dc-footer-note{margin:18px 0 0;color:#87979b;text-align:center;font-size:9px}
        .dc-dashboard .dc-dashboard-notice{position:fixed;right:22px;bottom:20px;z-index:5;display:flex;justify-content:space-between;gap:20px;max-width:min(470px,calc(100vw - 40px));padding:12px 14px;color:#fff;background:#183f4b;border-radius:7px;box-shadow:0 8px 24px rgba(22,51,62,.2);font-size:12px;cursor:pointer}
        .dc-dashboard .dc-dashboard-notice span{opacity:.7}
        .dc-dashboard .dc-modal-backdrop{position:fixed;inset:0;z-index:10;display:grid;place-items:center;padding:20px;background:rgba(19,43,53,.38)}
        .dc-dashboard .dc-modal{width:min(410px,100%);padding:23px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 24px 70px rgba(17,46,56,.2)}
        .dc-dashboard .dc-modal h2{margin:0 0 8px;color:var(--navy);font-size:18px}
        .dc-dashboard .dc-modal p{color:#70838b;font-size:13px}
        .dc-dashboard .dc-modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}
        @media(max-width:900px){.dc-dashboard .dc-layout{grid-template-columns:minmax(0,1fr) minmax(320px,.95fr)}.dc-dashboard .dc-lower-grid{grid-template-columns:1fr}.dc-dashboard .dc-quality-list{grid-template-columns:1fr 1fr}}
        @media(max-width:700px){
          .dc-dashboard .dc-bar{height:auto;min-height:62px;padding:12px 16px}
          .dc-dashboard .dc-research-tag{display:none}
          .dc-dashboard .dc-main{width:calc(100% - 28px);padding:22px 0 42px}
          .dc-dashboard .dc-heading-row{align-items:flex-start;flex-direction:column;margin-bottom:16px}
          .dc-dashboard .dc-layout{grid-template-columns:1fr;gap:13px}
          .dc-dashboard .dc-lower-grid{grid-template-columns:1fr;gap:13px;margin-top:13px}
          .dc-dashboard .dc-result-panel{padding:17px}
          .dc-dashboard .dc-quality{padding:17px}
          .dc-dashboard .dc-quality-list{grid-template-columns:1fr 1fr;column-gap:12px}
          .dc-dashboard .dc-action-row{align-items:stretch;flex-direction:column}
          .dc-dashboard .dc-action-links{display:grid;grid-template-columns:1fr}
          .dc-dashboard .dc-action-links .dc-btn{justify-content:flex-start}
        }
        @media(max-width:420px){.dc-dashboard .dc-quality-list{grid-template-columns:1fr}.dc-dashboard .dc-result-heading h2{font-size:24px}.dc-dashboard .dc-ref-chip{font-size:9px}}
        @media print{.dc-dashboard{background:#fff}.dc-dashboard .dc-bar,.dc-dashboard .dc-action-row,.dc-dashboard .dc-dashboard-notice{display:none!important}.dc-dashboard .dc-main{width:100%;padding:0}.dc-dashboard .dc-panel{box-shadow:none;break-inside:avoid}}
      `}</style>

      <header className="dc-bar">
        <div className="dc-brand" aria-label="DermaCheckerBD">
          <span className="dc-brand-mark"><ShieldCheck aria-hidden="true" /></span>
          <div><div className="dc-brand-name">DermaCheckerBD</div><div className="dc-brand-sub">Skin lesion research prototype</div></div>
        </div>
        <div className="dc-topright">
          <span className="dc-research-tag"><Sparkles aria-hidden="true" />Educational / research use only</span>
          <button className="dc-icon-btn" type="button" onClick={() => setNotice("This saved result is a static bundled sample preview.")} aria-label="About this sample preview"><CircleHelp aria-hidden="true" /></button>
        </div>
      </header>

      <div className="dc-main">
        <nav className="dc-breadcrumb" aria-label="Breadcrumb">
          <span>Research workspace</span><ChevronRight aria-hidden="true" /><strong>Saved prediction</strong>
        </nav>
        <div className="dc-heading-row">
          <div>
            <p className="dc-eyebrow">Saved analysis · single image</p>
            <h1>Prediction detail</h1>
            <p className="dc-created">Created 2025-02-14 10:32 +06 <span aria-hidden="true">·</span> <strong>Bundled sample preview — not a user’s case</strong></p>
          </div>
          <div className="dc-ref-chip"><FileText aria-hidden="true" />DCBD-7F3A2C9B</div>
        </div>

        <div className="dc-layout">
          <section className="dc-panel dc-image-panel" aria-labelledby="dc-image-title">
            <div className="dc-panel-head">
              <h2 className="dc-panel-title" id="dc-image-title"><ImageIcon aria-hidden="true" />Original image</h2>
              <span className="dc-sample-label">Bundled sample preview</span>
            </div>
            <img className="dc-lesion-img" src="/__mockup/images/lesion-sample.jpg" alt="Bundled dermoscopic sample preview: round pink-red lesion on light skin, shown for educational research; not a user's case." />
            <div className="dc-image-meta"><span className="dc-image-name"><ImageIcon aria-hidden="true" />lesion-sample.jpg</span><span className="dc-muted-small">Sample asset · no personal data</span></div>
          </section>

          <section className="dc-panel dc-result-panel" aria-labelledby="dc-prediction-title">
            <span className="dc-category"><ShieldCheck aria-hidden="true" />Benign category</span>
            <div className="dc-result-heading">
              <div><h2 id="dc-prediction-title">NV</h2><p className="dc-class-name">Melanocytic Nevi</p></div>
              <div className="dc-conf"><strong>46.46%</strong><span>Model confidence</span></div>
            </div>
            <div className="dc-callout"><Info aria-hidden="true" /><span>Confidence is the model’s maximum softmax probability, not a probability of correctness. It must not be read as diagnostic certainty.</span></div>

            <div className="dc-section-title"><span>Seven-class probabilities</span><em>max softmax output</em></div>
            <div className="dc-probs" aria-label="Class probabilities">
              {classProbabilities.map((item) => (
                <div className="dc-prob-row" key={item.code}>
                  <div className="dc-prob-label"><span className="dc-prob-code">{item.code}</span><span className="dc-prob-name">{item.name}</span></div>
                  <span className="dc-prob-pct">{item.value.toFixed(2)}%</span>
                  <div className="dc-prob-track" role="img" aria-label={`${item.name}: ${item.value.toFixed(2)} percent`}><div className="dc-prob-fill" style={{ width: `${item.value}%` }} /></div>
                </div>
              ))}
            </div>
            <div className="dc-backend"><span>Inference backend</span><code>keras</code></div>
          </section>
        </div>

        <div className="dc-lower-grid">
          <section className="dc-panel dc-quality" aria-labelledby="dc-quality-title">
            <div className="dc-quality-top">
              <div className="dc-quality-heading">
                <span className="dc-heading-icon"><ImageIcon aria-hidden="true" /></span>
                <div className="dc-heading-text"><h2 id="dc-quality-title">Image quality</h2><p>Input checks and capture context</p></div>
              </div>
              <div className="dc-score" role="img" aria-label="Image quality score 70 out of 100">
                <svg viewBox="0 0 36 36" aria-hidden="true"><circle className="dc-score-bg" cx="18" cy="18" r="15.9" pathLength="100" /><circle className="dc-score-fg" cx="18" cy="18" r="15.9" pathLength="100" /></svg>
                <span>70</span>
              </div>
            </div>
            <div className="dc-unsuitable"><AlertTriangle aria-hidden="true" />Not suitable by heuristic</div>
            <div className="dc-quality-list">
              {qualityChecks.map((check) => (
                <div className="dc-qrow" key={check.label}>
                  <span className={`dc-qicon${check.passed ? "" : " fail"}`}>{check.passed ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}</span>
                  <div><div className="dc-qrow-title">{check.label}</div><span className="dc-qrow-value">{check.value}</span><div className="dc-qrow-message">{check.message}</div>{check.suggestion && <div className="dc-suggestion">{check.suggestion}</div>}</div>
                </div>
              ))}
            </div>
            <p className="dc-heu-note"><Info aria-hidden="true" />The image-quality score is a heuristic, not a medical suitability certificate.</p>
          </section>

          <section className="dc-panel dc-reliability" aria-labelledby="dc-reliability-title">
            <div className="dc-reliability-head">
              <div className="dc-reliability-title">
                <span className="dc-heading-icon"><Activity aria-hidden="true" /></span>
                <div><h2 id="dc-reliability-title">Prediction stability</h2><p>Agreement across mild image variants</p></div>
              </div>
              <span className="dc-stable-pill"><Check aria-hidden="true" />Stable</span>
            </div>
            <div className="dc-reliability-body">
              <div className="dc-agreement">
                <div><strong>100%</strong><span>Top-class agreement</span></div>
                <span className="dc-variants">5 variants tested</span>
              </div>
              <div className="dc-agreement-track" role="img" aria-label="100 percent top-class agreement"><div className="dc-agreement-fill" /></div>
              <div className="dc-reliability-stats">
                <div className="dc-mini-stat"><strong>46.46%</strong><span>Original confidence</span></div>
                <div className="dc-mini-stat"><strong>0</strong><span>Class flips across variants</span></div>
              </div>
              <p className="dc-stable-explain"><Info aria-hidden="true" /><span>The top class stayed the same across all 5 variants. Stability describes consistency under these transforms; it does not establish accuracy or correctness.</span></p>
            </div>
          </section>
        </div>

        <section className="dc-disclaimer" aria-labelledby="dc-limitations-title">
          <span className="dc-disclaimer-icon"><AlertTriangle aria-hidden="true" /></span>
          <div>
            <h2 id="dc-limitations-title">Limitations &amp; next steps</h2>
            <p>DermaCheckerBD is an educational and research prototype, not a medical diagnostic tool. This model output is not a diagnosis. A prediction can be wrong even when confidence is high and results are stable; neither confidence nor stability indicates correctness.</p>
            <p>Consult a qualified dermatologist or healthcare professional for proper evaluation. If a lesion is changing, bleeding, growing, or painful, do not delay professional care based on this output.</p>
          </div>
        </section>

        <div className="dc-action-row">
          <div className="dc-action-links" aria-label="Prediction actions">
            <button className="dc-btn dc-btn-primary" type="button" onClick={() => unavailable("Analyze another image")} aria-label="Analyze another image"><RefreshCw aria-hidden="true" />Analyze another image<ArrowUpRight aria-hidden="true" /></button>
            <button className="dc-btn" type="button" onClick={() => unavailable("Standalone reliability check")} aria-label="Open standalone reliability check"><Activity aria-hidden="true" />Standalone reliability check</button>
            <button className="dc-btn" type="button" onClick={() => unavailable("Compare multiple images")} aria-label="Compare multiple images"><Layers aria-hidden="true" />Compare multiple images</button>
          </div>
          <div className="dc-action-links">
            <button className="dc-btn" type="button" onClick={printOrPdf} aria-label="Download PDF"><Download aria-hidden="true" />Download PDF</button>
            <button className="dc-btn" type="button" onClick={printOrPdf} aria-label="Print prediction"><Printer aria-hidden="true" />Print</button>
            <button className="dc-btn dc-btn-danger" type="button" onClick={() => setConfirmDelete(true)} aria-label="Delete saved prediction"><Trash2 aria-hidden="true" />Delete</button>
          </div>
        </div>
        <p className="dc-footer-note">Educational research prototype · Results are not a substitute for professional medical assessment.</p>
      </div>

      {notice && <Notice message={notice} onDismiss={() => setNotice("")} />}

      {confirmDelete && (
        <div className="dc-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setConfirmDelete(false); }}>
          <section className="dc-modal" role="dialog" aria-modal="true" aria-labelledby="dc-delete-heading">
            <h2 id="dc-delete-heading">Delete saved prediction?</h2>
            <p>This bundled sample is a static preview. No user record will be deleted.</p>
            <div className="dc-modal-actions">
              <button className="dc-btn" type="button" onClick={() => setConfirmDelete(false)}>Cancel</button>
              <button className="dc-btn dc-btn-danger" type="button" onClick={() => { setConfirmDelete(false); setNotice("Static sample preview only—no record was deleted."); }}>Confirm delete</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
