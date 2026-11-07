"""Olay doğrulama ve ilgililik kuralı: LLM çıktısı elle taklit ediliyor."""
from src.kasko.olay import ACENTE, beyan_uygula, dogrula, eksik_sorular, ilgili_alanlar
from src.kasko.police import olay_yap

IHBAR = "Gece direğe çarptım, polis gelmeden eve gittim."


def test_alintisiz_iddia_bilinmiyor_olur():
    o = olay_yap(["CARPISMA"])
    o.alkol_veya_madde.deger, o.alkol_veya_madde.alinti = "hayir", "hiç içmemiştim"    # metinde yok: uydurma
    o.olay_yerinden_ayrilma.deger, o.olay_yerinden_ayrilma.alinti = "evet", "polis gelmeden eve gittim"
    o.surucu.alinti = "direğe çarptım"
    o.olay_tarihi_alinti = "Gece"
    o.arac_hareket_halinde.alinti = "direğe çarptım"
    d, notlar = dogrula(o, IHBAR)
    assert d.alkol_veya_madde.deger == "bilinmiyor"           # sessizlik "hayır" değildir
    assert d.olay_yerinden_ayrilma.deger == "evet"            # alıntı metinde var: korunur
    assert len(notlar) == 1


def test_bosluk_ve_buyuk_harf_farki_alintiyi_bozmaz():
    o = olay_yap(["CARPISMA"])
    o.olay_yerinden_ayrilma.deger, o.olay_yerinden_ayrilma.alinti = "evet", "POLİS gelmeden  eve gittim"
    for b in (o.surucu, o.arac_hareket_halinde):
        b.alinti = "direğe çarptım"
    o.olay_tarihi_alinti = "Gece"
    d, _ = dogrula(o, IHBAR)
    assert d.olay_yerinden_ayrilma.deger == "evet"


def test_beyan_uygula_alanlari_gunceller_ve_kaynagi_isaretler():
    o = olay_yap(["CARPISMA"], tarih="", surucu_="bilinmiyor")
    y = beyan_uygula(o, {"olay_tarihi": "2026-11-01", "alkol_veya_madde": "hayir",
                         "surucu": {"deger": "baskasi", "kim": "oğlu"}})
    assert y.olay_tarihi == "2026-11-01" and y.alkol_veya_madde.deger == "hayir"
    assert y.alkol_veya_madde.alinti == ACENTE and y.surucu.kim == "oğlu"
    assert o.olay_tarihi == ""                                # orijinal olay değişmez
    assert "alkol_veya_madde" not in [a for a, _ in eksik_sorular(y)]


def test_saat_ihbarda_yoksa_silinir():
    o = olay_yap(["CARPISMA"], tarih="2026-11-06")
    o.olay_tarihi_alinti, o.olay_saati = "Dün akşam", "19:00"   # "akşam" -> 19:00 uydurması
    d, notlar = dogrula(o, "Dün akşam direğe çarptım")
    assert d.olay_tarihi == "2026-11-06" and d.olay_saati == ""


def test_park_halinde_selde_alkol_sorulmaz():
    o = olay_yap(["SEL_SU_BASKINI"], hareket="hayir", surucu_="bilinmiyor", tarih="")
    assert "alkol_veya_madde" not in ilgili_alanlar(o)
    assert [a for a, _ in eksik_sorular(o)] == ["olay_tarihi"]


def test_carpismada_surucu_alanlari_ilgili():
    o = olay_yap(["CARPISMA"], hareket="bilinmiyor", surucu_="bilinmiyor")
    alanlar = ilgili_alanlar(o)
    assert {"surucu", "alkol_veya_madde", "ehliyet", "olay_yerinden_ayrilma", "resmi_bildirim"} <= set(alanlar)


def test_sigortali_kendisi_suruyorsa_ehliyet_sorulmaz():
    assert "ehliyet" not in ilgili_alanlar(olay_yap(["CARPISMA"], surucu_="sigortali"))


def test_selde_hareket_bilinmiyorsa_sorulur():
    o = olay_yap(["SEL_SU_BASKINI"], hareket="bilinmiyor", surucu_="bilinmiyor")
    assert "arac_hareket_halinde" in ilgili_alanlar(o)
