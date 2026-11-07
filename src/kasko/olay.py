"""3a. İhbar metni -> yapılandırılmış olay (Haiku) -> kod doğrulaması -> acenteye eksik sorular.

İlkeler:
  - Üç değerli alanlar (evet / hayir / bilinmiyor): müşteri bir şeyden bahsetmediyse cevap "hayır" DEĞİL "bilinmiyor".
  - "evet"/"hayir" diyen her alan ihbardan BİREBİR alıntı göstermeli. Alıntı metinde yoksa kod alanı "bilinmiyor" yapar.
  - Hangi bilginin önemli olduğu olay türüne bağlı (park halindeyken sel -> alkol sorulmaz). Bu kural kodda.

Komut satırı:
  .venv/bin/python -m src.kasko.olay
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.kasko.belgeler import ROOT, sade

MODEL = "claude-haiku-5-5"

RiskKodu = Literal["CARPISMA", "UCUNCU_KISI_KOTU_NIYET", "YANMA", "CALINMA", "ANAHTAR_ELE_GECIRILMESI",
                   "SEL_SU_BASKINI", "DEPREM", "DIGER_DOGAL_AFET", "GLKHH_TEROR", "KISISEL_ESYA", "CAM", "DIGER"]


class Bulgu(BaseModel):
    deger: Literal["evet", "hayir", "bilinmiyor"]
    alinti: str = Field(description="İhbardan birebir kopyalanmış ifade. 'bilinmiyor' ise boş string.")


class Surucu(BaseModel):
    deger: Literal["sigortali", "baskasi", "bilinmiyor"]
    kim: str = Field(description="Başkasıysa kim olduğu (ör. 'kardeşi'), değilse boş string.")
    alinti: str


class Olay(BaseModel):
    ozet: str = Field(description="Olayın tek cümlelik tarafsız özeti.")
    risk_kodlari: list[RiskKodu] = Field(description="Olayın düştüğü teminat kodları (bir veya birkaç).")
    olay_tarihi: str = Field(description="YYYY-MM-DD. İhbar tarihine göre hesaplanır ('dün'). Belirsizse boş string.")
    olay_tarihi_alinti: str
    olay_saati: str = Field(description="HH:MM. Yalnız ihbarda saat AÇIKÇA yazıyorsa ('saat 10 gibi'); "
                                        "'akşam', 'gece' gibi ifadelerde boş string.")
    arac_hareket_halinde: Bulgu = Field(description="Olay anında araç sürülüyor muydu? Park halindeyse 'hayir'.")
    surucu: Surucu
    alkol_veya_madde: Bulgu = Field(description="Sürücü alkollü/uyuşturucu etkisinde miydi?")
    ehliyet: Bulgu = Field(description="Sürücünün geçerli sürücü belgesi (ehliyet) var mıydı? Söz edilmiyorsa bilinmiyor.")
    olay_yerinden_ayrilma: Bulgu = Field(description="Sürücü polis/tutanak olmadan olay yerinden ayrıldı mı?")
    resmi_bildirim: Bulgu = Field(description="Polise/jandarmaya bildirildi mi veya kaza tutanağı tutuldu mu?")
    arama_sorgulari: list[str] = Field(description="Sigorta sözleşmesi diliyle 2-4 kısa arama sorgusu. "
                                                   "Müşterinin kelimeleriyle değil, şart metinlerindeki terimlerle.")


RISK_TANIMLARI = {
    "CARPISMA": "aracın başka bir araçla veya sabit/duran bir cisimle (direk, duvar, bariyer) çarpışması; park hâlindeyken başka aracın çarpması dahil",
    "UCUNCU_KISI_KOTU_NIYET": "vandalizm: aracın çizilmesi, ayna/far kırılması, lastik kesilmesi, boya dökülmesi (çalınma amacı olmadan)",
    "YANMA": "aracın yanması, tutuşması",
    "CALINMA": "aracın kendisinin veya parçasının çalınması ya da çalınmaya teşebbüs",
    "ANAHTAR_ELE_GECIRILMESI": "aracın, ele geçirilen/çalınan/unutulan anahtarı kullanılarak çalınması",
    "SEL_SU_BASKINI": "sel, su baskını, aracın su altında kalması veya motora su girmesi",
    "DEPREM": "deprem",
    "DIGER_DOGAL_AFET": "dolu, fırtına, toprak kayması, yıldırım, yanardağ",
    "GLKHH_TEROR": "grev, lokavt, kargaşalık, halk hareketleri, terör",
    "KISISEL_ESYA": "araç içindeki kişisel eşyaların zarar görmesi/çalınması",
    "CAM": "yalnızca cam kırılması/çatlaması (taş sıçraması vb.)",
    "DIGER": "yukarıdakilerin hiçbirine uymuyorsa",
}

SISTEM = """Sen bir kasko hasar ihbarı ön işleme asistanısın. Görevin yalnızca ihbar metnindeki BİLGİYİ yapılandırmak; \
teminat kararı vermiyorsun.

Kurallar:
- Metinde açıkça geçmeyen hiçbir şeyi varsayma. Müşteri bir konudan bahsetmediyse değer "bilinmiyor", alıntı boş.
  Örnek: alkolden hiç söz edilmiyorsa alkol_veya_madde = bilinmiyor (hayir DEĞİL).
- "evet", "hayir", "sigortali", "baskasi" dediğin her alan için alıntıyı ihbardan KELİMESİ KELİMESİNE kopyala.
- Araç park halindeyken olan olaylarda (sel, park halinde çarpılma, çalınma) arac_hareket_halinde = hayir.
- Sigortalı "ben kullanıyordum", "çarptım" gibi birinci tekil konuşuyorsa sürücü = sigortali.
- surucu, alkol_veya_madde, ehliyet, olay_yerinden_ayrilma alanları SİGORTALI ARACIN sürücüsüyle ilgilidir.
  Karşı tarafın davranışı bu alanlara girmez: "birisi aracıma çarpıp kaçmış" -> olay_yerinden_ayrilma = bilinmiyor.
- arama_sorgulari sigorta terminolojisiyle olmalı. Örnek: "su dolmuş" -> "sel ve su baskını hasarı";
  "anahtarı masada unuttum, aracı aldılar" -> "araç anahtarının ele geçirilmesi suretiyle çalınma".
- risk_kodlari aşağıdaki tanımlara göre seçilir; araç çalınmadıysa CALINMA seçme. Hasarın ASIL nedenini seç:
  doğal afetin yol açtığı ikincil olaylar (depremde duvar çökmesi, fırtınada ağaç devrilmesi) yalnız afet
  kodudur, ayrıca CARPISMA eklenmez:
""" + "\n".join(f"  {k}: {v}" for k, v in RISK_TANIMLARI.items())


def cikar(ihbar: str, ihbar_tarihi: str | None = None) -> Olay:
    """LLM çıkarımı. Doğrulanmamış ham çıktıyı döndürür; doğrulama ayrı (dogrula)."""
    import anthropic
    load_dotenv(ROOT / ".env")
    istemci = anthropic.Anthropic()
    yanit = istemci.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SISTEM,
        messages=[{"role": "user", "content": f"İhbar tarihi: {ihbar_tarihi or date.today().isoformat()}\n\n"
                                              f"İhbar metni:\n<ihbar>\n{ihbar}\n</ihbar>"}],
        output_format=Olay,
    )
    return yanit.parsed_output


# --------------------------------------------------------------------------------------- kod doğrulaması
def _alinti_var(alinti: str, metin: str) -> bool:
    return bool(alinti.strip()) and sade(alinti) in sade(metin)


def dogrula(olay: Olay, ihbar: str) -> tuple[Olay, list[str]]:
    """Alıntısı metinde bulunmayan her iddiayı 'bilinmiyor'a düşürür. Ne düzeltildiğini de söyler."""
    o = olay.model_copy(deep=True)
    notlar = []
    for alan in ("arac_hareket_halinde", "alkol_veya_madde", "ehliyet", "olay_yerinden_ayrilma", "resmi_bildirim",
                 "surucu"):
        b = getattr(o, alan)
        if b.deger != "bilinmiyor" and not _alinti_var(b.alinti, ihbar):
            notlar.append(f"{alan}: '{b.deger}' dendi ama alıntı metinde yok ({b.alinti!r}) -> bilinmiyor")
            b.deger, b.alinti = "bilinmiyor", ""
            if alan == "surucu":
                b.kim = ""
    if o.olay_tarihi and not _alinti_var(o.olay_tarihi_alinti, ihbar):
        notlar.append(f"olay_tarihi: '{o.olay_tarihi}' dayanaksız ({o.olay_tarihi_alinti!r}) -> boş")
        o.olay_tarihi, o.olay_tarihi_alinti = "", ""
    if o.olay_saati and (not o.olay_tarihi or not re.fullmatch(r"\d{2}:\d{2}", o.olay_saati)
                         or int(o.olay_saati[:2]) not in {int(x) for x in re.findall(r"\d{1,2}", ihbar)}):
        notlar.append(f"olay_saati: '{o.olay_saati}' ihbarda açıkça yok -> boş")
        o.olay_saati = ""
    return o, notlar


ACENTE = "Acente beyanı"
BULGU_ALANLARI = ("arac_hareket_halinde", "alkol_veya_madde", "ehliyet", "olay_yerinden_ayrilma", "resmi_bildirim")


def beyan_uygula(olay: Olay, beyanlar: dict) -> Olay:
    """Acentenin form cevaplarını ilgili alanlara yazar (LLM yok). Kaynak 'Acente beyanı' olarak işaretlenir.
    Poliçe kontrolüne ait beyanlar (surucu_yetkili, zorunlu_neden) burada değil police.kontrol_et'te kullanılır."""
    o = olay.model_copy(deep=True)
    for alan in BULGU_ALANLARI:
        if beyanlar.get(alan) in ("evet", "hayir"):
            setattr(o, alan, Bulgu(deger=beyanlar[alan], alinti=ACENTE))
    if beyanlar.get("olay_tarihi"):
        o.olay_tarihi, o.olay_tarihi_alinti = beyanlar["olay_tarihi"], ACENTE
    if beyanlar.get("olay_saati"):
        o.olay_saati = beyanlar["olay_saati"]
    if isinstance(beyanlar.get("surucu"), dict) and beyanlar["surucu"].get("deger") in ("sigortali", "baskasi"):
        s = beyanlar["surucu"]
        o.surucu = Surucu(deger=s["deger"], kim=s.get("kim", ""), alinti=ACENTE)
    return o


# --------------------------------------------------------------------------------------- ilgililik kuralı
SURUS_RISKLERI = {"CARPISMA"}                                  # doğası gereği araç sürülürken olur
HAREKET_SORULACAK = {"SEL_SU_BASKINI", "DIGER_DOGAL_AFET", "DEPREM", "YANMA", "CAM", "UCUNCU_KISI_KOTU_NIYET"}
BILDIRIM_GEREKEN = {"CALINMA", "ANAHTAR_ELE_GECIRILMESI", "UCUNCU_KISI_KOTU_NIYET", "GLKHH_TEROR", "CARPISMA"}


def ilgili_alanlar(o: Olay) -> list[str]:
    """Bu olay için önemli olan alanlar. Park halindeki selde sürücü/alkol yoktur."""
    riskler = set(o.risk_kodlari)
    alanlar = ["olay_tarihi"]
    hareket = o.arac_hareket_halinde.deger
    if riskler & HAREKET_SORULACAK and hareket == "bilinmiyor":
        alanlar.append("arac_hareket_halinde")
    surus = hareket == "evet" or (hareket == "bilinmiyor" and riskler & SURUS_RISKLERI)
    if surus:
        alanlar += ["surucu", "alkol_veya_madde", "olay_yerinden_ayrilma"]
        if o.surucu.deger != "sigortali":      # başkası/bilinmiyor: ehliyet de önemli (GŞ A.5/5.4)
            alanlar.append("ehliyet")
    if riskler & BILDIRIM_GEREKEN:
        alanlar.append("resmi_bildirim")
    return alanlar


SORULAR = {
    "olay_tarihi": "Olay hangi tarihte meydana geldi?",
    "arac_hareket_halinde": "Olay anında araç park halinde miydi, yoksa sürülüyor muydu?",
    "surucu": "Olay anında aracı kim kullanıyordu?",
    "alkol_veya_madde": "Sürücünün olay anında alkol veya uyuşturucu madde etkisinde olup olmadığı biliniyor mu?",
    "ehliyet": "Olay anında aracı kullanan kişinin geçerli bir sürücü belgesi (ehliyet) var mıydı?",
    "olay_yerinden_ayrilma": "Sürücü, kaza tutanağı tutulmadan veya polis gelmeden olay yerinden ayrıldı mı?",
    "resmi_bildirim": "Olay polise/jandarmaya bildirildi mi veya kaza tespit tutanağı tutuldu mu?",
}


def eksik_sorular(o: Olay) -> list[tuple[str, str]]:
    """İlgili olup bilinmeyen alanlar için acenteye sorulacak sorular."""
    sorular = []
    for alan in ilgili_alanlar(o):
        bilinmiyor = (not o.olay_tarihi) if alan == "olay_tarihi" else getattr(o, alan).deger == "bilinmiyor"
        if bilinmiyor:
            sorular.append((alan, SORULAR[alan]))
    return sorular


# --------------------------------------------------------------------------------------- demo
ORNEKLER = [
    ("Mehmet (sel)", "Sağanak yağmurda araç sokakta park halindeydi, sabah baktığımda motor bölmesine kadar su dolmuştu."),
    ("Burak (çarpışma)", "Dün akşam Gebze'de kavşakta önümdeki araç ani fren yaptı, arkadan çarptık. Ön tampon ve "
                         "far kırıldı. O sırada aracı kardeşim kullanıyordu, ben yanında oturuyordum."),
    ("Ayşe (alkol)", "Cumartesi gece arkadaşlarla içtikten sonra eve dönerken direğe çarptım. Kimse yoktu, "
                     "polisi beklemeden eve gittim."),
]

if __name__ == "__main__":
    for ad, metin in ORNEKLER[: int(sys.argv[1]) if len(sys.argv) > 1 else None]:
        ham = cikar(metin, "2026-11-07")
        o, notlar = dogrula(ham, metin)
        print(f"\n{'=' * 100}\n{ad}: {metin}\n{'-' * 100}")
        print(json.dumps(o.model_dump(), ensure_ascii=False, indent=2))
        print("DOĞRULAMA:", notlar or "düzeltme yok")
        print("İLGİLİ ALANLAR:", ilgili_alanlar(o))
        print("ACENTEYE SORULAR:", [s for _, s in eksik_sorular(o)] or "yok")
