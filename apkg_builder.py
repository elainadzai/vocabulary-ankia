"""Tạo file .apkg bằng thư viện chuẩn Python (sqlite3 + zipfile), không cần genanki."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile

FIELDS = ["Word", "Meaning", "POS", "Example", "ExampleVI", "IPA", "Synonym", "Antonym", "Tag"]

CSS = """
.card{font-family:'Segoe UI',Arial,sans-serif;font-size:20px;text-align:center;color:#f1f5f9;background:#0f172a;padding:18px 14px}
.nightMode .card{background:#0f172a}
.meaning{font-size:26px;font-weight:700;margin:10px 0 4px}
.pos{display:inline-block;font-size:14px;color:#fbbf24;border:1px solid #fbbf24;border-radius:999px;padding:1px 10px;margin-bottom:14px}
.row{display:flex;justify-content:center;align-items:center;gap:8px;margin:10px 0}
#typeans{font-family:'Courier New',monospace;font-size:26px;text-align:center;caret-color:#fbbf24;color:#f8fafc;background:#1e293b;border:2px solid #475569;border-radius:10px;padding:8px 6px;max-width:92%}
#typeans:focus{outline:none;border-color:#fbbf24}
#hint{font-size:22px;background:#1e293b;border:2px solid #475569;border-radius:10px;padding:6px 10px;cursor:pointer}
code#typeans,.typeGood{color:#4ade80}.typeBad{color:#f87171}.typeMissed{color:#fbbf24}
.word{font-size:34px;font-weight:700;color:#4ade80;margin-top:8px}
.ipa{color:#94a3b8;margin:2px 0 10px}
.ex{font-style:italic;margin:12px 0 2px}.exvi{color:#94a3b8;margin-bottom:10px}
.syn{font-size:16px;color:#cbd5e1;margin-top:6px}.syn b{color:#fbbf24}
a.gpt{display:inline-block;margin-top:12px;font-size:14px;color:#0f172a;background:#fbbf24;border-radius:8px;padding:5px 12px;text-decoration:none}
hr#answer{border:0;border-top:1px solid #334155;margin:14px 0}
"""

FRONT = """<div class="card">
<div class="meaning">{{Meaning}}</div>
{{#POS}}<div class="pos">{{POS}}</div>{{/POS}}
<div class="row">{{type:Word}}<span id="hint" title="Gợi ý 1 chữ">💡</span></div>
<span id="w" style="display:none">{{text:Word}}</span>
</div>
<script>
(function(){
  var w=(document.getElementById('w').textContent||'').trim();
  var i=document.getElementById('typeans');
  if(!i)return;
  i.style.width=(Math.max(w.length,3)+2)+'ch';
  i.setAttribute('autocomplete','off');i.setAttribute('spellcheck','false');
  var h=document.getElementById('hint');
  if(h){h.onclick=function(){
    var v=i.value,n=0;
    while(n<v.length&&n<w.length&&v[n].toLowerCase()===w[n].toLowerCase())n++;
    i.value=w.slice(0,Math.min(n+1,w.length));i.focus();
  };}
})();
</script>"""

BACK = """{{FrontSide}}
<hr id="answer">
<div class="card">
<div class="word">{{Word}}</div>
{{#IPA}}<div class="ipa">/{{IPA}}/</div>{{/IPA}}
{{#Example}}<div class="ex">{{Example}}</div>{{/Example}}
{{#ExampleVI}}<div class="exvi">{{ExampleVI}}</div>{{/ExampleVI}}
{{#Synonym}}<div class="syn"><b>Syn:</b> {{Synonym}}</div>{{/Synonym}}
{{#Antonym}}<div class="syn"><b>Ant:</b> {{Antonym}}</div>{{/Antonym}}
<a class="gpt" href="https://chatgpt.com/?q=Explain+{{text:Word}}">Ask ChatGPT</a>
</div>"""


def _csum(text: str) -> int:
    plain = re.sub(r"<[^>]*>", "", text)
    return int(hashlib.sha1(plain.encode("utf-8")).hexdigest()[:8], 16)


def _clean(v: object) -> str:
    return html.escape(re.sub(r"\s+", " ", str(v or "")).strip(), quote=False)


def build_apkg(deck_name: str, rows: list[dict], out_path: str | None = None) -> str:
    deck_name = (deck_name or "Anki Card Maker").strip() or "Anki Card Maker"
    now = int(time.time())
    ms = now * 1000
    model_id = ms
    deck_id = ms + 1
    out_path = out_path or os.path.join(tempfile.mkdtemp(), "my_deck.apkg")

    model = {
        str(model_id): {
            "id": model_id, "name": "Type the word (custom)", "type": 0, "mod": now, "usn": -1,
            "sortf": 0, "did": deck_id, "latexPre": "", "latexPost": "", "latexsvg": False,
            "css": CSS, "req": [[0, "any", [0, 1]]], "tags": [], "vers": [],
            "flds": [{"name": n, "ord": i, "sticky": False, "rtl": False, "font": "Arial", "size": 20, "media": []}
                     for i, n in enumerate(FIELDS)],
            "tmpls": [{"name": "Type word", "ord": 0, "qfmt": FRONT, "afmt": BACK, "bqfmt": "", "bafmt": "",
                       "did": None, "bfont": "", "bsize": 0}],
        }
    }
    base_deck = {"lrnToday": [0, 0], "revToday": [0, 0], "newToday": [0, 0], "timeToday": [0, 0],
                 "collapsed": False, "browserCollapsed": False, "desc": "", "dyn": 0, "conf": 1,
                 "extendNew": 0, "extendRev": 0, "usn": 0, "mod": now}
    decks = {"1": {**base_deck, "id": 1, "name": "Default"},
             str(deck_id): {**base_deck, "id": deck_id, "name": deck_name}}
    dconf = {"1": {"id": 1, "name": "Default", "replayq": True, "timer": 0, "maxTaken": 60, "usn": 0, "mod": 0,
                   "autoplay": True, "dyn": False,
                   "new": {"bury": False, "delays": [1, 10], "initialFactor": 2500, "ints": [1, 4, 0],
                           "order": 1, "perDay": 20, "separate": True},
                   "lapse": {"delays": [10], "leechAction": 0, "leechFails": 8, "minInt": 1, "mult": 0},
                   "rev": {"bury": False, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1, "maxIvl": 36500,
                           "minSpace": 1, "perDay": 100}}}
    conf = {"activeDecks": [1], "curDeck": 1, "newSpread": 0, "collapseTime": 1200, "timeLim": 0,
            "estTimes": True, "dueCounts": True, "curModel": str(model_id), "nextPos": 1,
            "sortType": "noteFld", "sortBackwards": False, "addToCur": True}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "collection.anki2")
        con = sqlite3.connect(db_path)
        con.executescript("""
CREATE TABLE col (id integer primary key, crt integer not null, mod integer not null, scm integer not null, ver integer not null, dty integer not null, usn integer not null, ls integer not null, conf text not null, models text not null, decks text not null, dconf text not null, tags text not null);
CREATE TABLE notes (id integer primary key, guid text not null, mid integer not null, mod integer not null, usn integer not null, tags text not null, flds text not null, sfld integer not null, csum integer not null, flags integer not null, data text not null);
CREATE TABLE cards (id integer primary key, nid integer not null, did integer not null, ord integer not null, mod integer not null, usn integer not null, type integer not null, queue integer not null, due integer not null, ivl integer not null, factor integer not null, reps integer not null, lapses integer not null, left integer not null, odue integer not null, odid integer not null, flags integer not null, data text not null);
CREATE TABLE revlog (id integer primary key, cid integer not null, usn integer not null, ease integer not null, ivl integer not null, lastIvl integer not null, factor integer not null, time integer not null, type integer not null);
CREATE TABLE graves (usn integer not null, type integer not null, oid integer not null);
CREATE INDEX ix_notes_usn on notes (usn); CREATE INDEX ix_cards_usn on cards (usn);
CREATE INDEX ix_revlog_usn on revlog (usn); CREATE INDEX ix_cards_nid on cards (nid);
CREATE INDEX ix_cards_sched on cards (did, queue, due); CREATE INDEX ix_revlog_cid on revlog (cid);
CREATE INDEX ix_notes_csum on notes (csum);
""")
        con.execute("INSERT INTO col VALUES (1,?,?,?,11,0,0,0,?,?,?,?,'{}')",
                    (now, ms, ms, json.dumps(conf), json.dumps(model), json.dumps(decks), json.dumps(dconf)))
        n = 0
        for r in rows:
            word = _clean(r.get("word"))
            if not word:
                continue
            vals = [word, _clean(r.get("meaning")), _clean(r.get("pos")), _clean(r.get("example")),
                    _clean(r.get("example_vi")), _clean(str(r.get("ipa") or "").strip("/ ")),
                    _clean(r.get("synonym")), _clean(r.get("antonym")), _clean(r.get("tag"))]
            nid, cid = ms + 1000 + n, ms + 500000 + n
            n += 1
            tag = re.sub(r"\s+", "_", vals[8]) if vals[8] else ""
            guid = hashlib.sha1(f"{deck_name}|{word}|{ms}".encode()).hexdigest()[:10]
            con.execute("INSERT INTO notes VALUES (?,?,?,?,-1,?,?,?,?,0,'')",
                        (nid, guid, model_id, now, f" {tag} " if tag else "", "\x1f".join(vals), word, _csum(word)))
            con.execute("INSERT INTO cards VALUES (?,?,?,0,?,-1,0,0,?,0,0,0,0,0,0,0,0,'')",
                        (cid, nid, deck_id, now, n))
        con.commit()
        con.close()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_path, "collection.anki2")
            z.writestr("media", "{}")
    return out_path
