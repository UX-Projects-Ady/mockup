#!/usr/bin/env python3
"""Compose policies-app.html: a single-page app merging the policies list and the
create-policy screen (shared sidebar, JS-router views, in-memory state).
Reads the two standalone files (which stay usable on their own) and rewrites their
navigation hand-offs to in-memory App calls. Re-run after editing either source."""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))
L = open(os.path.join(BASE, "current-policies-screen.html"), encoding="utf-8").read()
C = open(os.path.join(BASE, "create-policy.html"), encoding="utf-8").read()

def styles(html):
    return re.findall(r'<style>(.*?)</style>', html, re.S)

def grab(pattern, html, flags=re.S):
    m = re.search(pattern, html, flags)
    if not m: raise SystemExit("NOT FOUND: " + pattern[:60])
    return m.group(0)

# ---------- extract LIST pieces ----------
L_head = grab(r'<head>.*?</head>', L)
L_ribbon   = grab(r'<div class="ribbon">.*?</div>', L)
L_aside    = grab(r'<aside class="side">.*?</aside>', L)
L_collapse = grab(r'<div class="collapse" id="collapseBtn">.*?</div>', L)
L_top      = grab(r'<header class="top">.*?</header>', L)
L_main     = grab(r'<div class="main">.*?(?=<script)', L)
L_icons    = grab(r'<script>\s*window\.ICONS=.*?</script>', L)
L_runtime_inner = re.search(r'<script>/\* ===== Open Source.*?\n(.*?)</script>', L, re.S).group(1)

# SEED literal (moves into App)
SEED_LITERAL = re.search(r'const SEED = (\[.*?\]);', L_runtime_inner, re.S).group(1)

# ---------- extract CREATE pieces ----------
C_css  = styles(C)[1]                       # component + chrome css (style #2)
C_top  = grab(r'<header class="top">.*?</header>', C)
C_main = grab(r'<div class="main">.*?(?=<script)', C)
C_js   = re.findall(r'<script>(.*?)</script>', C, re.S)[-1]   # last (only) create script

# ---------- CSS: pull :root global, scope the rest under #view-create ----------
C_root = re.search(r':root\s*\{.*?\}', C_css, re.S).group(0)
C_rest = C_css.replace(C_root, "")
C_rest = re.sub(r'/\*.*?\*/', '', C_rest, flags=re.S)          # strip comments
C_rest = re.sub(r'(?<![\w.#*\-])\*\s*\{[^}]*\}', '', C_rest, count=1)   # drop *{}
C_rest = re.sub(r'(?<![\w.#\-])body\s*\{[^}]*\}', '', C_rest, count=1)  # drop bare body{}
C_rest = re.sub(r'(?<![\w.#\-])svg\s*\{[^}]*\}', '', C_rest, count=1)   # drop svg{}

def scope_css(css, scope):
    # split into top-level rules by brace depth
    rules, buf, depth = [], "", 0
    for ch in css:
        buf += ch
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                rules.append(buf); buf = ""
    if buf.strip(): rules.append(buf)
    out = []
    for r in rules:
        i = r.find('{')
        if i < 0:
            out.append(r); continue
        sel, body = r[:i].strip(), r[i:]
        if not sel or sel.startswith('@'):
            out.append(r); continue
        parts = []
        for p in [s.strip() for s in sel.split(',') if s.strip()]:
            m = re.match(r'^(body|html)((?:[.#:\[][^\s]*)?)', p)
            if m and m.group(0):
                lead = m.group(0); rest = p[len(lead):].strip()
                parts.append(lead + ' ' + scope + ((' ' + rest) if rest else ''))
            else:
                parts.append(scope + ' ' + p)
        out.append(', '.join(parts) + body)
    return '\n'.join(out)

C_scoped = scope_css(C_rest, '#view-create')

# ---------- transform LIST runtime ----------
r = L_runtime_inner
r = r.replace("const SEED = " + SEED_LITERAL + ";", "")   # SEED now lives in App
r = re.sub(r'let policies = SEED\.concat\(loadNew\(\).*?\);', 'const policies = window.App.policies;', r, flags=re.S)
r = re.sub(r'\(function\(\)\{ try\{ const q=new URLSearchParams.*?\}\)\(\);', '', r, flags=re.S)  # ?new ingest
r = re.sub(r'\(function\(\)\{ const ov=loadOverrides\(\);.*?\}\)\(\);', '', r, flags=re.S)        # overrides
r = re.sub(r"try\{ localStorage\.setItem\('kodem_edit_policy'.*?location\.href='create-policy\.html';",
           "App.showCreate(p);", r, flags=re.S)          # edit -> in-memory
r = re.sub(r'\nrender\(\);\s*$', '\nwindow.ListView={render:render};\n', r)  # expose, don't auto-run
L_runtime_new = "(function(){\n" + r + "\n})();"

# list Create button -> App.showCreate(null)
L_main = re.sub(r'onclick="try\{localStorage\.removeItem\(\'kodem_edit_policy\'\)\}catch\(e\)\{\};location\.href=\'create-policy\.html\'"',
                'onclick="App.showCreate(null)"', L_main)

# ---------- transform CREATE js ----------
c = C_js
# Popovers/modals are built at runtime and appended to document.body; since create
# CSS is scoped under #view-create, they must live inside that container to be styled.
c = c.replace("document.body.appendChild(",
              "(document.getElementById('view-create')||document.body).appendChild(")
c = c.replace("location.href='current-policies-screen.html?new='+encodeURIComponent(JSON.stringify(p));",
              "window.App.save(p);")
c = c.replace("document.getElementById('cancelBtn').onclick=()=>location.href='current-policies-screen.html';",
              "document.getElementById('cancelBtn').onclick=()=>window.App.showList();")
# replace the load-time init tail (setScope('all')... through the initEdit IIFE) with a reusable initForm
tail_re = re.compile(r"setScope\('all'\); renderConds\(\);.*?\}\)\(\);", re.S)
INIT_FORM = r"""
function initForm(ep){
  window._editId=null;
  nameInp.value='';
  var _d=document.getElementById('polDesc'); if(_d) _d.value='';
  attrTags=[]; if(typeof renderAttrTags==='function') renderAttrTags();
  if(typeof setAttr==='function') setAttr('Repository Name');
  containers=[{type:'os',conds:[]}];
  setScope('all'); outcome=''; setOutcome(''); renderConds();
  var cur=document.querySelector('#view-create .crumbs .cur');
  if(ep){
    window._editId = ep.id || null;
    if(cur) cur.textContent='Edit Policy';
    nameInp.value = ep.name||'';
    if(_d) _d.value = ep.description||'';
    if(ep.scope && ep.scope.type==='attr'){ setScope('spec'); if(typeof setAttr==='function') setAttr(ep.scope.attr||'Repository Name'); attrTags=(ep.scope.values||[]).slice(); renderAttrTags(); }
    else { setScope('all'); }
    if(ep.outcome) setOutcome(ep.outcome);
    if(Array.isArray(ep.conditions) && ep.conditions.length){
      var mapCond=function(x){ return {name:x.name, values:(x.values&&x.values.slice)?x.values.slice():x.values, only:x.only, ack: x.only?(x.ack!==false):true}; };
      containers = ep.conditions.map(function(g){ if(Array.isArray(g)){ return {type:'os', conds:g.map(mapCond)}; } return {type:(g.type||'os'), conds:(g.conds||[]).map(mapCond)}; });
      if(!containers.length) containers=[{type:'os',conds:[]}];
      renderConds();
    }
  } else if(cur){ cur.textContent='Create Policy'; }
  validate();
}
window.CreateView={initForm:initForm};
""".strip()
if not tail_re.search(c): raise SystemExit("create init tail not found")
c = tail_re.sub(INIT_FORM, c, count=1)
C_js_new = "(function(){\n" + c + "\n})();"

# create breadcrumb links -> App.showList()
C_top = C_top.replace("location.href='current-policies-screen.html'", "App.showList()")

# ---------- App router ----------
APP = """
<script>
window.App = {
  policies: __SEED__,
  editPolicy: null,
  showList: function(){
    document.getElementById('view-create').classList.remove('active');
    document.getElementById('view-list').classList.add('active');
    window.scrollTo(0,0);
    if(window.ListView) ListView.render();
  },
  showCreate: function(p){
    this.editPolicy = p || null;
    document.getElementById('view-list').classList.remove('active');
    document.getElementById('view-create').classList.add('active');
    window.scrollTo(0,0);
    if(window.CreateView) CreateView.initForm(this.editPolicy);
  },
  save: function(p){
    if(p && p.id){
      var i=this.policies.findIndex(function(x){return x.id===p.id;});
      if(i>=0){ this.policies[i]=Object.assign({}, this.policies[i], p); }
      else { this.policies.push(p); }
    } else { p.id='n'+Date.now(); this.policies.push(p); }
    this.showList();
  }
};
</script>
""".replace("__SEED__", SEED_LITERAL)

VIEW_CSS = "<style>\n" + C_root + "\n.view{display:none;} .view.active{display:block;}\n" + C_scoped + "\n</style>"

# ---------- assemble ----------
out = f"""<!DOCTYPE html>
<html lang="en">
{L_head[:-7]}
{VIEW_CSS}
</head>
<body>
{L_ribbon}
{L_aside}
{L_collapse}
<section id="view-list" class="view active">
{L_top}
{L_main}
</section>
<section id="view-create" class="view">
{C_top}
{C_main}
</section>
{L_icons}
{APP}
<script>{L_runtime_new}</script>
<script>{C_js_new}</script>
<script>App.showList();</script>
</body>
</html>
"""

open(os.path.join(BASE, "policies-app.html"), "w", encoding="utf-8").write(out)
print("wrote policies-app.html", len(out), "bytes")
