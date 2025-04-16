from openai import OpenAI
from django.conf import settings
from .models import CVTranslation
import json

class TranslationService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # Desteklenen diller
    SUPPORTED_LANGUAGES = {
        'tr': 'Turkish',
        'en': 'English',
        'es': 'Spanish',
        'zh': 'Chinese',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'de': 'German'
    }

    def translate_cv_content(self, cv_data, target_language, fix_grammar=False):
        """
        CV içeriğini hedef dile çevirir ve isteğe bağlı olarak imla/dilbilgisi hatalarını düzeltir.
        
        Args:
            cv_data (dict): Çevrilecek CV verisi
            target_language (str): Hedef dil (örn: "Turkish", "English", "German")
            fix_grammar (bool): İmla ve dilbilgisi hatalarını düzelt
            
        Returns:
            dict: Çevrilmiş CV verisi
        """
        try:
            # CV verisini string'e çevir
            content_str = json.dumps(cv_data, ensure_ascii=False)
            
            # OpenAI API'ye gönderilecek sistem mesajı
            system_message = (
                "You are a professional CV translator and language expert with extensive experience in professional writing. "
                "Your task is to process the CV content according to these rules:\n\n"
                "1. For English content (whether translating to English or fixing grammar):\n"
                "   - Fix ALL spelling, grammar, and punctuation errors\n"
                "   - Improve sentence structure and word choice for better professional impact\n"
                "   - Ensure consistent professional terminology\n"
                "   - Use proper capitalization for job titles, company names, and skills\n"
                "   - Make the language more impactful and professional\n\n"
                "2. For translations to other languages:\n"
                "   - Provide accurate and natural-sounding translations\n"
                "   - Maintain professional CV terminology specific to the target language\n"
                "   - Preserve proper nouns, company names, and technical terms as appropriate\n"
                "   - Ensure dates and numbers are formatted according to local conventions\n\n"
                "3. Technical requirements:\n"
                "   - Return ONLY a valid JSON object with exactly the same structure\n"
                "   - Do not add or remove any fields\n"
                "   - Do not include any explanatory text outside the JSON\n"
                "   - Ensure all JSON strings are properly escaped\n"
                "   - Maintain the exact same data types for all fields"
            )
            
            # Kullanıcı mesajını hazırla
            if target_language == "English" and fix_grammar:
                user_message = (
                    "Review and enhance the following CV content. Fix ALL spelling and grammar errors, "
                    "improve word choice, and make the language more professional and impactful. "
                    "Return ONLY the corrected JSON object with the exact same structure: \n"
                    f"{content_str}"
                )
            else:
                user_message = (
                    f"Translate the following CV content to {target_language}, ensuring professional "
                    "language and proper terminology for the target language. "
                    "Return ONLY the translated JSON object with the exact same structure: \n"
                    f"{content_str}"
                )
            
            # API çağrısı - GPT-4 kullan
            response = self.client.chat.completions.create(
                model="gpt-4",  # GPT-4 modelini kullan
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3  # Daha tutarlı sonuçlar için
            )
            
            # API yanıtını al
            response_text = response.choices[0].message.content.strip()
            
            # Yanıtın başında veya sonunda fazladan metin varsa temizle
            response_text = response_text.strip('`') # Markdown backtick'leri temizle
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            try:
                # Çevrilmiş içeriği JSON'a çevir
                translated_content = json.loads(response_text)
                
                # Orijinal veri yapısını kontrol et
                expected_keys = set(cv_data.keys())
                actual_keys = set(translated_content.keys())
                
                if expected_keys != actual_keys:
                    print(f"Warning: JSON structure mismatch. Expected: {expected_keys}, Got: {actual_keys}")
                    # Eksik alanları orijinal veriden doldur
                    for key in expected_keys - actual_keys:
                        translated_content[key] = cv_data[key]
                
                return translated_content
                
            except json.JSONDecodeError as json_err:
                print(f"JSON parse error: {str(json_err)}")
                print(f"Response text: {response_text}")
                # JSON parse hatası durumunda orijinal veriyi döndür
                return cv_data
            
        except Exception as e:
            print(f"Translation error: {str(e)}")
            # Herhangi bir hata durumunda orijinal veriyi döndür
            return cv_data

    def translate_text(self, text: str, target_language: str, fix_grammar: bool = False) -> str:
        """
        OpenAI API kullanarak metni hedef dile çevirir ve isteğe bağlı olarak imla/dilbilgisi hatalarını düzeltir
        """
        try:
            system_message = (
                "You are a professional translator and language expert with extensive experience in professional writing. "
                "Process the text according to these rules:\n\n"
                "1. For English content (whether translating to English or fixing grammar):\n"
                "   - Fix ALL spelling, grammar, and punctuation errors\n"
                "   - Improve sentence structure and word choice\n"
                "   - Make the language more professional and impactful\n"
                "   - Ensure proper capitalization and formatting\n\n"
                "2. For translations to other languages:\n"
                "   - Provide accurate and natural-sounding translations\n"
                "   - Maintain the original tone while ensuring professional language\n"
                "   - Preserve proper nouns and technical terms as appropriate"
            )
            
            if target_language == "English" and fix_grammar:
                user_message = (
                    "Review and enhance the following text. Fix ALL spelling and grammar errors, "
                    f"improve word choice, and make it more professional: {text}"
                )
            else:
                user_message = (
                    f"Translate the following text to {target_language}, ensuring professional "
                    f"language while maintaining the original tone: {text}"
                )
            
            # GPT-4 modelini kullan
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3  # Daha tutarlı sonuçlar için
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return text  # Hata durumunda orijinal metni döndür 

    def validate_and_improve_content(self, cv_data, language_code):
        """
        CV içeriğini kontrol eder ve düzeltir:
        - Test/placeholder içeriği tespit eder
        - Anlamsız veya kısa içeriği düzeltir
        - Profesyonel olmayan dili düzeltir
        - Teknik terimleri ve deneyimleri doğrular
        - Noktalama işaretlerini düzeltir
        - İmla hatalarını düzeltir
        """
        try:
            # Önce içeriği kontrol et - test içeriği var mı?
            needs_improvement = False
            test_patterns = ['test', 'asd', 'asdf', '123', 'xyz', 'deneme']
            
            # Noktalama işareti hataları için kontrol
            punctuation_errors = [
                ',,', '..', '  ', ' ,', ' .', ' ;', ' :',  # Fazla boşluk ve tekrar
                '. ve', '. ama', '. fakat',  # Cümle başında bağlaç
                '( ', ' )', '[ ', ' ]',  # Parantez boşluk hataları
                ';ve', ',ve', 've,', 've.',  # Bağlaç hataları
            ]
            
            for field, content in cv_data.items():
                if isinstance(content, dict):
                    for _, value in content.items():
                        if isinstance(value, str):
                            # Test içeriği kontrolü
                            if any(pattern in value.lower() for pattern in test_patterns):
                                needs_improvement = True
                            # Noktalama işareti kontrolü
                            if any(error in value for error in punctuation_errors):
                                needs_improvement = True
                            # Ardışık noktalama kontrolü
                            if '..' in value or ',,' in value:
                                needs_improvement = True
                            # Cümle başı büyük harf kontrolü
                            sentences = value.split('. ')
                            if any(s and s[0].islower() for s in sentences):
                                needs_improvement = True
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            for _, value in item.items():
                                if isinstance(value, str):
                                    # Test içeriği kontrolü
                                    if any(pattern in value.lower() for pattern in test_patterns):
                                        needs_improvement = True
                                    # Noktalama işareti kontrolü
                                    if any(error in value for error in punctuation_errors):
                                        needs_improvement = True
                                    # Ardışık noktalama kontrolü
                                    if '..' in value or ',,' in value:
                                        needs_improvement = True
                                    # Cümle başı büyük harf kontrolü
                                    sentences = value.split('. ')
                                    if any(s and s[0].islower() for s in sentences):
                                        needs_improvement = True
                elif isinstance(content, str):
                    # Test içeriği kontrolü
                    if any(pattern in content.lower() for pattern in test_patterns):
                        needs_improvement = True
                    # Noktalama işareti kontrolü
                    if any(error in content for error in punctuation_errors):
                        needs_improvement = True
                    # Ardışık noktalama kontrolü
                    if '..' in content or ',,' in content:
                        needs_improvement = True
                    # Cümle başı büyük harf kontrolü
                    sentences = content.split('. ')
                    if any(s and s[0].islower() for s in sentences):
                        needs_improvement = True
            
            # Eğer iyileştirme gerekmiyorsa, orijinal veriyi döndür
            if not needs_improvement:
                return cv_data
            
            content_str = json.dumps(cv_data, ensure_ascii=False)
            
            system_message = (
                "You are an expert CV content validator and improver. Your task is to analyze and improve CV content by:\n\n"
                
                "PUNCTUATION & GRAMMAR RULES:\n"
                "1. Fix ALL punctuation errors:\n"
                "   - Correct spacing around punctuation marks\n"
                "   - Remove duplicate punctuation (e.g., multiple periods or commas)\n"
                "   - Ensure proper sentence endings\n"
                "   - Fix parentheses and bracket spacing\n"
                "2. Correct spelling and grammar:\n"
                "   - Fix all spelling mistakes\n"
                "   - Ensure proper capitalization\n"
                "   - Correct verb tenses and agreement\n"
                "   - Fix article usage (a/an/the)\n"
                "3. Improve sentence structure:\n"
                "   - Fix run-on sentences\n"
                "   - Correct comma splices\n"
                "   - Ensure proper conjunction usage\n"
                "   - Maintain professional tone\n\n"
                
                "DETECTION & VALIDATION:\n"
                "1. Identify test/placeholder content (e.g., 'test', 'asd', random letters)\n"
                "2. Find incomplete or unprofessional descriptions\n"
                "3. Validate technical terms and experiences\n"
                "4. Check for inconsistencies in dates and durations\n\n"
                
                "IMPROVEMENT RULES:\n"
                "1. Replace test content with professional equivalents\n"
                "2. Expand abbreviated or incomplete content\n"
                "3. Enhance technical descriptions while maintaining accuracy\n"
                "4. Use industry-standard terminology\n"
                "5. Keep legitimate technical terms unchanged\n"
                "6. Preserve actual company names and dates\n\n"
                
                "FIELD-SPECIFIC GUIDELINES:\n"
                "- Education: Validate institution names, degree names, and study fields\n"
                "- Experience: Ensure job titles match industry standards\n"
                "- Skills: Verify technical skills and group them logically\n"
                "- Languages: Use standard proficiency levels\n\n"
                
                "OUTPUT REQUIREMENTS:\n"
                "- Return ONLY a valid JSON object\n"
                "- The JSON must have exactly the same structure as the input\n"
                "- Do not add or remove any fields\n"
                "- Preserve all data types (strings, arrays, objects)\n"
                "- Keep technical terms in their original form\n"
                "- Do not include any text outside the JSON\n"
                "- Do not use markdown formatting\n"
            )
            
            user_message = (
                f"Analyze and improve the following CV content in {self.SUPPORTED_LANGUAGES[language_code]}. "
                "Fix ALL punctuation, spelling, and grammar errors. "
                "Replace any test/placeholder content with professional equivalents. "
                "Maintain technical accuracy and enhance descriptions. "
                "Return ONLY the improved JSON object:\n\n"
                f"{content_str}"
            )
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # JSON yanıtını temizle
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx >= 0 and end_idx >= 0:
                response_text = response_text[start_idx:end_idx + 1]
            
            try:
                improved_content = json.loads(response_text)
                
                # Yapı kontrolü
                if set(improved_content.keys()) != set(cv_data.keys()):
                    print("Warning: Structure mismatch in improved content")
                    return cv_data
                    
                return improved_content
            except json.JSONDecodeError as e:
                print(f"Error parsing improved content JSON: {str(e)}")
                print(f"Response text: {response_text}")
                return cv_data
                
        except Exception as e:
            print(f"Content improvement error: {str(e)}")
            return cv_data

    def translate_cv_content_all_languages(self, cv_data, source_language='en'):
        """
        CV içeriğini tüm desteklenen dillere tek seferde çevirir.
        Önce içeriği validate edip düzeltir, sonra çevirir.
        """
        try:
            # Önce içeriği validate et ve düzelt
            improved_content = self.validate_and_improve_content(cv_data, source_language)
            
            # İyileştirilmiş içeriği string'e çevir
            content_str = json.dumps(improved_content, ensure_ascii=False)
            
            example_structure = json.dumps({
                "tr": cv_data,
                "en": cv_data,
                "es": cv_data,
                "zh": cv_data,
                "ar": cv_data,
                "hi": cv_data,
                "de": cv_data
            }, indent=2)
            
            # OpenAI API'ye gönderilecek sistem mesajı
            system_message = (
                "STRICT OUTPUT FORMAT: You are a JSON-only CV translation API. Output must be pure JSON, starting with '{' and ending with '}'.\n\n"
                
                "CV TRANSLATION EXPERTISE:\n"
                "- Technical Terms: Keep programming languages, frameworks, tools unchanged\n"
                "- Work Experience: Use strong action verbs specific to tech roles\n"
                "- Professional Impact: Translate achievements while maintaining metrics\n"
                "- Industry Standards: Use local tech industry terminology\n"
                "- Testing/QA: Maintain technical accuracy in test methodologies\n"
                "- Development: Preserve technical stack and methodology terms\n\n"
                
                "LANGUAGE-SPECIFIC RULES:\n"
                "tr: Yazılım sektörüne özgü Türkçe terminoloji kullan\n"
                "en: Use standard technical English terminology\n"
                "es: Use region-neutral technical Spanish\n"
                "zh: Use simplified Chinese tech terminology\n"
                "ar: Use modern standard Arabic tech terms\n"
                "hi: Use standard Hindi with English tech terms\n\n"
                
                "OUTPUT STRUCTURE:\n"
                f"{example_structure}\n\n"
                
                "CRITICAL: ANY TEXT OUTSIDE {} WILL CAUSE SYSTEM FAILURE"
            )
            
            # Kullanıcı mesajını hazırla
            user_message = (
                "TRANSLATE CV\n"
                f"SOURCE={source_language}\n"
                "OUTPUT=JSON\n"
                f"CONTENT={content_str}"
            )
            
            # API çağrısı
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1
            )
            
            # API yanıtını al ve sadece JSON kısmını çıkar
            response_text = response.choices[0].message.content.strip()
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx >= 0 and end_idx >= 0:
                response_text = response_text[start_idx:end_idx + 1]
            else:
                raise json.JSONDecodeError("Invalid JSON format", response_text, 0)
            
            try:
                # Çevrilmiş içeriği JSON'a çevir
                all_translations = json.loads(response_text)
                
                # Her dil için yapıyı kontrol et ve düzelt
                expected_keys = set(cv_data.keys())
                result = {}
                
                # Kaynak dildeki içeriği doğrudan kullan
                result[source_language] = cv_data
                
                # Diğer diller için çevirileri kullan
                for lang_code in self.SUPPORTED_LANGUAGES.keys():
                    if lang_code != source_language:  # Kaynak dili atla
                        if lang_code in all_translations:
                            translation = all_translations[lang_code]
                            actual_keys = set(translation.keys())
                            
                            # Yapı uyuşmazlığı varsa düzelt
                            if expected_keys != actual_keys:
                                print(f"Warning: JSON structure mismatch for {lang_code}")
                                # Eksik alanları orijinal veriden doldur
                                for key in expected_keys - actual_keys:
                                    translation[key] = cv_data[key]
                            
                            result[lang_code] = translation
                        else:
                            print(f"Warning: Missing translation for {lang_code}")
                            # Eksik dil için orijinal veriyi kullan
                            result[lang_code] = cv_data
                
                return result
                
            except json.JSONDecodeError as json_err:
                print(f"JSON parse error: {str(json_err)}")
                print(f"Response text: {response_text}")
                # JSON parse hatası durumunda tüm diller için orijinal veriyi döndür
                return {lang_code: cv_data for lang_code in self.SUPPORTED_LANGUAGES.keys()}
            
        except Exception as e:
            print(f"Translation error: {str(e)}")
            # Herhangi bir hata durumunda tüm diller için orijinal veriyi döndür
            return {lang_code: cv_data for lang_code in self.SUPPORTED_LANGUAGES.keys()} 