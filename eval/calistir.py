"""Değerlendirme setini uçtan uca çalıştırır ve özellik tabanlı puanlar.

Metin "doğru cevaba eşit mi" diye değil, ölçülebilir özelliklerle puanlanır:
  etiket       : kodun hesapladığı etiket beklenenle aynı mı
  risk         : Haiku'nun çıkardığı risk kodları beklenenleri içeriyor mu
  atif         : beklenen maddeler gerekçede/atıflarda geçiyor mu (recall)
  soru         : sorulması gerekenler soruldu, sorulmaması gerekenler sorulmadı mı
  denetim      : son taslak kod denetiminden geçti mi; kaç yazım turu gerekti

  .venv/bin/python -m eval.calistir              # hepsi
  .venv/bin/python -m eval.calistir ali_lpg ...  # seçili senaryolar
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from src.kasko.arama import _model, koleksiyon, kucult
from src.kasko.degerlendirme import _ID_ETIKETI, ETIKETLER, degerlendir

KLASOR = Path(__file__).parent


def _var(alternatifler: str, kume: set[str]) -> bool:
    return any(a in kume for a in alternatifler.split("|"))


def puanla(sen: dict, s: dict) -> dict:
    b = sen["beklenen"]
    t = s["taslak"]
    atiflar = {a.parca_id for a in t.atiflar} | set(_ID_ETIKETI.findall(t.gerekce))
    sorular = kucult(" ".join(x["soru"] for x in s["sorular"]))
    risk_ok = all(_var(r, set(s["olay"].risk_kodlari)) for r in b.get("risk", []))
    atif_bulunan = [a for a in b.get("atif", []) if _var(a, atiflar)]
    soru_eksik = [k for k in b.get("sorulmali", []) if kucult(k) not in sorular]
    soru_fazla = [k for k in b.get("sorulmamali", []) if kucult(k) in sorular]
    return {
        "id": sen["id"],
        "etiket_ok": s["etiket"] == b["etiket"], "etiket": s["etiket"], "beklenen_etiket": b["etiket"],
        "risk_ok": risk_ok, "risk": s["olay"].risk_kodlari,
        "atif_beklenen": len(b.get("atif", [])), "atif_bulunan": len(atif_bulunan),
        "atif_eksik": [a for a in b.get("atif", []) if a not in atif_bulunan],
        "soru_ok": not soru_eksik and not soru_fazla, "soru_eksik": soru_eksik, "soru_fazla": soru_fazla,
        "denetim_ok": not s["denetim"], "tur": s["tur"], "denetim": s["denetim"],
        "sorular": [x["soru"] for x in s["sorular"]], "kontroller": [f"[{k.durum}] {k.ad}: {k.mesaj}" for k in s["kontroller"]],
        "gerekce": t.gerekce, "dogrulama_notlari": s["dogrulama_notlari"], "iz": s["iz"],
    }


def calistir(sen: dict) -> dict:
    t0 = time.time()
    try:
        s = degerlendir(sen["police_no"], sen["ihbar"], sen.get("ihbar_tarihi", "2026-11-07"))
        return {**puanla(sen, s), "sure": round(time.time() - t0, 1)}
    except Exception as e:   # bir senaryonun çökmesi tüm koşuyu durdurmasın; hata olarak sayılsın
        return {"id": sen["id"], "hata": f"{type(e).__name__}: {e}", "sure": round(time.time() - t0, 1)}


def main(secili: list[str]) -> None:
    senaryolar = yaml.safe_load((KLASOR / "senaryolar.yaml").read_text(encoding="utf-8"))
    if secili:
        senaryolar = [s for s in senaryolar if s["id"] in secili]
    _model(), koleksiyon()          # paylaşılan kaynakları iş parçacıklarından önce bir kez yükle
    with ThreadPoolExecutor(4) as ex:
        sonuclar = list(ex.map(calistir, senaryolar))

    tamam = [r for r in sonuclar if "hata" not in r]
    print(f"\n{'senaryo':28s} {'etiket':>22s}  risk atıf  soru denetim tur  süre")
    for r in sonuclar:
        if "hata" in r:
            print(f"{r['id']:28s} HATA: {r['hata'][:80]}")
            continue
        et = ("✅ " if r["etiket_ok"] else f"❌ {r['beklenen_etiket']}→") + r["etiket"]
        atif = f"{r['atif_bulunan']}/{r['atif_beklenen']}" if r["atif_beklenen"] else "  - "
        print(f"{r['id']:28s} {et:>22s}  {'✅' if r['risk_ok'] else '❌'}   {atif:4s}  {'✅' if r['soru_ok'] else '❌'}    "
              f"{'✅' if r['denetim_ok'] else '❌'}     {r['tur']}  {r['sure']:4.0f}s")

    n = len(sonuclar)
    oran = lambda k: sum(r[k] for r in tamam) / n
    ab, ak = sum(r["atif_bulunan"] for r in tamam), sum(r["atif_beklenen"] for r in tamam)
    print(f"\nÖZET ({n} senaryo, {n - len(tamam)} hata)")
    print(f"  Etiket doğruluğu     : {oran('etiket_ok'):.0%}")
    print(f"  Risk kodu doğruluğu  : {oran('risk_ok'):.0%}")
    print(f"  Atıf recall          : {ab}/{ak} = {ab / max(ak, 1):.0%}")
    print(f"  Soru doğruluğu       : {oran('soru_ok'):.0%}")
    print(f"  Denetimden geçen     : {oran('denetim_ok'):.0%}")
    print(f"  Yeniden yazım gereken: {sum(r['tur'] > 1 for r in tamam)} senaryo")
    print(f"  Ortalama süre        : {sum(r['sure'] for r in sonuclar) / n:.0f} s")

    (KLASOR / "sonuclar.json").write_text(json.dumps(sonuclar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAyrıntılar: eval/sonuclar.json  (etiketler: {', '.join(ETIKETLER)})")


if __name__ == "__main__":
    main(sys.argv[1:])
