"""Poliçe kontrolleri: LLM yok, elle kurulmuş olaylar. Her senaryo, kontrol adı -> beklenen durum."""
import pytest

from src.kasko.belgeler import tum_parcalar
from src.kasko.police import SENARYOLAR, kontrol_et, olay_yap, police

BEKLENEN = {
    "Mehmet: park halinde sel": {"Poliçe dönemi": "uygun", "Teminat: SEL_SU_BASKINI": "uygun", "Muafiyet": "bilgi"},
    "Mehmet: deprem": {"Teminat: DEPREM": "sorun"},
    "Ayşe: deprem (aynı olay, geniş poliçe)": {"Teminat: DEPREM": "uygun"},
    "Zeynep: çalınma": {"Teminat: CALINMA": "sorun"},
    "Ali: çarpışma (LPG)": {"LPG": "sorun", "Teminat: CARPISMA": "uygun"},
    "Elif: 3 Kasım çarpışma": {"Poliçe dönemi": "sorun"},
    "Elif: 15 Ekim çarpışma (bitiş günü)": {"Poliçe dönemi": "belirsiz"},
    "Burak: kardeşi kullanıyordu": {"Yetkili sürücü": "sorun"},
    "Burak: eşi kullanıyordu": {"Yetkili sürücü": "uygun"},
    "Ayşe: alkollü + yeri terk": {"İstisna: alkol/madde": "sorun", "İstisna: kaza yerini terk": "sorun"},
}


@pytest.mark.parametrize("baslik,no,olay", SENARYOLAR, ids=[s[0] for s in SENARYOLAR])
def test_senaryo(baslik, no, olay):
    sonuc = {k.ad: k.durum for k in kontrol_et(police(no), olay)}
    for ad, durum in BEKLENEN[baslik].items():
        assert sonuc.get(ad) == durum, f"{ad}: {sonuc.get(ad)} != {durum}  (tümü: {sonuc})"


def test_dayanaklar_dizinde_var():
    """Kodun gösterdiği her dayanak gerçekten var olan bir parça olmalı (uydurma atıf olamaz)."""
    gecerli = {p.id for p in tum_parcalar()}
    for _, no, olay in SENARYOLAR:
        for k in kontrol_et(police(no), olay):
            assert set(k.dayanak) <= gecerli, k


def test_tarih_yoksa_belirsiz_ve_soru():
    k = kontrol_et(police("RS-K-2026-000101"), olay_yap(["CARPISMA"], tarih=""))[0]
    assert k.durum == "belirsiz" and k.soru


def test_park_halinde_surucu_kontrolu_yok():
    """Burak'ın sürücü kısıtı var ama araç park hâlindeyken çalındıysa sürücü sorulmaz."""
    ad = {k.ad for k in kontrol_et(police("RS-K-2026-000106"), olay_yap(["CALINMA"], hareket="hayir", surucu_="bilinmiyor"))}
    assert "Yetkili sürücü" not in ad


def test_kardes_es_sanilmaz():
    k = [k for k in kontrol_et(police("RS-K-2026-000106"), olay_yap(["CARPISMA"], surucu_="baskasi", kim="kardeşim"))
         if k.ad == "Yetkili sürücü"][0]
    assert k.durum == "sorun"


def test_park_halinde_surucu_istisnasi_uygulanmaz():
    """'Birisi park hâlindeki aracıma çarpıp kaçmış': LLM yeri terk=evet dese bile A.5/5.10 işaretlenmez."""
    o = olay_yap(["CARPISMA"], hareket="hayir", surucu_="bilinmiyor", terk="evet", alkol="evet")
    assert not [k for k in kontrol_et(police("RS-K-2026-000101"), o) if k.ad.startswith("İstisna")]


def test_bitis_gunu_saat_belirleyici():
    p = police("RS-K-2025-000105")                       # bitiş 2026-10-15
    o = olay_yap(["CARPISMA"], tarih="2026-10-15")
    assert kontrol_et(p, o)[0].soru_alan == "olay_saati"
    o.olay_saati = "10:30"
    assert kontrol_et(p, o)[0].durum == "uygun"          # öğleden önce: dönem içinde
    o.olay_saati = "14:00"
    assert kontrol_et(p, o)[0].durum == "sorun"          # öğleden sonra: dönem bitmiş


def test_acente_surucu_teyidi():
    p, o = police("RS-K-2026-000106"), olay_yap(["CARPISMA"], surucu_="baskasi", kim="kardeşi")
    durum = lambda beyan: [k for k in kontrol_et(p, o, beyan) if k.ad == "Yetkili sürücü"][0]
    assert durum({}).soru_alan == "surucu_yetkili"
    assert durum({"surucu_yetkili": "evet"}).durum == "uygun"
    k = durum({"surucu_yetkili": "hayir"})
    assert k.durum == "sorun" and not k.soru


def test_ehliyetsiz_istisna():
    ad = {k.ad: k for k in kontrol_et(police("RS-K-2026-000101"), olay_yap(["CARPISMA"], ehliyet="hayir"))}
    assert ad["İstisna: ehliyetsiz sürücü"].dayanak == ["GS_A.5_5.4"]
