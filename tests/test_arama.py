"""Arama: gerçek embedding modeliyle (ilk çalıştırma yavaş). Ürün filtresi ve bilinen sorguların isabeti."""
from src.kasko.arama import ara, sorgu_kokleri


def ilk(soru, urun, n=6):
    return [r["id"] for r in ara(soru, urun, sonuc_sayisi=n) if not r["kardes"]]


def test_urun_filtresi_baska_urunun_klozunu_getirmez():
    for r in ara("Deprem sırasında aracın üzerine bina duvarı çöktü", "benim_uygun_kaskom"):
        assert not r["id"].startswith("BK_"), r["id"]


def test_sozlesme_diliyle_sel_klozu_ilk_ucte():
    assert any("sel" in i for i in ilk("Sel ve su baskını nedeniyle araçta oluşan hasar", "benim_uygun_kaskom", 3))


def test_alkol_istisnasi_ilk_ikide():
    assert "GS_A.5_5.5" in ilk("Gece alkollüyken direğe çarptım, polis gelmeden olay yerinden ayrıldım", "benim_kaskom", 2)


def test_turkce_kok():
    assert "alkol" in sorgu_kokleri("alkollüydüm")
