"""PDF'leri madde/bent bazında parçalara böler.

Neden sabit boyutlu değil de madde bazlı parçalama?
  Hukuki metinde anlam birimi bent'tir. "A.5 bent 5.5" (alkollü sürüş istisnası) iki parçaya bölünürse
  arama yarısını getirir; iki bent tek parçaya girerse model hangi bende atıf yapacağını karıştırır.
  Her parçanın başına bağlam başlığı eklenir ("Genel Şartlar › A.5 Teminat Dışında Kalan Zararlar › 5.5"):
  bent metni "istisna" kelimesini içermese de model ve arama bunun bir istisna olduğunu başlıktan bilir.

Komut satırı:  .venv/bin/python -m src.kasko.belgeler      (parça istatistiği ve örnekler)
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]

# Genel Şartlar'ın resmi madde başlıkları (Lexpera sistematik indeksi). PDF'ten çıkan metinde başlıklar
# iki satıra bölünüyor ve "B.1" bazen "B.l" (küçük L) olarak geliyor; başlığı tahmin etmek yerine sabit liste.
GS_MADDELER = {
    "A.1": "Sigortanın Konusu", "A.2": "Sigortanın Coğrafi Sınırı", "A.3": "Sigortanın Kapsamı",
    "A.4": "Ek Sözleşme ile Teminat Kapsamına Dahil Edilebilecek Zararlar",
    "A.5": "Teminat Dışında Kalan Zararlar", "A.6": "Muafiyetler",
    "A.7": "Sigorta Teminatına İlişkin Özel Belirlemeler", "A.8": "Sigortanın Başlangıcı ve Sonu",
    "B.1": "Rizikonun Gerçekleşmesi Halinde Sigortalı ve/veya Sigorta Ettirenin Yükümlülükleri",
    "B.2": "Koruma Önlemleri ve Kurtarma", "B.3": "Rizikonun Gerçekleşmesi Halinde Sigortacının Yükümlülükleri",
    "B.4": "Hasar ve Tazminatın Sonuçları",
    "C.1": "Sigorta Priminin Ödenmesi, Sigortacının Sorumluluğunun Başlaması ve Sigorta Ettirenin Temerrüdü",
    "C.2": "Sigortalı ve/veya Sigorta Ettirenin Sözleşme Yapıldığı Sırada Beyan Yükümlülüğü",
    "C.3": "Sigortalı ve/veya Sigorta Ettirenin Sigorta Süresi İçinde İhbar Yükümlülüğü ve Sonuçları",
    "C.4": "Birden Çok Sigorta", "C.5": "Menfaat Sahibinin Değişmesi", "C.6": "Tebliğ ve İhbarlar",
    "C.7": "Sırların Saklı Tutulması", "C.8": "Yetkili Mahkeme ve Tahkim", "C.9": "Eksper Tayini",
    "C.10": "Zamanaşımı", "C.11": "Özel Şartlar", "C.12": "Yürürlük",
}
_MADDE = re.compile(r"^\s*([ABC])\.\s?([0-9l]{1,2})\.\s*(.*)$")       # "A.5. Teminat..."  "B.l. Rizikonun..."
_BENT = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s*(.*)$")        # "5.5.Aracın..."  "3.3.2.2.Onarım..."
_SABLON = re.compile(r"^\s*POLİÇE\s+ŞABLONU", re.I)
_KUCUK = re.compile(r"[a-zçğıöşü]")


@dataclass
class Parca:
    id: str            # "GS_A.5_5.5"  "BK_sel-ve-su-baskini-klozu_1"
    belge: str         # config anahtarı: genel_sartlar | benim_kaskom | benim_uygun_kaskom
    urun: str          # hangi ürüne uygulanır: hepsi | benim_kaskom | benim_uygun_kaskom
    baslik: str        # bağlam yolu: "Genel Şartlar › A.5 Teminat Dışında Kalan Zararlar › 5.5"
    atif: str          # insana gösterilecek kısa atıf: "Genel Şartlar A.5 / 5.5"
    sayfa: int
    metin: str
    grup: str = ""     # aynı bende/bölüme ait parçalar aynı grupta ("GS_B.3_3.3.2.2"); kardeş genişletme için
    sira: int = 1      # grup içindeki sıra

    def gomme_metni(self) -> str:
        """Vektöre çevrilen metin: başlık + gövde (başlık bağlam verir)."""
        return f"{self.baslik}\n{self.metin}"


@lru_cache
def ayarlar() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@lru_cache
def _tokenizer():
    from transformers import AutoTokenizer  # ağır import: yalnızca gerektiğinde
    return AutoTokenizer.from_pretrained(ayarlar()["arama"]["embedding_model"])


def token_sayisi(metin: str) -> int:
    return len(_tokenizer().tokenize(metin))


def satirlar(pdf: Path) -> list[tuple[int, str]]:
    """[(sayfa_no, satır)]: sayfa bilgisi kaybolmasın diye satır satır."""
    return [(no, s.rstrip()) for no, sayfa in enumerate(PdfReader(pdf).pages, 1)
            for s in (sayfa.extract_text() or "").splitlines()]


def sha256(pdf: Path) -> str:
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def sade(metin: str) -> str:
    """Tüm boşlukları atar, harfleri küçültür. PDF metninde kelime içine boşluk giriyor ("d üşman", "il e");
    birebir alıntı kontrolü ve başlık eşleştirme bu sade halde yapılır."""
    metin = unicodedata.normalize("NFC", metin).replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"\s+", "", metin)


def _bol(metin: str, limit: int, baslik: str) -> list[str]:
    """Token sınırını aşan metni satır/cümle sınırından böler (başlık her parçaya eklendiği için onu da sayar)."""
    butce = limit - token_sayisi(baslik) - 4
    if token_sayisi(metin) <= butce:
        return [metin]
    birimler = [c for c in re.split(r"(?<=[.;:])\s+|\n", metin) if c.strip()]
    parcalar, simdiki = [], ""
    for b in birimler:
        aday = f"{simdiki} {b}".strip()
        if simdiki and token_sayisi(aday) > butce:
            parcalar.append(simdiki)
            simdiki = b
        else:
            simdiki = aday
    if simdiki:
        parcalar.append(simdiki)
    return parcalar


def _temizle(satirlar_: list[str]) -> str:
    return re.sub(r"[ \t]+", " ", "\n".join(s.strip() for s in satirlar_ if s.strip())).strip()


def _basligi_ayikla(metin: str, baslik: str) -> str:
    """Madde gövdesinin başındaki (iki satıra bölünmüş olabilen) başlığı atar."""
    hedef, i, alinan = sade(baslik), 0, ""
    while i < len(metin) and len(sade(alinan)) < len(hedef):
        alinan += metin[i]
        i += 1
    return metin[i:].strip() if sade(alinan) == hedef else metin


# ----------------------------------------------------------------------------------------- Genel Şartlar
def genel_sartlar_parcalari(anahtar: str = "genel_sartlar") -> list[Parca]:
    cfg = ayarlar()["belgeler"][anahtar]
    limit = ayarlar()["arama"]["parca_token"]
    satir = satirlar(ROOT / cfg["dosya"])

    # 1) Satırları maddelere grupla: {madde: [(sayfa, satır)]}
    maddeler: list[tuple[str, list[tuple[int, str]]]] = []
    for sayfa, s in satir:
        m = _MADDE.match(s)
        if m and f"{m[1]}.{m[2].replace('l', '1')}" in GS_MADDELER:
            maddeler.append((f"{m[1]}.{m[2].replace('l', '1')}", [(sayfa, m[3])]))
        elif _SABLON.match(s):
            maddeler.append(("Poliçe Şablonu", []))
        elif maddeler:
            maddeler[-1][1].append((sayfa, s))

    parcalar: list[Parca] = []
    for madde, icerik in maddeler:
        ad = GS_MADDELER.get(madde, "Poliçe Şablonu (poliçede yer alması zorunlu bilgiler)")
        no = int(madde.split(".")[1]) if madde in GS_MADDELER else None

        # 2) Madde içini bentlere böl. Bent numarasının ilk hanesi madde numarasıyla aynı olmalı
        #    (A.5 altında "5.x"); böylece metin içindeki "3713 sayılı" gibi sayılar bent sanılmaz.
        bentler: list[list] = [["", []]]              # [bent_no, [(sayfa, satır)]]; "" = madde girişi
        alt_baslik: dict[str, str] = {}               # "3.3.1" -> "Sigorta Bedeli" (gövdesiz başlık bentleri)
        for sayfa, s in icerik:
            b = _BENT.match(s)
            if no is not None and b and int(b[1].split(".")[0]) == no and len(b[1].split(".")) >= 2:
                bentler.append([b[1], [(sayfa, b[2])]])
            else:
                bentler[-1][1].append((sayfa, s))

        for bent_no, bs in bentler:
            govde = _temizle([s for _, s in bs])
            if bent_no == "":
                govde = _basligi_ayikla(govde, ad)
            if not govde:
                continue
            # Tek satırlık, nokta ile bitmeyen kısa bent = alt başlık ("3.3.1. Sigorta Bedeli")
            if bent_no and len(govde) < 70 and "\n" not in govde and not govde.endswith((".", ",", ":")):
                alt_baslik[bent_no] = govde
                continue
            yol = ["Genel Şartlar", f"{madde} {ad}" if no else ad]
            if bent_no:
                ust = [alt_baslik[k] for k in alt_baslik if bent_no.startswith(k + ".")]
                yol += ust + [bent_no]
            baslik = " › ".join(yol)
            atif = f"Genel Şartlar {madde}" + (f" / {bent_no}" if bent_no else "") if no else "Genel Şartlar, Poliçe Şablonu"
            sayfa0 = bs[0][0] if bs else icerik[0][0]
            bolunmus = _bol(govde, limit, baslik)
            pid = f"{cfg['kisa']}_{madde}" + (f"_{bent_no}" if bent_no else "_giris") if no else f"{cfg['kisa']}_sablon"
            for i, p in enumerate(bolunmus, 1):
                parcalar.append(Parca(id=f"{pid}_{i}" if len(bolunmus) > 1 else pid, belge=anahtar, urun=cfg["urun"],
                                      baslik=baslik, atif=atif, sayfa=sayfa0, metin=p, grup=pid, sira=i))
    return parcalar


# ----------------------------------------------------------------------------------------- Özel şartlar
_BAGLAC = re.compile(r"\b(ve|veya|ile|ya da)\b")


def _baslik_mi(s: str) -> bool:
    """Tamamı büyük harf, en az 10 harf: "SEL VE SU BASKINI KLOZU", "1. ÇARPIŞMA– ... ÖZEL ŞARTLARI".
    Başlık içindeki küçük harfli bağlaçlara izin var: "SES,GÖRÜNTÜ ve İLETİŞİM CİHAZLARI KLOZU"."""
    harf = [c for c in s if c.isalpha()]
    return len(harf) >= 10 and not _KUCUK.search(_BAGLAC.sub("", s)) and not set(s.strip()) <= set("-– ")


def _slug(metin: str) -> str:
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    kelime = re.sub(r"[^a-z0-9 ]", " ", re.sub(r"^\d+\.\s*", "", metin).translate(tablo).lower()).split()
    return "-".join(kelime[:6])


def tr_baslik(metin: str) -> str:
    """Türkçe baş harf büyütme. str.title() "MİNİ YOL YARDIM"ı "Mi̇ni̇ Yol Yardim" yapıyor (İ ve I bozuluyor)."""
    def kelime(k: str) -> str:
        kucuk = k.replace("I", "ı").replace("İ", "i").lower()
        return (kucuk[:1].replace("i", "İ").replace("ı", "I").upper() + kucuk[1:]) if kucuk else k
    return " ".join(kelime(k) for k in metin.split(" "))


def ozel_sartlar_parcalari(anahtar: str) -> list[Parca]:
    cfg = ayarlar()["belgeler"][anahtar]
    limit = ayarlar()["arama"]["parca_token"]
    bolumler: list[list] = [[cfg["ad"], []]]           # [başlık, [(sayfa, satır)]]
    onceki_baslik = False
    for sayfa, s in satirlar(ROOT / cfg["dosya"]):
        if _baslik_mi(s):
            if onceki_baslik and not bolumler[-1][1]:   # iki satıra bölünmüş başlık: birleştir
                bolumler[-1][0] += " " + s.strip()
            else:
                bolumler.append([s.strip(), []])
            onceki_baslik = True
        else:
            if s.strip():
                bolumler[-1][1].append((sayfa, s))
                onceki_baslik = False

    parcalar, sayac = [], {}
    kisa_ad = cfg["ad"].replace(" Sigortası Özel Şartları", "")
    for baslik_ham, bs in bolumler:
        govde = _temizle([s for _, s in bs])
        if not govde:
            continue
        baslik_ham = re.sub(r"\s+", " ", baslik_ham).strip()
        baslik = f"{kisa_ad} (özel şart) › {tr_baslik(baslik_ham)}"
        for p in _bol(govde, limit, baslik):
            slug = _slug(baslik_ham) or "giris"
            sayac[slug] = sayac.get(slug, 0) + 1
            parcalar.append(Parca(id=f"{cfg['kisa']}_{slug}_{sayac[slug]}", belge=anahtar, urun=cfg["urun"],
                                  baslik=baslik, atif=f"{kisa_ad} özel şartları, {tr_baslik(baslik_ham)}",
                                  sayfa=bs[0][0], metin=p, grup=f"{cfg['kisa']}_{slug}", sira=sayac[slug]))
    return parcalar


def tum_parcalar() -> list[Parca]:
    return (genel_sartlar_parcalari() + ozel_sartlar_parcalari("benim_kaskom")
            + ozel_sartlar_parcalari("benim_uygun_kaskom"))


if __name__ == "__main__":
    import statistics
    tum = tum_parcalar()
    ids = [p.id for p in tum]
    assert len(ids) == len(set(ids)), f"tekrarlanan id: {[i for i in ids if ids.count(i) > 1][:5]}"
    for belge in ayarlar()["belgeler"]:
        ps = [p for p in tum if p.belge == belge]
        tok = [token_sayisi(p.gomme_metni()) for p in ps]
        print(f"{belge:20s} {len(ps):4d} parça | token ort {statistics.mean(tok):.0f}, en büyük {max(tok)}, en küçük {min(tok)}")
    for pid in ["GS_A.5_5.5", "GS_A.4_4.5", "GS_B.3_3.3.2.2", "GS_B.1_1.1"]:
        p = next((x for x in tum if x.id == pid), None)
        print(f"\n--- {pid}: " + (f"[{p.atif}, s.{p.sayfa}]\n{p.baslik}\n{p.metin[:300]}" if p else "YOK"))
    print("\n--- Özel şart başlıkları (ilk 12, Benim Uygun Kaskom):")
    for p in [x for x in tum if x.belge == "benim_uygun_kaskom"][:12]:
        print(f"   {p.id:55s} s.{p.sayfa}")
