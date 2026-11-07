"""Ön değerlendirme sonucundan indirilebilir PDF rapor (fpdf2 + Noto Sans: Türkçe karakterler için gömülü font).

  rapor_pdf(sonuc, evrak_durumu, rapor_no) -> bytes
"""
from __future__ import annotations

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src.kasko import police as police_mod
from src.kasko.belgeler import ROOT
from src.kasko.sunum import (BEYAN_ADI, ETIKET, ID_ETIKETI, atif_numaralari, beyan_metni, kontrol_adi, olay_satirlari,
                             temiz, tr_tarih, urun_adi)

FONT = ROOT / "assets" / "fonts"
NAVY, TEAL, INK, MUTED, LINE, SOFT = (11, 31, 58), (15, 118, 110), (15, 23, 42), (100, 116, 139), (226, 232, 240), (245, 247, 250)
RENK = {  # durum/etiket -> (yazı, zemin)
    "uygun": ((21, 128, 61), (240, 253, 244)), "kapsamda": ((21, 128, 61), (240, 253, 244)),
    "sorun": ((185, 28, 28), (254, 242, 242)), "kapsam_disi": ((185, 28, 28), (254, 242, 242)),
    "belirsiz": ((180, 83, 9), (255, 251, 235)), "uzman": ((180, 83, 9), (255, 251, 235)),
    "bilgi": ((29, 78, 216), (239, 246, 255)), "ek_bilgi": ((29, 78, 216), (239, 246, 255)),
}
DURUM_YAZI = {"uygun": "UYGUN", "sorun": "SORUN", "belirsiz": "BELİRSİZ", "bilgi": "BİLGİ"}
NL = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


def tr_buyuk(metin: str) -> str:
    """Türkçe büyük harf: Python'un upper()'ı 'i'yi 'I' yapar (MÜŞTERI); doğrusu 'İ'."""
    return metin.replace("i", "İ").replace("ı", "I").upper()


class Rapor(FPDF):
    def __init__(self, rapor_no: str):
        super().__init__(format="A4")
        self.rapor_no = rapor_no
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=20)
        for stil, dosya in (("", "Regular"), ("B", "Bold"), ("I", "Italic")):
            self.add_font("Noto", stil, str(FONT / f"NotoSans-{dosya}.ttf"))
        self.set_title("Kasko Hasar Ön Değerlendirme Raporu")
        self.set_creator("Kasko Hasar Ön Değerlendirme Asistanı (prototip)")

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*LINE)
        self.line(16, self.get_y() - 2, 194, self.get_y() - 2)
        self.set_font("Noto", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(118, 5, "Ön değerlendirmedir, teminat kararı değildir · Prototip, sentetik veri", align="L")
        self.cell(60, 5, f"{self.rapor_no} · Sayfa {self.page_no()}/{{nb}}", align="R")

    # ------------------------------------------------------------------ yapı taşları
    def bolum(self, baslik: str):
        if self.get_y() > 245:
            self.add_page()
        self.ln(4)
        self.set_font("Noto", "B", 10.5)
        self.set_text_color(*NAVY)
        self.cell(0, 6, tr_buyuk(baslik), **NL)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.5)
        self.line(16, self.get_y(), 30, self.get_y())
        self.set_line_width(0.2)
        self.ln(2.5)

    def anahtar_deger(self, satirlar: list[tuple[str, str]], sutun: int = 2):
        """Anahtar-değer ızgarası (2 sütun)."""
        gen = (self.w - 32) / sutun
        for i in range(0, len(satirlar), sutun):
            y = self.get_y()
            yukseklik = 0
            for j, (k, v) in enumerate(satirlar[i:i + sutun]):
                self.set_xy(16 + j * gen, y)
                self.set_font("Noto", "", 7.5)
                self.set_text_color(*MUTED)
                self.cell(gen - 4, 4, k, new_x=XPos.LEFT, new_y=YPos.NEXT)
                self.set_font("Noto", "B", 9)
                self.set_text_color(*INK)
                self.multi_cell(gen - 4, 4.6, v, align="L", new_x=XPos.LEFT, new_y=YPos.NEXT)
                yukseklik = max(yukseklik, self.get_y() - y)
            self.set_xy(16, y + yukseklik + 2)

    def kutu(self, metin: str, zemin=SOFT, yazi=INK, stil: str = "", boyut: float = 9.5):
        self.set_fill_color(*zemin)
        self.set_text_color(*yazi)
        self.set_font("Noto", stil, boyut)
        self.multi_cell(0, 5.2, metin, fill=True, padding=(3, 4), align="L", **NL)

    def tablo(self, basliklar: list[str], satirlar: list[list[str]], genislik: list[float], renkler: list | None = None):
        self.set_font("Noto", "B", 7.5)
        self.set_text_color(*MUTED)
        self.set_fill_color(*SOFT)
        for b, g in zip(basliklar, genislik):
            self.cell(g, 6, " " + tr_buyuk(b), fill=True)
        self.ln()
        for r, satir in enumerate(satirlar):
            if self.get_y() > 265:
                self.add_page()
            y0, x = self.get_y(), 16
            yuks = []
            for c, (hucre, g) in enumerate(zip(satir, genislik)):
                self.set_xy(x, y0 + 1)
                renk = renkler[r][c] if renkler and renkler[r][c] else None
                self.set_font("Noto", "B" if renk or c == 0 else "", 8.5)
                self.set_text_color(*(renk or INK))
                self.multi_cell(g - 2, 4.4, hucre, align="L", new_x=XPos.RIGHT, new_y=YPos.TOP)
                yuks.append(self.get_y())
                x += g
            # multi_cell yüksekliği: en uzun hücreye göre satırı kapat
            self.set_y(y0)
            h = max(self._hucre_yuksekligi(s, g - 2) for s, g in zip(satir, genislik)) + 2
            self.set_draw_color(*LINE)
            self.line(16, y0 + h, 16 + sum(genislik), y0 + h)
            self.set_y(y0 + h)

    def _hucre_yuksekligi(self, metin: str, gen: float) -> float:
        satirlar = self.multi_cell(gen, 4.4, metin, align="L", dry_run=True, output="LINES")
        return 4.4 * max(len(satirlar), 1)


def rapor_pdf(s: dict, evrak_durumu: dict[str, bool] | None = None, rapor_no: str | None = None) -> bytes:
    p = police_mod.police(s["police_no"])
    o, t, parcalar = s["olay"], s["taslak"], s["parcalar"]
    simdi = datetime.now()
    rapor_no = rapor_no or f"ÖD-{p['police_no'][-6:]}-{simdi:%Y%m%d-%H%M}"
    evrak_durumu = evrak_durumu or {}

    pdf = Rapor(rapor_no)
    pdf.add_page()

    # --- başlık bandı
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 34, "F")
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 34, 210, 1.4, "F")
    pdf.set_xy(16, 9)
    pdf.set_font("Noto", "B", 16)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "Kasko Hasar Ön Değerlendirme Raporu", **NL)
    pdf.set_x(16)
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(203, 213, 225)
    pdf.cell(0, 5, f"Rapor no: {rapor_no}   ·   Oluşturma: {simdi:%d.%m.%Y %H:%M}   ·   Acente asistanı (prototip)", **NL)
    pdf.set_y(42)

    # --- etiket kutusu
    ic, baslik, aciklama = ETIKET[s["etiket"]]
    yazi, zemin = RENK[s["etiket"]]
    y = pdf.get_y()
    pdf.set_fill_color(*zemin)
    pdf.set_draw_color(*yazi)
    pdf.rect(16, y, 178, 20, "DF")
    pdf.set_fill_color(*yazi)
    pdf.rect(16, y, 2.2, 20, "F")
    pdf.set_xy(22, y + 3)
    pdf.set_font("Noto", "B", 13)
    pdf.set_text_color(*yazi)
    pdf.cell(0, 6, baslik, **NL)
    pdf.set_x(22)
    pdf.set_font("Noto", "", 8.8)
    pdf.set_text_color(*INK)
    pdf.multi_cell(168, 4.6, aciklama, align="L", **NL)
    pdf.set_y(y + 23)

    # --- müşteri ve poliçe
    pdf.bolum("Müşteri ve poliçe")
    a = p["arac"]
    pdf.anahtar_deger([
        ("Sigortalı", f"{p['sigortali']['ad']} ({p['sigortali']['il']})"), ("Poliçe no", p["police_no"]),
        ("Ürün / tür", f"{urun_adi(p['urun'])} · {p['kasko_turu']}"), ("Paketler", ", ".join(p["paketler"])),
        ("Araç", f"{a['marka']} {a['model']} ({a['yil']}) · {a['plaka']} · {a['yakit']}"),
        ("Poliçe dönemi", f"{tr_tarih(p['baslangic'])} – {tr_tarih(p['bitis'])}"),
        ("Muafiyet", f"{p['muafiyet_tl']:,} TL".replace(",", ".") if p["muafiyet_tl"] else "Yok"),
        ("Yetkili sürücü", p["yetkili_surucu"]),
    ])

    # --- ihbar
    pdf.bolum("İhbar")
    pdf.set_font("Noto", "", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, f"İhbar tarihi: {tr_tarih(s.get('ihbar_tarihi') or simdi.date().isoformat())}", **NL)
    pdf.ln(1)
    pdf.kutu(f"“{s['ihbar']}”", stil="I")
    pdf.ln(1.5)
    pdf.set_font("Noto", "B", 8.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 4.6, f"Olay özeti: {o.ozet}", align="L", **NL)

    # --- olay bilgileri
    pdf.bolum("Olay bilgileri ve dayanakları")
    satirlar = [[k, v, (f"“{d}”" if d and d not in ("Acente beyanı", "yorum (LLM)") else d) or "— ihbarda yok"]
                for k, v, d in olay_satirlari(o)]
    pdf.tablo(["Alan", "Değer", "Dayanak"], satirlar, [52, 46, 80])

    # --- kontroller
    pdf.bolum("Poliçe kontrolleri (deterministik kod)")
    satirlar, renkler = [], []
    for k in s["kontroller"]:
        dayanak = ", ".join(temiz(parcalar[d]["atif"]) if d in parcalar else d for d in k.dayanak)
        satirlar.append([DURUM_YAZI[k.durum], kontrol_adi(k.ad), k.mesaj + (f"  [{dayanak}]" if dayanak else "")])
        renkler.append([RENK[k.durum][0], None, None])
    pdf.tablo(["Durum", "Kontrol", "Açıklama ve dayanak"], satirlar, [22, 40, 116], renkler)

    # --- acente beyanları ve açık sorular
    if s.get("beyanlar"):
        pdf.bolum("Acente beyanları")
        pdf.tablo(["Alan", "Beyan"], [[BEYAN_ADI.get(k, k), beyan_metni(k, v)] for k, v in s["beyanlar"].items()], [80, 98])
    if s["sorular"]:
        pdf.bolum("Açık sorular")
        pdf.set_font("Noto", "", 9)
        pdf.set_text_color(*INK)
        for i, q in enumerate(s["sorular"], 1):
            pdf.multi_cell(0, 5, f"{i}.  {q['soru']}", align="L", **NL)

    # --- not ve kaynaklar
    pdf.bolum("Ön değerlendirme notu")
    numara = atif_numaralari(t.gerekce, t.atiflar, parcalar)
    gerekce = ID_ETIKETI.sub(lambda m: f"[{numara[m.group(1)]}]" if m.group(1) in numara else "", t.gerekce)
    pdf.set_font("Noto", "", 9.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.4, gerekce, align="L", **NL)
    pdf.ln(1)
    pdf.set_font("Noto", "", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4, f"Otomatik denetim: {'geçti' if not s['denetim'] else 'UYARI: ' + '; '.join(s['denetim'])} · "
                         f"{s['tur']}. yazım · Atıflar ve alıntılar kod tarafından şart metinlerinde birebir doğrulanmıştır.", **NL)

    pdf.bolum("Kaynak maddeler")
    alintilar = {x.parca_id: x.alinti for x in t.atiflar}
    for pid, n in numara.items():
        if pdf.get_y() > 262:
            pdf.add_page()
        pdf.set_font("Noto", "B", 8.8)
        pdf.set_text_color(*TEAL)
        pdf.multi_cell(0, 4.6, f"[{n}]  {temiz(parcalar[pid]['atif'])}", align="L", **NL)
        if alintilar.get(pid):
            pdf.set_x(22)
            pdf.set_font("Noto", "I", 8.5)
            pdf.set_text_color(*INK)
            pdf.multi_cell(172, 4.4, f"“{alintilar[pid]}”", align="L", **NL)
        pdf.ln(1.5)

    # --- evraklar
    pdf.bolum("Gerekli evraklar")
    if t.gerekli_belgeler:
        alinan = sum(evrak_durumu.get(b, False) for b in t.gerekli_belgeler)
        pdf.tablo(["Durum", "Evrak"],
                  [["Alındı" if evrak_durumu.get(b) else "Eksik", b] for b in t.gerekli_belgeler], [22, 156],
                  [[RENK["uygun" if evrak_durumu.get(b) else "sorun"][0], None] for b in t.gerekli_belgeler])
        pdf.ln(1)
        pdf.set_font("Noto", "B", 8.5)
        tamam = alinan == len(t.gerekli_belgeler)
        pdf.set_text_color(*RENK["uygun" if tamam else "belirsiz"][0])
        pdf.cell(0, 5, f"{alinan}/{len(t.gerekli_belgeler)} evrak teslim alındı"
                       + (" · Dosya hasar birimine iletilmeye hazır." if tamam else " · Eksik evraklar tamamlanmalı."), **NL)
    else:
        pdf.kutu("Evrak listesi üretilmedi.")

    return bytes(pdf.output())
