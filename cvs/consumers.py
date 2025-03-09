import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CV, CVTranslation
import asyncio
from .views import get_cv_group_name
from django.utils import timezone

class CVConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            print("="*50)
            print("WebSocket Connection Attempt")
            print(f"Scope type: {self.scope['type']}")
            print(f"Scope path: {self.scope.get('path', 'unknown')}")
            
            # URL'den CV bilgilerini al
            self.cv_id = self.scope['url_route']['kwargs']['cv_id']
            self.translation_key = self.scope['url_route']['kwargs']['translation_key']
            self.lang = self.scope['url_route']['kwargs']['lang']
            
            # template_id parametresi varsa al, yoksa varsayılan değer kullan
            self.template_id = self.scope['url_route']['kwargs'].get('template_id', '1')
            
            print(f"Connection parameters: template_id={self.template_id}, cv_id={self.cv_id}, translation_key={self.translation_key}, lang={self.lang}")
            
            # Grup adını oluştur
            self.group_name = get_cv_group_name(self.cv_id, self.translation_key, self.lang, self.template_id)
            print(f"Group name: {self.group_name}")
            
            # Channel layer bilgilerini kontrol et
            print(f"Channel layer type: {type(self.channel_layer).__name__}")
            
            # Gruba katıl
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
            print("WebSocket connection accepted")
            print(f"Channel name: {self.channel_name}")
            print("="*50)

            # Ping/pong mekanizmasını başlat
            self.ping_task = asyncio.create_task(self.send_ping())
            
            # Bağlantı başarılı olduğunda CV verilerini gönder
            cv_data = await self.get_cv_data()
            if cv_data:
                await self.send(text_data=json.dumps(cv_data))
                print("Initial CV data sent to client")
            else:
                print("No CV data available to send")
                await self.close()

        except Exception as e:
            print(f"Error in WebSocket connect: {str(e)}")
            await self.close()
            raise

    async def disconnect(self, close_code):
        print("="*50)
        print("WebSocket Disconnection")
        print(f"Close code: {close_code}")
        print(f"Group name: {self.group_name}")
        
        # Ping task'ı iptal et
        if hasattr(self, 'ping_task'):
            self.ping_task.cancel()
            
        # Gruptan ayrıl
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        print("Disconnected from group")
        print("="*50)

    async def receive(self, text_data):
        # Ping mesajını kontrol et ve sessizce işle
        if text_data == "ping":
            await self.send(text_data="pong")
            return
            
        # Normal mesajlar için log yazdır
        print("="*50)
        print("Received WebSocket message")
        print(f"Raw data: {text_data}")
        print(f"Channel name: {self.channel_name}")
        print(f"Group name: {self.group_name}")
            
        try:
            # Mesajı al ve gruba ilet
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message')
            
            if not message:
                print("Error: 'message' field not found in the received data")
                return
            
            print(f"Parsed message: {message}")
            
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'cv_update',
                    'message': message
                }
            )
            print("Message sent to group")
            print("="*50)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {str(e)}")
        except Exception as e:
            print(f"Error processing message: {str(e)}")
            import traceback
            traceback.print_exc()

    async def cv_update(self, event):
        try:
            print("="*50)
            print("Sending CV update to client")
            print(f"Event data: {event}")
            print(f"Channel name: {self.channel_name}")
            print(f"Group name: {self.group_name}")
            
            # Güncel CV verilerini gönder
            message = event['message']
            
            # Mesajın içeriğini detaylı bir şekilde yazdır
            print("Message content:")
            print(f"  ID: {message.get('id')}")
            print(f"  Template ID: {message.get('template_id')}")
            print(f"  Title: {message.get('title')}")
            print(f"  Language: {message.get('language')}")
            print(f"  Translation Key: {message.get('translation_key')}")
            print(f"  Updated At: {message.get('updated_at')}")
            
            # Mesajı JSON formatında gönder
            try:
                json_message = json.dumps(message)
                print(f"JSON message length: {len(json_message)} bytes")
            except TypeError as e:
                print(f"JSON serialization error in cv_update: {str(e)}")
                # Datetime nesnelerini string'e çevir
                if 'created_at' in message and message['created_at'] is not None and not isinstance(message['created_at'], str):
                    message['created_at'] = message['created_at'].isoformat() if hasattr(message['created_at'], 'isoformat') else str(message['created_at'])
                if 'updated_at' in message and message['updated_at'] is not None and not isinstance(message['updated_at'], str):
                    message['updated_at'] = message['updated_at'].isoformat() if hasattr(message['updated_at'], 'isoformat') else str(message['updated_at'])
                if 'timestamp' in message and not isinstance(message['timestamp'], str):
                    message['timestamp'] = str(message['timestamp'])
                
                # Tekrar dene
                json_message = json.dumps(message)
                print(f"JSON message length after fixing: {len(json_message)} bytes")
            
            # WebSocket bağlantı durumunu kontrol et
            if self.scope['type'] == 'websocket':
                print(f"WebSocket connection state: {self.scope.get('state', 'unknown')}")
            
            await self.send(text_data=json_message)
            print("CV update sent to client successfully")
            print("="*50)
        except Exception as e:
            print(f"Error sending CV update to client: {str(e)}")
            import traceback
            traceback.print_exc()

    @database_sync_to_async
    def get_cv_data(self):
        print("="*50)
        print("Getting CV data")
        print(f"Parameters: template_id={self.template_id}, cv_id={self.cv_id}, translation_key={self.translation_key}, lang={self.lang}")
        
        try:
            cv = CV.objects.get(id=self.cv_id, translation_key=self.translation_key)
            translation = cv.translations.filter(language_code=self.lang).first()
            
            if not translation:
                print(f"No translation found for language {self.lang}, trying English")
                translation = cv.translations.filter(language_code='en').first()
                if not translation:
                    print("No translation found at all")
                    return None
            
            data = {
                'id': cv.id,
                'template_id': self.template_id,
                'title': cv.title,
                'language': translation.language_code,
                'personal_info': translation.personal_info,
                'education': translation.education,
                'experience': translation.experience,
                'skills': translation.skills,
                'languages': translation.languages,
                'certificates': translation.certificates,
                'video_info': translation.video_info,
                'created_at': cv.created_at.isoformat() if cv.created_at else None,
                'updated_at': cv.updated_at.isoformat() if cv.updated_at else None,
                'translation_key': cv.translation_key,
                'action': 'initial',  # Başlangıç verisi olduğunu belirt
                'timestamp': str(timezone.now().timestamp())  # Zaman damgası ekle
            }

            # Kullanıcının profil resmini ekle
            if cv.user.profile_picture:
                # request nesnesini scope'dan al
                request = self.scope.get('request')
                if request:
                    data['personal_info']['photo'] = request.build_absolute_uri(cv.user.profile_picture.url)
                else:
                    data['personal_info']['photo'] = cv.user.profile_picture.url
            
            # Döndürülen verinin içeriğini detaylı bir şekilde yazdır
            print("Returned data content:")
            print(f"  ID: {data['id']}")
            print(f"  Template ID: {data['template_id']}")
            print(f"  Title: {data['title']}")
            print(f"  Language: {data['language']}")
            print(f"  Translation Key: {data['translation_key']}")
            print(f"  Updated At: {data['updated_at']}")
            print(f"  Action: {data['action']}")
            print(f"  Timestamp: {data['timestamp']}")
            
            # JSON serileştirme kontrolü
            try:
                json_data = json.dumps(data)
                print(f"JSON message length: {len(json_data)} bytes")
            except TypeError as e:
                print(f"JSON serialization error in get_cv_data: {str(e)}")
                # Basitleştirilmiş veri döndür
                data = {
                    'id': cv.id,
                    'template_id': self.template_id,
                    'title': cv.title,
                    'language': translation.language_code,
                    'action': 'initial',
                    'timestamp': str(timezone.now())
                }
            
            print("CV data retrieved successfully")
            print("="*50)
            return data
        except Exception as e:
            print(f"Error in get_cv_data: {str(e)}")
            print("="*50)
            return None

    async def send_ping(self):
        """Her 30 saniyede bir ping gönder"""
        try:
            while True:
                await asyncio.sleep(30)
                await self.send(text_data="ping")
                print(f"Ping sent to client: {self.channel_name}")
        except asyncio.CancelledError:
            # Task iptal edildiğinde sessizce çık
            pass
        except Exception as e:
            print(f"Error in send_ping: {str(e)}")
            import traceback
            traceback.print_exc() 