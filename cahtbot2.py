import google.generativeai as genai
import pandas as pd
import io

# --- YAPILANDIRMA ---
API_KEY = "AIzaSyBBsTNaBFb0Uo9AgBLxGyOMUgFCZUCp2S4"
genai.configure(api_key=API_KEY)

def get_working_model():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                return m.name
    except:
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

       
        new_row = {
            "Marka-Model": marka_model,
            "Motor": motor,
            "Sanziman": sanziman,
            "Yakit": yakit,
    
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        print("✅ Eklendi.\n")

    return df

def chatbot_arac_kiralama():
    print("="*60)
    print("🚗 AUTOZY AI - ÇOKLU ARAÇ SEÇİM SİSTEMİ")
    print("="*60)

    selected_model = get_working_model()
    segment_input = input("\nSegment Seçin (A/B/C/D/E): ").strip().upper()

    segments = {'A': 'Mini', 'B': 'Küçük', 'C': 'Kompakt/Sedan', 'D': 'Üst Orta', 'E': 'Lüks'}
    if segment_input not in segments:
        return

    print(f"\n🔍 {segments[segment_input]} segmenti araçlar taranıyor...")

    prompt = f"""
    Sen bir veri sağlayıcısın. {segments[segment_input]} segmentindeki kiralık araçları listele.
    SADECE aşağıdaki CSV formatında yanıt ver, başına numara ekleme:
    Marka-Model,Motor,Sanziman,Yakit,Gunluk_Fiyat_TL
    Fiat Egea,1.3 Multijet,Manuel,Dizel,1200
    Renault Megane,1.5 Blue dCi,Otomatik,Dizel,1800
    """

    try:
        model = genai.GenerativeModel(selected_model)
        response = model.generate_content(prompt)
        clean_data = response.text.replace('```csv', '').replace('```', '').strip()

        # Veriyi oku
        df = pd.read_csv(io.StringIO(clean_data))

        # ID index
        df.index = range(1, len(df) + 1)
        df.index.name = 'ID'

        print("\n✨ MEVCUT ARAÇLAR:")
        print(df.to_string())

        # ✅ YENİ: Kullanıcı listede olmayan araç ekleyebilsin (çoklu)
        if _ask_yes_no("\nListede olmayan araç eklemek ister misin? (E/H): "):
            # index'i kolona çevirip rahat ekleyelim
            df2 = df.reset_index(drop=True)  # ID'yi atıyoruz, sonra yeniden oluşturacağız
            df2 = _manual_car_input_loop(df2)

            # yeniden ID index
            df = df2.copy()
            df.index = range(1, len(df) + 1)
            df.index.name = 'ID'

            print("\n📌 GÜNCEL LİSTE (Manuel eklenenler dahil):")
            print(df.to_string())

        # --- ÇOKLU SEÇİM BÖLÜMÜ ---
        print("\n" + "-"*40)
        secim_input = input("Seçmek istediğiniz araçların ID'lerini girin (Örn: 1,3,5): ")

        try:
            secilen_id_listesi = [int(i.strip()) for i in secim_input.split(',') if i.strip()]
            secilen_araclar_df = df.loc[secilen_id_listesi]

            print("\nSEÇTİĞİNİZ ARAÇLARIN ÖZETİ:")
            print(secilen_araclar_df.to_string())

            dosya_adi = "Secilen_Araclar_Teklifi.xlsx"
            secilen_araclar_df.to_excel(dosya_adi)
            print(f"\n✅ {len(secilen_araclar_df)} araç için '{dosya_adi}' dosyası oluşturuldu.")

        except KeyError:
            print("❌ Hata: Girdiğiniz ID'lerden bazıları listede yok.")
        except ValueError:
            print("❌ Hata: Lütfen sadece rakam ve virgül kullanın.")

    except Exception as e:
        print(f"❌ Bir hata oluştu: {e}")

if __name__ == "__main__":
    chatbot_arac_kiralama()
