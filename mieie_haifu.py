#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mieie 見える図面 ― 配布ツール(最小版)
  図面PDFを配布先ごとの個別リンクで渡し、誰がいつ開いたかを記録し、失効させられる。
  1日分の閲覧ログを1ファイルに書き出し、既存の刻印ツールでチェーンへ刻む。

依存: Python 3 標準ライブラリのみ(追加インストール不要)
起動: python3 mieie_haifu.py
"""
import http.server, socketserver, sqlite3, json, secrets, hashlib, os, sys, io, re, urllib.parse
from datetime import datetime, date
from email.parser import BytesParser
from email.policy import default as email_default
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
FILES = DATA / "files"
EXPORTS = DATA / "exports"
DB = DATA / "mieie.db"
CONFIG = BASE / "config.json"
PORT = 8787

APP_NAME = "Mieie 見える図面 ― 配布ツール"
OFFICE = "一級建築士事務所 有限会社 佐藤靖生建築研究室"

# ---------------------------------------------------------------- setup
def ensure_dirs():
    for d in (DATA, FILES, EXPORTS):
        d.mkdir(parents=True, exist_ok=True)

def load_config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg = {"admin_key": secrets.token_urlsafe(18), "office": OFFICE}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS documents(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          property TEXT NOT NULL, title TEXT NOT NULL,
          filename TEXT NOT NULL, stored TEXT NOT NULL,
          sha256 TEXT NOT NULL, size INTEGER NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recipients(
          token TEXT PRIMARY KEY, doc_id INTEGER NOT NULL,
          name TEXT NOT NULL, created TEXT NOT NULL, revoked_at TEXT,
          FOREIGN KEY(doc_id) REFERENCES documents(id));
        CREATE TABLE IF NOT EXISTS opens(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          token TEXT NOT NULL, ts TEXT NOT NULL, ip TEXT, ua TEXT,
          FOREIGN KEY(token) REFERENCES recipients(token));
        CREATE INDEX IF NOT EXISTS idx_opens_ts ON opens(ts);
        """)

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sha256_bytes(b: bytes) -> str:
    return "0x" + hashlib.sha256(b).hexdigest()

def esc(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;"))

# ---------------------------------------------------------------- HTML
CSS = """
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;background:#f4f2ec;color:#333}
header{background:#1a2b4a;color:#fff;padding:14px 22px}header h1{margin:0;font-size:18px}header .sub{font-size:12px;color:#aab8cc;margin-top:3px}
main{max-width:1040px;margin:22px auto;padding:0 16px}
.card{background:#fff;border:1px solid #e3e0d6;border-radius:10px;padding:18px 20px;margin-bottom:18px}
h2{font-size:16px;margin:0 0 12px;border-left:4px solid #2f6b45;padding-left:10px}
label{display:block;font-size:12px;color:#555;margin:10px 0 3px}
input[type=text],input[type=date]{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;font-size:14px}
.btn{display:inline-block;background:#2f6b45;color:#fff;border:0;border-radius:6px;padding:8px 14px;font-size:13px;cursor:pointer;text-decoration:none}
.btn.gray{background:#777}.btn.red{background:#a63b22}.btn.small{padding:4px 10px;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #eee;vertical-align:top}
th{background:#f7f5ef;font-weight:600;font-size:12px}
.mono{font-family:Menlo,monospace;font-size:11px;word-break:break-all}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#e6efe9;color:#2f6b45}.pill.off{background:#f6e3de;color:#a63b22}
.muted{color:#888;font-size:12px}.ok{color:#2f6b45}.err{color:#a63b22}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:200px}
.link{background:#f7f5ef;padding:6px 8px;border-radius:6px;font-size:12px;word-break:break-all}
"""

def page(title, body, extra_head=""):
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}</style>{extra_head}</head><body>
<header><h1>{esc(APP_NAME)}</h1><div class="sub">{esc(OFFICE)}</div></header>
<main>{body}</main></body></html>"""

def admin_page(cfg, base_url):
    key = cfg["admin_key"]
    with db() as con:
        docs = con.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
        rec_rows = con.execute("""SELECT r.*, d.title, d.property,
              (SELECT COUNT(*) FROM opens o WHERE o.token=r.token) AS n_open,
              (SELECT MAX(ts) FROM opens o WHERE o.token=r.token) AS last_open
              FROM recipients r JOIN documents d ON d.id=r.doc_id ORDER BY r.created DESC""").fetchall()
        recent = con.execute("""SELECT o.ts,o.ip,o.ua,r.name,d.title,d.property FROM opens o
              JOIN recipients r ON r.token=o.token JOIN documents d ON d.id=r.doc_id
              ORDER BY o.id DESC LIMIT 30""").fetchall()
    doc_opts = "".join(f'<option value="{d["id"]}">{esc(d["property"])} / {esc(d["title"])}</option>' for d in docs)

    docs_html = "".join(f"""<tr><td>{d["id"]}</td><td>{esc(d["property"])}</td><td>{esc(d["title"])}</td>
      <td class="mono">{esc(d["sha256"])}</td><td class="muted">{esc(d["created"])}</td></tr>""" for d in docs) or \
      '<tr><td colspan="5" class="muted">まだ図面がありません。上の欄からPDFを登録してください。</td></tr>'

    rec_html = ""
    for r in rec_rows:
        url = f"{base_url}/v/{r['token']}"
        status = '<span class="pill off">失効</span>' if r["revoked_at"] else '<span class="pill">有効</span>'
        btn = (f'<button class="btn small gray" onclick="unrevoke(\'{r["token"]}\')">再有効化</button>' if r["revoked_at"]
               else f'<button class="btn small red" onclick="revoke(\'{r["token"]}\')">失効させる</button>')
        rec_html += f"""<tr><td><strong>{esc(r["name"])}</strong><div class="muted">{esc(r["property"])} / {esc(r["title"])}</div></td>
          <td><div class="link" id="u-{r['token']}">{esc(url)}</div>
              <button class="btn small gray" onclick="copyU('{r['token']}')">コピー</button></td>
          <td>{r["n_open"]}回<div class="muted">{esc(r["last_open"] or "―")}</div></td>
          <td>{status}<div class="muted">{esc(r["created"])}</div></td><td>{btn}</td></tr>"""
    rec_html = rec_html or '<tr><td colspan="5" class="muted">配布先がまだありません。</td></tr>'

    recent_html = "".join(f"""<tr><td>{esc(o["ts"])}</td><td><strong>{esc(o["name"])}</strong></td>
      <td>{esc(o["property"])} / {esc(o["title"])}</td><td class="mono">{esc(o["ip"] or "")}</td>
      <td class="muted" style="max-width:260px">{esc((o["ua"] or "")[:80])}</td></tr>""" for o in recent) or \
      '<tr><td colspan="5" class="muted">まだ閲覧はありません。</td></tr>'

    today = date.today().isoformat()
    body = f"""
<div class="card"><h2>1. 図面を登録する</h2>
<form id="up" onsubmit="return upload(event)">
<div class="row"><div><label>物件名 *</label><input type="text" name="property" placeholder="例: 砂川邸" required></div>
<div><label>図面名 *</label><input type="text" name="title" placeholder="例: 床下換気 改修図 A-01" required></div></div>
<label>PDF *</label><input type="file" name="pdf" accept="application/pdf" required>
<div style="margin-top:12px"><button class="btn" type="submit">登録する</button> <span id="upmsg" class="muted"></span></div>
</form></div>

<div class="card"><h2>2. 配布先にリンクを発行する</h2>
<div class="row"><div><label>図面</label><select id="docsel" style="width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;font-size:14px">{doc_opts}</select></div>
<div><label>配布先の名前 *</label><input type="text" id="rname" placeholder="例: オリオン様 / 〇〇工務店様"></div></div>
<div style="margin-top:12px"><button class="btn" onclick="addRecipient()">リンクを発行</button> <span id="rmsg" class="muted"></span></div>
<p class="muted" style="margin-top:10px">発行されたリンクを、メール・LINE等で相手に送ってください。相手はリンクを開くだけで図面を見られます(登録・アプリ不要)。</p>
</div>

<div class="card"><h2>3. 配布先と閲覧状況</h2>
<table><tr><th>配布先</th><th>リンク</th><th>開封</th><th>状態</th><th></th></tr>{rec_html}</table></div>

<div class="card"><h2>4. 最近の閲覧(新しい順)</h2>
<table><tr><th>日時</th><th>配布先</th><th>図面</th><th>IP</th><th>端末</th></tr>{recent_html}</table></div>

<div class="card"><h2>5. 1日分の閲覧ログを書き出す(刻印用)</h2>
<div class="row"><div><label>日付</label><input type="date" id="expdate" value="{today}"></div>
<div style="align-self:flex-end"><button class="btn" onclick="doExport()">書き出す</button></div></div>
<div id="expmsg" style="margin-top:10px"></div>
<p class="muted">「刻印用_閲覧ログ_日付.json」を、刻印ツール(mieie_nft_tool.html)の「②記録をNFT化する」に入れて刻印してください。<br>
刻印用には配布先の名前・IP・端末は入っていません(ランダムなIDのみ)。名前入りの「_控え」は刻印しないでください。<br>
これで「その日の閲覧記録が、後から書き換えられていない」ことを誰でも検証できるようになります。</p></div>

<div class="card"><h2>登録済みの図面</h2>
<table><tr><th>#</th><th>物件</th><th>図面</th><th>SHA-256</th><th>登録</th></tr>{docs_html}</table></div>

<script>
const KEY="{key}";
async function upload(e){{e.preventDefault();const f=document.getElementById('up');const fd=new FormData(f);
 document.getElementById('upmsg').textContent='登録中…';
 const r=await fetch('/admin/'+KEY+'/upload',{{method:'POST',body:fd}});const j=await r.json();
 if(j.ok){{location.reload();}}else{{document.getElementById('upmsg').textContent='エラー: '+j.error;}}return false;}}
async function addRecipient(){{const doc_id=document.getElementById('docsel').value;const name=document.getElementById('rname').value.trim();
 if(!doc_id){{alert('先に図面を登録してください');return;}} if(!name){{alert('配布先の名前を入力してください');return;}}
 const r=await fetch('/admin/'+KEY+'/recipient',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{doc_id,name}})}});
 const j=await r.json(); if(j.ok) location.reload(); else document.getElementById('rmsg').textContent='エラー: '+j.error;}}
async function revoke(t){{if(!confirm('この配布先の閲覧権を失効させます。よろしいですか?'))return;
 await fetch('/admin/'+KEY+'/revoke',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:t}})}});location.reload();}}
async function unrevoke(t){{await fetch('/admin/'+KEY+'/unrevoke',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token:t}})}});location.reload();}}
function copyU(t){{const s=document.getElementById('u-'+t).textContent;navigator.clipboard.writeText(s).then(()=>alert('リンクをコピーしました'));}}
async function doExport(){{const d=document.getElementById('expdate').value;const r=await fetch('/admin/'+KEY+'/export?date='+d);const j=await r.json();
 const el=document.getElementById('expmsg');
 if(!j.ok){{el.innerHTML='<span class="err">'+j.error+'</span>';return;}}
 el.innerHTML='<div class="ok">書き出しました('+j.count+'件)</div>'+
  '<div style="margin-top:6px">刻印するファイル: <strong>'+j.file+'</strong></div>'+
  '<div class="mono" style="margin-top:4px">SHA-256: '+j.sha256+'</div>'+
  '<div class="muted" style="margin-top:6px">保存先: '+j.path+'</div>'+
  '<div class="muted" style="margin-top:4px">控え(名前入り・刻印しない): '+j.full_file+'</div>';}}
</script>"""
    return page(APP_NAME + " ― 管理", body)

VIEWER_HEAD = """<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
body{background:#2b2b2b}
#bar{background:#1a2b4a;color:#dfe6f0;font-size:12px;padding:8px 14px;position:sticky;top:0;z-index:5}
#bar b{color:#fff}
#pages{padding:14px}canvas{display:block;margin:0 auto 14px;max-width:100%;box-shadow:0 2px 12px rgba(0,0,0,.5);background:#fff}
#wm{position:fixed;inset:0;pointer-events:none;z-index:4;overflow:hidden}
#wm div{position:absolute;white-space:nowrap;color:rgba(160,40,40,.16);font-size:22px;font-weight:700;transform:rotate(-28deg);transform-origin:left top}
#note{color:#bbb;font-size:11px;text-align:center;padding:10px}
</style>"""

def viewer_page(rec, doc, opened_at):
    wm = f"{rec['name']}用 ／ 見える図面 ／ 閲覧 {opened_at}"
    # 透かしを画面全体に敷き詰める
    tiles = "".join(f'<div style="left:{x}px;top:{y}px">{esc(wm)}</div>'
                    for y in range(-100, 2200, 150) for x in range(-200, 1800, 560))
    body = f"""
<div id="bar"><b>{esc(doc['property'])} / {esc(doc['title'])}</b>　配布先: <b>{esc(rec['name'])}</b>　閲覧: {esc(opened_at)}
　<span style="opacity:.7">この図面は配布先ごとに個別に発行されています。閲覧は記録されます。</span></div>
<div id="wm">{tiles}</div>
<div id="pages"></div>
<div id="note">図面SHA-256: {esc(doc['sha256'])}　―　{esc(OFFICE)}</div>
<script>
document.addEventListener('contextmenu',e=>e.preventDefault());
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
const WM={json.dumps(wm, ensure_ascii=False)};
(async()=>{{
 const pdf=await pdfjsLib.getDocument('/f/{rec["token"]}').promise;
 const host=document.getElementById('pages');
 const scale=Math.min(1.6,(Math.min(window.innerWidth-40,1100))/595);
 for(let p=1;p<=pdf.numPages;p++){{
  const pg=await pdf.getPage(p);const vp=pg.getViewport({{scale}});
  const c=document.createElement('canvas');c.width=vp.width;c.height=vp.height;host.appendChild(c);
  const ctx=c.getContext('2d');await pg.render({{canvasContext:ctx,viewport:vp}}).promise;
  ctx.save();ctx.globalAlpha=.13;ctx.fillStyle='#a02828';ctx.font='bold 20px sans-serif';ctx.rotate(-28*Math.PI/180);
  for(let y=-c.height;y<c.height*2;y+=120)for(let x=-c.width;x<c.width*2;x+=520)ctx.fillText(WM,x,y);
  ctx.restore();
 }}
}})().catch(e=>{{document.getElementById('pages').innerHTML='<p style="color:#fff;text-align:center">図面を読み込めませんでした: '+e.message+'</p>';}});
</script>"""
    return page(f"{doc['property']} / {doc['title']}", body, VIEWER_HEAD)

def revoked_page(rec, doc):
    body = f"""<div class="card"><h2>この図面の閲覧権は失効しています</h2>
<p>{esc(doc['property'])} / {esc(doc['title'])}(配布先: {esc(rec['name'])})</p>
<p class="muted">配布元により閲覧が終了されました。必要な場合は配布元へお問い合わせください。</p></div>"""
    return page("閲覧権は失効しています", body)

# ---------------------------------------------------------------- handler
class H(http.server.BaseHTTPRequestHandler):
    cfg = None
    server_version = "MieieHaifu/0.1"

    def log_message(self, fmt, *args):  # 端末を静かに
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # helpers
    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def client_ip(self):
        # 中継(トンネル)が付ける「本当の接続元」の見出しを順に探す。
        # localhost.run は X_Forwarded_For(下線)で渡してくる(2026-09-26 公式ドキュメントで確認)
        for h in ("CF-Connecting-IP", "X-Forwarded-For", "X_Forwarded_For", "X-Real-IP"):
            v = self.headers.get(h)
            if v: return v.split(",")[0].strip()
        fwd = self.headers.get("Forwarded")
        if fwd:
            m = re.search(r'for="?\[?([^;,"\]]+)', fwd)
            if m: return m.group(1)
        return self.client_address[0]

    def base_url(self):
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("X_Forwarded_Host")
                or self.headers.get("Host") or f"localhost:{PORT}")
        tunnel = any(host.endswith(s) for s in (".lhr.life", ".localhost.run", ".trycloudflare.com", ".pinggy.link"))
        proto = (self.headers.get("X-Forwarded-Proto") or self.headers.get("X_Forwarded_Proto")
                 or ("https" if tunnel else "http"))
        return f"{proto}://{host}"

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def is_admin(self, key):
        return secrets.compare_digest(key, self.cfg["admin_key"])

    # routes
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); path = u.path; q = urllib.parse.parse_qs(u.query)
        m = re.fullmatch(r"/admin/([A-Za-z0-9_\-]+)", path)
        if m:
            if not self.is_admin(m.group(1)): return self.send(403, page("403", '<div class="card">管理キーが違います。</div>'))
            return self.send(200, admin_page(self.cfg, self.base_url()))
        m = re.fullmatch(r"/admin/([A-Za-z0-9_\-]+)/export", path)
        if m:
            if not self.is_admin(m.group(1)): return self.json({"ok":False,"error":"forbidden"},403)
            return self.export(q.get("date",[date.today().isoformat()])[0])
        m = re.fullmatch(r"/v/([A-Za-z0-9_\-]+)", path)
        if m: return self.view(m.group(1))
        m = re.fullmatch(r"/f/([A-Za-z0-9_\-]+)", path)
        if m: return self.file(m.group(1))
        if path == "/":
            return self.send(200, page(APP_NAME, '<div class="card"><h2>Mieie 見える図面 配布ツール</h2><p class="muted">配布先ごとに発行されたリンクからご覧ください。</p></div>'))
        self.send(404, page("404", '<div class="card">ページが見つかりません。</div>'))

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        m = re.fullmatch(r"/admin/([A-Za-z0-9_\-]+)/(upload|recipient|revoke|unrevoke)", path)
        if not m: return self.json({"ok":False,"error":"not found"},404)
        if not self.is_admin(m.group(1)): return self.json({"ok":False,"error":"forbidden"},403)
        act = m.group(2)
        try:
            if act == "upload": return self.upload()
            data = json.loads(self.read_body() or b"{}")
            if act == "recipient": return self.add_recipient(data)
            if act == "revoke": return self.set_revoked(data.get("token",""), now())
            if act == "unrevoke": return self.set_revoked(data.get("token",""), None)
        except Exception as e:
            return self.json({"ok":False,"error":str(e)},500)

    # actions
    def upload(self):
        ctype = self.headers.get("Content-Type","")
        raw = self.read_body()
        msg = BytesParser(policy=email_default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        fields, pdf, fname = {}, None, ""
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if part.get_filename():
                fname = part.get_filename(); pdf = part.get_payload(decode=True)
            else:
                fields[name] = part.get_payload(decode=True).decode("utf-8").strip()
        prop, title = fields.get("property",""), fields.get("title","")
        if not (prop and title and pdf): return self.json({"ok":False,"error":"物件名・図面名・PDFは必須です"},400)
        if not pdf.startswith(b"%PDF"): return self.json({"ok":False,"error":"PDFファイルではありません"},400)
        h = sha256_bytes(pdf)
        stored = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.pdf"
        (FILES / stored).write_bytes(pdf)
        with db() as con:
            con.execute("INSERT INTO documents(property,title,filename,stored,sha256,size,created) VALUES(?,?,?,?,?,?,?)",
                        (prop, title, fname, stored, h, len(pdf), now()))
        return self.json({"ok":True,"sha256":h})

    def add_recipient(self, data):
        doc_id = int(data.get("doc_id")); name = (data.get("name") or "").strip()
        if not name: return self.json({"ok":False,"error":"配布先の名前が空です"},400)
        token = secrets.token_urlsafe(12)
        with db() as con:
            if not con.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone():
                return self.json({"ok":False,"error":"図面が見つかりません"},404)
            con.execute("INSERT INTO recipients(token,doc_id,name,created) VALUES(?,?,?,?)", (token, doc_id, name, now()))
        return self.json({"ok":True,"token":token,"url":f"{self.base_url()}/v/{token}"})

    def set_revoked(self, token, ts):
        with db() as con:
            con.execute("UPDATE recipients SET revoked_at=? WHERE token=?", (ts, token))
        return self.json({"ok":True})

    def lookup(self, token):
        with db() as con:
            rec = con.execute("SELECT * FROM recipients WHERE token=?", (token,)).fetchone()
            if not rec: return None, None
            doc = con.execute("SELECT * FROM documents WHERE id=?", (rec["doc_id"],)).fetchone()
        return rec, doc

    def view(self, token):
        rec, doc = self.lookup(token)
        if not rec: return self.send(404, page("404", '<div class="card">このリンクは無効です。</div>'))
        if rec["revoked_at"]: return self.send(403, revoked_page(rec, doc))
        ts = now()
        with db() as con:
            con.execute("INSERT INTO opens(token,ts,ip,ua) VALUES(?,?,?,?)", (token, ts, self.client_ip(), self.headers.get("User-Agent","")[:300]))
        return self.send(200, viewer_page(rec, doc, ts))

    def file(self, token):
        rec, doc = self.lookup(token)
        if not rec or rec["revoked_at"]: return self.send(403, "forbidden", "text/plain")
        data = (FILES / doc["stored"]).read_bytes()
        return self.send(200, data, "application/pdf", {"Content-Disposition":"inline"})

    def export(self, d):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d): return self.json({"ok":False,"error":"日付の形式が不正です"},400)
        with db() as con:
            rows = con.execute("""SELECT o.ts,o.ip,o.ua,r.token,r.name,d.id AS doc_id,d.property,d.title,d.sha256
                FROM opens o JOIN recipients r ON r.token=o.token JOIN documents d ON d.id=r.doc_id
                WHERE substr(o.ts,1,10)=? ORDER BY o.ts""", (d,)).fetchall()
        entries = [dict(r) for r in rows]
        # (1) 控え ― 名前・IP・端末を含む完全な記録。手元に保管するだけ。刻印しない
        full = {"tool":"Mieie 見える図面 配布ツール","office":OFFICE,"date":d,"count":len(entries),"entries":entries,
                "note":"個人情報を含む控え。刻印には使わないこと"}
        full_name = f"閲覧ログ_{d}_控え.json"
        (EXPORTS / full_name).write_bytes(json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        # (2) 刻印用 ― ランダムな配布先ID・時刻・図面ハッシュだけ + ソルト。名前・IP・端末は入れない
        #     手元の対応表(DB)を消せば、チェーン上のハッシュは誰とも結びつかなくなる(削除請求と衝突しない)
        seal = {"tool":"Mieie 見える図面 配布ツール","date":d,"count":len(entries),
                "salt":secrets.token_hex(16),
                "entries":[{"recipient_id":e["token"],"ts":e["ts"],"doc_sha256":e["sha256"]} for e in entries]}
        blob = json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        fname = f"刻印用_閲覧ログ_{d}.json"; (EXPORTS / fname).write_bytes(blob)
        return self.json({"ok":True,"file":fname,"full_file":full_name,"path":str(EXPORTS / fname),
                          "count":len(entries),"sha256":sha256_bytes(blob)})

# ---------------------------------------------------------------- main
class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; allow_reuse_address = True

def main():
    ensure_dirs(); cfg = load_config(); init_db(); H.cfg = cfg
    print("=" * 64)
    print(f" {APP_NAME}")
    print("=" * 64)
    print(f" 管理画面(このMacから):  http://localhost:{PORT}/admin/{cfg['admin_key']}")
    print(f" データ保存先:            {DATA}")
    print()
    print(" 外部に公開するには、「公開する.command」をダブルクリック(または別のターミナルで)")
    print(f"   ssh -R 80:localhost:{PORT} nokey@localhost.run")
    print(" 表示された https://〜.lhr.life のアドレスが公開用です。")
    print(" 管理画面は  https://〜.lhr.life/admin/" + cfg["admin_key"])
    print(" ※ 公開アドレスは起動のたびに変わります。相手に送るリンクは公開後に発行してください。")
    print()
    print(" 終了: Control + C")
    print("=" * 64)
    with Srv(("0.0.0.0", PORT), H) as s:
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n停止しました。")

if __name__ == "__main__":
    main()
