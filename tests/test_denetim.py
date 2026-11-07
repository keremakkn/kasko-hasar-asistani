"""Yazım denetimi: kasıtlı bozulmuş taslaklarla. Yeniden yazım döngüsünün tetikleyicisi bu fonksiyon."""
from src.kasko.degerlendirme import Atif, Taslak, denetim_hatalari, etiket_hesapla
from src.kasko.police import Kontrol

PARCALAR = {
    "GS_A.5_5.5": {"metin": "Aracın, uyuşturucu madde veya Karayolları Trafik Yönetmeliğinde belirlenen seviyenin "
                            "üzerinde alkollü içki almış kişiler tarafından kullanılması sırasında meydana gelen zararlar"},
    "BK_belgeler_1": {"metin": "Trafik kazası tespit tutanağı  Alkol raporu  Ruhsat fotokopisi  Ehliyet fotokopisi"},
}
BELGE = ["BK_belgeler_1"]


def taslak(gerekce="Alkollü kullanım teminat dışı hâller arasında sayılıyor [GS_A.5_5.5].",
           atiflar=(("GS_A.5_5.5", "alkollü içki almış kişiler"),), belgeler=("Alkol raporu",)):
    return Taslak(gerekce=gerekce, atiflar=[Atif(parca_id=i, alinti=a) for i, a in atiflar], gerekli_belgeler=list(belgeler))


def test_temiz_taslak_gecer():
    assert denetim_hatalari(taslak(), PARCALAR, BELGE) == []


def test_uydurma_id_yakalanir():
    h = denetim_hatalari(taslak(gerekce="Kapsam dışı hâl [GS_A.5_5.99]."), PARCALAR, BELGE)
    assert any("GS_A.5_5.99" in x for x in h)


def test_atifsiz_gerekce_yakalanir():
    assert any("hiç" in x for x in denetim_hatalari(taslak(gerekce="Uzman incelemeli."), PARCALAR, BELGE))


def test_uydurma_alinti_yakalanir():
    h = denetim_hatalari(taslak(atiflar=(("GS_A.5_5.5", "alkollü araç kullanımı her durumda teminat dışıdır"),)),
                         PARCALAR, BELGE)
    assert any("birebir yok" in x for x in h)


def test_sartlarda_olmayan_evrak_yakalanir():
    h = denetim_hatalari(taslak(belgeler=("Noter onaylı vekaletname",)), PARCALAR, BELGE)
    assert any("vekaletname" in x for x in h)


def test_karar_dili_yakalanir():
    h = denetim_hatalari(taslak(gerekce="Hasar ödenmeyecektir [GS_A.5_5.5]."), PARCALAR, BELGE)
    assert any("ödenmeyecek" in x for x in h)


def test_tirnak_icindeki_sart_alintisi_karar_dili_sayilmaz():
    g = 'Klozda "tazminat orana göre ödenecek" deniyor; uzman değerlendirmesi gerekir [GS_A.5_5.5].'
    assert denetim_hatalari(taslak(gerekce=g), PARCALAR, BELGE) == []


def test_park_halinde_surucu_evraki_yakalanir():
    h = denetim_hatalari(taslak(belgeler=("Ehliyet fotokopisi", "Ruhsat fotokopisi")), PARCALAR, BELGE, park_halinde=True)
    assert len(h) == 1 and "Ehliyet" in h[0]


def test_etiket_onceligi():
    k = lambda ad, d: Kontrol(ad, d, "")
    assert etiket_hesapla([k("Teminat: DEPREM", "sorun"), k("Yetkili sürücü", "sorun")], []) == "kapsam_disi"
    assert etiket_hesapla([k("Teminat: CARPISMA", "uygun"), k("LPG", "sorun")], []) == "uzman"
    assert etiket_hesapla([k("Teminat: CARPISMA", "uygun")], ["soru?"]) == "ek_bilgi"
    assert etiket_hesapla([k("Teminat: CARPISMA", "uygun"), k("Muafiyet", "bilgi")], []) == "kapsamda"
