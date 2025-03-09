import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CV, CVTranslation
import asyncio

class CVConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            print("="*50)
            print("WebSocket Connection Attempt")
            
            # URL'den CV bilgilerini al
            self.cv_id = self.scope['url_route']['kwargs']['cv_id']
            self.translation_key = self.scope['url_route']['kwargs']['translation_key']
            self.lang = self.scope['url_route']['kwargs']['lang']
            
            # template_id parametresi varsa al, yoksa varsayılan değer kullan
            self.template_id = self.scope['url_route']['kwargs'].get('template_id', '1')
            
            print(f"Connection parameters: template_id={self.template_id}, cv_id={self.cv_id}, translation_key={self.translation_key}, lang={self.lang}")
            
            # Grup adını oluştur
            self.group_name = f'cv_{self.template_id}_{self.cv_id}_{self.translation_key}_{self.lang}'
            print(f"Group name: {self.group_name}")
            
            # Gruba katıl
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
            print("WebSocket connection accepted")
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
        print("="*50)
        print("Received WebSocket message")
        print(f"Raw data: {text_data}")
        
        # Ping mesajını kontrol et
        if text_data == "ping":
            await self.send(text_data="pong")
            print("Ping received, pong sent")
            print("="*50)
            return
            
        # Mesajı al ve gruba ilet
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        
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

    async def cv_update(self, event):
        try:
            print("="*50)
            print("Sending CV update to client")
            print(f"Event data: {event}")
            print(f"Channel name: {self.channel_name}")
            print(f"Group name: {self.group_name}")
            
            # Güncel CV verilerini gönder
            message = event['message']
            await self.send(text_data=json.dumps(message))
            print("CV update sent to client successfully")
            print("="*50)
        except Exception as e:
            print(f"Error sending CV update to client: {str(e)}")
            import traceback
            traceback.print_exc()

    @database_sync_to_async
    def get_cv_data(self):
        # print("="*50)
        # print("Getting CV data")
        # print(f"Parameters: template_id={self.template_id}, cv_id={self.cv_id}, translation_key={self.translation_key}, lang={self.lang}")
        
        try:
            cv = CV.objects.get(id=self.cv_id, translation_key=self.translation_key)
            translation = cv.translations.filter(language_code=self.lang).first()
            
            if not translation:
                # print(f"No translation found for language {self.lang}, trying English")
                translation = cv.translations.filter(language_code='en').first()
                if not translation:
                    # print("No translation found at all")
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
                'updated_at': cv.updated_at.isoformat() if cv.updated_at else None
            }

            # Kullanıcının profil resmini ekle
            if cv.user.profile_picture:
                # request nesnesini scope'dan al
                request = self.scope.get('request')
                if request:
                    data['personal_info']['photo'] = request.build_absolute_uri(cv.user.profile_picture.url)
                else:
                    data['personal_info']['photo'] = cv.user.profile_picture.url
            
            # print("CV data retrieved successfully")
            # print("="*50)
            return data
        except Exception as e:
            # print(f"Error in get_cv_data: {str(e)}")
            # print("="*50)
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