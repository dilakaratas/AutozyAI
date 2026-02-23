import google.generativeai as genai
import pandas as pd
import io
from pathlib import Path
from datetime import datetime
import os

# --- YAPILANDIRMA ---
# ❗ Güvenli öneri: ENV’den oku (PowerShell: setx GEMINI_API_KEY "KEY" -> yeni terminal)
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Eğer ENV kullanmayacaksan şunu açıp kendi key’ini yapıştır:
API_KEY = "AIzaSyBBsTNaBFb0Uo9AgBLxGyOMUgFCZUCp2S4"

if not API_KEY:
    raise RuntimeError(
        "API Key bulunamadı. Ya GEMINI_API_KEY env set et, ya da kodda API_KEY='...' yap."
    )

genai.configure(api_key=API_KEY)


def get_working_model():
    try:
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                return m.name
    except Exception:
        return "models/gemini-1.5-flash"
    return "models/gemini-1.5-flash"


def _ask_yes_no(msg: str) -> bool:
    while True:
        ans = input(msg).strip().lower()
        if ans in ("e", "evet", "y", "yes"):
            return True
        if ans in ("h", "hayır", "hayir", "n", "no"):
            return False
        print("Lütfen E/H gir.")


def _assign_ids(df: pd.DataFrame) -> pd.DataFrame:
    """ID'yi index değil kolonda tutarak kaymayı engeller."""
    df = df.reset_index(drop=True).copy()
    if "ID" in df.columns:
        df = df.drop(columns=["ID"])
    df.insert(0, "ID", range(1, len(df) + 1))
    return df


def standardize_vehicle_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gemini bazen kolon adlarını/formatını bozabiliyor.
    Bu fonksiyon en azından ilk 5 kolonu standarda çeker:
    Marka-Model, Motor, Sanziman, Yakit, Gunluk_Fiyat_TL
    """
    df = df.copy()
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]

    expected = ["Marka-Model", "Motor", "Sanziman", "Yakit", "Gunluk_Fiyat_TL"]

    # Eğer Marka-Model zaten varsa, eksikleri tamamla
    if "Marka-Model" in df.columns:
        for col in expected:
            if col not in df.columns:
                df[col] = ""
        df = df[expected + [c for c in df.columns if c not in expected]]
        return df

    # Yoksa: ilk 5 kolonu sırayla map et
    cols = list(df.columns)
    mapping = {}
    for i in range(min(len(cols), 5)):
        mapping[cols[i]] = expected[i]
    df = df.rename(columns=mapping)

    # Eksik beklenen kolonları ekle
    for col in expected:
        if col not in df.columns:
            df[col] = ""

    df = df[expected + [c for c in df.columns if c not in expected]]
    return df


def _manual_car_input_loop(df: pd.DataFrame) -> pd.DataFrame:
    """
    Kullanıcıdan listede olmayan araç(lar)ı alır ve df'ye ekler.
    Çıkmak için Marka-Model boş + Enter.
    """
    print("\n📝 Listede olmayan araç ekleme (çıkmak için Marka-Model boş bırak -> Enter)\n")

    while True:
        marka_model = input("Marka-Model: ").strip()
        if not marka_model:
            break

        motor = input("Motor: ").strip()
        sanziman = input("Sanziman (Manuel/Otomatik): ").strip()
        yakit = input("Yakit (Benzin/Dizel/Hibrit/Elektrik): ").strip()
        gunluk = input("Gunluk_Fiyat_TL (opsiyonel): ").strip()

        new_row = {
            "Marka-Model": marka_model,
            "Motor": motor,
            "Sanziman": sanziman,
            "Yakit": yakit,
            "Gunluk_Fiyat_TL": ""
        }

        if gunluk:
            try:
                new_row["Gunluk_Fiyat_TL"] = float(gunluk)
            except Exception:
                new_row["Gunluk_Fiyat_TL"] = gunluk

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        print("✅ Eklendi.\n")

    return df


def build_ay_km_matrisi(secilen_araclar_df: pd.DataFrame) -> pd.DataFrame:
    """
    Satırlar: seçilen araçlar * (30k, 40k, 50k)
    Sütunlar: 12 Ay, 24 Ay, 36 Ay
    Hücreler boş (kullanıcı doldursun diye)
    """
    kms = ["30.000 KM", "40.000 KM", "50.000 KM"]
    rows = []

    for _, r in secilen_araclar_df.iterrows():
        mm = str(r.get("Marka-Model", "")).strip()
        motor = str(r.get("Motor", "")).strip()
        sanz = str(r.get("Sanziman", "")).strip()
        yakit = str(r.get("Yakit", "")).strip()

        base = " ".join([mm, motor, sanz, yakit]).strip()
        base = " ".join(base.split())

        for km in kms:
            rows.append({
                "Arac": f"{base} - {km}".strip(),
                "12 Ay": "",
                "24 Ay": "",
                "36 Ay": ""
            })

    return pd.DataFrame(rows)


def chatbot_arac_kiralama():
    print("=" * 60)
    print("🚗 AUTOZY AI - ÇOKLU ARAÇ SEÇİM SİSTEMİ")
    print("=" * 60)

    selected_model = get_working_model()

    segment_input = input("\nSegment Seçin (A/B/C/D/E): ").strip().upper()
    segments = {"A": "Mini", "B": "Küçük", "C": "Kompakt/Sedan", "D": "Üst Orta", "E": "Lüks"}

    if segment_input not in segments:
        print("❌ Geçersiz segment.")
        return

    print(f"\n🔍 {segments[segment_input]} segmenti araçlar taranıyor...")

    prompt = f"""
Sen bir veri sağlayıcısın. {segments[segment_input]} segmentindeki kiralık araçları listele.

KESİN KURALLAR:
- SADECE CSV döndür (başka hiçbir açıklama/başlık/markdown yok)
- Her satır 5 kolon içerecek:
  Marka-Model,Motor,Sanziman,Yakit,Gunluk_Fiyat_TL
- Boş değer varsa yine de virgül ile kolonu koru.

Örnek:
Marka-Model,Motor,Sanziman,Yakit,Gunluk_Fiyat_TL
Fiat Egea,1.3 Multijet,Manuel,Dizel,1200
Renault Megane,1.5 Blue dCi,Otomatik,Dizel,1800
"""

    try:
        model = genai.GenerativeModel(selected_model)
        response = model.generate_content(prompt)

        clean_data = (
            (response.text or "")
            .replace("```csv", "")
            .replace("```", "")
            .strip()
        )

        # CSV oku
        df = pd.read_csv(io.StringIO(clean_data))

        # Kolonları standarda çek
        df = standardize_vehicle_columns(df)

        # ID ekle
        df = _assign_ids(df)

        print("\n✨ MEVCUT ARAÇLAR:")
        print(df[["ID", "Marka-Model", "Motor", "Sanziman", "Yakit", "Gunluk_Fiyat_TL"]].to_string(index=False))

        # Manuel araç ekleme
        if _ask_yes_no("\nListede olmayan araç eklemek ister misin? (E/H): "):
            df_no_id = df.drop(columns=["ID"], errors="ignore")
            df_no_id = _manual_car_input_loop(df_no_id)

            df_no_id = standardize_vehicle_columns(df_no_id)
            df = _assign_ids(df_no_id)

            print("\n📌 GÜNCEL LİSTE (Manuel eklenenler dahil):")
            print(df[["ID", "Marka-Model", "Motor", "Sanziman", "Yakit", "Gunluk_Fiyat_TL"]].to_string(index=False))

        # Seçim
        print("\n" + "-" * 40)
        secim_input = input("Seçmek istediğiniz araçların ID'lerini girin (Örn: 1,3,5): ").strip()

        secilen_id_listesi = [int(i.strip()) for i in secim_input.split(",") if i.strip()]
        secilen_araclar_df = df[df["ID"].isin(secilen_id_listesi)].copy()

        if secilen_araclar_df.empty:
            print("❌ Seçtiğiniz ID'lere ait araç bulunamadı.")
            return

        # Seçim sırasını koru
        secilen_araclar_df["__order"] = pd.Categorical(
            secilen_araclar_df["ID"],
            categories=secilen_id_listesi,
            ordered=True
        )
        secilen_araclar_df = secilen_araclar_df.sort_values("__order").drop(columns="__order")

        print("\n✅ SEÇTİĞİNİZ ARAÇLARIN ÖZETİ:")
        print(secilen_araclar_df[["ID", "Marka-Model", "Motor", "Sanziman", "Yakit", "Gunluk_Fiyat_TL"]].to_string(index=False))

        # 12/24/36 ay - 30/40/50 km matrisi
        ay_km_matrisi_df = build_ay_km_matrisi(secilen_araclar_df)

        # ✅ Excel'i HER SEFERİNDE AYNI DOSYAYA YAZ (overwrite)
        dosya_adi = Path(r"C:\Users\DILAKARATAS\Desktop\Secilen_Araclar_Teklifi_20260206_105919.xlsx")
        dosya_adi.parent.mkdir(parents=True, exist_ok=True)

        # ✅ İKİ SHEET'İ DE YAZ (senin kodunda Sheet1 eksikti)
        with pd.ExcelWriter(dosya_adi, engine="openpyxl", mode="w") as writer:
            secilen_araclar_df.to_excel(writer, sheet_name="Secilen_Araclar", index=False)
            ay_km_matrisi_df.to_excel(writer, sheet_name="12-24-36_Ay_Matrisi", index=False)

        print(f"\n✅ Excel oluşturuldu (overwrite): {dosya_adi}")
        print("   - Sheet1: Secilen_Araclar")
        print("   - Sheet2: 12-24-36_Ay_Matrisi (30k/40k/50k KM satırları)")

    except Exception as e:
        print(f"❌ Bir hata oluştu: {e}")


if __name__ == "__main__":
    chatbot_arac_kiralama()
