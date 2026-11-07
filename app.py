"""Acente ekranı: Kasko Hasar Ön Değerlendirme Asistanı (prototip).

  .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import date, datetime

import streamlit as st
import yaml

from src.kasko import police as police_mod
from src.kasko.arama import _model, koleksiyon, kucult
from src.kasko.belgeler import ROOT, ayarlar
from src.kasko.degerlendirme import baslangic, graf, yeniden_baslangic
from src.kasko.rapor import rapor_pdf
from src.kasko.sunum import (ETIKET, ID_ETIKETI, KISA, atif_numaralari, kontrol_adi, olay_satirlari, temiz,
                             tr_tarih, urun_adi)

st.set_page_config(page_title="Hasar Ön Değerlendirme", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="auto")

# ============================================================================================ görünüm
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{
  --ink:#0F172A; --ink2:#334155; --muted:#64748B; --line:#E2E8F0; --soft:#F1F5F9; --bg:#F5F7FA; --card:#FFFFFF;
  --navy:#0B1F3A; --teal:#0F766E; --teal2:#14B8A6; --tealbg:#F0FDFA;
  --ok:#15803D; --okbg:#F0FDF4; --okln:#BBF7D0;
  --bad:#B91C1C; --badbg:#FEF2F2; --badln:#FECACA;
  --warn:#B45309; --warnbg:#FFFBEB; --warnln:#FDE68A;
  --info:#1D4ED8; --infobg:#EFF6FF; --infoln:#BFDBFE;
}
html, body, [class*="css"], .stMarkdown, .stTextArea textarea, .stButton button, .stSelectbox, .stRadio, input {
  font-family:'Inter', system-ui, -apple-system, sans-serif !important;
}
#MainMenu, footer, [data-testid="stDecoration"] {visibility:hidden; height:0;}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.6rem; padding-bottom:3rem; max-width:1240px;}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid var(--line);}
[data-testid="stSidebar"] .block-container {padding-top:1.2rem;}

/* --- marka --- */
.brand {display:flex; gap:.7rem; align-items:center; margin:0 0 1.1rem 0;}
.brand-logo {width:40px; height:40px; border-radius:11px; display:grid; place-items:center; color:#fff; font-weight:800;
  background:linear-gradient(135deg,var(--navy),var(--teal)); box-shadow:0 6px 16px rgba(15,118,110,.25); font-size:1.05rem;}
.brand-t {font-weight:750; color:var(--ink); line-height:1.15; font-size:1rem;}
.brand-s {color:var(--muted); font-size:.76rem; letter-spacing:.02em;}
.side-h {font-size:.7rem; font-weight:700; color:var(--muted); letter-spacing:.08em; text-transform:uppercase; margin:.9rem 0 .45rem;}

/* --- poliçe kartı --- */
.pcard {border:1px solid var(--line); border-radius:14px; padding:14px 14px 10px; background:linear-gradient(180deg,#FFFFFF, #FBFCFE);}
.pcard-top {display:flex; justify-content:space-between; align-items:flex-start; gap:.5rem;}
.pname {font-weight:700; font-size:1.02rem; color:var(--ink);}
.pmeta {color:var(--muted); font-size:.78rem; margin-top:2px;}
.prow {display:flex; justify-content:space-between; gap:.6rem; padding:7px 0; border-top:1px dashed var(--line); font-size:.82rem;}
.prow:first-of-type {border-top:none;}
.prow .k {color:var(--muted);} .prow .v {color:var(--ink); font-weight:600; text-align:right;}
.badge {display:inline-flex; align-items:center; gap:.3rem; padding:2px 9px; border-radius:999px; font-size:.72rem; font-weight:650;
  border:1px solid transparent; white-space:nowrap;}
.b-ok {background:var(--okbg); color:var(--ok); border-color:var(--okln);}
.b-bad {background:var(--badbg); color:var(--bad); border-color:var(--badln);}
.b-warn {background:var(--warnbg); color:var(--warn); border-color:var(--warnln);}
.b-info {background:var(--infobg); color:var(--info); border-color:var(--infoln);}
.b-mute {background:var(--soft); color:var(--ink2); border-color:var(--line);}
.chips {display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;}
.tgrid {display:grid; grid-template-columns:1fr 1fr; gap:5px;}
.tem {font-size:.76rem; padding:5px 8px; border-radius:8px; display:flex; align-items:center; gap:6px; border:1px solid var(--line);}
.tem.on {background:var(--tealbg); border-color:#99F6E4; color:#115E59; font-weight:600;}
.tem.off {background:#FAFAFA; color:#94A3B8; text-decoration:line-through;}
.side-foot {color:var(--muted); font-size:.7rem; line-height:1.45; margin-top:1rem; padding-top:.8rem; border-top:1px solid var(--line);}

/* --- başlık --- */
.hero {border-radius:18px; padding:22px 26px; color:#fff; margin-bottom:1.1rem;
  background:radial-gradient(1200px 300px at 85% -40%, rgba(20,184,166,.55), transparent 60%),
             linear-gradient(120deg,#0B1F3A 0%, #12355B 55%, #0F766E 120%);
  box-shadow:0 12px 30px rgba(11,31,58,.18);}
.hero h1 {font-size:1.55rem; font-weight:800; margin:0 0 .25rem; color:#fff; letter-spacing:-.01em;}
.hero p {margin:0; color:#CBD5E1; font-size:.92rem; max-width:760px;}
.hero-steps {display:flex; gap:.5rem; flex-wrap:wrap; margin-top:.9rem;}
.hero-steps span {background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); color:#E2E8F0; font-size:.74rem;
  padding:3px 10px; border-radius:999px;}

/* --- kart --- */
.card {background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px 20px; box-shadow:0 1px 2px rgba(15,23,42,.04);}
.card-h {display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-bottom:.7rem;}
.card-t {font-weight:700; font-size:.98rem; color:var(--ink); display:flex; align-items:center; gap:.5rem;}
.card-t .n {width:24px; height:24px; border-radius:7px; background:var(--soft); display:grid; place-items:center; font-size:.75rem; color:var(--ink2);}
.sub {color:var(--muted); font-size:.8rem;}
.lbl {font-size:.78rem; font-weight:650; color:var(--ink2); margin:.2rem 0 .35rem;}

/* --- etiket bandı --- */
.verdict {border-radius:16px; padding:18px 22px; display:flex; gap:16px; align-items:center; border:1px solid; margin:.4rem 0 1rem;}
.verdict .ic {width:48px; height:48px; flex:0 0 48px; border-radius:14px; display:grid; place-items:center; font-size:1.4rem; font-weight:800; color:#fff;}
.verdict .t {font-size:1.25rem; font-weight:800; letter-spacing:.01em;}
.verdict .d {font-size:.88rem; margin-top:2px; color:var(--ink2);}
.verdict .meta {display:flex; flex-wrap:wrap; gap:6px; margin-top:9px;}
.v-kapsamda {background:linear-gradient(90deg,var(--okbg),#fff); border-color:var(--okln);} .v-kapsamda .ic{background:var(--ok);} .v-kapsamda .t{color:var(--ok);}
.v-kapsam_disi {background:linear-gradient(90deg,var(--badbg),#fff); border-color:var(--badln);} .v-kapsam_disi .ic{background:var(--bad);} .v-kapsam_disi .t{color:var(--bad);}
.v-uzman {background:linear-gradient(90deg,var(--warnbg),#fff); border-color:var(--warnln);} .v-uzman .ic{background:#D97706;} .v-uzman .t{color:var(--warn);}
.v-ek_bilgi {background:linear-gradient(90deg,var(--infobg),#fff); border-color:var(--infoln);} .v-ek_bilgi .ic{background:var(--info);} .v-ek_bilgi .t{color:var(--info);}

/* --- kontrol satırları --- */
.chk {display:flex; gap:12px; padding:11px 12px; border-radius:12px; border:1px solid var(--line); margin-bottom:8px; background:#fff;}
.chk .ic {width:26px; height:26px; flex:0 0 26px; border-radius:8px; display:grid; place-items:center; font-weight:800; font-size:.8rem;}
.chk .t {font-weight:650; font-size:.88rem; color:var(--ink);}
.chk .m {font-size:.82rem; color:var(--ink2); margin-top:2px; line-height:1.45;}
.chk .src {margin-top:6px; display:flex; gap:5px; flex-wrap:wrap;}
.c-uygun .ic {background:var(--okbg); color:var(--ok); border:1px solid var(--okln);}
.c-sorun {border-color:var(--badln); background:linear-gradient(90deg,#FFF7F7,#fff);} .c-sorun .ic {background:var(--bad); color:#fff;}
.c-belirsiz {border-color:var(--warnln); background:linear-gradient(90deg,#FFFCF0,#fff);} .c-belirsiz .ic {background:#F59E0B; color:#fff;}
.c-bilgi .ic {background:var(--infobg); color:var(--info); border:1px solid var(--infoln);}
.srcpill {font-size:.68rem; color:var(--teal); background:var(--tealbg); border:1px solid #99F6E4; padding:1px 7px; border-radius:6px; font-weight:600;}

/* --- not ve atıflar --- */
.note {font-size:.95rem; line-height:1.7; color:var(--ink);}
.ref {display:inline-grid; place-items:center; min-width:19px; height:19px; padding:0 5px; margin:0 1px; border-radius:6px; font-size:.68rem;
  font-weight:700; color:#fff; background:var(--teal); vertical-align:2px;}
.quote {border-left:3px solid var(--teal2); background:var(--tealbg); padding:8px 12px; border-radius:0 10px 10px 0; font-size:.86rem; color:#134E4A;}
.full {font-size:.84rem; color:var(--ink2); line-height:1.6; background:#FAFBFC; border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-top:8px;}
mark {background:#FEF08A; padding:0 2px; border-radius:3px;}
.disclaimer {display:flex; gap:10px; align-items:center; color:var(--ink2); font-size:.8rem; background:#fff; border:1px dashed #CBD5E1;
  border-radius:12px; padding:10px 14px; margin-top:1.2rem;}

/* --- şeffaflık tablosu --- */
table.tr {width:100%; border-collapse:collapse; font-size:.82rem;}
table.tr td, table.tr th {padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top;}
table.tr th {color:var(--muted); font-weight:600; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em;}
.q {color:#0F766E; font-style:italic;}

/* --- streamlit bileşenleri --- */
.stTextArea textarea {border-radius:12px !important; font-size:.95rem !important; line-height:1.55 !important;}
.stButton button {border-radius:10px !important; font-weight:600 !important;}
.stButton button[kind="secondary"] {background:#fff; border:1px solid var(--line); color:var(--ink2); font-size:.8rem !important;
  padding:.25rem .7rem !important; min-height:0 !important;}
.stButton button[kind="secondary"]:hover {border-color:var(--teal2); color:var(--teal);}
.stButton button[kind="primary"] {background:linear-gradient(135deg,#0F766E,#0D9488) !important; border:none !important;
  box-shadow:0 6px 16px rgba(15,118,110,.25);}
.stButton button[kind="primary"]:disabled {background:#E2E8F0 !important; color:#94A3B8 !important; box-shadow:none;}
[data-testid="stExpander"] details {border-radius:12px !important; border:1px solid var(--line) !important; background:#fff;}
[data-testid="stExpander"] summary p {font-weight:600; font-size:.88rem;}
div[data-testid="stStatusWidget"] {display:none;}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] .kart-isaret) {
  background:#fff; border:1px solid var(--line) !important; border-radius:16px !important; padding:6px 8px;
  box-shadow:0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.04);}
.kart-isaret {display:none;}
.sec-h {display:flex; justify-content:space-between; align-items:flex-end; margin:.4rem 0 .8rem;}
.sec-t {font-weight:750; font-size:1.15rem; color:var(--ink);}
.mk-top {display:flex; gap:12px; align-items:center; margin:2px 0 10px;}
.avatar {width:42px; height:42px; border-radius:12px; display:grid; place-items:center; color:#fff; font-weight:750; font-size:.95rem;}
.mk-chips {min-height:56px; align-content:flex-start;}
.mk-car {font-size:.84rem; color:var(--ink2); margin-bottom:8px;}
.mk-alt {font-size:.74rem; color:var(--muted); margin:10px 0 2px; padding-top:8px; border-top:1px dashed var(--line);}
.steps {display:flex; flex-direction:column; gap:7px; font-size:.82rem; color:var(--ink2);}
.steps b {display:inline-grid; place-items:center; width:20px; height:20px; border-radius:6px; background:var(--tealbg);
  color:var(--teal); font-size:.72rem; margin-right:8px; border:1px solid #99F6E4;}
[data-testid="stProgress"] p {font-size:.8rem; font-weight:600; color:var(--ink2);}
.stDownloadButton button {border-radius:10px !important; font-weight:650 !important; background:linear-gradient(135deg,#0F766E,#0D9488) !important;
  color:#fff !important; border:none !important; box-shadow:0 6px 16px rgba(15,118,110,.25); min-height:2.8rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ============================================================================================ veri ve yardımcılar
DURUM_IC = {"uygun": "✓", "sorun": "✕", "belirsiz": "?", "bilgi": "i"}
ADIMLAR = {"olay_cikar": "İhbar yapılandırıldı", "police_kontrol": "Poliçe kontrolleri yapıldı",
           "ara": "İlgili şart maddeleri bulundu", "yaz": "Ön değerlendirme notu yazıldı", "denetle": "Otomatik denetim"}
ADIM_KIM = {"olay_cikar": "Haiku", "police_kontrol": "kod", "ara": "hibrit arama", "yaz": "Haiku", "denetle": "kod"}
ORNEK_AD = {
    "mehmet_sel_park": "Sel · park hâlinde", "mehmet_sel_tarihsiz": "Sel · tarih yok", "mehmet_deprem": "Deprem",
    "ayse_deprem": "Deprem", "mehmet_yangin": "Yangın", "zeynep_calinma": "Çalınma", "ayse_anahtar": "Anahtarla çalınma",
    "ayse_kotu_niyet": "Vandalizm", "burak_dolu": "Dolu", "ayse_dolu": "Dolu", "ali_lpg": "Arkadan çarpma",
    "elif_suresi_dolmus": "3 Kasım · sürtme", "elif_bitis_gunu": "Bitiş günü · sürtme", "burak_kardes": "Kardeşi kullanıyordu",
    "burak_esi": "Eşi kullanıyordu", "ayse_alkol_terk": "Alkol + yeri terk", "ayse_ehliyetsiz": "Ehliyetsiz sürücü",
    "ayse_sel_surerken": "Sel · sürerken", "ayse_carpip_kacma_tarihsiz": "Çarpıp kaçma", "zeynep_cam": "Taş sıçraması",
}
def e(metin) -> str:
    """HTML kaçışı + PDF'ten gelen özel glifler yerine ayraç."""
    return html.escape(temiz(metin))


@st.cache_resource(show_spinner="Arama dizini ve model hazırlanıyor (ilk açılış ~20 sn)…")
def hazirla():
    _model()
    koleksiyon()
    return graf()


@st.cache_data
def ornekler() -> list[dict]:
    return yaml.safe_load((ROOT / "eval" / "senaryolar.yaml").read_text(encoding="utf-8"))


def html_blok(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def kart_basligi(no: int, baslik: str, sag: str = "") -> None:
    """st.container(border=True) içinde çağrılır; içerdiği işaret sayesinde CSS o container'ı kart yapar."""
    html_blok(f'<span class="kart-isaret"></span><div class="card-h"><div class="card-t"><span class="n">{no}</span>'
              f'{baslik}</div><div class="sub">{sag}</div></div>')


# ============================================================================================ oturum
ss = st.session_state
ss.setdefault("sonuc", None)
ss.setdefault("tur_id", 0)
ss.setdefault("ihbar", "")

def musteri_sec(no: str) -> None:
    ss.police_no, ss.sonuc, ss.ihbar = no, None, ""


def ana_ekran() -> None:
    ss.police_no, ss.sonuc, ss.ihbar = None, None, ""


def durum_rozetleri(p: dict, gun: date) -> list[str]:
    bitti = date.fromisoformat(p["bitis"]) < gun
    r = [f'<span class="badge {"b-bad" if bitti else "b-ok"}">{"Sona erdi" if bitti else "Aktif"}</span>']
    if p["muafiyet_tl"]:
        r.append(f'<span class="badge b-warn">Muafiyet {p["muafiyet_tl"]:,} TL</span>'.replace(",", "."))
    if p["yetkili_surucu"] != "Sınırsız":
        r.append('<span class="badge b-warn">Sürücü kısıtı</span>')
    if "LPG" in p["arac"]["yakit"].upper() and not p.get("lpg_beyan_edildi", True):
        r.append('<span class="badge b-warn">LPG beyansız</span>')
    return r


MARKA = ('<div class="brand"><div class="brand-logo">HÖ</div><div><div class="brand-t">Hasar Ön Değerlendirme</div>'
         '<div class="brand-s">Acente asistanı · prototip</div></div></div>')
ALT_NOT = ('<div class="side-foot">Bağımsız prototip. Müşteri ve poliçe verileri <b>sentetiktir</b>; şart metinleri TSB '
           'Kasko Genel Şartları ile Referans Sigorta\'nın yayımlanmış özel şartlarından alınmıştır.</div>')
RENKLER = ["#0F766E", "#1D4ED8", "#7C3AED", "#B45309", "#BE123C", "#0E7490"]
ss.setdefault("police_no", None)
policeler = police_mod.policeler()
POLICE = {x["police_no"]: x for x in policeler}
bugun = ss.get("ihbar_tarihi", date.today())

# ============================================================================================ ana ekran: müşteri seçimi
if not ss.police_no:
    with st.sidebar:
        html_blok(MARKA)
        html_blok('<div class="side-h">Nasıl çalışır</div><div class="steps">'
                  '<div><b>1</b>Müşteriyi seçin</div><div><b>2</b>İhbarı olduğu gibi yazın</div>'
                  '<div><b>3</b>Kontrolleri ve kaynaklı notu inceleyin</div><div><b>4</b>Eksik bilgileri cevaplayın</div>'
                  '<div><b>5</b>Evrakları işaretleyip raporu indirin</div></div>')
        html_blok(ALT_NOT)
    html_blok('<div class="hero"><h1>Hasar İhbarı Ön Değerlendirme</h1>'
              '<p>Müşterinin anlattığını olduğu gibi yazın. Asistan olayı yapılandırır, poliçeyi kontrol eder, ilgili şart '
              'maddelerini bulur, eksik bilgileri size sorar ve kaynaklı bir rapor hazırlar. Karar her zaman hasar '
              'uzmanınındır.</p><div class="hero-steps"><span>① İhbarı yapılandır</span><span>② Poliçeyi kontrol et</span>'
              '<span>③ Şartları bul</span><span>④ Kaynaklı not yaz</span><span>⑤ Denetle</span><span>⑥ Rapor</span></div></div>')
    html_blok(f'<div class="sec-h"><div><div class="sec-t">Müşteri seçin</div><div class="sub">Portföydeki {len(policeler)} '
              'kasko poliçesi · ihbar almak istediğiniz müşteriye tıklayın</div></div></div>')
    kol = st.columns(3, gap="medium")
    for i, p in enumerate(policeler):
        a = p["arac"]
        bas = "".join(x[0] for x in p["sigortali"]["ad"].split()[:2])
        ornek_sayisi = sum(o["police_no"] == p["police_no"] for o in ornekler())
        with kol[i % 3], st.container(border=True):
            html_blok(
                f'<span class="kart-isaret"></span><div class="mk-top"><div class="avatar" style="background:{RENKLER[i % 6]}">'
                f'{e(bas)}</div><div style="flex:1"><div class="pname">{e(p["sigortali"]["ad"])}</div>'
                f'<div class="pmeta">{e(p["sigortali"]["il"])} · {e(p["police_no"])}</div></div></div>'
                f'<div class="mk-car">🚗 {e(a["marka"])} {e(a["model"])} · {a["yil"]} · {e(a["plaka"])}</div>'
                f'<div class="chips mk-chips"><span class="badge b-info">{e(urun_adi(p["urun"]))}</span>'
                f'<span class="badge b-mute">{e(p["kasko_turu"])}</span>{"".join(durum_rozetleri(p, bugun))}</div>'
                f'<div class="mk-alt">{len(p["teminatlar"])} teminat · {ornek_sayisi} örnek ihbar</div>')
            st.button("İhbar al  →", key=f"sec_{p['police_no']}", on_click=musteri_sec, args=(p["police_no"],),
                      use_container_width=True)
    html_blok('<div class="disclaimer">🛡️ <span>Bu araç bir <b>ön değerlendirme</b> asistanıdır; teminat kararı vermez. '
              'Nihai karar, dosyayı inceleyen hasar uzmanınındır.</span></div>')
    st.stop()

# ============================================================================================ yan panel (seçili müşteri)
p = POLICE[ss.police_no]
with st.sidebar:
    html_blok(MARKA)
    st.button("←  Müşteri listesi", on_click=ana_ekran, use_container_width=True)
    bitti = date.fromisoformat(p["bitis"]) < bugun
    a = p["arac"]
    lpg_uyari = (' <span class="badge b-warn">LPG beyansız</span>'
                 if "LPG" in a["yakit"].upper() and not p.get("lpg_beyan_edildi", True) else "")
    satir = lambda k, v: f'<div class="prow"><span class="k">{k}</span><span class="v">{v}</span></div>'
    html_blok(
        f'<div class="pcard"><div class="pcard-top"><div><div class="pname">{e(p["sigortali"]["ad"])}</div>'
        f'<div class="pmeta">{e(p["police_no"])} · {e(p["sigortali"]["il"])}</div></div>'
        f'<span class="badge {"b-bad" if bitti else "b-ok"}">{"Sona erdi" if bitti else "Aktif"}</span></div>'
        f'<div style="margin-top:10px">'
        + satir("Ürün", e(urun_adi(p["urun"])))
        + satir("Tür", f'<span class="badge b-mute">{e(p["kasko_turu"])}</span>')
        + satir("Araç", f'{e(a["marka"])} {e(a["model"])} · {a["yil"]}')
        + satir("Plaka / yakıt", f'{e(a["plaka"])} · {e(a["yakit"])}{lpg_uyari}')
        + satir("Dönem", f'{tr_tarih(p["baslangic"])} – {tr_tarih(p["bitis"])}')
        + satir("Muafiyet", f'{p["muafiyet_tl"]:,} TL'.replace(",", ".") if p["muafiyet_tl"] else "Yok")
        + satir("Yetkili sürücü", e(p["yetkili_surucu"]))
        + '</div></div>')
    html_blok('<div class="side-h">Paketler</div><div class="chips">'
              + "".join(f'<span class="badge b-info">{e(x)}</span>' for x in p["paketler"]) + '</div>')
    html_blok('<div class="side-h">Teminatlar</div><div class="tgrid">'
              + "".join(f'<div class="tem {"on" if k in p["teminatlar"] else "off"}">{"✓" if k in p["teminatlar"] else "–"} {e(v)}</div>'
                        for k, v in KISA.items() if k != "DIGER") + '</div>')
    html_blok(ALT_NOT)

# ============================================================================================ başlık + ihbar
html_blok('<div class="hero"><h1>Hasar İhbarı Ön Değerlendirme</h1>'
          '<p>Müşterinin anlattığını olduğu gibi yazın. Asistan olayı yapılandırır, poliçeyi kontrol eder, ilgili şart '
          'maddelerini bulur, eksik bilgileri size sorar. Karar her zaman hasar uzmanınındır.</p>'
          '<div class="hero-steps"><span>① İhbarı yapılandır</span><span>② Poliçeyi kontrol et</span>'
          '<span>③ Şartları bul</span><span>④ Kaynaklı not yaz</span><span>⑤ Denetle</span></div></div>')


def ornek_sec(metin: str) -> None:
    ss.ihbar, ss.sonuc = metin, None


with st.container(border=True):
    kart_basligi(1, "Müşterinin ihbarı", f'{e(p["sigortali"]["ad"])} adına')
    musteri_ornekleri = [o for o in ornekler() if o["police_no"] == p["police_no"]]
    if musteri_ornekleri:
        html_blok('<div class="lbl">Hazır örnekler</div>')
        kol = st.columns(min(len(musteri_ornekleri), 5) or 1)
        for i, o in enumerate(musteri_ornekleri):
            kol[i % len(kol)].button(ORNEK_AD.get(o["id"], o["id"]), key=f"ornek_{o['id']}", use_container_width=True,
                                     on_click=ornek_sec, args=(o["ihbar"],))
    st.text_area("İhbar metni", key="ihbar", height=110, label_visibility="collapsed",
                 placeholder="Ör. “Dün akşam kavşakta önümdeki araç ani fren yaptı, arkadan çarptım…”")
    k1, k2, k3 = st.columns([1.1, 1, 1.4])
    k1.date_input("İhbar tarihi", key="ihbar_tarihi", value=date.today(), format="DD.MM.YYYY",
                  help="'Dün', 'geçen cuma' gibi ifadeler bu tarihe göre hesaplanır.")
    with k3:
        st.write("")
        calistir = st.button("Değerlendir  →", type="primary", use_container_width=True)


# ============================================================================================ akış (canlı adımlar)
def akis(durum: dict, baslik: str) -> dict | None:
    g = hazirla()
    son, gorulen, t0 = None, 0, time.time()
    with st.status(baslik, expanded=True) as kutu:
        try:
            for s in g.stream(durum, stream_mode="values"):
                son = s
                for satir_ in s.get("iz", [])[gorulen:]:
                    if satir_.startswith("   - "):
                        st.markdown(f"<span class='sub'>↳ {e(satir_.strip()[2:])}</span>", unsafe_allow_html=True)
                        continue
                    adim, _, detay = satir_.partition(":")
                    st.markdown(f"**✓ {ADIMLAR.get(adim, adim)}** <span class='sub'>· {ADIM_KIM.get(adim, '')} · "
                                f"{e(detay.strip())}</span>", unsafe_allow_html=True)
                gorulen = len(s.get("iz", []))
        except Exception as ex:   # API/ağ hatası: ekranı çökertme
            kutu.update(label="Değerlendirme tamamlanamadı", state="error")
            st.error(f"{type(ex).__name__}: {ex}")
            return None
        kutu.update(label=f"Değerlendirme tamamlandı · {time.time() - t0:.0f} sn", state="complete", expanded=False)
    return son


if calistir and not ss.ihbar.strip():
    st.toast("Önce müşterinin ihbarını yazın veya bir örnek seçin.", icon="✍️")
elif calistir:
    ss.sonuc = akis(baslangic(p["police_no"], ss.ihbar.strip(), ss.ihbar_tarihi.isoformat()), "Değerlendiriliyor…")
    ss.tur_id, ss.rapor_zamani = ss.tur_id + 1, datetime.now()

# ============================================================================================ sonuç
s = ss.sonuc
if s:
    o, t = s["olay"], s["taslak"]
    ic, baslik_, aciklama = ETIKET[s["etiket"]]

    # --- etiket bandı + olay özeti çipleri
    hareket = {"evet": "Sürülüyordu", "hayir": "Park hâlinde", "bilinmiyor": "Araç durumu ?"}[o.arac_hareket_halinde.deger]
    surucu_ = {"sigortali": "Sürücü: sigortalı", "baskasi": f"Sürücü: {o.surucu.kim or 'başkası'}",
               "bilinmiyor": "Sürücü ?"}[o.surucu.deger]
    tarih_ = (tr_tarih(o.olay_tarihi) + (f" · {o.olay_saati}" if o.olay_saati else "")) if o.olay_tarihi else "Tarih ?"
    cipler = ([f'<span class="badge b-mute">{e(KISA.get(r, r))}</span>' for r in o.risk_kodlari]
              + [f'<span class="badge b-mute">📅 {e(tarih_)}</span>', f'<span class="badge b-mute">{e(hareket)}</span>']
              + ([f'<span class="badge b-mute">{e(surucu_)}</span>'] if o.arac_hareket_halinde.deger != "hayir" else [])
              + ([f'<span class="badge b-info">Acente beyanı ile güncellendi</span>'] if s.get("beyanlar") else []))
    html_blok(f'<div class="verdict v-{s["etiket"]}"><div class="ic">{ic}</div><div style="flex:1">'
              f'<div class="t">{baslik_}</div><div class="d">{e(aciklama)}</div>'
              f'<div class="d" style="margin-top:6px"><b>Olay:</b> {e(o.ozet)}</div>'
              f'<div class="meta">{"".join(cipler)}</div></div></div>')

    sol, sag = st.columns([1.15, 1], gap="large")

    # --- poliçe kontrolleri
    with sol:
        parcalar = s["parcalar"]
        satirlar = []
        for k in s["kontroller"]:
            ad = kontrol_adi(k.ad)
            kaynak = "".join(f'<span class="srcpill">{e(parcalar[d]["atif"] if d in parcalar else d)}</span>' for d in k.dayanak)
            satirlar.append(f'<div class="chk c-{k.durum}"><div class="ic">{DURUM_IC[k.durum]}</div><div>'
                            f'<div class="t">{e(ad)}</div><div class="m">{e(k.mesaj)}</div>'
                            + (f'<div class="src">{kaynak}</div>' if kaynak else "") + '</div></div>')
        sayac = {d: sum(k.durum == d for k in s["kontroller"]) for d in ("uygun", "sorun", "belirsiz")}
        html_blok('<div class="card"><div class="card-h"><div class="card-t"><span class="n">2</span>Poliçe kontrolleri</div>'
                  f'<span class="sub">{sayac["uygun"]} uygun · {sayac["sorun"]} sorun · {sayac["belirsiz"]} belirsiz</span></div>'
                  + "".join(satirlar) + '<div class="sub" style="margin-top:4px">Bu kontroller deterministik koddur; '
                  'LLM karar vermez.</div></div>')

    # --- acenteye sorular (form)
    with sag, st.container(border=True):
        kart_basligi(3, "Acenteye sorular", f'{len(s["sorular"])} soru')
        if not s["sorular"]:
            html_blok('<div class="chk c-uygun"><div class="ic">✓</div><div><div class="t">Eksik bilgi yok</div>'
                      '<div class="m">Bu olay için gereken bilgiler ihbarda veya beyanlarda mevcut.</div></div></div>')
        else:
            html_blok('<div class="sub" style="margin-bottom:.6rem">Müşteriye sorup cevapları işaretleyin; yalnız ilgili '
                      'alanlar güncellenir ve değerlendirme yeniden yapılır (ihbar yeniden yorumlanmaz).</div>')
            cevaplar, tid = {}, ss.tur_id
            EHB = ["Evet", "Hayır", "Bilinmiyor"]
            for q in s["sorular"]:
                alan, soru = q["alan"], q["soru"]
                key = f"q_{alan}_{tid}"
                if alan == "olay_tarihi":
                    v = st.date_input(soru, value=None, key=key, format="DD.MM.YYYY")
                    if v:
                        cevaplar[alan] = v.isoformat()
                elif alan == "olay_saati":
                    v = st.time_input(soru, value=None, key=key, step=900)
                    if v:
                        cevaplar[alan] = v.strftime("%H:%M")
                elif alan == "arac_hareket_halinde":
                    v = st.radio(soru, ["Park hâlindeydi", "Sürülüyordu", "Bilinmiyor"], index=2, key=key, horizontal=True)
                    if v != "Bilinmiyor":
                        cevaplar[alan] = "hayir" if v.startswith("Park") else "evet"
                elif alan == "surucu":
                    v = st.radio(soru, ["Sigortalının kendisi", "Başka biri", "Bilinmiyor"], index=2, key=key, horizontal=True)
                    if v == "Sigortalının kendisi":
                        cevaplar[alan] = {"deger": "sigortali"}
                    elif v == "Başka biri":
                        kim = st.text_input("Kim? (yakınlık)", key=f"{key}_kim", placeholder="ör. eşi, oğlu, arkadaşı")
                        cevaplar[alan] = {"deger": "baskasi", "kim": kim.strip() or "başkası"}
                else:   # evet / hayır alanları (alkol, ehliyet, yeri terk, bildirim, yetkili sürücü, zorunlu neden)
                    v = st.radio(soru, EHB, index=2, key=key, horizontal=True)
                    if v != "Bilinmiyor":
                        cevaplar[alan] = "evet" if v == "Evet" else "hayir"
            guncelle = st.button(f"Cevapları ekle ve yeniden değerlendir ({len(cevaplar)})", type="primary",
                                 use_container_width=True, disabled=not cevaplar)
            if guncelle:
                yeni = akis(yeniden_baslangic(s, cevaplar), "Acente cevaplarıyla yeniden değerlendiriliyor…")
                if yeni:
                    ss.sonuc, ss.tur_id, ss.rapor_zamani = yeni, ss.tur_id + 1, datetime.now()
                    st.rerun()

    # --- ön değerlendirme notu (numaralı atıflar)
    st.write("")
    numara = atif_numaralari(t.gerekce, t.atiflar, parcalar)
    not_html = e(t.gerekce)
    not_html = re.sub(r"\[([A-Za-z0-9_.\-]+)\]",
                      lambda m: f'<span class="ref" title="{e(parcalar[m.group(1)]["atif"])}">{numara[m.group(1)]}</span>'
                      if m.group(1) in numara else "", not_html)
    denetim_rozeti = ('<span class="badge b-ok">✓ Denetimden geçti</span>' if not s["denetim"]
                      else '<span class="badge b-bad">Denetim uyarısı</span>')
    tur_rozeti = f'<span class="badge b-mute">{s["tur"]}. yazım</span>' if s["tur"] > 1 else ""
    html_blok('<div class="card"><div class="card-h"><div class="card-t"><span class="n">4</span>Ön değerlendirme notu</div>'
              f'<div class="chips">{tur_rozeti}{denetim_rozeti}</div></div><div class="note">{not_html}</div></div>')

    n1, n2 = st.columns([1.5, 1], gap="large")
    with n1:
        html_blok('<div class="lbl" style="margin-top:.9rem">Kaynak maddeler</div>')
        alintilar = {a.parca_id: a.alinti for a in t.atiflar}
        for pid, n in numara.items():
            pc = parcalar[pid]
            with st.expander(f"[{n}]  {temiz(pc['atif'])}"):
                alinti = alintilar.get(pid, "")
                if alinti:
                    html_blok(f'<div class="quote">“{e(alinti)}”</div>')
                metin = " ".join(pc["metin"].split())
                yer = kucult(metin).find(kucult(" ".join(alinti.split()))) if alinti else -1
                if yer >= 0:
                    L = len(" ".join(alinti.split()))
                    govde = e(metin[:yer]) + "<mark>" + e(metin[yer:yer + L]) + "</mark>" + e(metin[yer + L:])
                else:
                    govde = e(metin)
                html_blok(f'<div class="full">{govde}</div>')
                st.caption(f"Parça kimliği: {pid}")
    evrak_durumu: dict[str, bool] = {}
    with n2:
        html_blok('<div class="lbl" style="margin-top:.9rem">Gerekli evraklar · teslim alınanları işaretleyin</div>')
        if t.gerekli_belgeler:
            for b in t.gerekli_belgeler:   # anahtar evrak metninden: yeniden değerlendirmede işaretler korunur
                evrak_durumu[b] = st.checkbox(b, key=f"evrak_{p['police_no']}_{hashlib.md5(b.encode()).hexdigest()[:10]}")
            alinan, toplam = sum(evrak_durumu.values()), len(evrak_durumu)
            st.progress(alinan / toplam, text=f"{alinan}/{toplam} evrak teslim alındı")
            if alinan == toplam:
                html_blok('<div class="chk c-uygun" style="margin-top:6px"><div class="ic">✓</div><div><div class="t">'
                          'Evraklar tamam</div><div class="m">Dosya hasar birimine iletilmeye hazır.</div></div></div>')
            st.caption("Kaynak: özel şartlar › Hasar Anında Gerekli Belgeler")
        else:
            st.caption("Evrak listesi üretilmedi.")

    # --- rapor
    st.write("")
    with st.container(border=True):
        kart_basligi(5, "Ön değerlendirme raporu", "PDF · A4")
        r1, r2 = st.columns([2.2, 1], gap="large")
        eksik = [b for b, v in evrak_durumu.items() if not v]
        rozet = []
        if eksik:
            rozet.append(f'<span class="badge b-warn">{len(eksik)} evrak eksik</span>')
        if s["sorular"]:
            rozet.append(f'<span class="badge b-info">{len(s["sorular"])} açık soru</span>')
        if not rozet:
            rozet.append('<span class="badge b-ok">✓ Evraklar tamam · açık soru yok</span>')
        r1.markdown('<div class="sub" style="font-size:.86rem;line-height:1.6">Müşteri ve poliçe bilgileri, ihbar, olay '
                    'bilgileri ve dayanakları, poliçe kontrolleri, acente beyanları, kaynaklı ön değerlendirme notu, '
                    'alıntılı şart maddeleri ve evrak durumu tek bir raporda.</div>'
                    f'<div class="chips" style="margin-top:8px">{"".join(rozet)}</div>', unsafe_allow_html=True)
        rapor_no = f"ÖD-{p['police_no'][-6:]}-{ss.get('rapor_zamani', datetime.now()):%Y%m%d-%H%M}"
        with r2:
            st.download_button("⬇  PDF raporu indir", data=rapor_pdf(s, evrak_durumu, rapor_no), type="primary",
                               file_name=f"{rapor_no}.pdf", mime="application/pdf", use_container_width=True)
            st.caption(f"Rapor no: {rapor_no}")

    # --- şeffaflık
    with st.expander("Sistem ihbardan neyi, nereden çıkardı?"):
        def kaynak_(alinti: str) -> str:
            if not alinti:
                return '<span class="sub">— (ihbarda yok)</span>'
            if alinti == "yorum (LLM)":
                return '<span class="sub">yorum (Haiku)</span>'
            if alinti == "Acente beyanı":
                return '<span class="badge b-info">Acente beyanı</span>'
            return f'<span class="q">“{e(alinti)}”</span>'
        satirlar_ = [(a_, b_, kaynak_(c_)) for a_, b_, c_ in olay_satirlari(o)]
        html_blok('<table class="tr"><tr><th>Alan</th><th>Değer</th><th>Dayanak</th></tr>'
                  + "".join(f"<tr><td>{e(a_)}</td><td><b>{e(b_)}</b></td><td>{c_}</td></tr>" for a_, b_, c_ in satirlar_)
                  + "</table>")
        st.caption("Kural: 'Evet/Hayır' diyen her alan ihbardan birebir alıntı göstermek zorundadır; alıntı metinde "
                   "bulunamazsa kod değeri 'Bilinmiyor' yapar. Müşterinin söz etmediği şey 'Hayır' sayılmaz.")
        if s.get("dogrulama_notlari"):
            st.warning("Alıntı doğrulamasında düzeltilenler:\n\n" + "\n".join(f"- {x}" for x in s["dogrulama_notlari"]))
        st.caption("Şart metinlerinde aranan sorgular (sözleşme dili): " + " · ".join(o.arama_sorgulari))

    with st.expander("Akış izi ve otomatik denetim"):
        st.code("\n".join(s["iz"]), language=None)
        st.caption("Denetim: atıf ID'leri verilen parçalardan mı, alıntılar birebir mi, evraklar şartlarda var mı, "
                   "kesin karar dili kullanılmış mı. Hata varsa not geri bildirimle en fazla 2 kez yeniden yazılır.")

    html_blok('<div class="disclaimer">🛡️ <span>Bu ekran bir <b>ön değerlendirmedir</b>; teminat kararı vermez. '
              'Nihai karar, dosyayı inceleyen hasar uzmanınındır.</span></div>')
else:
    html_blok('<div class="disclaimer" style="margin-top:1rem">💡 <span>Hazır örneklerden birine tıklayın veya müşterinin '
              'anlattığını yazın; ardından <b>Değerlendir</b>.</span></div>')
