import streamlit as st
import pandas as pd
import random
import time
import plotly.express as px
import os
import json
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- AYARLAR ---
st.set_page_config(page_title="AHAL TEKE Tenis Kulubü", layout="wide")

# GÜN SÖZLÜĞÜ
GUNLER_MAP = {
    0: 'Pazartesi', 1: 'Salı', 2: 'Çarşamba',
    3: 'Perşembe', 4: 'Cuma', 5: 'Cumartesi', 6: 'Pazar'
}

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def init_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

    if "GOOGLE_JSON" in os.environ:
        creds_dict = json.loads(os.environ["GOOGLE_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    elif "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        st.error("Hata: Google şifreleri bulunamadı!")
        st.stop()

    client = gspread.authorize(creds)
    return client

def get_data():
    client = init_connection()
    sh = client.open("tenis_db")
    return sh

# --- YARDIMCI FONKSİYONLAR ---
def veri_getir_df():
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    data = wks.get_all_records()
    if not data: return pd.DataFrame()
    return pd.DataFrame(data)

def yoneticileri_getir():
    sh = get_data()
    try:
        wks = sh.worksheet("yoneticiler")
        return wks.get_all_records()
    except:
        return []

def yeni_yonetici_ekle(kadi, sifre):
    sh = get_data()
    wks = sh.worksheet("yoneticiler")
    wks.append_row([kadi, sifre])

def sifre_guncelle(kadi, yeni_sifre):
    sh = get_data()
    wks = sh.worksheet("yoneticiler")
    cell = wks.find(kadi)
    if cell:
        wks.update_cell(cell.row, 2, yeni_sifre)

# --- OTOMATİK KONTROL SİSTEMİ (GÜNCELLENDİ: Tatil Günleri Eklendi) ---
def sistem_kontrol_sessiz_gs():
    sh = get_data()
    wks_uye = sh.worksheet("uyelikler")

    try:
        wks_gecmis = sh.worksheet("ders_gecmisi")
    except:
        wks_gecmis = sh.add_worksheet(title="ders_gecmisi", rows=1000, cols=3)
        wks_gecmis.append_row(["uye_id", "tarih", "islem_tipi"])

    # YENİ: Tatiller sayfasını bul veya oluştur
    try:
        wks_tatil = sh.worksheet("tatiller")
    except:
        wks_tatil = sh.add_worksheet(title="tatiller", rows=100, cols=1)
        wks_tatil.append_row(["tarih"])
        
    tatil_kayitlari = wks_tatil.get_all_records()
    tatiller = set(str(r['tarih']) for r in tatil_kayitlari if r.get('tarih'))

    uyeler = wks_uye.get_all_records()
    gecmis = wks_gecmis.get_all_records()

    gecmis_set = set()
    for g in gecmis:
        gecmis_set.add(f"{g['uye_id']}_{g['tarih']}")

    bugun = datetime.now().date()

    for i, uye in enumerate(uyeler):
        row_num = i + 2
        try:
            kalan = int(uye['kalan_hak'])
        except:
            continue

        if kalan <= 0: continue

        try:
            try:
                baslangic = datetime.strptime(str(uye['baslangic_tarihi']), "%Y-%m-%d").date()
            except:
                baslangic = datetime.strptime(str(uye['baslangic_tarihi']), "%d.%m.%Y").date()
        except:
            continue

        gunler = str(uye['gunler'])
        if not gunler: continue
        secilen_gunler = gunler.split(',')

        gecen_gun = (bugun - baslangic).days
        if gecen_gun < 0: continue  

        dusulecek = 0

        for j in range(gecen_gun + 1):
            tarih = baslangic + timedelta(days=j)
            if tarih > bugun: continue

            gun_int = tarih.weekday()
            gun_tr = GUNLER_MAP[gun_int] 
            t_str = tarih.strftime("%Y-%m-%d")

            # YENİ EKLENEN KISIM: Eğer bu tarih tatiller listesindeyse bugünü atla (düşme yapma)
            if t_str in tatiller:
                continue

            if gun_tr in secilen_gunler:
                key = f"{uye['id']}_{t_str}"
                if key not in gecmis_set:
                    dusulecek += 1
                    wks_gecmis.append_row([uye['id'], t_str, 'Otomatik'])
                    gecmis_set.add(key)

        if dusulecek > 0:
            yeni_hak = max(0, kalan - dusulecek)
            wks_uye.update_cell(row_num, 9, yeni_hak)

def yeni_uye_ekle_gs(ad, tel, cins, dt, bas, bitis, ucret, yontem, gunler_list, ders_tipi, hak_sayisi, veli_adi, kategori):
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    yeni_id = int(time.time())
    g_str = ",".join(gunler_list)
    hak = int(hak_sayisi)

    row = [
        yeni_id, ad, tel, cins, str(dt), str(bas), str(bitis),
        hak, hak, ucret, yontem, g_str, ders_tipi, veli_adi, "Aktif", kategori
    ]
    wks.append_row(row)

    try:
        sistem_kontrol_sessiz_gs()
    except:
        pass

def uye_guncelle_gs(uye_id, ad, tel, dt_str, paket_tipi, toplam_hak, kalan_hak, veli_adi, kategori):
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    cell = wks.find(str(uye_id))
    if cell:
        wks.update_cell(cell.row, 2, ad)
        wks.update_cell(cell.row, 3, tel)
        wks.update_cell(cell.row, 5, dt_str) 
        wks.update_cell(cell.row, 8, toplam_hak)
        wks.update_cell(cell.row, 9, kalan_hak)
        wks.update_cell(cell.row, 13, paket_tipi)
        wks.update_cell(cell.row, 14, veli_adi)
        wks.update_cell(cell.row, 16, kategori) 

def uye_sil_gs(uye_id):
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    cell = wks.find(str(uye_id))
    if cell:
        wks.delete_rows(cell.row)

def manuel_islem_gs(uye_id, miktar):
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    cell = wks.find(str(uye_id))
    if cell:
        kalan_hak_col = 9
        mevcut = int(wks.cell(cell.row, kalan_hak_col).value)
        yeni = max(0, mevcut + miktar)
        wks.update_cell(cell.row, kalan_hak_col, yeni)

def uyelik_yenile_gs(uye_id, eklenecek_hak, manuel_bitis_tarihi=None):
    sh = get_data()
    wks = sh.worksheet("uyelikler")
    cell = wks.find(str(uye_id))
    if cell:
        bugun = str(datetime.now().date())
        if manuel_bitis_tarihi:
            yeni_bitis = str(manuel_bitis_tarihi)
        else:
            yeni_bitis = str((datetime.now() + timedelta(days=30)).date())

        mevcut_kalan = int(wks.cell(cell.row, 9).value)
        yeni_toplam_bakiye = mevcut_kalan + eklenecek_hak

        wks.update_cell(cell.row, 6, bugun)
        wks.update_cell(cell.row, 7, yeni_bitis)
        wks.update_cell(cell.row, 8, eklenecek_hak)
        wks.update_cell(cell.row, 9, yeni_toplam_bakiye)

def yas_hesapla(dt_str):
    if not dt_str: return 0
    try:
        try:
            dt = datetime.strptime(str(dt_str), "%Y-%m-%d")
        except:
            dt = datetime.strptime(str(dt_str), "%d.%m.%Y")
        bugun = datetime.now()
        yas = bugun.year - dt.year - ((bugun.month, bugun.day) < (dt.month, dt.day))
        return yas
    except:
        return 0

# --- GİRİŞ MANTIĞI ---
def giris_kontrol(kadi_girilen, sifre_girilen):
    yoneticiler = yoneticileri_getir()
    for y in yoneticiler:
        if str(y['kullanici_adi']) == kadi_girilen and str(y['sifre']) == sifre_girilen:
            return True
    return False

query_params = st.query_params
if "durum" in query_params and query_params["durum"] == "giris_ok":
    st.session_state.giris_yapildi = True
    st.session_state.aktif_kullanici = query_params.get("user", "Admin")
elif 'giris_yapildi' not in st.session_state:
    st.session_state.giris_yapildi = False
    st.session_state.aktif_kullanici = ""

# --- LOGIN EKRANI ---
if not st.session_state.giris_yapildi:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        sub_c1, sub_c2, sub_c3 = st.columns([5, 3, 5])
        with sub_c2:
            if os.path.exists("logo.png"):
                st.image("logo.png", use_container_width=True)
            else:
                st.markdown("<h1 style='text-align: center; font-size: 80px;'>🎾</h1>", unsafe_allow_html=True)

        st.markdown("<h3 style='text-align: center;'>AHAL TEKE Yönetim Paneli</h3>", unsafe_allow_html=True)
        st.write("")

        with st.container(border=True):
            kadi = st.text_input("Kullanıcı Adı")
            sifre = st.text_input("Şifre", type="password")
            if st.button("Giriş Yap", type="primary", use_container_width=True):
                if giris_kontrol(kadi, sifre):
                    st.session_state.giris_yapildi = True
                    st.session_state.aktif_kullanici = kadi
                    st.query_params["durum"] = "giris_ok"
                    st.query_params["user"] = kadi
                    st.success("Giriş başarılı!")
                    time.sleep(0.5);
                    st.rerun()
                else:
                    st.error("Hatalı bilgiler! (Lütfen Google Sheet 'yoneticiler' sayfasını kontrol edin)")
    st.stop()

# --- SIDEBAR (GÜNCELLENDİ: Tatiller Sekmesi Eklendi) ---
with st.sidebar:
    st.write(f"👤 Yönetici: **{st.session_state.aktif_kullanici}**")
    st.info("🟢 Bağlantı: Google Sheets (Online)")

    with st.expander("⚙️ Yönetici Ayarları"):
        tab_admin1, tab_admin2, tab_admin3 = st.tabs(["🔑 Şifre", "➕ Yeni", "🏖️ Tatiller"])

        with tab_admin1:
            st.caption("Mevcut kullanıcının şifresini değiştir")
            with st.form("sifre_degis_form", clear_on_submit=True):
                yeni_pass = st.text_input("Yeni Şifre", type="password")
                submitted = st.form_submit_button("Şifreyi Güncelle")
                if submitted:
                    if yeni_pass:
                        sifre_guncelle(st.session_state.aktif_kullanici, yeni_pass)
                        st.success("Şifre değişti!")
                        time.sleep(1)
                    else:
                        st.error("Şifre boş olamaz")

        with tab_admin2:
            st.caption("Yeni yönetici ekle")
            with st.form("yeni_yonetici_form", clear_on_submit=True):
                new_admin_user = st.text_input("Kullanıcı Adı")
                new_admin_pass = st.text_input("Şifre")
                submitted_new = st.form_submit_button("Yönetici Ekle")
                if submitted_new:
                    if new_admin_user and new_admin_pass:
                        yeni_yonetici_ekle(new_admin_user, new_admin_pass)
                        st.success(f"{new_admin_user} eklendi!")
                        time.sleep(1)
                    else:
                        st.error("Bilgileri eksiksiz girin")
        
        with tab_admin3:
            st.caption("Ders düşülmeyecek günleri ekleyin.")
            try:
                sh_t = get_data()
                wks_t = sh_t.worksheet("tatiller")
                mevcut_tatiller = [str(r['tarih']) for r in wks_t.get_all_records() if r.get('tarih')]
            except:
                mevcut_tatiller = []
            
            if mevcut_tatiller:
                st.write("**Mevcut Tatiller:**")
                for t in mevcut_tatiller:
                    st.markdown(f"- `{t}`")
            else:
                st.info("Kayıtlı tatil yok.")

            yeni_tatil = st.date_input("Tatil Günü Seç", datetime.now(), format="DD/MM/YYYY")
            if st.button("Tatil Ekle", use_container_width=True):
                t_str = str(yeni_tatil)
                if t_str not in mevcut_tatiller:
                    try:
                        wks_t = sh_t.worksheet("tatiller")
                    except:
                        wks_t = sh_t.add_worksheet(title="tatiller", rows=100, cols=1)
                        wks_t.append_row(["tarih"])
                    wks_t.append_row([t_str])
                    st.success("Eklendi!")
                    time.sleep(1)
                    st.cache_resource.clear()
                    st.rerun()
                else:
                    st.warning("Bu tarih zaten listede var.")

    with st.expander("🛠️ Veri İşlemleri"):
        st.write("Google Sheet'te elle değişiklik yaparsanız buraya basıp güncelleyin.")
        if st.button("🔄 Verileri Yenile", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()

    st.divider()
    if st.button("🔴 Çıkış Yap", use_container_width=True):
        st.session_state.giris_yapildi = False
        st.query_params.clear()
        st.rerun()

# --- BAŞLIK ---
col_logo, col_title = st.columns([1, 15])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=100)
    else:
        st.markdown("# 🎾")
with col_title:
    st.markdown("## 🎾 AHAL TEKE Tenis Kulübü Yönetim Sistemi")

try:
    sistem_kontrol_sessiz_gs()
except Exception as e:
    print(f"Kontrol Hatası: {e}")

try:
    df = veri_getir_df()
except:
    st.error("Google Sheets bağlantı hatası! 'yoneticiler' sayfası oluşturuldu mu?")
    st.stop()

bugun = pd.to_datetime(datetime.now().date())

def kategori_belirle(row):
    kat = str(row.get('kategori', '')).strip()
    if kat in ['Çocuk', 'Yetişkin']:
        return kat
    
    if str(row.get('veli_adi', '')).strip() not in ['', 'nan', 'None']:
        return 'Çocuk'
    return 'Yetişkin'

# --- GLOBAL VERİ İŞLEME ---
if not df.empty:
    df['bitis_tarihi'] = pd.to_datetime(df['bitis_tarihi'], errors='coerce')
    df['baslangic_tarihi'] = pd.to_datetime(df['baslangic_tarihi'], errors='coerce')
    df['yas'] = df['dogum_tarihi'].apply(yas_hesapla)
    
    df['kategori_hesaplanan'] = df.apply(kategori_belirle, axis=1)
    df['yas_grubu'] = df['kategori_hesaplanan'].apply(lambda x: 'Çocuk (Junior)' if x == 'Çocuk' else 'Yetişkin')
    
    df['aktif_mi'] = (df['bitis_tarihi'] >= bugun) & (df['kalan_hak'] > 0)

    tum_bitenler = df[~df['aktif_mi']]
    bir_hafta_once = bugun - timedelta(days=7)

    bitenler_gosterim = tum_bitenler[
        (tum_bitenler['bitis_tarihi'] >= bir_hafta_once) |
        (tum_bitenler['kalan_hak'] <= 0)
        ]
    yaklasanlar = df[
        (df['aktif_mi']) &
        (((df['bitis_tarihi'] - bugun).dt.days <= 7) | (df['kalan_hak'] <= 2))
        ]
else:
    df = pd.DataFrame(
        columns=['aktif_mi', 'yas', 'yas_grubu', 'cinsiyet', 'ders_tipi', 'ucret', 'veli_adi', 'ad_soyad'])
    yaklasanlar = pd.DataFrame()
    bitenler_gosterim = pd.DataFrame()

tabs = st.tabs(["⚠️ Yaklaşanlar & Bitenler", "➕ Yeni Üye Ekle", "📋 Üye Listesi", "📑 Raporlar", "📊 Grafikler"])

# --- TAB 1: UYARILAR ---
with tabs[0]:
    col_yak, col_bit = st.columns(2)
    with col_yak:
        st.subheader(f"🟡 Yaklaşanlar ({len(yaklasanlar)})")
        if not yaklasanlar.empty:
            for i, row in yaklasanlar.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 2])
                    c1.markdown(f"**{row['ad_soyad']}**")
                    c1.write(f"🎾 **{row['ders_tipi']}**")
                    tarih_str = row['baslangic_tarihi'].strftime('%d.%m.%Y') if pd.notnull(
                        row['baslangic_tarihi']) else "-"
                    bitis_str = row['bitis_tarihi'].strftime('%d.%m.%Y') if pd.notnull(row['bitis_tarihi']) else "-"
                    c1.caption(f"📅 {tarih_str} - {bitis_str}")

                    msg = []
                    if pd.notnull(row['bitis_tarihi']) and (row['bitis_tarihi'] - bugun).days <= 7: msg.append(
                        "Süre Az")
                    if row['kalan_hak'] <= 2: msg.append("Hak Az")
                    c1.warning(" & ".join(msg))
                    c1.write(f"Kalan: **{row['kalan_hak']}**")

                    y_adet = c2.number_input("Adet", value=int(row['toplam_hak']), key=f"yak_n_{row['id']}")
                    y_tarih = c2.date_input("Yeni Bitiş", value=bugun + timedelta(days=30), format="DD/MM/YYYY",
                                            key=f"yak_d_{row['id']}")
                    if c2.button("➕ Uzat", key=f"yak_b_{row['id']}"):
                        uyelik_yenile_gs(row['id'], y_adet, y_tarih)
                        st.success("Yenilendi!");
                        st.cache_resource.clear();
                        st.rerun()
        else:
            st.success("Riskli üye yok.")

    with col_bit:
        st.subheader(f"🔴 Son 1 Haftada Bitenler ({len(bitenler_gosterim)})")
        if not bitenler_gosterim.empty:
            for i, row in bitenler_gosterim.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 2])
                    c1.markdown(f"**{row['ad_soyad']}**")
                    c1.write(f"🎾 **{row['ders_tipi']}**")
                    tarih_str = row['baslangic_tarihi'].strftime('%d.%m.%Y') if pd.notnull(
                        row['baslangic_tarihi']) else "-"
                    bitis_str = row['bitis_tarihi'].strftime('%d.%m.%Y') if pd.notnull(row['bitis_tarihi']) else "-"
                    c1.caption(f"📅 {tarih_str} - {bitis_str}")
                    c1.error("HAK BİTTİ" if row['kalan_hak'] <= 0 else "SÜRE BİTTİ")

                    y_adet = c2.number_input("Adet", value=int(row['toplam_hak']), key=f"bit_n_{row['id']}")
                    y_tarih = c2.date_input("Yeni Bitiş", value=bugun + timedelta(days=30), format="DD/MM/YYYY",
                                            key=f"bit_d_{row['id']}")
                    if c2.button("♻️ Yenile / Uzat", key=f"bit_b_{row['id']}"):
                        uyelik_yenile_gs(row['id'], y_adet, y_tarih)
                        st.success("Yenilendi!");
                        st.cache_resource.clear();
                        st.rerun()
        else:
            st.success("Temiz")

# --- TAB 2: YENİ ÜYE ---
with tabs[1]:
    st.header("📝 Yeni Üye Kaydı")

    if st.session_state.get('form_hata'):
        st.error(st.session_state.form_hata)
        st.session_state.form_hata = None
    if st.session_state.get('form_basari'):
        st.balloons()
        st.success("Kayıt Başarıyla Oluşturuldu!")
        st.session_state.form_basari = False

    with st.form("yeni_uye_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        yeni_ad = c1.text_input("Ad Soyad")
        yeni_tel = c2.text_input("Telefon (11 Hane)", placeholder="05321234567", max_chars=11)

        st.divider()
        c3, c4, c_kat = st.columns(3)
        yeni_dt = c3.date_input("Doğum Tarihi",
                                value=datetime(2000, 1, 1),
                                min_value=datetime(1900, 1, 1),
                                max_value=datetime.now(),
                                format="DD/MM/YYYY")
        yeni_cins = c4.selectbox("Cinsiyet", ["Erkek", "Kadın"])
        yeni_kategori = c_kat.selectbox("Kategori (Yaş Grubu)", ["Yetişkin", "Çocuk"])

        st.info("ℹ️ Lütfen çocuk üyeler için Veli Adını girmeyi unutmayınız. Yetişkinler boş bırakabilir.")
        yeni_veli = st.text_input("👨‍👩‍👦 Veli Adı Soyadı")

        st.divider()
        c5, c6, c7 = st.columns(3)
        yeni_tip = c5.selectbox("Paket Tipi", ["Grup Dersi", "Özel Ders"])
        yeni_hak = c6.number_input("Ders Sayısı", min_value=1, value=8)
        yeni_ucret = c7.number_input("Ücret (TL)", value=3000)

        st.divider()
        c8, c_bitis, c9 = st.columns(3)
        yeni_bas = c8.date_input("Başlangıç Tarihi", datetime.now(), format="DD/MM/YYYY")
        yeni_bitis = c_bitis.date_input("Bitiş Tarihi", datetime.now() + timedelta(days=30), format="DD/MM/YYYY")
        yeni_odeme = c9.selectbox("Ödeme", ["Nakit", "IBAN", "Kredi Kartı"])

        yeni_gunler = st.multiselect("Günler",
                                      ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
                                      placeholder="Gün seçiniz!")

        submitted = st.form_submit_button("✅ Üyeyi Kaydet", type="primary")

        if submitted:
            hata_var = False

            if not yeni_ad:
                st.session_state.form_hata = "İsim giriniz."
                hata_var = True
            elif not yeni_gunler:
                st.session_state.form_hata = "Gün seçiniz."
                hata_var = True

            if not hata_var:
                yeni_uye_ekle_gs(yeni_ad, yeni_tel, yeni_cins, yeni_dt, yeni_bas, yeni_bitis, yeni_ucret,
                                 yeni_odeme, yeni_gunler, yeni_tip, yeni_hak, yeni_veli, yeni_kategori)
                st.session_state.form_basari = True
                st.cache_resource.clear()
                st.rerun()

# --- TAB 3: LİSTE ---
with tabs[2]:
    if not df.empty:
        fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
        arama = fc1.text_input("🔍 Kişi Ara", placeholder="Ali...")
        f_tip = fc2.multiselect("Ders Tipi", df['ders_tipi'].unique(), placeholder="Seçiniz")
        f_durum = fc3.radio("Durum", ["Aktif", "Pasif", "Hepsi"], horizontal=True, index=0)
        f_kategori = fc4.radio("Kategori", ["Hepsi", "Yetişkin", "Çocuk"], horizontal=True, index=0)

        view_df = df.copy()
        if 'bitis_tarihi' in view_df.columns:
            view_df = view_df.sort_values(by='bitis_tarihi', ascending=True)

        if arama: view_df = view_df[view_df['ad_soyad'].str.contains(arama, case=False)]
        if f_tip: view_df = view_df[view_df['ders_tipi'].isin(f_tip)]
        if f_durum == "Aktif": view_df = view_df[view_df['aktif_mi']]
        if f_durum == "Pasif": view_df = view_df[~view_df['aktif_mi']]
        if f_kategori == "Yetişkin": view_df = view_df[view_df['yas_grubu'] == 'Yetişkin']
        if f_kategori == "Çocuk": view_df = view_df[view_df['yas_grubu'] == 'Çocuk (Junior)']

        st.write(f"**Toplam: {len(view_df)} Kişi**")

        for i, row in view_df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
                
                ikon = "🧒" if row['yas_grubu'] == 'Çocuk (Junior)' else ("👨" if row['cinsiyet'] == "Erkek" else "👩")
                c1.markdown(f"### {ikon} {row['ad_soyad']}")
                if row['yas_grubu'] == 'Çocuk (Junior)' and str(row.get('veli_adi', '')).strip():
                    c1.caption(f"Veli: {row['veli_adi']}")

                tarih_str = row['baslangic_tarihi'].strftime('%d.%m.%Y') if pd.notnull(row['baslangic_tarihi']) else "-"
                bitis_str = row['bitis_tarihi'].strftime('%d.%m.%Y') if pd.notnull(row['bitis_tarihi']) else "-"

                c2.caption(f"{row['ders_tipi']} | {row['gunler']}")
                c2.write(f"📅 {tarih_str} ➡ **{bitis_str}**")

                if row['kalan_hak'] == 0:
                    c3.error("Hak: 0")
                else:
                    c3.metric("Hak", row['kalan_hak'])

                b_art, b_azal = c4.columns(2)
                if b_art.button("➕", key=f"p_{row['id']}"):
                    manuel_islem_gs(row['id'], 1);
                    st.toast("+1");
                    st.cache_resource.clear();
                    st.rerun()
                if b_azal.button("➖", key=f"m_{row['id']}"):
                    if row['kalan_hak'] > 0:
                        manuel_islem_gs(row['id'], -1);
                        st.toast("-1");
                        st.cache_resource.clear();
                        st.rerun()
                    else:
                        st.error("0!")

                with st.expander("✏️ Düzenle / 🗑️ Sil"):
                    tab_duzen, tab_sil = st.tabs(["Düzenle", "Sil"])
                    with tab_duzen:
                        with st.form(key=f"edit_form_{row['id']}"):
                            d_ad = st.text_input("Ad Soyad", value=row['ad_soyad'])
                            
                            c_edit1, c_edit2 = st.columns(2)
                            d_tel = c_edit1.text_input("Telefon", value=row['telefon'])
                            
                            try:
                                mevcut_dt = datetime.strptime(str(row['dogum_tarihi']), "%Y-%m-%d").date()
                            except:
                                try:
                                    mevcut_dt = datetime.strptime(str(row['dogum_tarihi']), "%d.%m.%Y").date()
                                except:
                                    mevcut_dt = datetime(2000, 1, 1).date()
                                    
                            d_dt = c_edit2.date_input("Doğum Tarihi", value=mevcut_dt, format="DD/MM/YYYY")

                            c_kat_edit, c_veli_edit = st.columns(2)
                            mevcut_kat = "Çocuk" if row['yas_grubu'] == 'Çocuk (Junior)' else "Yetişkin"
                            d_kategori = c_kat_edit.selectbox("Kategori", ["Yetişkin", "Çocuk"], index=1 if mevcut_kat == "Çocuk" else 0)
                            d_veli = c_veli_edit.text_input("Veli Adı Soyadı", value=str(row.get('veli_adi', '')).replace('nan',''))

                            d_tip = st.selectbox("Paket", ["Grup Dersi", "Özel Ders"],
                                                 index=0 if row['ders_tipi'] == "Grup Dersi" else 1)
                            c_d1, c_d2 = st.columns(2)
                            d_top = c_d1.number_input("Toplam Hak", value=int(row['toplam_hak']))
                            d_kal = c_d2.number_input("Kalan Hak", value=int(row['kalan_hak']))
                            
                            if st.form_submit_button("💾 Değişiklikleri Kaydet"):
                                uye_guncelle_gs(row['id'], d_ad, d_tel, str(d_dt), d_tip, d_top, d_kal, d_veli, d_kategori)
                                st.success("Güncellendi!");
                                time.sleep(1);
                                st.cache_resource.clear();
                                st.rerun()
                    with tab_sil:
                        st.warning("Bu işlem geri alınamaz!")
                        if st.button("🗑️ Üyeyi Kalıcı Olarak Sil", key=f"del_{row['id']}"):
                            uye_sil_gs(row['id'])
                            st.success("Üye Silindi.");
                            time.sleep(1);
                            st.cache_resource.clear();
                            st.rerun()

                with st.expander("♻️ Paket / Süre Uzatma"):
                    rc1, rc2 = st.columns(2)
                    y_adet = rc1.number_input("Ders Sayısı", value=int(row['toplam_hak']), key=f"list_n_{row['id']}")
                    y_tarih = rc1.date_input("Yeni Bitiş", value=bugun + timedelta(days=30), format="DD/MM/YYYY", key=f"list_d_{row['id']}")
                    if rc2.button("Yenile / Uzat", key=f"list_b_{row['id']}"):
                        uyelik_yenile_gs(row['id'], y_adet, y_tarih)
                        st.success("İşlem Tamam!");
                        st.cache_resource.clear();
                        st.rerun()
    else:
        st.info("Kayıt yok veya veritabanı boş.")

# --- TAB 4: RAPORLAR ---
with tabs[3]:
    st.header("📑 Detaylı Rapor Listeleri")
    if not df.empty:
        rc1, rc2 = st.columns(2)
        rapor_turu = rc1.selectbox("Rapor Türü Seçiniz:",
                                   ["Tüm Üyeler (Detaylı)", "Çocuklar ve Velileri", "Grup Dersi Alanlar",
                                    "Özel Ders Alanlar", "Kadın Üyeler", "Erkek Üyeler", "Nakit Ödeyenler",
                                    "Kredi Kartı ile Ödeyenler", "IBAN ile Ödeyenler"])
        durum_filtresi = rc2.radio("Durum Filtresi:", ["Hepsi", "Sadece Aktifler", "Sadece Pasifler"], horizontal=True)

        temp_df = df.copy()
        if durum_filtresi == "Sadece Aktifler":
            temp_df = temp_df[temp_df['aktif_mi']]
        elif durum_filtresi == "Sadece Pasifler":
            temp_df = temp_df[~temp_df['aktif_mi']]

        gosterilecek_tablo = pd.DataFrame()
        if rapor_turu == "Tüm Üyeler (Detaylı)":
            gosterilecek_tablo = temp_df[['ad_soyad', 'telefon', 'cinsiyet', 'yas', 'ders_tipi', 'kalan_hak', 'durum']]
        elif rapor_turu == "Çocuklar ve Velileri":
            gosterilecek_tablo = temp_df[temp_df['yas_grubu'] == 'Çocuk (Junior)'][['ad_soyad', 'veli_adi', 'telefon', 'kalan_hak']]
        elif rapor_turu == "Grup Dersi Alanlar":
            gosterilecek_tablo = temp_df[temp_df['ders_tipi'] == "Grup Dersi"][
                ['ad_soyad', 'telefon', 'gunler', 'kalan_hak']]
        elif rapor_turu == "Özel Ders Alanlar":
            gosterilecek_tablo = temp_df[temp_df['ders_tipi'] == "Özel Ders"][
                ['ad_soyad', 'telefon', 'gunler', 'kalan_hak', 'toplam_hak']]
        elif rapor_turu == "Kadın Üyeler":
            gosterilecek_tablo = temp_df[temp_df['cinsiyet'] == "Kadın"][['ad_soyad', 'telefon', 'yas', 'ders_tipi']]
        elif rapor_turu == "Erkek Üyeler":
            gosterilecek_tablo = temp_df[temp_df['cinsiyet'] == "Erkek"][['ad_soyad', 'telefon', 'yas', 'ders_tipi']]
        elif rapor_turu == "Nakit Ödeyenler":
            gosterilecek_tablo = temp_df[temp_df['odeme_yontemi'] == "Nakit"][['ad_soyad', 'ucret', 'baslangic_tarihi']]
        elif rapor_turu == "Kredi Kartı ile Ödeyenler":
            gosterilecek_tablo = temp_df[temp_df['odeme_yontemi'] == "Kredi Kartı"][
                ['ad_soyad', 'ucret', 'baslangic_tarihi']]
        elif rapor_turu == "IBAN ile Ödeyenler":
            gosterilecek_tablo = temp_df[temp_df['odeme_yontemi'] == "IBAN"][['ad_soyad', 'ucret', 'baslangic_tarihi']]

        if not gosterilecek_tablo.empty:
            gosterilecek_tablo.rename(
                columns={'ad_soyad': 'Ad Soyad', 'telefon': 'Telefon', 'cinsiyet': 'Cinsiyet', 'yas': 'Yaş',
                         'ders_tipi': 'Ders Tipi', 'kalan_hak': 'Kalan Hak', 'durum': 'Durum', 'veli_adi': 'Veli Adı',
                         'gunler': 'Günler', 'toplam_hak': 'Paket Büyüklüğü', 'ucret': 'Ücret',
                         'baslangic_tarihi': 'Kayıt Tarihi'}, inplace=True)
            st.dataframe(gosterilecek_tablo, use_container_width=True)
            csv_rapor = gosterilecek_tablo.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Bu Raporu İndir", csv_rapor, "ozel_rapor.csv", "text/csv")
        else:
            st.warning("Kayıt bulunamadı.")

# --- TAB 5: GRAFİKLER ---
with tabs[4]:
    st.header("📊 Grafiksel Analiz")
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Cinsiyet")
            cinsiyet_count = df['cinsiyet'].value_counts().reset_index()
            cinsiyet_count.columns = ['Cinsiyet', 'Adet']
            fig1 = px.pie(cinsiyet_count, values='Adet', names='Cinsiyet', color='Cinsiyet',
                          color_discrete_map={'Kadın': 'pink', 'Erkek': 'blue'})
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            st.subheader("Yetişkin / Çocuk")
            yas_count = df['yas_grubu'].value_counts().reset_index()
            yas_count.columns = ['Grup', 'Adet']
            fig2 = px.pie(yas_count, values='Adet', names='Grup', color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        st.subheader("Ders Tiplerine Göre")
        ders_count = df['ders_tipi'].value_counts().reset_index()
        ders_count.columns = ['Ders Tipi', 'Adet']
        fig3 = px.pie(ders_count, values='Adet', names='Ders Tipi', hole=0.4)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Grafik için veri yok.")