#!/usr/bin/env python3
"""Build the shareable technical reference page from share/docs/*.md."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "share" / "docs"
OUT = ROOT / "share" / "polysil-technical-reference.html"

TITLES = {
    "01": ("Backend Architecture", "Stack, structure, auth, and the conventions every module follows"),
    "02": ("Database Schema", "105 tables, RLS patterns, indexes, migration order"),
    "03": ("Schema Corrections", "Stock, targets, payments, intake — added and fixed"),
    "04": ("Permissions & RBAC", "16 roles, five scopes, and the policy design"),
    "05": ("Module Design", "How each module behaves, end to end"),
    "06": ("Subsidy Calculation", "Three different models, one per system"),
    "07": ("WhatsApp Integration", "11za contract and the provider port"),
    "08": ("Acceptance Criteria", "What must be true before anything ships"),
    "09": ("Testing Strategy", "Layers, fixtures, gates"),
    "10": ("Feature Spec Template", "The handover document every feature starts with"),
    "11": ("Requirements Register", "Requirement IDs for traceability"),
    "12": ("Auth API Contract", "Six endpoints, the envelopes, and the screens they imply"),
}

CSS = """
:root{
  --paper:#F6F5F2; --raise:#FFFFFF; --sink:#EEEDE8;
  --ink:#171C1E; --ink-2:#41504F; --ink-3:#6B7A7C;
  --line:#DDDCD5; --line-2:#C9C8C0;
  --accent:#0E6E75; --accent-soft:#E2EFEF;
  --warn:#9E5A22; --warn-soft:#F6EDE1;
  --danger:#A03D2C; --danger-soft:#F7E8E4;
  --rail:280px;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#121618; --raise:#1A2023; --sink:#0D1113;
    --ink:#E2E6E5; --ink-2:#AFBCBB; --ink-3:#7D8C8C;
    --line:#252D30; --line-2:#333E41;
    --accent:#49AEB6; --accent-soft:#123034;
    --warn:#D69A55; --warn-soft:#2E2415;
    --danger:#D97A63; --danger-soft:#2E1A16;
  }
}
:root[data-theme="dark"]{
  --paper:#121618; --raise:#1A2023; --sink:#0D1113;
  --ink:#E2E6E5; --ink-2:#AFBCBB; --ink-3:#7D8C8C;
  --line:#252D30; --line-2:#333E41;
  --accent:#49AEB6; --accent-soft:#123034;
  --warn:#D69A55; --warn-soft:#2E2415;
  --danger:#D97A63; --danger-soft:#2E1A16;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Source Serif 4",Georgia,serif; font-size:17px; line-height:1.65;
  -webkit-font-smoothing:antialiased;
}
h1,h2,h3,h4,.ui{font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif}
code,pre,.mono{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace}

/* ---- shell ---- */
.wrap{display:grid; grid-template-columns:var(--rail) minmax(0,1fr); min-height:100vh}
.rail{
  border-right:1px solid var(--line); background:var(--sink);
  position:sticky; top:0; height:100vh; overflow-y:auto; padding:28px 0 40px;
}
.main{min-width:0; padding:0 0 120px}

/* ---- rail ---- */
.brand{padding:0 24px 22px; border-bottom:1px solid var(--line); margin-bottom:18px}
.brand h1{
  font-size:19px; line-height:1.25; margin:0 0 5px; letter-spacing:-.01em; font-weight:600;
}
.brand p{margin:0; font-size:12.5px; color:var(--ink-3); font-family:"IBM Plex Sans",sans-serif}
.navlabel{
  font-family:"IBM Plex Sans",sans-serif; font-size:10.5px; font-weight:600;
  letter-spacing:.13em; text-transform:uppercase; color:var(--ink-3);
  padding:0 24px; margin:0 0 10px;
}
.docnav{list-style:none; margin:0; padding:0 12px}
.docnav button{
  width:100%; text-align:left; background:none; border:0; cursor:pointer;
  display:grid; grid-template-columns:26px 1fr; gap:10px; align-items:baseline;
  padding:8px 12px; border-radius:5px; color:var(--ink-2);
  font-family:"IBM Plex Sans",sans-serif; font-size:13.5px; line-height:1.35;
}
.docnav button:hover{background:var(--raise); color:var(--ink)}
.docnav button[aria-current="true"]{background:var(--accent-soft); color:var(--accent); font-weight:600}
.docnav .n{
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3);
  font-variant-numeric:tabular-nums;
}
.docnav button[aria-current="true"] .n{color:var(--accent)}
.railfoot{padding:22px 24px 0; margin-top:20px; border-top:1px solid var(--line)}
.railfoot p{margin:0 0 8px; font-size:11.5px; color:var(--ink-3); font-family:"IBM Plex Sans",sans-serif; line-height:1.5}

/* ---- top bar ---- */
.bar{
  position:sticky; top:0; z-index:20; background:var(--paper);
  border-bottom:1px solid var(--line); padding:14px 48px;
  display:flex; align-items:center; gap:16px;
}
.bar .crumb{
  font-family:"IBM Plex Sans",sans-serif; font-size:13px; color:var(--ink-3); flex:1;
}
.bar .crumb b{color:var(--ink); font-weight:600}
.tbtn{
  border:1px solid var(--line-2); background:var(--raise); color:var(--ink-2);
  border-radius:5px; padding:5px 11px; cursor:pointer;
  font-family:"IBM Plex Sans",sans-serif; font-size:12px;
}
.tbtn:hover{color:var(--ink); border-color:var(--accent)}
.tbtn:focus-visible,.docnav button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}

/* ---- facts ---- */
.facts{
  display:grid; grid-template-columns:repeat(4,1fr); gap:0;
  border-bottom:1px solid var(--line); margin:0 0 8px;
}
.fact{padding:20px 48px 20px 0; border-right:1px solid var(--line)}
.fact:first-child{padding-left:48px}
.fact:last-child{border-right:0}
.fact b{
  display:block; font-family:"IBM Plex Sans",sans-serif; font-size:27px;
  font-weight:600; letter-spacing:-.02em; line-height:1.1; font-variant-numeric:tabular-nums;
}
.fact span{
  display:block; margin-top:3px; font-family:"IBM Plex Sans",sans-serif;
  font-size:11.5px; color:var(--ink-3); letter-spacing:.02em;
}

/* ---- doc body ---- */
.doc{padding:34px 48px 0; max-width:74ch}
.doc.hidden{display:none}
.doc>h1:first-child{
  font-size:30px; line-height:1.2; letter-spacing:-.022em; margin:0 0 6px;
  font-weight:600; text-wrap:balance;
}
.doc .sub{
  font-family:"IBM Plex Sans",sans-serif; font-size:14px; color:var(--ink-3);
  margin:0 0 30px; padding-bottom:20px; border-bottom:1px solid var(--line);
}
.doc h2{
  font-size:20px; letter-spacing:-.012em; margin:44px 0 12px; font-weight:600;
  text-wrap:balance; padding-top:14px; border-top:1px solid var(--line);
}
.doc h3{font-size:16px; margin:30px 0 8px; font-weight:600; text-wrap:balance}
.doc h4{font-size:14px; margin:22px 0 6px; font-weight:600; color:var(--ink-2)}
.doc p{margin:0 0 15px}
.doc ul,.doc ol{margin:0 0 15px; padding-left:22px}
.doc li{margin-bottom:5px}
.doc li::marker{color:var(--ink-3)}
.doc a{color:var(--accent); text-underline-offset:2px}
.doc strong{font-weight:600}
.doc hr{border:0; border-top:1px solid var(--line); margin:34px 0}

.doc code{
  background:var(--sink); border:1px solid var(--line); border-radius:3px;
  padding:.08em .34em; font-size:.855em;
}
.doc pre{
  background:var(--sink); border:1px solid var(--line); border-radius:6px;
  padding:15px 17px; overflow-x:auto; margin:0 0 18px; line-height:1.55;
}
.doc pre code{background:none; border:0; padding:0; font-size:12.6px}

.tablewrap{overflow-x:auto; margin:0 0 20px; border:1px solid var(--line); border-radius:6px}
.doc table{border-collapse:collapse; width:100%; font-size:13.5px;
  font-family:"IBM Plex Sans",sans-serif}
.doc th,.doc td{
  text-align:left; padding:9px 14px; border-bottom:1px solid var(--line);
  vertical-align:top; line-height:1.5;
}
.doc thead th{
  background:var(--sink); font-size:11px; font-weight:600; letter-spacing:.06em;
  text-transform:uppercase; color:var(--ink-3); white-space:nowrap;
}
.doc tbody tr:last-child td{border-bottom:0}
.doc td code{font-size:12px}

.doc blockquote{
  margin:0 0 20px; padding:14px 18px; border-left:3px solid var(--accent);
  background:var(--accent-soft); border-radius:0 5px 5px 0; font-size:15.5px;
}
.doc blockquote p:last-child{margin-bottom:0}

.doc>p:has(>strong:first-child)+ul{margin-top:-6px}

@media (max-width:1000px){
  :root{--rail:0px}
  .wrap{grid-template-columns:1fr}
  .rail{display:none}
  .bar,.doc{padding-left:22px; padding-right:22px}
  .facts{grid-template-columns:repeat(2,1fr)}
  .fact{padding:16px 20px}
  .fact:first-child{padding-left:22px}
  .fact:nth-child(2){border-right:0}
  .fact:nth-child(3){padding-left:22px; border-top:1px solid var(--line)}
  .fact:nth-child(4){border-top:1px solid var(--line)}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *{transition:none!important; animation:none!important}
}
"""

JS = """
const docs=[...document.querySelectorAll('.doc')];
const btns=[...document.querySelectorAll('.docnav button')];
const crumb=document.getElementById('crumb');
function show(id){
  docs.forEach(d=>d.classList.toggle('hidden',d.id!==id));
  btns.forEach(b=>b.setAttribute('aria-current',String(b.dataset.target===id)));
  const b=btns.find(x=>x.dataset.target===id);
  if(b) crumb.innerHTML='Technical Reference &nbsp;/&nbsp; <b>'+b.dataset.name+'</b>';
  document.querySelector('.main').scrollTo?.(0,0);
  window.scrollTo(0,0);
  try{localStorage.setItem('polysil-doc',id)}catch(e){}
}
btns.forEach(b=>b.addEventListener('click',()=>show(b.dataset.target)));
let start=btns[0].dataset.target;
try{const s=localStorage.getItem('polysil-doc'); if(s&&document.getElementById(s))start=s}catch(e){}
show(start);

const root=document.documentElement, tb=document.getElementById('theme');
function setTheme(t){root.setAttribute('data-theme',t); try{localStorage.setItem('polysil-theme',t)}catch(e){}}
try{const t=localStorage.getItem('polysil-theme'); if(t)root.setAttribute('data-theme',t)}catch(e){}
tb.addEventListener('click',()=>{
  const cur=root.getAttribute('data-theme')
    || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  setTheme(cur==='dark'?'light':'dark');
});

addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.metaKey||e.ctrlKey)return;
  const i=btns.findIndex(b=>b.getAttribute('aria-current')==='true');
  if(e.key===']'&&i<btns.length-1)show(btns[i+1].dataset.target);
  if(e.key==='['&&i>0)show(btns[i-1].dataset.target);
});
"""


def render(md_text: str) -> str:
    body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"]
    )
    # tables get their own scroll container
    body = re.sub(r"<table>", '<div class="tablewrap"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    return body


def main() -> None:
    parts, navs = [], []
    for path in sorted(SRC.glob("*.md")):
        num = path.name[:2]
        title, sub = TITLES.get(num, (path.stem, ""))
        did = f"doc-{num}"
        text = path.read_text(encoding="utf-8")
        # drop the file's own H1; the page supplies the title
        text = re.sub(r"\A#\s+[^\n]*\n", "", text)
        parts.append(
            f'<article class="doc hidden" id="{did}">'
            f"<h1>{html.escape(title)}</h1>"
            f'<p class="sub">{html.escape(sub)}</p>'
            f"{render(text)}</article>"
        )
        navs.append(
            f'<li><button data-target="{did}" data-name="{html.escape(title)}">'
            f'<span class="n">{num}</span><span>{html.escape(title)}</span></button></li>'
        )

    facts = [
        ("105", "tables"),
        ("3", "subsidy models"),
        ("16", "roles · 5 scopes"),
        ("37", "SQL checks passing"),
    ]
    factbar = "".join(
        f'<div class="fact"><b>{v}</b><span>{l}</span></div>' for v, l in facts
    )

    page = f"""<title>Polysil Irrigation Technical Reference</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <nav class="rail">
    <div class="brand">
      <h1>Polysil Irrigation</h1>
      <p>CRM &amp; Dealer Portal &mdash; technical reference</p>
    </div>
    <p class="navlabel">Documents</p>
    <ul class="docnav">{"".join(navs)}</ul>
    <div class="railfoot">
      <p>Read in order for the full picture. Each document stands alone if you need one answer.</p>
      <p class="mono" style="font-size:11px">[ and ] move between documents</p>
    </div>
  </nav>
  <div class="main">
    <header class="bar">
      <div class="crumb" id="crumb">Technical Reference</div>
      <button class="tbtn" id="theme">Theme</button>
    </header>
    <div class="facts">{factbar}</div>
    {"".join(parts)}
  </div>
</div>
<script>{JS}</script>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT}  ({len(page)/1024:.0f} KB, {len(navs)} documents)")


if __name__ == "__main__":
    main()
