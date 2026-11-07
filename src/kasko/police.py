"""3b. Poliçe kontrolleri: tamamen deterministik kod, LLM yok.

Neden kod: cevap poliçe kaydında hazır (tarih, teminat listesi, sürücü kısıtı). Yorum gerektirmeyen bir şeyi LLM'e
sormak halüsinasyon riski ekler, tekrarlanabilirliği ve denetlenebilirliği bozar.

Her kontrol: durum (uygun / sorun / belirsiz / bilgi) + mesaj + dayanak parça ID'leri (+ gerekirse acenteye soru).
Mesajlar KARAR dili kullanmaz ("ödenmez" yerine "teminat listesinde yok"): karar hasar uzmanınındır.

Komut satırı (LLM çağırmaz, elle kurulmuş olaylarla):
  .venv/bin/python -m src.kasko.police
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from src.kasko.belgeler import ROOT, ayarlar
from src.kasko.olay import Bulgu, Olay, Surucu

DURUMLAR = ("uygun", "sorun", "belirsiz", "bilgi")


@dataclass
class Kontrol:
    ad: str
    durum: str
    mesaj: str
    dayanak: list[str] = field(default_factory=list)
    soru: str = ""
    soru_alan: str = ""       # arayüz bu alana göre form elemanı seçer


@lru_cache
def _veri() -> dict:
    return json.loads((ROOT / "data" / "policeler.json").read_text(encoding="utf-8"))


def policeler() -> list[dict]:
    return _veri()["policeler"]


def police(police_no: str) -> dict:
    return next(p for p in policeler() if p["police_no"] == police_no)


def teminat_adi(kod: str) -> str:
    return _veri()["teminat_kodlari"].get(kod, kod)


def _kisa(p: dict) -> str:
    return ayarlar()["belgeler"][p["urun"]]["kisa"]


# --------------------------------------------------------------------------------------- tek tek kontroller
def donem(p: dict, o: Olay) -> Kontrol:
    """GŞ A.8: sigorta başlama ve bitiş günlerinde öğleyin 12.00'de başlar/biter."""
    ad, dayanak = "Poliçe dönemi", ["GS_A.8_giris"]
    aralik = f"{p['baslangic']} – {p['bitis']}"
    if not o.olay_tarihi:
        return Kontrol(ad, "belirsiz", f"Olay tarihi bilinmiyor; poliçe dönemi {aralik}.", dayanak,
                       "Olay hangi tarihte meydana geldi?", "olay_tarihi")
    d, bas, bit = (date.fromisoformat(x) for x in (o.olay_tarihi, p["baslangic"], p["bitis"]))
    if d < bas or d > bit:
        return Kontrol(ad, "sorun", f"Olay tarihi {d} poliçe dönemi ({aralik}) DIŞINDA.", dayanak)
    if d in (bas, bit) and o.olay_saati:
        oglen_once = o.olay_saati < "12:00"
        icinde = (d == bit and oglen_once) or (d == bas and not oglen_once)
        return Kontrol(ad, "uygun" if icinde else "sorun",
                       f"Olay {d} saat {o.olay_saati}; poliçe {'bitiş' if d == bit else 'başlangıç'} gününde öğleyin "
                       f"12.00'de {'sona erer' if d == bit else 'başlar'}: olay dönemin {'İÇİNDE' if icinde else 'DIŞINDA'}.",
                       dayanak)
    if d in (bas, bit):
        return Kontrol(ad, "belirsiz", f"Olay {'başlangıç' if d == bas else 'bitiş'} gününde ({d}). Sigorta "
                       "bu günde öğleyin 12.00'de başlar/biter; saat belirleyici.", dayanak,
                       "Olay saat kaçta meydana geldi (öğle 12.00'den önce mi sonra mı)?", "olay_saati")
    return Kontrol(ad, "uygun", f"Olay tarihi {d} poliçe dönemi ({aralik}) içinde.", dayanak)


def teminatlar(p: dict, o: Olay) -> list[Kontrol]:
    """Risk kodu poliçenin teminat listesinde var mı? (Liste paket seçiminden gelir.)"""
    sonuc = []
    for kod in o.risk_kodlari:
        ad = f"Teminat: {kod}"
        if kod == "DIGER":
            sonuc.append(Kontrol(ad, "belirsiz", "Olay tanımlı bir teminat koduna eşlenemedi; uzman incelemeli."))
        elif kod in p["teminatlar"]:
            sonuc.append(Kontrol(ad, "uygun", f"'{teminat_adi(kod)}' poliçenin teminat listesinde var."))
        else:
            sonuc.append(Kontrol(ad, "sorun", f"'{teminat_adi(kod)}' poliçenin teminat listesinde YOK "
                                 f"(paketler: {', '.join(p['paketler'])}; tür: {p['kasko_turu']})."))
    return sonuc


_ES = re.compile(r"\beş(i|im)?\b")   # "eşim", "eşi"; "kardeşim" eşleşmez (ş'den önce kelime sınırı yok)


def surucu(p: dict, o: Olay, beyan: dict) -> Kontrol | None:
    """Poliçe Şablonu Bölüm 4: yetkili sürücü kısıtı. Araç sürülmüyorsa (park halinde) kontrol yok."""
    kisit = p["yetkili_surucu"]
    if o.arac_hareket_halinde.deger == "hayir":
        return None
    ad = "Yetkili sürücü"
    if kisit == "Sınırsız":
        return Kontrol(ad, "uygun", "Poliçede sürücü kısıtı yok.")
    s = o.surucu
    if s.deger == "sigortali":
        return Kontrol(ad, "uygun", f"Sürücü sigortalının kendisi; kısıt: '{kisit}'.")
    if s.deger == "baskasi":
        if "eşi" in kisit.lower() and _ES.search(s.kim.lower()):
            return Kontrol(ad, "uygun", f"Sürücü sigortalının eşi; kısıt: '{kisit}'.")
        if beyan.get("surucu_yetkili") == "evet":
            return Kontrol(ad, "uygun", f"Sürücü '{s.kim}'; acente poliçede yetkili sürücü olarak tanımlı olduğunu teyit etti.")
        if beyan.get("surucu_yetkili") == "hayir":
            return Kontrol(ad, "sorun", f"Sürücü '{s.kim}' poliçede yetkili sürücü olarak tanımlı DEĞİL (acente beyanı); "
                           f"poliçe kısıtı: '{kisit}'.")
        return Kontrol(ad, "sorun", f"Sürücü '{s.kim}' görünüyor; poliçe kısıtı: '{kisit}'.", soru=
                       f"Aracı kullanan kişi ({s.kim}) poliçede yetkili sürücü olarak tanımlı mı?", soru_alan="surucu_yetkili")
    return Kontrol(ad, "belirsiz", f"Sürücü bilinmiyor; poliçe kısıtı: '{kisit}'.",
                   soru="Olay anında aracı kim kullanıyordu?", soru_alan="surucu")


def istisnalar(p: dict, o: Olay, beyan: dict) -> list[Kontrol]:
    """Olayda ihbarla DESTEKLENEN istisna işaretleri (alıntılı 'evet'ler). Bilinmiyorsa burada sorun yok;
    soru olay.eksik_sorular'dan gelir."""
    sonuc = []
    if o.arac_hareket_halinde.deger == "hayir":   # park hâlinde: sigortalı aracın sürücüsü yoktu.
        return sonuc                               # ("çarpıp kaçmış" karşı tarafın eylemidir, A.5/5.10 değil)
    if o.alkol_veya_madde.deger == "evet":
        sonuc.append(Kontrol("İstisna: alkol/madde", "sorun",
                             f"İhbarda alkol/madde etkisi işareti var: \"{o.alkol_veya_madde.alinti}\". "
                             "Genel Şartlar'da yasal sınırın üzerinde alkollü sürüş teminat dışı hâller arasında.",
                             ["GS_A.5_5.5"]))
    if o.ehliyet.deger == "hayir":
        sonuc.append(Kontrol("İstisna: ehliyetsiz sürücü", "sorun",
                             f"İhbarda sürücü belgesi olmadığı işareti var: \"{o.ehliyet.alinti}\". "
                             "Gerekli sürücü belgesi olmayan kişilerce kullanım teminat dışı hâller arasında.",
                             ["GS_A.5_5.4"]))
    if o.olay_yerinden_ayrilma.deger == "evet" and beyan.get("zorunlu_neden") == "evet":
        sonuc.append(Kontrol("İstisna: kaza yerini terk", "belirsiz",
                             "Sürücü olay yerinden ayrılmış; acente zorunlu bir neden (sağlık, can güvenliği) beyan etti. "
                             "Zorunlu hâller istisna dışında tutulur; uzman doğrulamalı.", ["GS_A.5_5.10"]))
    elif o.olay_yerinden_ayrilma.deger == "evet":
        zorunlu_yok = beyan.get("zorunlu_neden") == "hayir"
        sonuc.append(Kontrol("İstisna: kaza yerini terk", "sorun",
                             f"İhbarda olay yerinden ayrılma işareti var: \"{o.olay_yerinden_ayrilma.alinti}\". "
                             "Zorunlu hâller (sağlık, can güvenliği) hariç teminat dışı hâller arasında.",
                             ["GS_A.5_5.10"],
                             "" if zorunlu_yok else "Olay yerinden ayrılmanın zorunlu bir nedeni (sağlık, can güvenliği) var mıydı?",
                             "" if zorunlu_yok else "zorunlu_neden"))
    return sonuc


def lpg(p: dict, o: Olay) -> Kontrol | None:
    """LPG ile çalışan araç + beyan/ek prim yok -> ret değil ORANTILI tazminat."""
    if "LPG" not in p["arac"]["yakit"].upper():
        return None
    dayanak = [f"{_kisa(p)}_lpg-ile-calisan-araclar-klozu_1"]
    if p.get("lpg_beyan_edildi", True):
        return Kontrol("LPG", "uygun", "Araç LPG'li ve poliçede beyan edilmiş.", dayanak)
    return Kontrol("LPG", "sorun", "Araç LPG'li fakat poliçede LPG beyanı/ek primi yok. Kloza göre tazminat, "
                   "alınan prim ile alınması gereken prim arasındaki ORANA göre ödenir (orantılı tazminat).", dayanak)


def muafiyet(p: dict, o: Olay) -> Kontrol | None:
    if not p["muafiyet_tl"]:
        return None
    dayanak = ["BUK_muafiyet-klozu_1" if p["urun"] == "benim_uygun_kaskom" else "BK_muafiyet-secimi-ozel-sartlari_2"]
    return Kontrol("Muafiyet", "bilgi", f"Poliçede {p['muafiyet_tl']:,} TL muafiyet var; hasar tutarından düşülür."
                   .replace(",", "."), dayanak)


def kontrol_et(p: dict, o: Olay, beyan: dict | None = None) -> list[Kontrol]:
    beyan = beyan or {}
    sonuc = [donem(p, o), *teminatlar(p, o), surucu(p, o, beyan), *istisnalar(p, o, beyan), lpg(p, o), muafiyet(p, o)]
    return [k for k in sonuc if k is not None]


# --------------------------------------------------------------------------------------- demo (LLM'siz)
def olay_yap(riskler: list[str], tarih: str = "2026-11-05", hareket: str = "evet", surucu_: str = "sigortali",
             kim: str = "", alkol: str = "bilinmiyor", terk: str = "bilinmiyor", ehliyet: str = "bilinmiyor") -> Olay:
    """Test için elle olay: alıntılar sembolik."""
    b = lambda d: Bulgu(deger=d, alinti="" if d == "bilinmiyor" else "(alıntı)")
    return Olay(ozet="", risk_kodlari=riskler, olay_tarihi=tarih, olay_tarihi_alinti="(alıntı)" if tarih else "",
                olay_saati="",
                arac_hareket_halinde=b(hareket), surucu=Surucu(deger=surucu_, kim=kim, alinti="(alıntı)"),
                alkol_veya_madde=b(alkol), ehliyet=b(ehliyet), olay_yerinden_ayrilma=b(terk), resmi_bildirim=b("bilinmiyor"),
                arama_sorgulari=[])


SENARYOLAR = [
    ("Mehmet: park halinde sel", "RS-K-2026-000102", olay_yap(["SEL_SU_BASKINI"], hareket="hayir", surucu_="bilinmiyor")),
    ("Mehmet: deprem", "RS-K-2026-000102", olay_yap(["DEPREM"], hareket="hayir", surucu_="bilinmiyor")),
    ("Ayşe: deprem (aynı olay, geniş poliçe)", "RS-K-2026-000101", olay_yap(["DEPREM"], hareket="hayir", surucu_="bilinmiyor")),
    ("Zeynep: çalınma", "RS-K-2026-000103", olay_yap(["CALINMA"], hareket="hayir", surucu_="bilinmiyor")),
    ("Ali: çarpışma (LPG)", "RS-K-2026-000104", olay_yap(["CARPISMA"])),
    ("Elif: 3 Kasım çarpışma", "RS-K-2025-000105", olay_yap(["CARPISMA"], tarih="2026-11-03")),
    ("Elif: 15 Ekim çarpışma (bitiş günü)", "RS-K-2025-000105", olay_yap(["CARPISMA"], tarih="2026-10-15")),
    ("Burak: kardeşi kullanıyordu", "RS-K-2026-000106", olay_yap(["CARPISMA"], surucu_="baskasi", kim="kardeşi")),
    ("Burak: eşi kullanıyordu", "RS-K-2026-000106", olay_yap(["CARPISMA"], surucu_="baskasi", kim="eşi")),
    ("Ayşe: alkollü + yeri terk", "RS-K-2026-000101", olay_yap(["CARPISMA"], alkol="evet", terk="evet")),
]

if __name__ == "__main__":
    from src.kasko.belgeler import tum_parcalar
    gecerli = {pc.id for pc in tum_parcalar()}
    isaret = {"uygun": "✅", "sorun": "❌", "belirsiz": "❓", "bilgi": "ℹ️ "}
    for baslik, no, o in SENARYOLAR:
        p = police(no)
        print(f"\n■ {baslik}   [{no} · {p['sigortali']['ad']} · {p['urun']}]")
        for k in kontrol_et(p, o):
            assert all(d in gecerli for d in k.dayanak), f"Geçersiz dayanak: {k.dayanak}"
            print(f"   {isaret[k.durum]} {k.ad:28s} {k.mesaj}" + (f"  [{', '.join(k.dayanak)}]" if k.dayanak else ""))
            if k.soru:
                print(f"      → ACENTEYE: {k.soru}")
