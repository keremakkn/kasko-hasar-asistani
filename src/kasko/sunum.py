"""Arayüz ve PDF raporunun ortak sunum yardımcıları (etiket metinleri, kısa adlar, tarih, atıf numaraları)."""
from __future__ import annotations

import re
from datetime import date

from src.kasko.belgeler import ayarlar

KISA = {"CARPISMA": "Çarpışma", "UCUNCU_KISI_KOTU_NIYET": "Kötü niyet", "YANMA": "Yanma", "CALINMA": "Çalınma",
        "ANAHTAR_ELE_GECIRILMESI": "Anahtar", "SEL_SU_BASKINI": "Sel / su baskını", "DEPREM": "Deprem",
        "DIGER_DOGAL_AFET": "Doğal afet", "GLKHH_TEROR": "GLKHH / terör", "KISISEL_ESYA": "Kişisel eşya", "CAM": "Cam",
        "IMM": "İMM", "YOL_YARDIM": "Yol yardım", "IKAME_ARAC": "İkame araç", "DIGER": "Diğer"}

ETIKET = {   # kod etiketi -> (ikon, başlık, açıklama)
    "kapsamda": ("✓", "KAPSAMDA GÖRÜNÜYOR",
                 "Poliçe kontrollerinde engel görünmüyor. Evraklar tamamlanınca hasar dosyası açılabilir."),
    "kapsam_disi": ("✕", "KAPSAM DIŞI GÖRÜNÜYOR",
                    "Olay poliçenin teminat listesi veya dönemi dışında görünüyor. Müşteriye bilgi vermeden önce uzman görüşü alın."),
    "uzman": ("!", "UZMAN İNCELEMESİ GEREKLİ",
              "Teminat var; ancak istisna veya özel durum işaretleri bulundu. Dosya hasar uzmanına yönlendirilmeli."),
    "ek_bilgi": ("?", "EK BİLGİ GEREKLİ",
                 "Değerlendirmeyi tamamlamak için açık soruların cevaplanması gerekiyor."),
}

DEGER_TR = {"evet": "Evet", "hayir": "Hayır", "bilinmiyor": "Bilinmiyor", "sigortali": "Sigortalı", "baskasi": "Başkası"}
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_OZEL_GLIF = re.compile(r"\s*[-]\s*")       # PDF'ten gelen özel alan karakterleri (ör. U+F0D8)
ID_ETIKETI = re.compile(r"\[([A-Za-z0-9_.\-]+)\]")


def temiz(metin: str) -> str:
    return _OZEL_GLIF.sub(" › ", str(metin))


def tr_tarih(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d.day} {AYLAR[d.month - 1]} {d.year}"
    except ValueError:
        return iso


def urun_adi(urun: str) -> str:
    return ayarlar()["belgeler"][urun]["ad"].replace(" Sigortası Özel Şartları", "")


def kontrol_adi(ad: str) -> str:
    return "Teminat · " + KISA.get(ad[9:], ad[9:]) if ad.startswith("Teminat: ") else ad


def atif_numaralari(gerekce: str, atiflar: list, parcalar: dict) -> dict[str, int]:
    """Gerekçede geçiş sırasına göre [ID] -> 1, 2, 3 ... (yalnız verilen parçalar)."""
    numara: dict[str, int] = {}
    for i in ID_ETIKETI.findall(gerekce) + [a.parca_id for a in atiflar]:
        if i in parcalar:
            numara.setdefault(i, len(numara) + 1)
    return numara


def olay_satirlari(o) -> list[tuple[str, str, str]]:
    """(alan, değer, dayanak) — dayanak: ihbardan alıntı / 'Acente beyanı' / ''."""
    tarih = (tr_tarih(o.olay_tarihi) + (f" · {o.olay_saati}" if o.olay_saati else "")) if o.olay_tarihi else "Bilinmiyor"
    return [
        ("Risk kodları", ", ".join(KISA.get(r, r) for r in o.risk_kodlari), "yorum (LLM)"),
        ("Olay tarihi", tarih, o.olay_tarihi_alinti),
        ("Araç sürülüyor muydu", DEGER_TR[o.arac_hareket_halinde.deger], o.arac_hareket_halinde.alinti),
        ("Sürücü", DEGER_TR[o.surucu.deger] + (f" ({o.surucu.kim})" if o.surucu.kim else ""), o.surucu.alinti),
        ("Alkol / madde", DEGER_TR[o.alkol_veya_madde.deger], o.alkol_veya_madde.alinti),
        ("Ehliyet var mı", DEGER_TR[o.ehliyet.deger], o.ehliyet.alinti),
        ("Olay yerinden ayrılma", DEGER_TR[o.olay_yerinden_ayrilma.deger], o.olay_yerinden_ayrilma.alinti),
        ("Polis / tutanak", DEGER_TR[o.resmi_bildirim.deger], o.resmi_bildirim.alinti),
    ]


BEYAN_ADI = {"olay_tarihi": "Olay tarihi", "olay_saati": "Olay saati", "arac_hareket_halinde": "Araç sürülüyor muydu",
             "surucu": "Sürücü", "alkol_veya_madde": "Alkol / madde", "ehliyet": "Ehliyet var mı",
             "olay_yerinden_ayrilma": "Olay yerinden ayrılma", "resmi_bildirim": "Polis / tutanak",
             "surucu_yetkili": "Sürücü poliçede yetkili mi", "zorunlu_neden": "Yeri terkin zorunlu nedeni var mı"}


def beyan_metni(alan: str, deger) -> str:
    if isinstance(deger, dict):
        return DEGER_TR.get(deger.get("deger", ""), "") + (f" ({deger['kim']})" if deger.get("kim") else "")
    if alan == "olay_tarihi":
        return tr_tarih(deger)
    return DEGER_TR.get(deger, str(deger))
