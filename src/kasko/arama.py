"""Hibrit arama: anlam (e5 embedding) + kelime (BM25), Reciprocal Rank Fusion ile birleşir.

Hackathon'dan (rm-karar-destek/src/rag/query.py) farkları:
  - Kelime araması sabit kelime listesi yerine BM25: ihbar metni serbest, konu listesi önceden bilinemez.
    BM25 nadir kelimeye ("alkol") yüksek, her yerde geçen kelimeye ("araç") düşük ağırlık verir.
  - Türkçe sondan eklemeli: sorgu kelimesinin ilk 5 harfi, belgedeki kelimenin ÖNEKİ olarak aranır
    ("alkollüydüm" -> "alkol" -> "alkollü", "alkol"; "sel" -> "seli", "selden").
  - Ürün filtresi: Genel Şartlar herkese, özel şartlar yalnız kendi ürününe. Mehmet'in (Benim Uygun Kaskom)
    sorgusunda Benim Kaskom'un deprem klozu ASLA gelmez; gelirse model "deprem kapsamda" diye yazabilirdi.
  - Kardeş genişletme: token sınırı yüzünden bölünmüş bir bendin bir parçası bulunursa komşu parçası (sira ± 1)
    otomatik eklenir. Bölünme yapısı kodda bilindiği için bunu LLM'e değil koda yaptırıyoruz (ucuz, deterministik).

Komut satırı:
  .venv/bin/python -m src.kasko.arama                                   # örnek sorgular
  .venv/bin/python -m src.kasko.arama benim_uygun_kaskom "araç yandı"   # tek sorgu
"""
from __future__ import annotations

import hashlib
import math
import re
import sys
from functools import lru_cache

from src.kasko.belgeler import ROOT, Parca, ayarlar, tum_parcalar

_KELIME = re.compile(r"[a-zçğıöşü0-9]+")
_DURAK = {"ve", "veya", "ile", "bir", "bu", "şu", "da", "de", "mi", "mı", "mu", "mü", "ne", "için", "gibi", "olan",
          "olarak", "ama", "çok", "daha", "en", "her", "ben", "benim", "sen", "biz", "ki", "ya", "ise", "diye",
          "kadar", "sonra", "önce", "şey", "var", "yok", "oldu", "olur", "dün", "bugün", "gece", "sabah", "akşam"}


def kucult(metin: str) -> str:
    """Türkçe küçük harf: Python'un lower()'ı "I"yı "i", "İ"yi "i̇" yapar."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def kelimeler(metin: str) -> list[str]:
    return _KELIME.findall(kucult(metin))


def sorgu_kokleri(metin: str) -> list[str]:
    """Sorgu kelimelerinin ilk 5 harfi (durak kelimeler ve 3 harften kısalar atılır)."""
    return sorted({k[:5] for k in kelimeler(metin) if len(k) >= 3 and k not in _DURAK})


# ------------------------------------------------------------------------------------------------ dizin
@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer  # ağır import: yalnızca gerektiğinde
    return SentenceTransformer(ayarlar()["arama"]["embedding_model"])


def gom(metinler: list[str], tur: str) -> list[list[float]]:
    """e5 belge parçasında "passage: ", soruda "query: " öneki ister. Vektörler normalize: iç çarpım = kosinüs."""
    return _model().encode([f"{tur}: {m}" for m in metinler], normalize_embeddings=True).tolist()


def _parmak_izi(parcalar: list[Parca]) -> str:
    """Parçalar değişirse (parçalayıcı düzeltildi, PDF güncellendi) dizin otomatik yeniden kurulsun."""
    h = hashlib.sha256()
    for p in parcalar:
        h.update(f"{p.id}|{p.gomme_metni()}".encode())
    return h.hexdigest()[:16]


@lru_cache
def koleksiyon():
    import chromadb
    from chromadb.config import Settings
    cfg = ayarlar()["arama"]
    istemci = chromadb.PersistentClient(path=str(ROOT / cfg["chroma_dir"]), settings=Settings(anonymized_telemetry=False))
    parcalar = tum_parcalar()
    iz = _parmak_izi(parcalar)
    k = istemci.get_or_create_collection(cfg["koleksiyon"], embedding_function=None,
                                         metadata={"hnsw:space": "cosine", "parmak_izi": ""})
    if (k.metadata or {}).get("parmak_izi") != iz or k.count() != len(parcalar):
        print(f"[dizin] {len(parcalar)} parça vektöre çevriliyor (ilk sefer ~1 dk)...", file=sys.stderr)
        istemci.delete_collection(cfg["koleksiyon"])
        k = istemci.create_collection(cfg["koleksiyon"], embedding_function=None,
                                      metadata={"hnsw:space": "cosine", "parmak_izi": iz})
        k.add(ids=[p.id for p in parcalar], documents=[p.metin for p in parcalar],
              embeddings=gom([p.gomme_metni() for p in parcalar], "passage"),
              metadatas=[{"belge": p.belge, "urun": p.urun, "baslik": p.baslik, "atif": p.atif, "sayfa": p.sayfa,
                          "grup": p.grup, "sira": p.sira} for p in parcalar])
    return k


def urun_parcalari(urun: str) -> dict:
    """Ürüne uygulanan tüm parçalar: Genel Şartlar (urun=hepsi) + o ürünün özel şartları."""
    return koleksiyon().get(where={"urun": {"$in": ["hepsi", urun]}},
                            include=["documents", "metadatas", "embeddings"])


# ------------------------------------------------------------------------------------------------ BM25
def bm25(kokler: list[str], belgeler: list[str], k1: float = 1.5, b: float = 0.75) -> tuple[list[float], list[list[str]]]:
    """Her belge için BM25 puanı ve eşleşen kökler. Eşleşme: belgedeki kelime sorgu köküyle BAŞLIYOR mu."""
    toks = [kelimeler(d) for d in belgeler]
    n, ort = len(toks), sum(map(len, toks)) / max(len(toks), 1)
    tf = [{q: sum(t.startswith(q) for t in ts) for q in kokler} for ts in toks]
    df = {q: sum(1 for x in tf if x[q]) for q in kokler}
    idf = {q: math.log((n - df[q] + 0.5) / (df[q] + 0.5) + 1) for q in kokler}
    puan = [sum(idf[q] * x[q] * (k1 + 1) / (x[q] + k1 * (1 - b + b * len(ts) / ort)) for q in kokler if x[q])
            for x, ts in zip(tf, toks)]
    return puan, [[q for q in kokler if x[q]] for x in tf]


# ------------------------------------------------------------------------------------------------ arama
def ara(soru: str, urun: str, sonuc_sayisi: int | None = None, kardes: bool = True) -> list[dict]:
    """En alakalı parçalar (kardeşleriyle). Her sonuç neden geldiğini taşır: benzerlik, bm25, eşleşen kökler."""
    cfg = ayarlar()["arama"]
    r = urun_parcalari(urun)
    n = len(r["ids"])
    if not n:
        return []
    q = gom([soru], "query")[0]
    benzerlik = [sum(a * b for a, b in zip(q, e)) for e in r["embeddings"]]
    gomme_metinleri = [f"{m['baslik']}\n{d}" for m, d in zip(r["metadatas"], r["documents"])]
    bm, eslesen = bm25(sorgu_kokleri(soru), gomme_metinleri)

    anlam_sira = {i: s for s, i in enumerate(sorted(range(n), key=lambda i: -benzerlik[i]), 1)}
    kelime_sira = {i: s for s, i in enumerate(sorted((i for i in range(n) if bm[i] > 0), key=lambda i: -bm[i]), 1)}
    k = cfg["rrf_k"]
    rrf = {i: 1 / (k + anlam_sira[i]) + (1 / (k + kelime_sira[i]) if i in kelime_sira else 0) for i in range(n)}
    secilen = sorted(range(n), key=lambda i: -rrf[i])[: sonuc_sayisi or cfg["sonuc_sayisi"]]

    def kayit(i: int, kardes_mi: bool = False) -> dict:
        return {"id": r["ids"][i], "metin": r["documents"][i], **r["metadatas"][i],
                "benzerlik": round(benzerlik[i], 3), "bm25": round(bm[i], 2), "rrf": round(rrf[i], 4),
                "anlam_sira": anlam_sira[i], "kelime_sira": kelime_sira.get(i), "eslesen": eslesen[i],
                "kardes": kardes_mi}

    sonuc, eklenen = [], set()
    for i in secilen:
        if i in eklenen:
            continue
        sonuc.append(kayit(i))
        eklenen.add(i)
        if kardes:
            m = r["metadatas"][i]
            for j in range(n):
                mj = r["metadatas"][j]
                if j not in eklenen and mj["grup"] == m["grup"] and abs(mj["sira"] - m["sira"]) == 1:
                    sonuc.append(kayit(j, kardes_mi=True))
                    eklenen.add(j)
    return sonuc


def yazdir(soru: str, urun: str) -> None:
    print(f"\n{'=' * 110}\nSORGU: {soru!r}   ÜRÜN: {urun}   kökler: {sorgu_kokleri(soru)}")
    for s in ara(soru, urun):
        isaret = "  ↳ kardeş" if s["kardes"] else f"{s['anlam_sira']:>3}/{s['kelime_sira'] or '-':>3}"
        print(f"  {isaret:10s} benz {s['benzerlik']:.3f} bm25 {s['bm25']:5.2f} | {s['atif'][:62]:62s} | "
              f"{' '.join(s['metin'].split())[:70]}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        yazdir(" ".join(sys.argv[2:]), sys.argv[1])
    else:
        for urun, soru in [
            ("benim_uygun_kaskom", "Sağanak yağmurda araç sokakta park halindeydi, sabah motor bölmesine kadar su dolmuş"),
            ("benim_uygun_kaskom", "Deprem sırasında aracın üzerine bina duvarı çöktü"),
            ("benim_kaskom", "Deprem sırasında aracın üzerine bina duvarı çöktü"),
            ("benim_kaskom", "Gece alkollüyken direğe çarptım, polis gelmeden olay yerinden ayrıldım"),
            ("benim_kaskom", "Kafeteryada masada unuttuğum anahtarımı alıp aracımı çalmışlar"),
            ("benim_uygun_kaskom", "Hasarı kaç gün içinde sigorta şirketine bildirmem gerekiyor"),
        ]:
            yazdir(soru, urun)
