"""3c. Uçtan uca akış (LangGraph):

  olay_cikar ─► police_kontrol ─► ara ─► yaz ─► denetle ─┬─► SON
   (Haiku)        (kod)          (kod)  (Haiku)  (kod)    └─► yaz  (hata varsa, en fazla 2 yeniden yazım)

Görev paylaşımı:
  - Etiket (kapsamda / kapsam dışı / uzman / ek bilgi) KOD tarafından poliçe kontrollerinden hesaplanır.
  - Haiku yalnız GEREKÇEYİ yazar: kodun bulduğunu açıklar, verilen maddelere atıf yapar, evrakları listeler.
  - Kod denetler: atıf ID'leri verilen parçalardan mı, alıntılar birebir mi, evraklar şartlarda var mı, karar dili var mı.

Komut satırı:
  .venv/bin/python -m src.kasko.degerlendirme            # 2 örnek
  .venv/bin/python -m src.kasko.degerlendirme RS-K-2026-000102 "ihbar metni"
"""
from __future__ import annotations

import operator
import re
import sys
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.kasko import olay as olay_mod
from src.kasko import police as police_mod
from src.kasko.arama import ara, koleksiyon, kucult
from src.kasko.belgeler import ROOT, ayarlar, sade
from src.kasko.olay import MODEL, Olay
from src.kasko.police import Kontrol

AZAMI_YENIDEN_YAZIM = 2

ETIKETLER = {
    "kapsam_disi": "KAPSAM DIŞI GÖRÜNÜYOR",
    "uzman": "UZMAN İNCELEMESİ GEREKLİ",
    "ek_bilgi": "EK BİLGİ GEREKLİ",
    "kapsamda": "KAPSAMDA GÖRÜNÜYOR",
}


class Atif(BaseModel):
    parca_id: str
    alinti: str = Field(description="O parçanın metninden KELİMESİ KELİMESİNE kopyalanmış kısa ifade.")


class Taslak(BaseModel):
    gerekce: str = Field(description="3-6 cümlelik açıklama. Şartlara dayanan her cümlenin sonunda [PARCA_ID].")
    atiflar: list[Atif]
    gerekli_belgeler: list[str] = Field(description="'Hasar Anında Gerekli Belgeler' parçasından, bu olaya uyan "
                                                    "evraklar; her biri parça metninden birebir kopya.")


class Durum(TypedDict, total=False):
    police_no: str
    ihbar: str
    ihbar_tarihi: str
    olay: Olay
    dogrulama_notlari: list[str]
    kontroller: list[Kontrol]
    sorular: list[dict]             # [{"alan": ..., "soru": ...}] — alan, arayüzdeki form elemanını belirler
    beyanlar: dict                  # acentenin form cevapları (alan -> değer)
    etiket: str
    parcalar: dict[str, dict]       # id -> {metin, atif, baslik}
    belge_idleri: list[str]
    taslak: Taslak
    denetim: list[str]
    tur: int
    iz: Annotated[list[str], operator.add]


# --------------------------------------------------------------------------------------- düğümler
def olay_cikar(d: Durum) -> dict:
    ham = olay_mod.cikar(d["ihbar"], d.get("ihbar_tarihi"))
    o, notlar = olay_mod.dogrula(ham, d["ihbar"])
    return {"olay": o, "dogrulama_notlari": notlar,
            "iz": [f"olay_cikar: {o.risk_kodlari}, {len(notlar)} alıntı düzeltmesi"]}


def etiket_hesapla(kontroller: list[Kontrol], sorular: list) -> str:
    sorun = [k for k in kontroller if k.durum == "sorun"]
    if any(k.ad == "Poliçe dönemi" or k.ad.startswith("Teminat:") for k in sorun):
        return "kapsam_disi"
    if sorun:
        return "uzman"
    if sorular or any(k.durum == "belirsiz" for k in kontroller):
        return "ek_bilgi"
    return "kapsamda"


def police_kontrol(d: Durum) -> dict:
    beyan = d.get("beyanlar") or {}
    p, o = police_mod.police(d["police_no"]), olay_mod.beyan_uygula(d["olay"], beyan)
    kontroller = police_mod.kontrol_et(p, o, beyan)
    adaylar = [(k.soru_alan, k.soru) for k in kontroller if k.soru] + olay_mod.eksik_sorular(o)
    sorular = list({alan: {"alan": alan, "soru": s} for alan, s in reversed(adaylar)}.values())[::-1]
    # (aynı alan için tek soru; kontrolün sorusu öncelikli, sıra korunur)
    etiket = etiket_hesapla(kontroller, sorular)
    ozet = {s: sum(k.durum == s for k in kontroller) for s in police_mod.DURUMLAR}
    return {"olay": o, "kontroller": kontroller, "sorular": sorular, "etiket": etiket,
            "iz": [f"police_kontrol: {ozet}, {len(sorular)} soru → {ETIKETLER[etiket]}"]}


def _parcalari_getir(**sorgu) -> dict[str, dict]:
    r = koleksiyon().get(include=["documents", "metadatas"], **sorgu)
    return {i: {"metin": m_, "atif": md["atif"], "baslik": md["baslik"]}
            for i, m_, md in zip(r["ids"], r["documents"], r["metadatas"])}


def ara_dugumu(d: Durum) -> dict:
    p, o = police_mod.police(d["police_no"]), d["olay"]
    sorgular = o.arama_sorgulari[:4] + [police_mod.teminat_adi(k) for k in o.risk_kodlari if k != "DIGER"]
    parcalar: dict[str, dict] = {}
    for s in sorgular:
        for r in ara(s, p["urun"], sonuc_sayisi=4):
            parcalar.setdefault(r["id"], {"metin": r["metin"], "atif": r["atif"], "baslik": r["baslik"]})
    # Kontrollerin dayanakları her zaman bağlamda olsun (kod onlara atıf yaptı, metin de onlara yapabilmeli)
    dayanaklar = sorted({i for k in d["kontroller"] for i in k.dayanak} - parcalar.keys())
    if dayanaklar:
        parcalar.update(_parcalari_getir(ids=dayanaklar))
    kisa = ayarlar()["belgeler"][p["urun"]]["kisa"]
    belgeler = _parcalari_getir(where={"grup": f"{kisa}_hasar-aninda-gerekli-belgeler-1-kasko"})
    parcalar.update(belgeler)
    return {"parcalar": parcalar, "belge_idleri": sorted(belgeler),
            "iz": [f"ara: {len(sorgular)} sorgu → {len(parcalar)} parça (dayanak +{len(dayanaklar)}, evrak +{len(belgeler)})"]}


SISTEM = """Sen bir sigorta acentesine kasko hasar ihbarı için ÖN DEĞERLENDİRME notu yazan asistansın. \
Karar vermiyorsun; karar hasar uzmanınındır.

Kurallar:
1. Etiket ve poliçe kontrol sonuçları kod tarafından hesaplandı. Bunları DOĞRU kabul et, onlarla çelişme, \
yeniden yorumlama; görevin bunları acentenin anlayacağı dille AÇIKLAMAK.
2. Yalnızca <parca> etiketleri içinde verilen metinlere dayan. Şartlara dayanan her cümlenin sonuna [PARCA_ID] koy. \
Verilmeyen bir madde numarası veya ID uydurma.
3. atiflar: kullandığın her parça için o parçanın metninden kelimesi kelimesine kısa bir alıntı.
4. Kesin karar dili YASAK: "ödenecek", "ödenmez", "reddedilir", "onaylandı", "kesinlikle", "kapsam dışıdır", \
"kapsamdadır" gibi ifadeler kullanma. Bunun yerine "görünüyor", "teminat listesinde yer almıyor", \
"teminat dışı hâller arasında sayılıyor", "uzman değerlendirmesi gerekir" de.
5. gerekli_belgeler: yalnız "Hasar Anında Gerekli Belgeler" parçasından, bu olaya uyanları birebir kopyala. \
Araç park hâlindeyken (sürülmüyorken) ehliyet, alkol raporu, sürücü beyanı gibi sürücüye ait evrak isteme.
6. Türkçe, sade, 3-6 cümle."""


def _baglam(d: Durum) -> str:
    p, o = police_mod.police(d["police_no"]), d["olay"]
    isaret = {"uygun": "UYGUN", "sorun": "SORUN", "belirsiz": "BELİRSİZ", "bilgi": "BİLGİ"}
    kontroller = "\n".join(f"- [{isaret[k.durum]}] {k.ad}: {k.mesaj}" + (f" (dayanak: {', '.join(k.dayanak)})" if k.dayanak else "")
                           for k in d["kontroller"])
    sorular = "\n".join(f"- {s['soru']}" for s in d["sorular"]) or "- yok"
    beyanlar = "\n".join(f"- {k}: {v}" for k, v in (d.get("beyanlar") or {}).items()) or "- yok"
    parcalar = "\n\n".join(f'<parca id="{i}" kaynak="{v["atif"]}">\n{v["metin"]}\n</parca>' for i, v in d["parcalar"].items())
    return (f"POLİÇE: {p['police_no']} · {p['sigortali']['ad']} · {p['urun']} · {p['kasko_turu']} · "
            f"paketler: {', '.join(p['paketler'])}\n\n"
            f"İHBAR:\n<ihbar>\n{d['ihbar']}\n</ihbar>\n\nOLAY ÖZETİ: {o.ozet}\n"
            f"ARAÇ OLAY ANINDA SÜRÜLÜYOR MUYDU: {o.arac_hareket_halinde.deger}\n\n"
            f"KOD TARAFINDAN HESAPLANAN ETİKET: {ETIKETLER[d['etiket']]}\n\nPOLİÇE KONTROLLERİ:\n{kontroller}\n\n"
            f"ACENTE BEYANLARI (ihbar sonrası acentenin verdiği bilgiler; gerekçede 'acente beyanına göre' de):\n"
            f"{beyanlar}\n\nACENTEYE SORULACAKLAR:\n{sorular}\n\nŞART PARÇALARI:\n{parcalar}")


def yaz(d: Durum) -> dict:
    import anthropic
    load_dotenv(ROOT / ".env")
    icerik = _baglam(d)
    tur = d.get("tur", 0)
    if tur:   # yeniden yazım: önceki taslak + denetim hataları
        icerik += (f"\n\nÖNCEKİ TASLAĞIN:\n{d['taslak'].model_dump_json(indent=2)}\n\n"
                   "OTOMATİK DENETİM ŞU HATALARI BULDU, DÜZELTEREK YENİDEN YAZ:\n" + "\n".join(f"- {h}" for h in d["denetim"]))
    from pydantic import ValidationError
    try:
        yanit = anthropic.Anthropic().messages.parse(
            model=MODEL, max_tokens=16000, output_config={"effort": "medium"}, system=SISTEM,
            messages=[{"role": "user", "content": icerik}], output_format=Taslak)
    except ValidationError as e:   # yarım JSON: genelde token sınırı (düşünme token'ları da sınırdan yer)
        raise RuntimeError("Değerlendirme çıktısı yarım kaldı (max_tokens?). Tekrar deneyin.") from e
    return {"taslak": yanit.parsed_output, "tur": tur + 1, "iz": [f"yaz: tur {tur + 1}"]}


_ID_ETIKETI = re.compile(r"\[([A-Za-z0-9_.\-]+)\]")
_TIRNAK = re.compile(r"[\"“”'‘’«»][^\"“”'‘’«»]*[\"“”'‘’«»]")
_KARAR = re.compile(r"ödenecek|ödenmeyecek|ödenmez|reddedil|reddediyor|onaylan|kabul edil|kesinlikle|kesin olarak|"
                    r"kapsam dışıdır|kapsamdadır|teminat altındadır|tazmin edilecek|tazmin edilmeyecek")


_SURUCU_EVRAKI = ("ehliyet", "alkol", "sürücü")


def denetim_hatalari(t: Taslak, parcalar: dict[str, dict], belge_idleri: list[str],
                     park_halinde: bool = False) -> list[str]:
    """Taslağın deterministik denetimi. Boş liste = geçti."""
    hatalar = []
    etiketler = _ID_ETIKETI.findall(t.gerekce)
    if not etiketler:
        hatalar.append("Gerekçede hiç [PARCA_ID] atfı yok.")
    for i in etiketler:
        if i not in parcalar:
            hatalar.append(f"Gerekçedeki [{i}] verilen parçalar arasında yok (uydurma ID).")
    for a in t.atiflar:
        if a.parca_id not in parcalar:
            hatalar.append(f"Atıf ID'si {a.parca_id} verilen parçalar arasında yok.")
        elif not a.alinti.strip() or sade(a.alinti) not in sade(parcalar[a.parca_id]["metin"]):
            hatalar.append(f"{a.parca_id} alıntısı parça metninde birebir yok: {a.alinti!r}")
    belge_metni = sade(" ".join(parcalar[i]["metin"] for i in belge_idleri))
    for b in t.gerekli_belgeler:
        if sade(b) not in belge_metni:
            hatalar.append(f"Evrak 'Hasar Anında Gerekli Belgeler' metninde birebir yok: {b!r}")
    if park_halinde:
        for b in t.gerekli_belgeler:
            if any(k in kucult(b) for k in _SURUCU_EVRAKI):
                hatalar.append(f"Araç park hâlindeyken sürücüye ait evrak istenmemeli: {b!r}")
    serbest = kucult(_TIRNAK.sub(" ", t.gerekce))          # tırnak içindeki şart alıntıları hariç
    for m in sorted(set(_KARAR.findall(serbest))):
        hatalar.append(f"Kesin karar dili kullanılmış: '{m}'. 'görünüyor / uzman değerlendirmesi gerekir' gibi yaz.")
    return hatalar


def denetle(d: Durum) -> dict:
    h = denetim_hatalari(d["taslak"], d["parcalar"], d["belge_idleri"],
                         park_halinde=d["olay"].arac_hareket_halinde.deger == "hayir")
    return {"denetim": h, "iz": [f"denetle: GEÇTİ"] if not h else [f"denetle: {len(h)} hata", *(f"   - {x}" for x in h)]}


def sonraki(d: Durum) -> str:
    return "yaz" if d["denetim"] and d["tur"] <= AZAMI_YENIDEN_YAZIM else "son"


def graf():
    from langgraph.graph import END, START, StateGraph
    g = StateGraph(Durum)
    for ad, f in [("olay_cikar", olay_cikar), ("police_kontrol", police_kontrol), ("ara", ara_dugumu),
                  ("yaz", yaz), ("denetle", denetle)]:
        g.add_node(ad, f)
    # Acente cevaplarıyla yeniden değerlendirmede olay zaten çıkarılmış: Haiku çıkarımı atlanır.
    g.add_conditional_edges(START, lambda d: "police_kontrol" if d.get("olay") else "olay_cikar",
                            {"police_kontrol": "police_kontrol", "olay_cikar": "olay_cikar"})
    g.add_edge("olay_cikar", "police_kontrol")
    g.add_edge("police_kontrol", "ara")
    g.add_edge("ara", "yaz")
    g.add_edge("yaz", "denetle")
    g.add_conditional_edges("denetle", sonraki, {"yaz": "yaz", "son": END})
    return g.compile()


def baslangic(police_no: str, ihbar: str, ihbar_tarihi: str | None = None) -> Durum:
    return {"police_no": police_no, "ihbar": ihbar, "ihbar_tarihi": ihbar_tarihi or "", "beyanlar": {}, "iz": []}


def yeniden_baslangic(onceki: Durum, yeni_beyanlar: dict) -> Durum:
    """Acente cevaplarıyla: önceki olay korunur, yalnız ilgili alanlar güncellenir, akış poliçe kontrolünden başlar."""
    return {"police_no": onceki["police_no"], "ihbar": onceki["ihbar"], "ihbar_tarihi": onceki.get("ihbar_tarihi", ""),
            "olay": onceki["olay"], "dogrulama_notlari": onceki.get("dogrulama_notlari", []),
            "beyanlar": {**(onceki.get("beyanlar") or {}), **yeni_beyanlar}, "iz": []}


def degerlendir(police_no: str, ihbar: str, ihbar_tarihi: str | None = None) -> Durum:
    return graf().invoke(baslangic(police_no, ihbar, ihbar_tarihi))


def yeniden_degerlendir(onceki: Durum, yeni_beyanlar: dict) -> Durum:
    return graf().invoke(yeniden_baslangic(onceki, yeni_beyanlar))


# --------------------------------------------------------------------------------------- demo
def yazdir(s: Durum) -> None:
    p = police_mod.police(s["police_no"])
    print(f"\n{'=' * 100}\n{p['sigortali']['ad']} ({p['police_no']}): {s['ihbar']}\n{'-' * 100}")
    print("İZ:", *s["iz"], sep="\n  ")
    print(f"\nETİKET (kod): {ETIKETLER[s['etiket']]}")
    print("\nKONTROLLER:")
    for k in s["kontroller"]:
        print(f"  [{k.durum}] {k.ad}: {k.mesaj}")
    print("\nGEREKÇE (Haiku):\n ", s["taslak"].gerekce)
    print("\nATIFLAR:")
    for a in s["taslak"].atiflar:
        print(f"  {a.parca_id}: \"{a.alinti}\"")
    print("\nGEREKLİ BELGELER:", *s["taslak"].gerekli_belgeler, sep="\n  - ")
    print("\nACENTEYE SORULAR:", *([x["soru"] for x in s["sorular"]] or ["yok"]), sep="\n  - ")
    print("\nDENETİM:", "GEÇTİ" if not s["denetim"] else s["denetim"])


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        yazdir(degerlendir(sys.argv[1], " ".join(sys.argv[2:])))
    else:
        for no, metin in [
            ("RS-K-2026-000102", olay_mod.ORNEKLER[0][1]),   # Mehmet sel
            ("RS-K-2026-000106", olay_mod.ORNEKLER[1][1]),   # Burak, kardeşi kullanıyordu
        ]:
            yazdir(degerlendir(no, metin, "2026-11-07"))
